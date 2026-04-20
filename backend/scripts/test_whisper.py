"""Sanity-check faster-whisper. Generates a short silent WAV (with spoken phrase via TTS
substitute = just a 1s sine), transcribes it, reports timing. We do NOT need it to be
intelligible — we want proof the model loads, runs, and returns without error.
"""
from __future__ import annotations

import math
import struct
import sys
import time
import wave
from pathlib import Path


def synth_silence(path: Path, seconds: float = 1.0, sr: int = 16000):
    """Write a short mostly-silent wav so faster-whisper has input to process."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = []
        for n in range(int(sr * seconds)):
            # faint sine so Whisper doesn't skip entirely on pure silence
            v = int(400 * math.sin(2 * math.pi * 440 * n / sr))
            frames.append(struct.pack("<h", v))
        w.writeframes(b"".join(frames))


def main():
    from faster_whisper import WhisperModel
    out = Path("/tmp/whisper_test.wav")
    synth_silence(out, seconds=1.5)

    t0 = time.perf_counter()
    # 'small' per the spec. int8 so CPU is fast.
    model = WhisperModel("small", device="cpu", compute_type="int8")
    load = time.perf_counter() - t0
    print(f"[load]   {load:.1f}s")

    t1 = time.perf_counter()
    segments, info = model.transcribe(str(out), language="fr", beam_size=1)
    segs = list(segments)
    infer = time.perf_counter() - t1
    print(f"[infer]  {infer:.2f}s, lang={info.language} prob={info.language_probability:.2f}")
    for s in segs:
        print(f"  [{s.start:.1f}-{s.end:.1f}s] {s.text!r}")
    print("OK" if info else "FAIL")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        sys.exit(1)
