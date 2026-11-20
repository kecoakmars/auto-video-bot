import io
import os
import re
import sys
import json
import time
import shutil
import subprocess
from google import genai

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

MODEL_CANDIDATES = [
    "models/gemini-4-hydrogen",
    "gemini-4-hydrogen",
    "gemini-4-neon",
]

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi")
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".cache", ".github"}
SKIP_JSONS = {
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "reel-segments.json",
    "reel-words.json",
}

SYSTEM_PROMPT = """Kamu adalah Sutradara & Editor Video Short-Form Profesional (TikTok / Reels / Shorts) dengan gaya visual dinamis, padat, dan high-retention.

Tugasmu adalah menonton:
1. Video Referensi Style (jika dilampirkan) untuk meniru ritme cut, kepadatan B-roll tutorial, gaya subtitle, dan kartu callout-nya.
2. Video utama A-Roll (talking head) dan seluruh klip B-Roll (screen recording tutorial).
3. Transkrip kata ber-timestamp.

Lalu susun rencana editing JSON yang presisi untuk dirender oleh Remotion.

ATURAN WAJIB EDITING:
1. BUANG COUNT-IN & SALAH UCAP (RETAKE):
   - Tonton & dengarkan A-roll dari awal. Jika ada hitungan mundur ("tiga...", "satu dua"), tarikan napas panjang sebelum mulai, atau salah ucap yang diulang ("Kemudian pilih... Kemudian pilih..."), JANGAN masukkan indeks kata tersebut ke `keep_word_ranges`.
   - Hanya pertahankan rentang kata dari take yang bersih dan lancar.
   - Buang jeda kosong di paling akhir setelah kalimat penutup selesai.

2. TUTUP BAGIAN TUTORIAL DENGAN B-ROLL LAYAR PENUH (85% - 95% DURASI DEMO):
   - Tonton isi visual setiap klip B-roll dan perhatikan durasi aslinya.
   - Saat pembicara mulai menjelaskan langkah teknis, mengunduh aplikasi, mengetik URL, atau menunduk mengoperasikan HP, WAJIB tutup layar menggunakan klip B-roll yang paling cocok dengan ucapan tersebut.
   - Sambung klip B-roll secara berurutan mengikuti alur tutorial, dan atur `clip_start_sec` sesuai detik adegan yang tepat di dalam file B-roll (pastikan `clip_start_sec` selalu lebih kecil dari durasi file B-roll).

3. KOREKSI TRANSKRIP INDONESIA & HIGHLIGHT NEON:
   - Perbaiki seluruh kata salah ketik dari transkrip otomatis (misal: "walaulah" -> "BOLEHLAH", "undur" -> "UNDUH", "cerian" -> "CARANYA") pada `clean_word` dalam huruf KAPITAL tanpa mengubah timestamp aslinya.
   - Tandai `highlight: true` pada kata kunci/aksi/angka penting, dan pilih `highlight_color`: `"green"` (kata kunci utama) atau `"red"` (peringatan/larangan/CTA penting).

4. KARTU CALLOUT KONTEKSTUAL (`callouts`):
   - `follow_badge`: Saat pembicara mengajak follow/subscribe/cek profil (durasi ~2.2 detik).
   - `store_badge`: Saat menyebut unduh/download aplikasi di Play Store / App Store (durasi ~2.5 detik).
   - `url_card`: Saat menyebut alamat website/link/URL — tulis alamat URL akurat di `primary_text` (misal `"ip-tv.app/indonesia"` atau `"iptv.llc"`) dan keterangan singkat di `secondary_text` (durasi ~3.0 detik).
   - `step_card`: Saat masuk ke langkah penting atau tips utama (durasi ~2.4 detik).

5. KELUARAN JSON MURNI:
   - Balas HANYA dengan objek JSON valid tanpa teks pembuka/penutup.
"""


def get_video_duration_sec(video_path):
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return round(float(out), 3)
    except Exception:
        return 0.0


def download_reference_style_video(dest_dir="workspace/ref_style"):
    """Mengunduh video referensi dari folder Google Drive 01-Referensi-Style jika ada."""
    try:
        from drive_sync import get_drive_service, get_folder_ids
        from googleapiclient.http import MediaIoBaseDownload

        os.makedirs(dest_dir, exist_ok=True)
        service = get_drive_service()
        folders = get_folder_ids(service)
        ref_folder_id = folders.get("01-Referensi-Style")
        if not ref_folder_id:
            return None

        query = (
            f"'{ref_folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' "
            f"and trashed = false"
        )
        files = (
            service.files()
            .list(q=query, fields="files(id, name, createdTime)", orderBy="createdTime desc")
            .execute()
            .get("files", [])
        )
        for f in files:
            if f["name"].lower().endswith(VIDEO_EXTS):
                local_path = os.path.join(dest_dir, f["name"])
                print(f"[REF STYLE] Mengunduh video referensi: {f['name']}...")
                req = service.files().get_media(fileId=f["id"])
                with io.FileIO(local_path, "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, req)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                return local_path
    except Exception as err:
        print(f"[INFO] Lewati unduh 01-Referensi-Style ({err})")
    return None


def find_prep_data():
    """Memindai file JSON hasil langkah 1 (prep_and_transcribe.py)."""
    matches = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if not fn.lower().endswith(".json") or fn in SKIP_JSONS:
                continue
            full_path = os.path.join(root, fn)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            if isinstance(data, dict) and any(
                k in data for k in ("words", "segments", "captions", "transcript", "arollCuts")
            ):
                matches.append((os.path.getmtime(full_path), full_path, data))
            elif (
                isinstance(data, list)
                and len(data) > 0
                and isinstance(data[0], dict)
                and any(k in data[0] for k in ("word", "text", "start"))
            ):
                matches.append((os.path.getmtime(full_path), full_path, {"words": data}))

    if not matches:
        raise FileNotFoundError("File JSON transkrip hasil langkah 1 tidak ditemukan.")

    matches.sort(key=lambda item: item[0], reverse=True)
    _, chosen_path, chosen_data = matches[0]
    print(f"[DIRECTOR] Membaca data transkrip dari: {chosen_path}")
    return chosen_path, chosen_data


def extract_words_from_data(data, fps=30):
    """Mengekstrak daftar kata beserta timestamp detik asli."""
    if isinstance(data.get("words"), list) and data["words"]:
        return [
            {
                "word": str(w.get("word") or w.get("text", "")).strip(),
                "start": round(float(w.get("start", 0.0)), 3),
                "end": round(float(w.get("end", 0.0)), 3),
            }
            for w in data["words"]
            if str(w.get("word") or w.get("text", "")).strip()
        ]

    transcript_obj = data.get("transcript")
    if isinstance(transcript_obj, list) and transcript_obj:
        return extract_words_from_data({"words": transcript_obj}, fps)
    if isinstance(transcript_obj, dict):
        nested = extract_words_from_data(transcript_obj, fps)
        if nested:
            return nested

    if isinstance(data.get("segments"), list) and data["segments"]:
        words = []
        for seg in data["segments"]:
            if isinstance(seg.get("words"), list) and seg["words"]:
                for w in seg["words"]:
                    txt = str(w.get("word") or w.get("text", "")).strip()
                    if txt:
                        words.append({
                            "word": txt,
                            "start": round(float(w.get("start", seg.get("start", 0.0))), 3),
                            "end": round(float(w.get("end", seg.get("end", 0.0))), 3),
                        })
            else:
                tokens = str(seg.get("text", "")).strip().split()
                if tokens:
                    s0 = float(seg.get("start", 0.0))
                    s1 = max(s0 + 0.1, float(seg.get("end", s0 + 0.5)))
                    dt = (s1 - s0) / len(tokens)
                    for i, tok in enumerate(tokens):
                        words.append({
                            "word": tok,
                            "start": round(s0 + i * dt, 3),
                            "end": round(s0 + (i + 1) * dt, 3),
                        })
        if words:
            return words

    words = []
    aroll_cuts = data.get("arollCuts", [])

    def frame_to_sec(out_f):
        for cut in aroll_cuts:
            cs = cut["outStartFrame"]
            ce = cs + cut["durationFrames"]
            if cs <= out_f <= ce:
                return cut["srcStartSec"] + (out_f - cs) / fps
        return out_f / fps

    for block in data.get("captions", []):
        for w in block.get("words", []):
            txt = str(w.get("text") or w.get("word", "")).strip()
            if txt:
                words.append({
                    "word": txt,
                    "start": round(frame_to_sec(int(w.get("startFrame", 0))), 3),
                    "end": round(frame_to_sec(int(w.get("endFrame", 0))), 3),
                })
    return words


def sync_media_to_public(base_data, public_dir="remotion/public"):
    """Menyinkronkan A-roll dan semua B-roll ke remotion/public beserta durasinya."""
    os.makedirs(public_dir, exist_ok=True)
    aroll_name = os.path.basename(base_data.get("arollSrc") or "aroll.mp4")

    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if "ref_style" in root or "out" in root.split(os.sep):
            continue
        for fn in sorted(files):
            if not fn.lower().endswith(VIDEO_EXTS) or "final" in fn.lower():
                continue
            src = os.path.join(root, fn)
            dest = os.path.join(public_dir, fn)
            if os.path.abspath(src) != os.path.abspath(dest):
                if not os.path.exists(dest) or os.path.getsize(src) != os.path.getsize(dest):
                    shutil.copy2(src, dest)

    aroll_path = os.path.join(public_dir, aroll_name)
    if not os.path.exists(aroll_path):
        for fn in sorted(os.listdir(public_dir)):
            if fn.lower().endswith(VIDEO_EXTS) and ("aroll" in fn.lower() or "clean" in fn.lower()):
                aroll_name = fn
                aroll_path = os.path.join(public_dir, fn)
                break

    brolls = []
    for fn in sorted(os.listdir(public_dir)):
        full = os.path.join(public_dir, fn)
        if not os.path.isfile(full) or not fn.lower().endswith(VIDEO_EXTS):
            continue
        if fn == aroll_name or "final" in fn.lower():
            continue
        brolls.append({
            "name": fn,
            "path": full,
            "duration_sec": get_video_duration_sec(full),
        })

    aroll_info = {
        "name": aroll_name,
        "path": aroll_path if os.path.exists(aroll_path) else "",
        "duration_sec": get_video_duration_sec(aroll_path) if os.path.exists(aroll_path) else 0.0,
    }
    return aroll_info, brolls


def upload_video(client, file_path):
    print(f"[GEMINI UPLOAD] Mengunggah {os.path.basename(file_path)}...")
    uploaded = client.files.upload(file=file_path)
    waited = 0
    while getattr(uploaded.state, "name", str(uploaded.state)) == "PROCESSING":
        if waited >= 240:
            raise TimeoutError(f"Waktu tunggu pemrosesan video habis: {file_path}")
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
        raise ValueError("Respons Gemini tidak mengandung objek JSON valid.")
    return json.loads(match.group(0))


def build_remotion_timeline(base_data, words, aroll_info, brolls, plan):
    """Mengonversi arahan Gemini 4 Hydrogen menjadi TimelineData siap render."""
    fps = int(base_data.get("fps") or 30)
    width = int(base_data.get("width") or 1080)
    height = int(base_data.get("height") or 1920)
    aroll_src = aroll_info["name"] or "aroll.mp4"

    word_map = {int(w["idx"]): w for w in plan.get("words", []) if "idx" in w}
    punch_map = {
        int(p["word_idx"]): float(p.get("zoom", 1.12))
        for p in plan.get("camera_punches", [])
        if "word_idx" in p
    }

    raw_ranges = plan.get("keep_word_ranges") or [{"start_idx": 0, "end_idx": len(words) - 1}]
    clean_ranges = []
    for r in raw_ranges:
        s_idx = max(0, min(len(words) - 1, int(r.get("start_idx", 0))))
        e_idx = max(s_idx, min(len(words) - 1, int(r.get("end_idx", len(words) - 1))))
        clean_ranges.append((s_idx, e_idx))
    clean_ranges.sort(key=lambda x: x[0])

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
                "zoom": zoom_val,
            })

    aroll_cuts = []
    current_out_frame = 0
    for seg in merged_segments:
        dur_frames = max(6, round((seg["srcEndSec"] - seg["srcStartSec"]) * fps))
        aroll_cuts.append({
            "srcStartSec": seg["srcStartSec"],
            "srcEndSec": seg["srcEndSec"],
            "outStartFrame": current_out_frame,
            "durationFrames": dur_frames,
            "zoom": seg["zoom"],
        })
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
            "text": clean_txt,
            "startFrame": sf,
            "endFrame": ef,
            "isNeon": bool(ai_w.get("highlight", False)),
            "neonColor": "red" if ai_w.get("highlight_color") == "red" else "green",
        })

    captions = []
    chunk = []
    for cw in kept_caption_words:
        chunk.append(cw)
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

    broll_by_name = {b["name"]: b for b in brolls}
    broll_overlays = []
    for bp in plan.get("broll_placements", []):
        b_name = str(bp.get("broll_name", "")).strip()
        if b_name not in broll_by_name and brolls:
            b_name = next(
                (b["name"] for b in brolls if b_name.lower() in b["name"].lower()),
                brolls[0]["name"],
            )
        if b_name not in broll_by_name:
            continue

        s_idx = max(0, min(len(words) - 1, int(bp.get("start_word_idx", 0))))
        e_idx = max(s_idx, min(len(words) - 1, int(bp.get("end_word_idx", s_idx))))
        out_start = src_sec_to_out_frame(words[s_idx]["start"])
        out_end = src_sec_to_out_frame(words[e_idx]["end"] + 0.15)
        dur = max(18, out_end - out_start)
        if out_start >= total_duration_frames:
            continue
        dur = min(dur, total_duration_frames - out_start)

        b_dur_sec = broll_by_name[b_name]["duration_sec"]
        clip_start = max(0.0, float(bp.get("clip_start_sec", 0.0)))
        if b_dur_sec > 1.0:
            max_start = max(0.0, b_dur_sec - (dur / fps) - 0.1)
            clip_start = min(clip_start, max_start)

        broll_overlays.append({
            "src": b_name,
            "outStartFrame": out_start,
            "durationFrames": dur,
            "clipStartSec": round(clip_start, 3),
            "filter": "crt-chromatic",
            "transition": "light-leak" if bp.get("transition") == "light-leak" else "glitch",
        })

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

    bgm_cfg = plan.get("bgm") if isinstance(plan.get("bgm"), dict) else {}

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
        "bgm": {
            "enabled": bool(bgm_cfg.get("enabled", True)),
            "volume": float(bgm_cfg.get("volume", 0.09)),
        },
    }


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Secret GEMINI_API_KEY belum terbaca!")

    ref_video_path = download_reference_style_video()
    prep_path, base_data = find_prep_data()
    fps = int(base_data.get("fps") or 30)
    words = extract_words_from_data(base_data, fps)
    if not words:
        raise ValueError(f"Daftar kata transkrip kosong di dalam {prep_path}.")

    aroll_info, brolls = sync_media_to_public(base_data, "remotion/public")
    print(f"[DIRECTOR] Kata: {len(words)} | A-roll: {aroll_info['name']} | B-roll: {[b['name'] for b in brolls]}")

    client = genai.Client(api_key=api_key)
    uploaded_handles = []
    plan = None

    generation_config = {
        "max_output_tokens": 65536,
        "thinking_level": "high",
    }

    try:
        multimodal_input = []

        if ref_video_path and os.path.exists(ref_video_path):
            ref_handle = upload_video(client, ref_video_path)
            uploaded_handles.append(ref_handle)
            multimodal_input.append({
                "type": "text",
                "text": (
                    f"VIDEO REFERENSI STYLE EDITAN MANUAL ({os.path.basename(ref_video_path)}): "
                    "Tiru ritme potongan cepat, kepadatan B-roll tutorial penuh, "
                    "dan kemunculan kartu callout dari video referensi ini."
                ),
            })
            multimodal_input.append({
                "type": "video",
                "uri": ref_handle.uri,
                "mime_type": ref_handle.mime_type or "video/mp4",
            })

        if aroll_info["path"] and os.path.exists(aroll_info["path"]):
            aroll_handle = upload_video(client, aroll_info["path"])
            uploaded_handles.append(aroll_handle)
            multimodal_input.append({
                "type": "text",
                "text": f"VIDEO UTAMA A-ROLL TALKING HEAD ('{aroll_info['name']}', durasi {aroll_info['duration_sec']}s):",
            })
            multimodal_input.append({
                "type": "video",
                "uri": aroll_handle.uri,
                "mime_type": aroll_handle.mime_type or "video/mp4",
            })

        for idx, b in enumerate(brolls):
            b_handle = upload_video(client, b["path"])
            uploaded_handles.append(b_handle)
            multimodal_input.append({
                "type": "text",
                "text": f"KLIP B-ROLL #{idx} — nama file: '{b['name']}' (durasi {b['duration_sec']}s):",
            })
            multimodal_input.append({
                "type": "video",
                "uri": b_handle.uri,
                "mime_type": b_handle.mime_type or "video/mp4",
            })

        indexed_words = [
            {
                "idx": i,
                "word": w["word"],
                "start": w["start"],
                "end": w["end"],
            }
            for i, w in enumerate(words)
        ]

        schema_instruction = f"""
TRANSKRIP BERINDEKS ({len(indexed_words)} kata):
{json.dumps(indexed_words, ensure_ascii=False)}

DAFTAR KLIP B-ROLL TERSEDIA:
{json.dumps([{"name": b["name"], "duration_sec": b["duration_sec"]} for b in brolls], ensure_ascii=False)}

Balas HANYA dengan JSON berstruktur PERSIS seperti ini:
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
    {{"word_idx": 15, "zoom": 1.14}}
  ],
  "sfx_cues": [
    {{"word_idx": 1, "type": "whoosh"}},
    {{"word_idx": 12, "type": "pop"}}
  ],
  "bgm": {{
    "enabled": true,
    "volume": 0.09
  }}
}}
"""
        multimodal_input.append({"type": "text", "text": schema_instruction})

        for model_name in MODEL_CANDIDATES:
            try:
                print(f"[DIRECTOR] Menyusun rencana edit multimodal dengan {model_name} (thinking_level=high)...")
                interaction = client.interactions.create(
                    model=model_name,
                    system_instruction=SYSTEM_PROMPT,
                    input=multimodal_input,
                    generation_config=generation_config,
                )
                plan = extract_json_object(interaction.output_text or "")
                print(f"[SUKSES] Timeline berhasil disusun oleh {model_name}!")
                break
            except Exception as err:
                print(f"[WARNING] Model {model_name} gagal ({err}), mencoba cadangan...")

    finally:
        for h in uploaded_handles:
            try:
                client.files.delete(name=h.name)
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
            "bgm": {"enabled": True, "volume": 0.09},
        }

    final_timeline = build_remotion_timeline(base_data, words, aroll_info, brolls, plan)

    os.makedirs("remotion/public", exist_ok=True)
    remotion_target = "remotion/public/timeline.json"
    with open(remotion_target, "w", encoding="utf-8") as f:
        json.dump(final_timeline, f, ensure_ascii=False, indent=2)
    print(f"[SAVED] Timeline final ({final_timeline['durationInFrames']} frames) tersimpan ke {remotion_target}")

    prep_dir = os.path.dirname(prep_path)
    if prep_dir:
        alt_target = os.path.join(prep_dir, "timeline.json")
        if os.path.abspath(alt_target) != os.path.abspath(remotion_target):
            with open(alt_target, "w", encoding="utf-8") as f:
                json.dump(final_timeline, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
