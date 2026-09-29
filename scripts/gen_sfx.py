#!/usr/bin/env python3
"""Synthesize the pipeline's SFX from scratch (no samples, zero licensing).

- shutter.wav: camera-shutter double-click — two short filtered-noise
  bursts ~180ms apart (mirror-up / mirror-down), like the reference video
  Lawal flagged (2026-09-27). Played on portrait reveals and map pin drops.
- click.wav: single short click for select scene transitions.
- boom.wav: deep cinematic boom for dramatic beats (low sine pitch-drop
  + noise thump, ~1.4s).
- riser.wav: 2s rising tension sweep (pitch + brightness swell) for
  pre-reveal / pre-stat tension.
- stinger.wav: short dramatic hit (metallic burst + low thump, ~0.7s)
  for overlay card pops and stat reveals.

Run: python3 scripts/gen_sfx.py   (writes public/sfx/*.wav)
"""
import numpy as np
import os

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "public", "sfx")


def burst(dur_ms: float, cutoff: float, decay_ms: float, gain: float = 1.0) -> np.ndarray:
    """One filtered-noise click: white noise -> one-pole lowpass -> exp decay."""
    n = int(SR * dur_ms / 1000)
    noise = np.random.default_rng(0).standard_normal(n)
    # one-pole lowpass; cutoff in Hz
    alpha = 1.0 - np.exp(-2.0 * np.pi * cutoff / SR)
    y = np.zeros(n)
    acc = 0.0
    for i in range(n):
        acc += alpha * (noise[i] - acc)
        y[i] = acc
    t = np.arange(n) / SR * 1000.0
    env = np.exp(-t / decay_ms)
    # sharp attack: first 2ms ramp
    attack = min(int(SR * 0.002), n)
    env[:attack] *= np.linspace(0, 1, attack)
    return (y * env * gain).astype(np.float64)


def write_wav(path: str, sig: np.ndarray) -> None:
    sig = sig / max(1e-9, np.abs(sig).max()) * 0.9
    pcm = (sig * 32767).astype(np.int16)
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"wrote {path} ({len(sig) / SR:.2f}s)")


def sine_sweep(f0: float, f1: float, dur_s: float, seed: int = 0) -> np.ndarray:
    """Sine with exponential pitch glide f0 -> f1 over dur_s."""
    n = int(SR * dur_s)
    t = np.arange(n) / SR
    # exponential glide: instantaneous freq f(t) = f0 * (f1/f0)^(t/dur)
    k = np.log(f1 / f0) / dur_s
    phase = 2 * np.pi * f0 * (np.exp(k * t) - 1) / k
    return np.sin(phase)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)

    # camera shutter: bright snap, 180ms gap, slightly duller second snap
    s1 = burst(70, cutoff=6500, decay_ms=9, gain=1.0)
    gap = np.zeros(int(SR * 0.18))
    s2 = burst(70, cutoff=4200, decay_ms=11, gain=0.85)
    shutter = np.concatenate([s1, gap, s2])
    write_wav(os.path.join(OUT, "shutter.wav"), shutter)

    # single UI click for transitions: short, tight, mid-bright
    click = burst(45, cutoff=5200, decay_ms=7, gain=1.0)
    write_wav(os.path.join(OUT, "click.wav"), click)

    # deep cinematic boom: pitch-dropping low sine + noise thump
    rng = np.random.default_rng(7)
    bd = 1.4
    n = int(SR * bd)
    t = np.arange(n) / SR
    body = sine_sweep(70, 32, bd) * np.exp(-t / 0.55)
    thump = rng.standard_normal(n)
    alpha = 1.0 - np.exp(-2.0 * np.pi * 220 / SR)
    acc = 0.0
    lp = np.zeros(n)
    for i in range(n):
        acc += alpha * (thump[i] - acc)
        lp[i] = acc
    thump = lp * np.exp(-t / 0.18) * 0.8
    boom = body * 1.0 + thump
    write_wav(os.path.join(OUT, "boom.wav"), boom)

    # riser: 2s swell — rising sine + noise that gets brighter
    rd = 2.0
    n = int(SR * rd)
    t = np.arange(n) / SR
    cresc = (1 - np.exp(-t / 0.7)) ** 2  # swell envelope
    tone = sine_sweep(180, 1400, rd) * cresc * 0.5
    noise = np.random.default_rng(11).standard_normal(n)
    # time-varying brightness: cutoff sweeps 400 -> 6000 Hz
    y = np.zeros(n)
    acc = 0.0
    for i in range(n):
        frac = i / n
        cutoff = 400 * (6000 / 400) ** frac
        a = 1.0 - np.exp(-2.0 * np.pi * cutoff / SR)
        acc += a * (noise[i] - acc)
        y[i] = acc
    riser = (tone + y * cresc * 0.6)
    # short fade at the very end so it can cut into a hit cleanly
    fade = min(int(SR * 0.03), n)
    riser[-fade:] *= np.linspace(1, 0, fade)
    write_wav(os.path.join(OUT, "riser.wav"), riser)

    # stinger: metallic burst + low thump for card pops / stat reveals
    sd = 0.7
    n = int(SR * sd)
    t = np.arange(n) / SR
    metallic = (np.sin(2 * np.pi * 820 * t)
                + 0.6 * np.sin(2 * np.pi * 1290 * t)
                + 0.4 * np.sin(2 * np.pi * 1930 * t))
    metallic *= np.exp(-t / 0.09)
    hit = sine_sweep(110, 48, sd) * np.exp(-t / 0.22) * 0.9
    stinger = metallic * 0.5 + hit
    write_wav(os.path.join(OUT, "stinger.wav"), stinger)


if __name__ == "__main__":
    main()
