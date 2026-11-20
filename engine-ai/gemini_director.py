import os
import re
import json
import glob
import time
from google import genai

MODEL_CANDIDATES = [
    "gemini-4-hydrogen",
    "gemini-4-neon",
    "gemini-3.5-flash-lite",
]

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi")

SYSTEM_PROMPT = """Kamu adalah Sutradara & Editor Video Short-Form Profesional (TikTok / Reels / Shorts) dengan gaya visual dinamis, padat, dan high-retention.

Tugasmu adalah menonton rekaman A-roll (talking head) dan semua klip B-roll (screen recording / footage pendukung), lalu menyusun rencana editing JSON yang presisi.

ATURAN WAJIB EDITING:
1. BUANG COUNT-IN & SALAH UCAP (RETAKE):
   - Jika di awal video ada hitungan mundur (misalnya "tiga...", "satu dua", tarikan napas panjang sebelum kalimat pembuka), JANGAN masukkan rentang indeks kata tersebut ke `keep_word_ranges`.
   - Jika pembicara salah ucap lalu mengulang frasa/kalimat yang sama (contoh: "Kemudian pilih... Kemudian pilih..."), BUANG percobaan pertama yang salah dan HANYA pertahankan pengulangan yang benar.
   - Buang jeda kosong di paling akhir setelah kalimat penutup selesai.

2. TUTUP BAGIAN TUTORIAL DENGAN B-ROLL PENUH (80% - 95% DURASI DEMO):
   - Tonton isi visual setiap klip B-roll yang diberikan.
   - Saat pembicara mulai menjelaskan langkah teknis, tutorial aplikasi, atau menunduk mengoperasikan HP, WAJIB tutup layar menggunakan klip B-roll yang paling relevan dengan langkah yang sedang diucapkan.
   - Jangan biarkan A-roll menampilkan pembicara yang menunduk terlalu lama; sambung klip B-roll secara berurutan mengikuti alur tutorial.

3. KOREKSI TRANSKRIP & HIGHLIGHT KATA KUNCI:
   - Perbaiki kata-kata salah ketik dari transkrip otomatis (misal: "walaulah" -> "bolehlah", "undur" -> "unduh", "cerian" -> "caranya") pada field `clean_word` tanpa mengubah `start` dan `end` detik aslinya.
   - Tandai `highlight: true` pada kata-kata penting/aksi/angka, dan pilih `highlight_color`: `"green"` (default untuk kata kunci utama) atau `"red"` (untuk peringatan/larangan/CTA penting).

4. ASET GRAFIS KONTEKSTUAL (`callouts`):
   - Buat overlay grafis otomatis saat momen berikut muncul:
     - `follow_badge`: Saat mengajak follow/subscribe/cek profil (durasi ~2.2 detik).
     - `store_badge`: Saat menyebut unduh/download aplikasi di Play Store / App Store (durasi ~2.5 detik).
     - `url_card`: Saat menyebut alamat website/link/URL — ekstrak teks URL-nya (misal `"ip-tv.app/indonesia"` atau `"iptv.llc"`) ke `primary_text` (durasi ~3.0 detik).
     - `step_card`: Saat masuk ke langkah penting atau tips utama (durasi ~2.5 detik).

5. KELUARAN JSON MURNI:
   - Balas HANYA dengan objek JSON valid tanpa teks pembuka/penutup dan tanpa blok markdown.
"""


def find_workspace_artifacts():
    """Mencari file transkrip & daftar video hasil langkah 1 secara otomatis."""
    transcript_candidates = [
        "workspace/transcript.json",
        "workspace/prep_data.json",
        "workspace/metadata.json",
        "temp/transcript.json",
        "remotion/public/transcript.json",
    ]
    transcript_path = next((p for p in transcript_candidates if os.path.exists(p)), None)

    if not transcript_path:
        found = glob.glob("**/transcript*.json", recursive=True) + glob.glob("**/prep*.json", recursive=True)
        transcript_path = found[0] if found else None

    if not transcript_path:
        raise FileNotFoundError("File transkrip hasil langkah 1 tidak ditemukan di workspace.")

    with open(transcript_path, "r", encoding="utf-8") as f:
        prep_data = json.load(f)

    return transcript_path, prep_data


def collect_media_files(prep_data):
    """Mengumpulkan path file A-roll dan B-roll dari metadata atau folder kerja."""
    aroll_path = prep_data.get("aroll_path") or prep_data.get("a_roll")
    broll_list = prep_data.get("broll_files") or prep_data.get("b_rolls") or []

    # Normalisasi struktur broll_list
    normalized_brolls = []
    for item in broll_list:
        if isinstance(item, str) and os.path.exists(item):
            normalized_brolls.append({"name": os.path.basename(item), "path": item})
        elif isinstance(item, dict):
            p = item.get("path") or item.get("local_path") or item.get("src")
            if p and os.path.exists(p):
                normalized_brolls.append({"name": item.get("name") or os.path.basename(p), "path": p})

    # Fallback scan folder jika metadata belum lengkap
    if not aroll_path or not os.path.exists(str(aroll_path)):
        for folder in ["workspace", "remotion/public/assets", "remotion/public", "temp"]:
            if not os.path.isdir(folder):
                continue
            for fn in sorted(os.listdir(folder)):
                full = os.path.join(folder, fn)
                if fn.lower().endswith(VIDEO_EXTS) and "final" not in fn.lower():
                    if "aroll" in fn.lower() or "a_roll" in fn.lower() or "cut" in fn.lower():
                        aroll_path = full
                    elif not any(b["path"] == full for b in normalized_brolls):
                        normalized_brolls.append({"name": fn, "path": full})

    return aroll_path, normalized_brolls


def upload_video_to_gemini(client, file_path):
    """Mengunggah video ke Gemini File API dan menunggu hingga status ACTIVE."""
    print(f"[GEMINI FILE] Mengunggah {os.path.basename(file_path)}...")
    uploaded = client.files.upload(file=file_path)
    max_wait = 180
    waited = 0
    while getattr(uploaded.state, "name", str(uploaded.state)) == "PROCESSING":
        if waited >= max_wait:
            raise TimeoutError(f"Waktu tunggu pemrosesan video habis untuk {file_path}")
        time.sleep(3)
        waited += 3
        uploaded = client.files.get(name=uploaded.name)

    state_name = getattr(uploaded.state, "name", str(uploaded.state))
    if state_name != "ACTIVE":
        raise RuntimeError(f"Gagal memproses file {file_path}, status: {state_name}")
    return uploaded


def extract_json_object(raw_text):
    """Membersihkan pembungkus markdown dan mem-parsing JSON dari respons model."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError("Respons Gemini tidak mengandung objek JSON yang valid.")
    return json.loads(match.group(0))


def build_fallback_plan(words, brolls):
    """Rencana cadangan otomatis jika seluruh kandidat model gagal merespons."""
    total_words = len(words)
    clean_words = []
    for i, w in enumerate(words):
        txt = str(w.get("word", "")).strip()
        clean_words.append({
            "idx": i,
            "clean_word": txt.upper(),
            "start": float(w.get("start", 0.0)),
            "end": float(w.get("end", 0.0)),
            "highlight": len(txt) >= 6 and i % 3 == 0,
            "highlight_color": "green",
        })

    return {
        "keep_word_ranges": [{"start_idx": 0, "end_idx": max(0, total_words - 1), "reason": "fallback_full"}],
        "words": clean_words,
        "broll_placements": [],
        "callouts": [],
        "camera_punches": [],
        "sfx_cues": [],
        "bgm": {"enabled": True, "volume": 0.12},
    }


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Secret GEMINI_API_KEY belum terbaca!")

    transcript_path, prep_data = find_workspace_artifacts()
    words = prep_data.get("words") or []
    if not words:
        raise ValueError("Daftar kata transkrip kosong, tidak ada yang bisa disusun.")

    aroll_path, brolls = collect_media_files(prep_data)
    print(f"[DIRECTOR] Ditemukan {len(words)} kata transkrip, A-roll: {aroll_path}, B-roll: {len(brolls)} klip.")

    client = genai.Client(api_key=api_key)
    uploaded_handles = []

    try:
        multimodal_input = []

        if aroll_path and os.path.exists(aroll_path):
            aroll_file = upload_video_to_gemini(client, aroll_path)
            uploaded_handles.append(aroll_file)
            multimodal_input.append({"type": "text", "text": "VIDEO UTAMA (A-ROLL TALKING HEAD):"})
            multimodal_input.append({
                "type": "video",
                "uri": aroll_file.uri,
                "mime_type": aroll_file.mime_type or "video/mp4",
            })

        for idx, b in enumerate(brolls):
            b_file = upload_video_to_gemini(client, b["path"])
            uploaded_handles.append(b_file)
            multimodal_input.append({
                "type": "text",
                "text": f"KLIP B-ROLL #{idx} — nama file: '{b['name']}':"
            })
            multimodal_input.append({
                "type": "video",
                "uri": b_file.uri,
                "mime_type": b_file.mime_type or "video/mp4",
            })

        indexed_words = [
            {
                "idx": i,
                "word": w.get("word", "").strip(),
                "start": round(float(w.get("start", 0.0)), 3),
                "end": round(float(w.get("end", 0.0)), 3),
            }
            for i, w in enumerate(words)
        ]

        schema_instruction = f"""
TRANSKRIP BERINDEKS ({len(indexed_words)} kata):
{json.dumps(indexed_words, ensure_ascii=False)}

DAFTAR NAMA FILE B-ROLL TERSEDIA:
{json.dumps([b["name"] for b in brolls], ensure_ascii=False)}

Susun JSON dengan struktur PERSIS berikut:
{{
  "keep_word_ranges": [
    {{"start_idx": 1, "end_idx": 45, "reason": "hook dan penjelasan awal bersih"}}
  ],
  "words": [
    {{
      "idx": 1,
      "clean_word": "TERNYATA",
      "start": 0.42,
      "end": 0.85,
      "highlight": true,
      "highlight_color": "green"
    }}
  ],
  "broll_placements": [
    {{
      "broll_name": "nama_file_broll.mp4",
      "start_word_idx": 28,
      "end_word_idx": 65,
      "clip_start_sec": 0.0,
      "transition": "glitch",
      "crt_effect": true
    }}
  ],
  "callouts": [
    {{
      "type": "url_card",
      "start_word_idx": 52,
      "duration_sec": 3.0,
      "primary_text": "ip-tv.app/indonesia",
      "secondary_text": "MASUKKAN URL PLAYLIST"
    }}
  ],
  "camera_punches": [
    {{"word_idx": 1, "zoom": 1.12, "transition": "blur_in"}},
    {{"word_idx": 15, "zoom": 1.15, "transition": "punch"}}
  ],
  "sfx_cues": [
    {{"word_idx": 1, "type": "whoosh"}},
    {{"word_idx": 12, "type": "pop"}},
    {{"word_idx": 28, "type": "impact"}}
  ],
  "bgm": {{
    "enabled": true,
    "mood": "tech_lo_fi_beat",
    "volume": 0.12
  }}
}}
"""
        multimodal_input.append({"type": "text", "text": schema_instruction})

        plan = None
        last_error = None

        for model_name in MODEL_CANDIDATES:
            try:
                print(f"[DIRECTOR] Meminta arahan multimodal ke model: {model_name}...")
                interaction = client.interactions.create(
                    model=model_name,
                    system_instruction=SYSTEM_PROMPT,
                    input=multimodal_input,
                    generation_config={"temperature": 0.2},
                )
                raw_output = interaction.output_text or ""
                plan = extract_json_object(raw_output)
                print(f"[SUKSES] Timeline berhasil disusun oleh {model_name}!")
                break
            except Exception as err:
                last_error = err
                print(f"[WARNING] Model {model_name} gagal ({err}), beralih ke cadangan...")

        if plan is None:
            print(f"[FALLBACK] Semua model gagal ({last_error}), menggunakan timeline cadangan aman.")
            plan = build_fallback_plan(words, brolls)

    finally:
        # Bersihkan file video sementara dari server Gemini File API
        for handle in uploaded_handles:
            try:
                client.files.delete(name=handle.name)
            except Exception:
                pass

    # Validasi minimum agar pipeline tidak pernah kosong
    if not plan.get("keep_word_ranges"):
        plan["keep_word_ranges"] = [{"start_idx": 0, "end_idx": len(words) - 1, "reason": "auto_guard"}]
    if not plan.get("words"):
        plan["words"] = build_fallback_plan(words, brolls)["words"]

    # Gabungkan dengan metadata asli agar kompatibel dengan komponen Remotion & SFX
    final_timeline = {
        **prep_data,
        "director_plan": plan,
        "keep_word_ranges": plan["keep_word_ranges"],
        "words": plan["words"],
        "broll_placements": plan.get("broll_placements", []),
        "callouts": plan.get("callouts", []),
        "camera_punches": plan.get("camera_punches", []),
        "sfx_cues": plan.get("sfx_cues", []),
        "bgm": plan.get("bgm", {"enabled": True, "volume": 0.12}),
    }

    output_targets = [
        os.path.join(os.path.dirname(transcript_path), "timeline.json"),
        "remotion/src/timeline.json",
        "remotion/public/timeline.json",
    ]
    for target in output_targets:
        parent = os.path.dirname(target)
        if parent and os.path.isdir(parent):
            with open(target, "w", encoding="utf-8") as f:
                json.dump(final_timeline, f, ensure_ascii=False, indent=2)
            print(f"[SAVED] Timeline tersimpan ke: {target}")


if __name__ == "__main__":
    main()
