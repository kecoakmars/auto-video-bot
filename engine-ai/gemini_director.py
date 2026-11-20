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
   - Jika di awal video ada hitungan mundur (misalnya "tiga...", "satu dua", atau jeda napas panjang sebelum kalimat pembuka), JANGAN masukkan rentang indeks kata tersebut ke `keep_word_ranges`.
   - Jika pembicara salah ucap lalu mengulang frasa/kalimat yang sama (contoh: "Kemudian pilih... Kemudian pilih..."), BUANG percobaan pertama yang salah dan HANYA pertahankan pengulangan yang benar.
   - Buang jeda kosong di paling akhir setelah kalimat penutup selesai.

2. TUTUP BAGIAN TUTORIAL DENGAN B-ROLL PENUH (80% - 95% DURASI DEMO):
   - Tonton isi visual setiap klip B-roll yang diberikan.
   - Saat pembicara mulai menjelaskan langkah teknis, tutorial aplikasi, atau menunduk mengoperasikan HP, WAJIB tutup layar menggunakan klip B-roll yang paling relevan dengan langkah yang sedang diucapkan.
   - Jangan biarkan A-roll menampilkan pembicara yang menunduk terlalu lama; sambung klip B-roll secara berurutan mengikuti alur tutorial, dan atur `clip_start_sec` sesuai bagian layar yang relevan di dalam file B-roll tersebut.

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


def find_timeline_file():
    candidates = [
        "remotion/public/timeline.json",
        "workspace/timeline.json",
        "workspace/transcript.json",
        "temp/timeline.json",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    found = glob.glob("**/timeline.json", recursive=True) + glob.glob("**/transcript*.json", recursive=True)
    if found:
        return found[0]
    raise FileNotFoundError("File timeline.json / transcript.json hasil langkah 1 tidak ditemukan.")


def extract_words_from_data(data, fps):
    """Mengambil daftar kata beserta timestamp detik asli dari timeline.json."""
    if isinstance(data.get("words"), list) and len(data["words"]) > 0:
        return [
            {
                "word": str(w.get("word") or w.get("text", "")).strip(),
                "start": float(w.get("start", 0.0)),
                "end": float(w.get("end", 0.0)),
            }
            for w in data["words"]
            if str(w.get("word") or w.get("text", "")).strip()
        ]

    # Jika prep_and_transcribe hanya menyimpan captions berbasis frame
    words = []
    aroll_cuts = data.get("arollCuts", [])

    def out_frame_to_src_sec(out_f):
        for cut in aroll_cuts:
            c_start = cut["outStartFrame"]
            c_end = c_start + cut["durationFrames"]
            if c_start <= out_f <= c_end:
                return cut["srcStartSec"] + (out_f - c_start) / fps
        return out_f / fps

    for block in data.get("captions", []):
        for w in block.get("words", []):
            txt = str(w.get("text") or w.get("word", "")).strip()
            if txt:
                words.append({
                    "word": txt,
                    "start": out_frame_to_src_sec(int(w.get("startFrame", 0))),
                    "end": out_frame_to_src_sec(int(w.get("endFrame", 0))),
                })
    return words


def discover_media_files(data):
    """Mencari file A-roll dan semua file B-roll yang tersedia di remotion/public."""
    public_dir = "remotion/public"
    aroll_src = data.get("arollSrc", "aroll.mp4")
    aroll_path = os.path.join(public_dir, aroll_src)
    if not os.path.exists(aroll_path):
        aroll_path = data.get("aroll_path") or ""

    brolls = []
    if os.path.isdir(public_dir):
        for fn in sorted(os.listdir(public_dir)):
            full_path = os.path.join(public_dir, fn)
            if not os.path.isfile(full_path):
                continue
            if not fn.lower().endswith(VIDEO_EXTS):
                continue
            if fn == os.path.basename(aroll_src) or "final" in fn.lower():
                continue
            brolls.append({"name": fn, "path": full_path})

    return aroll_path, brolls


def upload_video_to_gemini(client, file_path):
    print(f"[GEMINI FILE] Mengunggah {os.path.basename(file_path)}...")
    uploaded = client.files.upload(file=file_path)
    waited = 0
    while getattr(uploaded.state, "name", str(uploaded.state)) == "PROCESSING":
        if waited >= 180:
            raise TimeoutError(f"Waktu tunggu pemrosesan video habis untuk {file_path}")
        time.sleep(3)
        waited += 3
        uploaded = client.files.get(name=uploaded.name)

    state_name = getattr(uploaded.state, "name", str(uploaded.state))
    if state_name != "ACTIVE":
        raise RuntimeError(f"Gagal memproses file {file_path}, status: {state_name}")
    return uploaded


def extract_json_object(raw_text):
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError("Respons Gemini tidak mengandung objek JSON yang valid.")
    return json.loads(match.group(0))


def build_remotion_timeline(base_data, words, brolls, plan):
    """Mengonversi rencana AI menjadi struktur TimelineData presisi untuk Remotion."""
    fps = int(base_data.get("fps") or 30)
    width = int(base_data.get("width") or 1080)
    height = int(base_data.get("height") or 1920)
    aroll_src = base_data.get("arollSrc") or "aroll.mp4"

    word_map = {int(w["idx"]): w for w in plan.get("words", []) if "idx" in w}
    punch_map = {int(p["word_idx"]): float(p.get("zoom", 1.12)) for p in plan.get("camera_punches", []) if "word_idx" in p}

    # 1. Susun potongan A-roll bersih berdasarkan keep_word_ranges
    raw_ranges = plan.get("keep_word_ranges") or [{"start_idx": 0, "end_idx": len(words) - 1}]
    clean_ranges = []
    for r in raw_ranges:
        s_idx = max(0, min(len(words) - 1, int(r.get("start_idx", 0))))
        e_idx = max(s_idx, min(len(words) - 1, int(r.get("end_idx", len(words) - 1))))
        clean_ranges.append((s_idx, e_idx))
    clean_ranges.sort(key=lambda x: x[0])

    # Gabungkan segmen yang berdekatan (< 0.35 detik) agar potongan tetap natural
    merged_segments = []
    for s_idx, e_idx in clean_ranges:
        src_start = max(0.0, words[s_idx]["start"] - 0.08)
        src_end = words[e_idx]["end"] + 0.14
        if merged_segments and src_start - merged_segments[-1]["srcEndSec"] < 0.35:
            merged_segments[-1]["srcEndSec"] = max(merged_segments[-1]["srcEndSec"], src_end)
            merged_segments[-1]["end_idx"] = e_idx
        else:
            zoom_val = 1.0
            for idx_check in range(s_idx, e_idx + 1):
                if idx_check in punch_map:
                    zoom_val = punch_map[idx_check]
                    break
            merged_segments.append({
                "srcStartSec": round(src_start, 3),
                "srcEndSec": round(src_end, 3),
                "start_idx": s_idx,
                "end_idx": e_idx,
                "zoom": zoom_val,
            })

    aroll_cuts = []
    current_out_frame = 0
    for seg in merged_segments:
        dur_frames = max(6, round((seg["srcEndSec"] - seg["srcStartSec"]) * fps))
        cut_obj = {
            "srcStartSec": seg["srcStartSec"],
            "srcEndSec": seg["srcEndSec"],
            "outStartFrame": current_out_frame,
            "durationFrames": dur_frames,
            "zoom": seg["zoom"],
        }
        aroll_cuts.append(cut_obj)
        current_out_frame += dur_frames

    total_duration_frames = max(30, current_out_frame)

    def is_word_kept(idx):
        return any(s <= idx <= e for s, e in clean_ranges)

    def src_sec_to_out_frame(sec):
        for cut in aroll_cuts:
            if cut["srcStartSec"] - 0.15 <= sec <= cut["srcEndSec"] + 0.15:
                rel_sec = max(0.0, min(cut["srcEndSec"] - cut["srcStartSec"], sec - cut["srcStartSec"]))
                return cut["outStartFrame"] + round(rel_sec * fps)
        for cut in aroll_cuts:
            if sec < cut["srcStartSec"]:
                return cut["outStartFrame"]
        return total_duration_frames

    # 2. Susun CaptionBlock (3 kata per blok) dengan koreksi teks & warna neon
    kept_caption_words = []
    for i, orig_w in enumerate(words):
        if not is_word_kept(i):
            continue
        ai_w = word_map.get(i, {})
        clean_txt = str(ai_w.get("clean_word") or orig_w["word"]).strip().upper()
        if not clean_txt:
            continue
        sf = src_sec_to_out_frame(orig_w["start"])
        ef = max(sf + 3, src_sec_to_out_frame(orig_w["end"]))
        kept_caption_words.append({
            "idx": i,
            "text": clean_txt,
            "startFrame": sf,
            "endFrame": ef,
            "isNeon": bool(ai_w.get("highlight", False)),
            "neonColor": "red" if ai_w.get("highlight_color") == "red" else "green",
        })

    captions = []
    chunk = []
    for cw in kept_caption_words:
        chunk.append({
            "text": cw["text"],
            "startFrame": cw["startFrame"],
            "endFrame": cw["endFrame"],
            "isNeon": cw["isNeon"],
            "neonColor": cw["neonColor"],
        })
        ends_sentence = bool(re.search(r"[.?!,]$", cw["text"]))
        if len(chunk) >= 3 or ends_sentence:
            captions.append({
                "startFrame": chunk[0]["startFrame"],
                "endFrame": chunk[-1]["endFrame"] + 4,
                "words": chunk,
            })
            chunk = []
    if chunk:
        captions.append({
            "startFrame": chunk[0]["startFrame"],
            "endFrame": chunk[-1]["endFrame"] + 4,
            "words": chunk,
        })

    # 3. Susun B-Roll Overlays dengan clipStartSec
    valid_broll_names = {b["name"]: b["name"] for b in brolls}
    broll_overlays = []
    for bp in plan.get("broll_placements", []):
        b_name = str(bp.get("broll_name", "")).strip()
        if b_name not in valid_broll_names and brolls:
            # Cocokkan parsial jika nama file sedikit berbeda
            matched = next((b["name"] for b in brolls if b_name.lower() in b["name"].lower()), brolls[0]["name"])
            b_name = matched
        if b_name not in valid_broll_names:
            continue

        s_idx = max(0, min(len(words) - 1, int(bp.get("start_word_idx", 0))))
        e_idx = max(s_idx, min(len(words) - 1, int(bp.get("end_word_idx", s_idx))))
        out_start = src_sec_to_out_frame(words[s_idx]["start"])
        out_end = src_sec_to_out_frame(words[e_idx]["end"] + 0.15)
        dur = max(18, out_end - out_start)
        if out_start >= total_duration_frames:
            continue
        dur = min(dur, total_duration_frames - out_start)

        broll_overlays.append({
            "src": b_name,
            "outStartFrame": out_start,
            "durationFrames": dur,
            "clipStartSec": max(0.0, float(bp.get("clip_start_sec", 0.0))),
            "filter": "crt-chromatic",
            "transition": "light-leak" if bp.get("transition") == "light-leak" else "glitch",
        })

    # 4. Susun Callout Overlays (Kartu URL, Follow Badge, Store Badge)
    callouts = []
    for co in plan.get("callouts", []):
        w_idx = max(0, min(len(words) - 1, int(co.get("start_word_idx", 0))))
        out_start = src_sec_to_out_frame(words[w_idx]["start"])
        dur_frames = max(36, round(float(co.get("duration_sec", 2.5)) * fps))
        if out_start >= total_duration_frames:
            continue
        dur_frames = min(dur_frames, total_duration_frames - out_start)
        callouts.append({
            "type": co.get("type", "step_card"),
            "outStartFrame": out_start,
            "durationFrames": dur_frames,
            "primaryText": str(co.get("primary_text", "")).strip(),
            "secondaryText": str(co.get("secondary_text", "")).strip(),
        })

    # 5. Susun SFX Events (dari AI + otomatis di awal B-roll & Callout)
    sfx_events = []
    for sfx in plan.get("sfx_cues", []):
        w_idx = max(0, min(len(words) - 1, int(sfx.get("word_idx", 0))))
        sfx_type = sfx.get("type", "whoosh")
        if sfx_type not in ("whoosh", "pop", "impact"):
            sfx_type = "whoosh"
        sfx_events.append({
            "type": sfx_type,
            "frame": src_sec_to_out_frame(words[w_idx]["start"]),
            "volume": 0.45,
        })

    for bo in broll_overlays:
        sfx_events.append({
            "type": "impact" if bo["transition"] == "glitch" else "whoosh",
            "frame": bo["outStartFrame"],
            "volume": 0.45,
        })

    for co in callouts:
        sfx_events.append({
            "type": "pop",
            "frame": co["outStartFrame"],
            "volume": 0.5,
        })

    return {
        **base_data,
        "fps": fps,
        "width": width,
        "height": height,
        "durationInFrames": total_duration_frames,
        "arollSrc": aroll_src,
        "arollCuts": aroll_cuts,
        "brollOverlays": broll_overlays,
        "captions": captions,
        "callouts": callouts,
        "sfxEvents": sfx_events,
        "bgm": plan.get("bgm", {"enabled": True, "volume": 0.1}),
    }


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Secret GEMINI_API_KEY belum terbaca!")

    timeline_path = find_timeline_file()
    with open(timeline_path, "r", encoding="utf-8") as f:
        base_data = json.load(f)

    fps = int(base_data.get("fps") or 30)
    words = extract_words_from_data(base_data, fps)
    if not words:
        raise ValueError("Daftar kata transkrip kosong di dalam timeline.json.")

    aroll_path, brolls = discover_media_files(base_data)
    print(f"[DIRECTOR] Kata: {len(words)} | A-roll: {aroll_path} | B-roll ditemukan: {[b['name'] for b in brolls]}")

    client = genai.Client(api_key=api_key)
    uploaded_handles = []
    plan = None

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
                "word": w["word"],
                "start": round(w["start"], 3),
                "end": round(w["end"], 3),
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
    {{"start_idx": 1, "end_idx": 45, "reason": "kalimat pembuka bersih tanpa count-in"}}
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
      "transition": "glitch"
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
    {{"word_idx": 1, "zoom": 1.12}},
    {{"word_idx": 15, "zoom": 1.15}}
  ],
  "sfx_cues": [
    {{"word_idx": 1, "type": "whoosh"}},
    {{"word_idx": 12, "type": "pop"}}
  ],
  "bgm": {{
    "enabled": true,
    "volume": 0.1
  }}
}}
"""
        multimodal_input.append({"type": "text", "text": schema_instruction})

        for model_name in MODEL_CANDIDATES:
            try:
                print(f"[DIRECTOR] Meminta arahan multimodal ke model: {model_name}...")
                interaction = client.interactions.create(
                    model=model_name,
                    system_instruction=SYSTEM_PROMPT,
                    input=multimodal_input,
                    generation_config={"temperature": 0.2},
                )
                plan = extract_json_object(interaction.output_text or "")
                print(f"[SUKSES] Timeline berhasil disusun oleh {model_name}!")
                break
            except Exception as err:
                print(f"[WARNING] Model {model_name} gagal ({err}), mencoba cadangan...")

    finally:
        for handle in uploaded_handles:
            try:
                client.files.delete(name=handle.name)
            except Exception:
                pass

    if plan is None:
        print("[FALLBACK] Menggunakan susunan aman bawaan.")
        plan = {
            "keep_word_ranges": [{"start_idx": 0, "end_idx": len(words) - 1}],
            "words": [],
            "broll_placements": [],
            "callouts": [],
            "camera_punches": [],
            "sfx_cues": [],
            "bgm": {"enabled": True, "volume": 0.1},
        }

    final_timeline = build_remotion_timeline(base_data, words, brolls, plan)

    with open(timeline_path, "w", encoding="utf-8") as f:
        json.dump(final_timeline, f, ensure_ascii=False, indent=2)
    print(f"[SAVED] Timeline final ({final_timeline['durationInFrames']} frames) tersimpan ke {timeline_path}")


if __name__ == "__main__":
    main()
