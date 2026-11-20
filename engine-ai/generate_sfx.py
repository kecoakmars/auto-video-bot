import os
import math
import wave
import struct
import random

SAMPLE_RATE = 44100


def write_wav(filepath, samples):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with wave.open(filepath, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            frames.extend(struct.pack("<h", int(clamped * 32767)))
        wf.writeframes(bytes(frames))


def generate_whoosh(duration=0.35):
    n = int(SAMPLE_RATE * duration)
    rng = random.Random(42)
    raw = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    out = []
    lp = 0.0
    for i in range(n):
        t = i / n
        env = math.sin(math.pi * t) ** 1.6
        alpha = 0.04 + 0.22 * math.sin(math.pi * t)
        lp = lp + alpha * (raw[i] - lp)
        tone = 0.15 * math.sin(2 * math.pi * (140 + 260 * t) * (i / SAMPLE_RATE))
        out.append((lp * 1.4 + tone) * env * 0.65)
    return out


def generate_pop(duration=0.12):
    n = int(SAMPLE_RATE * duration)
    out = []
    phase = 0.0
    for i in range(n):
        norm = i / n
        freq = 560.0 * ((0.32) ** norm)
        phase += 2 * math.pi * freq / SAMPLE_RATE
        env = math.exp(-norm * 6.5) * min(1.0, i / (SAMPLE_RATE * 0.005))
        out.append(math.sin(phase) * env * 0.75)
    return out


def generate_impact(duration=0.55):
    n = int(SAMPLE_RATE * duration)
    rng = random.Random(99)
    out = []
    phase = 0.0
    for i in range(n):
        norm = i / n
        freq = 115.0 * ((0.33) ** (norm ** 0.7))
        phase += 2 * math.pi * freq / SAMPLE_RATE
        sub = math.sin(phase) * math.exp(-norm * 4.5)
        punch_noise = rng.uniform(-1.0, 1.0) * math.exp(-norm * 24.0) * 0.45
        env = min(1.0, i / (SAMPLE_RATE * 0.004))
        out.append((sub + punch_noise) * env * 0.85)
    return out


def generate_tap(duration=0.07):
    n = int(SAMPLE_RATE * duration)
    rng = random.Random(7)
    out = []
    for i in range(n):
        norm = i / n
        env = math.exp(-norm * 14.0) * min(1.0, i / (SAMPLE_RATE * 0.002))
        sig = 0.6 * math.sin(2 * math.pi * 920.0 * (i / SAMPLE_RATE)) + 0.4 * rng.uniform(-1.0, 1.0)
        out.append(sig * env * 0.55)
    return out


def generate_tick(duration=0.045):
    n = int(SAMPLE_RATE * duration)
    rng = random.Random(13)
    out = []
    for i in range(n):
        norm = i / n
        env = math.exp(-norm * 18.0)
        sig = 0.5 * math.sin(2 * math.pi * 1450.0 * (i / SAMPLE_RATE)) + 0.5 * rng.uniform(-1.0, 1.0)
        out.append(sig * env * 0.45)
    return out


def generate_thud(duration=0.32):
    n = int(SAMPLE_RATE * duration)
    out = []
    phase = 0.0
    for i in range(n):
        norm = i / n
        freq = 92.0 * ((0.45) ** norm)
        phase += 2 * math.pi * freq / SAMPLE_RATE
        env = math.exp(-norm * 6.0) * min(1.0, i / (SAMPLE_RATE * 0.005))
        out.append(math.sin(phase) * env * 0.8)
    return out


def generate_bgm_loop(duration=8.0):
    """Membangkitkan loop musik latar lo-fi/tech beat lembut 120 BPM (4 bar)."""
    n = int(SAMPLE_RATE * duration)
    bpm = 120.0
    beat_sec = 60.0 / bpm
    rng = random.Random(2026)

    chords = [
        [130.81, 155.56, 196.00, 233.08],  # Cm7
        [130.81, 155.56, 196.00, 233.08],  # Cm7
        [174.61, 207.65, 261.63, 311.13],  # Fm7
        [174.61, 207.65, 261.63, 311.13],  # Fm7
    ]

    out = []
    lp = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        bar_idx = int(t / (beat_sec * 4)) % 4
        beat_pos = (t % beat_sec) / beat_sec
        eighth_pos = (t % (beat_sec * 0.5)) / (beat_sec * 0.5)
        beat_in_bar = int(t / beat_sec) % 4

        pad = 0.0
        for f in chords[bar_idx]:
            pad += math.sin(2 * math.pi * f * t)
        pad = (pad / len(chords[bar_idx])) * 0.22

        kick = 0.0
        if beat_in_bar in (0, 2) and beat_pos < 0.35:
            k_norm = beat_pos / 0.35
            k_freq = 95.0 * ((0.42) ** k_norm)
            kick = math.sin(2 * math.pi * k_freq * (beat_pos * beat_sec)) * math.exp(-k_norm * 7.0) * 0.32

        hat_noise = rng.uniform(-1.0, 1.0)
        lp = lp + 0.35 * (hat_noise - lp)
        hat = (hat_noise - lp) * math.exp(-eighth_pos * 16.0) * 0.09

        loop_fade = 1.0
        fade_samples = int(SAMPLE_RATE * 0.05)
        if i < fade_samples:
            loop_fade = i / fade_samples
        elif i > n - fade_samples:
            loop_fade = (n - i) / fade_samples

        out.append((pad + kick + hat) * loop_fade)
    return out


def main():
    sfx_dir = "remotion/public/sfx"
    files = {
        "whoosh.wav": generate_whoosh(),
        "pop.wav": generate_pop(),
        "impact.wav": generate_impact(),
        "tap.wav": generate_tap(),
        "tick.wav": generate_tick(),
        "thud.wav": generate_thud(),
        "bgm.wav": generate_bgm_loop(),
    }
    for name, data in files.items():
        path = os.path.join(sfx_dir, name)
        write_wav(path, data)
        print(f"[SFX] Berhasil dibuat: {path}")


if __name__ == "__main__":
    main()
