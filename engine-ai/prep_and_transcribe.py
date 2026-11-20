import os
import re
import json
import shutil
import subprocess
from faster_whisper import WhisperModel
from drive_sync import download_bahan_video

def run_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"[CMD WARNING] {' '.join(cmd)}\n{result.stderr[-500:]}")
    return result

def get_video_info(path):
    # Ambil durasi video
    cmd_dur = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    res_dur = run_cmd(cmd_dur)
    try:
        duration = float(res_dur.stdout.strip())
    except ValueError:
        duration = 0.0

    # Cek rata-rata volume suara untuk membedakan talking head vs B-roll
    cmd_vol = [
        "ffmpeg", "-i", path, "-af", "volumedetect", "-vn", "-sn", "-dn",
        "-f", "null", "/dev/null"
    ]
    res_vol = run_cmd(cmd_vol)
    match = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", res_vol.stderr)
    mean_vol = float(match.group(1)) if match else -91.0

    return duration, mean_vol

def normalize_video(src, dst, mute=False):
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p"
    ]
    if mute:
        cmd.append("-an")
    else:
        cmd.extend(["-c:a", "aac", "-ar", "44100", "-ac", "1", "-b:a", "128k"])
    cmd.append(dst)
    run_cmd(cmd)

def extract_thumbnail(video_path, thumb_path, duration):
    mid_time = max(0.2, duration * 0.5)
    cmd = [
        "ffmpeg", "-y", "-ss", str(mid_time), "-i", video_path,
        "-vframes", "1", "-vf", "scale=540:-1", "-q:v", "5", thumb_path
    ]
    run_cmd(cmd)

def main():
    os.makedirs("workspace/raw", exist_ok=True)
    os.makedirs("workspace/aroll", exist_ok=True)
    os.makedirs("workspace/thumbs", exist_ok=True)
    os.makedirs("remotion/public/broll", exist_ok=True)

    print("=== 1. MENGUNDUH BAHAN DARI GOOGLE DRIVE ===")
    files = download_bahan_video("workspace/raw")
    if not files:
        raise RuntimeError("Folder 02-Bahan-Video kosong! Upload video A-roll terlebih dahulu.")

    print("\n=== 2. MEMISAHKAN A-ROLL & B-ROLL SECARA OTOMATIS ===")
    analyzed = []
    for f in files:
        dur, vol = get_video_info(f["local_path"])
        print(f"- {f['name']}: durasi={dur:.1f}s, volume={vol:.1f}dB")
        analyzed.append({**f, "duration": dur, "mean_vol": vol})

    # Klip >= 7 detik dengan suara bicara (> -40 dB) dianggap A-Roll
    aroll_list = [x for x in analyzed if x["duration"] >= 7.0 and x["mean_vol"] > -40.0]
    if not aroll_list:
        # Fallback: ambil klip terpanjang sebagai A-Roll
        analyzed.sort(key=lambda x: x["duration"], reverse=True)
        aroll_list = [analyzed[0]]

    aroll_ids = {x["id"] for x in aroll_list}
    broll_list = [x for x in analyzed if x["id"] not in aroll_ids]
    aroll_list.sort(key=lambda x: x["name"])

    print(f"Terdeteksi {len(aroll_list)} klip A-Roll dan {len(broll_list)} klip B-Roll.")

    print("\n=== 3. NORMALISASI & ROUGH CUT A-ROLL (AUTO-EDITOR) ===")
    norm_arolls = []
    for idx, item in enumerate(aroll_list):
        norm_path = f"workspace/aroll/norm_{idx:02d}.mp4"
        normalize_video(item["local_path"], norm_path, mute=False)
        norm_arolls.append(norm_path)

    if len(norm_arolls) == 1:
        combined_aroll = norm_arolls[0]
    else:
        concat_txt = "workspace/aroll/concat.txt"
        with open(concat_txt, "w") as cf:
            for p in norm_arolls:
                cf.write(f"file '{os.path.abspath(p)}'\n")
        combined_aroll = "workspace/aroll/combined.mp4"
        run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", combined_aroll])

    clean_aroll = "workspace/aroll/clean_aroll.mp4"
    res_ae = run_cmd([
        "auto-editor", combined_aroll,
        "--edit", "audio:4%",
        "--margin", "0.12s",
        "-o", clean_aroll
    ])
    if res_ae.returncode != 0 or not os.path.exists(clean_aroll):
        print("Auto-editor fallback ke video gabungan tanpa potong jeda.")
        shutil.copy(combined_aroll, clean_aroll)

    final_aroll_public = "remotion/public/aroll.mp4"
    shutil.copy(clean_aroll, final_aroll_public)
    final_aroll_dur, _ = get_video_info(final_aroll_public)

    print("\n=== 4. MEMPROSES B-ROLL & EKSTRAK THUMBNAIL ===")
    broll_manifest = []
    for idx, item in enumerate(broll_list):
        b_id = f"broll_{idx+1:02d}"
        rel_public_path = f"broll/{b_id}.mp4"
        full_public_path = f"remotion/public/{rel_public_path}"
        thumb_path = f"workspace/thumbs/{b_id}.jpg"

        normalize_video(item["local_path"], full_public_path, mute=True)
        b_dur, _ = get_video_info(full_public_path)
        extract_thumbnail(full_public_path, thumb_path, b_dur)

        broll_manifest.append({
            "id": b_id,
            "original_name": item["name"],
            "src": rel_public_path,
            "thumb": thumb_path,
            "duration": round(b_dur, 2)
        })

    print("\n=== 5. TRANSKRIPSI LOKAL PER KATA (FASTER-WHISPER) ===")
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(final_aroll_public, word_timestamps=True)

    words_data = []
    segments_data = []
    for idx, seg in enumerate(segments):
        segments_data.append({
            "id": idx,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip()
        })
        if seg.words:
            for w in seg.words:
                words_data.append({
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3)
                })

    manifest = {
        "aroll_src": "aroll.mp4",
        "aroll_duration": round(final_aroll_dur, 3),
        "segments": segments_data,
        "words": words_data,
        "brolls": broll_manifest,
        "drive_file_ids": [f["id"] for f in files]
    }

    with open("workspace/prep_manifest.json", "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2, ensure_ascii=False)

    print(f"\n[SELESAI] Total kata tertranskripsi: {len(words_data)} | Durasi bersih A-Roll: {final_aroll_dur:.1f}s")

if __name__ == "__main__":
    main()
