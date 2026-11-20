import os
import math
import wave
import struct
import random

SAMPLE_RATE = 44100

def write_wav(path, samples):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            clamped = max(-32767, min(32767, int(s * 32767)))
            frames.extend(struct.pack("<h", clamped))
        wf.writeframes(frames)

def make_whoosh(duration=0.35):
    total = int(SAMPLE_RATE * duration)
    samples = []
    lp = 0.0
    random.seed(42)
    for i in range(total):
        t = i / total
        env = math.sin(math.pi * t) ** 2
        alpha = 0.05 + 0.35 * math.sin(math.pi * t)
        noise = random.uniform(-1.0, 1.0)
        lp = lp + alpha * (noise - lp)
        samples.append(lp * env * 0.85)
    return samples

def make_pop(duration=0.085):
    total = int(SAMPLE_RATE * duration)
    samples = []
    phase = 0.0
    for i in range(total):
        t = i / total
        freq = 540.0 * ((180.0 / 540.0) ** t)
        env = ((1.0 - t) ** 2.2) * min(1.0, i / 40.0)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        samples.append(math.sin(phase) * env * 0.9)
    return samples

def make_impact(duration=0.45):
    total = int(SAMPLE_RATE * duration)
    samples = []
    phase = 0.0
    for i in range(total):
        t = i / total
        freq = 115.0 * ((36.0 / 115.0) ** (t ** 0.7))
        env = ((1.0 - t) ** 1.8) * min(1.0, i / 60.0)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        val = (math.sin(phase) + 0.25 * math.sin(phase * 2.0)) * env * 0.9
        samples.append(val)
    return samples

def main():
    out_dir = "remotion/public/sfx"
    write_wav(f"{out_dir}/whoosh.wav", make_whoosh())
    write_wav(f"{out_dir}/pop.wav", make_pop())
    write_wav(f"{out_dir}/impact.wav", make_impact())
    print("[SUKSES] Efek suara prosedural (whoosh, pop, impact) berhasil dibuat.")

if __name__ == "__main__":
    main()
