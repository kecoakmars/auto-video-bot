import os
import re
import sys
import json
import shutil
import subprocess
import time
from google import genai

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi")
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".cache", ".github"}
SKIP_JSONS = {
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "reel-segments.json",
    "reel-words.json",
}

EDITOR_SYSTEM_PROMPT = """Kamu adalah Senior Video Editor & Remotion Creative Developer spesialis video short-form (TikTok / Reels / Shorts) gaya kreator teknologi Indonesia yang tajam, padat, dan high-retention.

Tugasmu adalah menonton:
1. Video Referensi Style (jika dilampirkan) untuk meniru ritme cut, kepadatan B-roll, gaya subtitle, dan aset grafisnya.
2. Rekaman mentah A-Roll (talking head) dan seluruh klip B-Roll (screen recording tutorial).
3. Transkrip kata ber-timestamp.

Lalu tuliskan kode lengkap file `remotion/src/AutoTalkingHead.tsx` yang siap di-render oleh Remotion (1080x1920, 30 fps) beserta total durasinya dalam frame.

ATURAN WAJIB EDITING:
1. BUANG COUNT-IN & SALAH UCAP (RETAKE):
   - Tonton & dengarkan A-roll dari detik 0. Jika ada hitungan mundur ("tiga...", "satu dua"), tarikan napas panjang sebelum mulai, atau salah ucap yang diulang ("Kemudian pilih... Kemudian pilih..."), POTONG dan BUANG bagian yang salah. Hanya sambungkan take yang bersih menggunakan `<Sequence>` + `<OffthreadVideo startFrom={...} endAt={...} />`.
   - Tambahkan crossfade audio 2 frame di setiap sambungan potongan A-roll agar tidak terdengar bunyi klik.

2. TUTUP BAGIAN TUTORIAL DENGAN B-ROLL LAYAR PENUH:
   - Tonton isi visual tiap klip B-roll dan cek durasi masing-masing file yang diberikan.
   - Saat pembicara mulai menjelaskan langkah teknis, mengunduh aplikasi, mengetik URL, atau menunduk melihat HP, WAJIB tutup layar dengan B-roll yang sesuai dengan langkah yang diucapkan (85%-95% durasi bagian tutorial).
   - Atur `startFrom` dan `endAt` pada tiap B-roll agar menampilkan momen yang tepat (jangan selalu mulai dari detik 0, dan jangan pernah melebihi durasi asli file B-roll).
   - Gunakan transisi masuk dinamis (RGB glitch, light-leak, atau zoom-in halus) dan pastikan tulisan di layar HP tetap tajam & terbaca.

3. FRAMING WAJAH TETAP TERKUNCI DI TENGAH:
   - Pada A-roll, selalu gunakan `objectFit: 'cover'`, `objectPosition: 'center center'`, dan `transformOrigin: '50% 34%'` saat melakukan punch-in zoom (`1.0` <-> `1.12`) agar wajah pembicara tidak bergeser ke pinggir layar.
   - Tambahkan efek `blur-in` halus pada 8 frame pertama pembuka video.

4. ASET GRAFIS KONTEKSTUAL (CALLOUT CARDS & BADGES):
   - Saat pembicara mengajak follow/subscribe -> tampilkan badge pop-up dengan ikon centang merah + teks ajakan.
   - Saat menyebut unduh/download aplikasi -> tampilkan badge Google Play & App Store.
   - Saat menyebut alamat website/URL/link -> tampilkan kartu URL gelap bergaya monospace hijau neon (`#39FF14`) dengan alamat URL yang akurat (misal `ip-tv.app/indonesia`, `iptv.llc`).

5. SUBTITLE TEBAL ALL-CAPS GAYA KREATOR:
   - Tampilkan 2-4 kata per baris di zona aman bawah (`bottom: 440`), huruf `UPPERCASE`, font `'Geist', system-ui, sans-serif` weight `900`, ukuran `68px-76px`, warna putih `#FFFFFF` dengan sorotan kata kunci penting berwarna hijau neon `#39FF14` atau merah `#FF3B30`, `paintOrder: 'stroke fill'`, `WebkitTextStroke: '7px #000000'`, dan drop-shadow hitam pekat.
   - Perbaiki seluruh typo transkrip bahasa Indonesia (misal "walaulah" -> "BOLEHLAH", "undur" -> "UNDUH", "cerian" -> "CARANYA").

6. AUDIO LENGKAP (SFX + BGM AUTO-DUCKING):
   - Pasang SFX (`sfx/whoosh.wav`, `sfx/pop.wav`, `sfx/impact.wav`) di setiap transisi cut, B-roll masuk, dan kemunculan kartu callout.
   - Jika file `sfx/bgm.wav` tersedia di daftar aset public, putar sebagai musik latar sepanjang video (`loop`) dengan volume rendah (`0.09`) agar tempo video terasa hidup.

7. ATURAN TEKNIS REMOTION (SANGAT PENTING):
   - Ekspor komponen bernama `AutoTalkingHead`:
     `export const AutoTalkingHead: React.FC<{ timeline: TimelineData }> = ({ timeline }) => { ... }`
   - Import `TimelineData` dari `'./types'` dan import `'./fonts'`.
   - Gunakan `staticFile("nama_file.mp4")` HANYA untuk nama file yang ada di daftar `PUBLIC_ASSETS` yang diberikan.
   - Pastikan semua kalkulasi `startFrom`, `endAt`, dan `durationInFrames` berupa bilangan bulat (`Math.round(...)`) dan `durationInFrames >= 1`.

FORMAT BALASAN WAJIB:
Balas dengan dua blok berurutan persis seperti ini:
1) Blok JSON metadata:
```json
{
  "durationInFrames": 1650,
  "editSummary": "Ringkasan singkat potongan dan B-roll yang dipasang"
}
