import os
import re
import glob
import json
import base64
from google import genai

FPS = 30

def load_editorial_rules():
    rules = []
    for md_path in sorted(glob.glob("references/*.md")):
        with open(md_path, "r", encoding="utf-8") as f:
            rules.append(f"--- {os.path.basename(md_path)} ---\n{f.read()}")
    return "\n\n".join(rules)

def encode_image_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def extract_json_object(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"Gemini tidak mengembalikan JSON valid:\n{text[:500]}")
    return json.loads(match.group(0))

def ask_gemini_director(manifest, rules_text):
    words = manifest["words"]
    brolls = manifest["brolls"]

    numbered_words = " ".join([f"[{i}]{w['word']}" for i, w in enumerate(words)])
    broll_desc = "\n".join([
        f"- {b['id']} (durasi {b['duration']}s, file asli: {b['original_name']})"
        for b in brolls
    ]) if brolls else "Tidak ada klip B-Roll tersedia."

    system_instruction = f"""Kamu adalah sutradara video pendek vertikal (9:16) profesional untuk konten talking head.
Tugasmu menganalisis transkrip kata bernomor dan gambar thumbnail B-Roll, lalu menyusun rencana editing yang padat, tajam, dan bebas salah ucap.

Ikuti aturan editorial berikut secara ketat:
{rules_text}

Kamu WAJIB menjawab HANYA dalam format JSON murni tanpa penjelasan tambahan, mengikuti struktur persis ini:
{{
  "kept_word_ranges": [[0, 15], [22, 60]],
  "broll_placements": [
    {{
      "broll_id": "broll_01",
      "start_word_idx": 25,
      "end_word_idx": 34,
      "transition": "glitch"
    }}
  ],
  "neon_word_indices": [2, 3, 28, 29, 55, 56],
  "impact_word_indices": [2, 28, 55]
}}

Ketentuan teknis JSON:
1. `kept_word_ranges`: Daftar pasangan [indeks_awal, indeks_akhir] (inklusif) dari kata-kata yang DIPERTAHANKAN. Buang indeks di mana pembicara salah bicara atau mengulang kalimat. Indeks harus berurutan naik dan tidak tumpang tindih.
2. `broll_placements`: Gunakan `broll_id` yang tersedia di daftar (dan gambar terlampir) jika cocok dengan topik kata pada rentang tersebut. Nilai `transition` hanya boleh `"glitch"` atau `"light-leak"`. Kosongkan `[]` jika tidak ada B-Roll yang relevan.
3. `neon_word_indices`: Daftar indeks kata kunci penting (maksimal 20% dari total kata) untuk disorot warna hijau neon.
4. `impact_word_indices`: 2 hingga 4 indeks kata paling krusial untuk memicu efek suara dentuman halus (`impact`)."""

    prompt_text = f"""TRANSKRIP KATA BERNOMOR (Total {len(words)} kata, durasi audio {manifest['aroll_duration']}s):
{numbered_words}

DAFTAR B-ROLL TERSEDIA:
{broll_desc}

Susun rencana editing JSON terbaik sekarang."""

    input_blocks = [{"type": "text", "text": prompt_text}]
    for b in brolls:
        if os.path.exists(b["thumb"]):
            input_blocks.append({
                "type": "text",
                "text": f"Thumbnail untuk {b['id']}:"
            })
            input_blocks.append({
                "type": "image",
                "data": encode_image_b64(b["thumb"]),
                "mime_type": "image/jpeg"
            })

    client = genai.Client()
    last_err = None
    for model_name in ["gemini-4-hydrogen", "gemini-3.5-flash-lite"]:
        try:
            print(f"Meminta arahan sutradara ke model {model_name}...")
            interaction = client.interactions.create(
                model=model_name,
                input=input_blocks,
                system_instruction=system_instruction,
            )
            return extract_json_object(interaction.output_text)
        except Exception as e:
            print(f"[WARNING] Model {model_name} gagal: {e}")
            last_err = e

    raise RuntimeError(f"Semua model Gemini gagal merespons: {last_err}")

def build_remotion_timeline(manifest, plan):
    words = manifest["words"]
    aroll_dur = manifest["aroll_duration"]
    broll_map = {b["id"]: b for b in manifest["brolls"]}

    if not words:
        raise RuntimeError("Transkrip kosong! Pastikan video A-Roll memiliki suara bicara yang jelas.")

    # 1. Validasi & rapikan rentang kata yang dipertahankan
    raw_ranges = plan.get("kept_word_ranges") or [[0, len(words) - 1]]
    clean_ranges = []
    last_idx = -1
    for r in sorted(raw_ranges, key=lambda x: x[0]):
        s = max(0, int(r[0]))
        e = min(len(words) - 1, int(r[1]))
        if s > last_idx and e >= s:
            clean_ranges.append((s, e))
            last_idx = e

    if not clean_ranges:
        clean_ranges = [(0, len(words) - 1)]

    # 2. Bangun potongan A-Roll & petakan ulang timestamp kata secara presisi
    aroll_cuts = []
    mapped_words = {}  # orig_word_idx -> dict word baru di timeline output
    current_out_sec = 0.0

    for cut_idx, (w_start_idx, w_end_idx) in enumerate(clean_ranges):
        src_start = max(0.0, words[w_start_idx]["start"] - 0.08)
        src_end = min(aroll_dur, words[w_end_idx]["end"] + 0.12)
        if src_end <= src_start:
            continue

        seg_dur = src_end - src_start
        out_start_frame = round(current_out_sec * FPS)
        dur_frames = max(1, round(seg_dur * FPS))

        # Pola zoom dinamis: bergantian 1.0 dan 1.13 setiap potongan
        zoom_val = 1.0 if cut_idx % 2 == 0 else 1.13

        aroll_cuts.append({
            "srcStartSec": round(src_start, 3),
            "srcEndSec": round(src_end, 3),
            "outStartFrame": out_start_frame,
            "durationFrames": dur_frames,
            "zoom": zoom_val
        })

        for wi in range(w_start_idx, w_end_idx + 1):
            w_orig = words[wi]
            rel_start = max(0.0, w_orig["start"] - src_start)
            rel_end = max(rel_start + 0.05, w_orig["end"] - src_start)
            mapped_words[wi] = {
                "origIdx": wi,
                "text": w_orig["word"],
                "startFrame": out_start_frame + round(rel_start * FPS),
                "endFrame": out_start_frame + round(rel_end * FPS)
            }

        current_out_sec += seg_dur

    total_frames = max(1, round(current_out_sec * FPS))

    # 3. Tambahkan variasi punch-in zoom otomatis tiap ~4 detik jika satu potongan terlalu panjang
    split_cuts = []
    max_chunk_frames = 4 * FPS
    for cut in aroll_cuts:
        if cut["durationFrames"] <= max_chunk_frames * 1.3:
            split_cuts.append(cut)
        else:
            rem_frames = cut["durationFrames"]
            cur_out = cut["outStartFrame"]
            cur_src = cut["srcStartSec"]
            sub_i = 0
            while rem_frames > 0:
                step_f = min(rem_frames, max_chunk_frames)
                step_s = step_f / FPS
                split_cuts.append({
                    "srcStartSec": round(cur_src, 3),
                    "srcEndSec": round(cur_src + step_s, 3),
                    "outStartFrame": cur_out,
                    "durationFrames": step_f,
                    "zoom": 1.0 if (sub_i % 2 == 0) else 1.13
                })
                cur_out += step_f
                cur_src += step_s
                rem_frames -= step_f
                sub_i += 1
    aroll_cuts = split_cuts

    # 4. Susun B-Roll Overlays + Efek CRT & SFX Whoosh
    broll_overlays = []
    sfx_events = []
    used_brolls = set()

    for bp in plan.get("broll_placements", []):
        b_id = bp.get("broll_id")
        if b_id not in broll_map or b_id in used_brolls:
            continue
        s_idx = int(bp.get("start_word_idx", -1))
        e_idx = int(bp.get("end_word_idx", -1))
        valid_indices = [i for i in range(s_idx, e_idx + 1) if i in mapped_words]
        if not valid_indices:
            continue

        start_f = mapped_words[valid_indices[0]]["startFrame"]
        end_f = mapped_words[valid_indices[-1]]["endFrame"]
        max_b_frames = int(broll_map[b_id]["duration"] * FPS)
        dur_f = min(max(int(2.0 * FPS), end_f - start_f), max_b_frames)

        if start_f + dur_f > total_frames:
            dur_f = max(1, total_frames - start_f)

        transition = bp.get("transition") if bp.get("transition") in ("glitch", "light-leak") else "glitch"
        broll_overlays.append({
            "src": broll_map[b_id]["src"],
            "outStartFrame": start_f,
            "durationFrames": dur_f,
            "filter": "crt-chromatic",
            "transition": transition
        })
        sfx_events.append({
            "type": "whoosh",
            "frame": max(0, start_f - 3),
            "volume": 0.22
        })
        used_brolls.add(b_id)

    # 5. Kelompokkan Subtitle menjadi blok 3 kata yang dinamis + Sorotan Hijau Neon
    neon_set = set(int(i) for i in plan.get("neon_word_indices", []))
    impact_set = set(int(i) for i in plan.get("impact_word_indices", []))

    ordered_mapped = [mapped_words[k] for k in sorted(mapped_words.keys())]
    captions = []
    chunk_size = 3
    for i in range(0, len(ordered_mapped), chunk_size):
        chunk = ordered_mapped[i:i + chunk_size]
        c_start = chunk[0]["startFrame"]
        c_end = chunk[-1]["endFrame"] + 4
        if i + chunk_size < len(ordered_mapped):
            next_start = ordered_mapped[i + chunk_size]["startFrame"]
            c_end = min(c_end, next_start)

        word_items = []
        for w in chunk:
            is_neon = w["origIdx"] in neon_set
            word_items.append({
                "text": w["text"],
                "startFrame": w["startFrame"],
                "endFrame": max(w["startFrame"] + 2, w["endFrame"]),
                "isNeon": is_neon
            })
            if is_neon:
                sfx_events.append({
                    "type": "pop",
                    "frame": w["startFrame"],
                    "volume": 0.14
                })
            if w["origIdx"] in impact_set:
                sfx_events.append({
                    "type": "impact",
                    "frame": w["startFrame"],
                    "volume": 0.25
                })

        captions.append({
            "startFrame": c_start,
            "endFrame": max(c_start + 3, c_end),
            "words": word_items
        })

    return {
        "fps": FPS,
        "width": 1080,
        "height": 1920,
        "durationInFrames": total_frames,
        "arollSrc": manifest["aroll_src"],
        "arollCuts": aroll_cuts,
        "brollOverlays": broll_overlays,
        "captions": captions,
        "sfxEvents": sfx_events
    }

def main():
    with open("workspace/prep_manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)

    rules_text = load_editorial_rules()
    plan = ask_gemini_director(manifest, rules_text)
    timeline = build_remotion_timeline(manifest, plan)

    os.makedirs("remotion/public", exist_ok=True)
    out_path = "remotion/public/timeline.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2, ensure_ascii=False)

    print(f"[SUKSES] Timeline Remotion tersimpan di {out_path}")
    print(f"- Total durasi final: {timeline['durationInFrames'] / FPS:.1f} detik ({timeline['durationInFrames']} frames)")
    print(f"- Jumlah potongan A-Roll: {len(timeline['arollCuts'])}")
    print(f"- Jumlah B-Roll CRT: {len(timeline['brollOverlays'])}")
    print(f"- Jumlah blok subtitle: {len(timeline['captions'])}")

if __name__ == "__main__":
    main()
