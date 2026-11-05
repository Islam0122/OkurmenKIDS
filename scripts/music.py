"""Upbeat background music for the demo video — synthesised from scratch.

No samples, no downloads and no AI: plain DSP with numpy/scipy. 112 BPM,
C–G–Am–F (the «corporate promo» progression): a soft pad, plucked
arpeggios (Karplus–Strong strings), bass, a soft kick, shaker and claps.
A quiet two-bar intro, then the full groove, and the last chord rings out.

    python scripts/music.py 65 out.wav
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, lfilter

SR = 44_100
BPM = 112
BEAT = 60 / BPM
BAR = 4 * BEAT

# Chords as MIDI notes (pad voicing) and their bass roots.
PROGRESSION = [
    ([60, 64, 67, 71], 36),  # Cmaj7
    ([59, 62, 67, 74], 43),  # G/B add9-ish
    ([57, 60, 64, 69], 45),  # Am
    ([57, 60, 65, 69], 41),  # F
]


def hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def _lowpass(x, cutoff, order=2):
    b, a = butter(order, cutoff / (SR / 2), btype="low")
    return lfilter(b, a, x)


def _bandpass(x, low, high, order=2):
    b, a = butter(order, [low / (SR / 2), high / (SR / 2)], btype="band")
    return lfilter(b, a, x)


def _env(n, attack, release):
    env = np.ones(n)
    a, r = max(1, int(attack * SR)), max(1, int(release * SR))
    env[:a] = np.linspace(0, 1, a)
    env[-r:] *= np.linspace(1, 0, r)
    return env


def _pad_note(freq, seconds, rng):
    t = np.arange(int(seconds * SR)) / SR
    wave = np.zeros_like(t)
    for detune in (-0.07, 0.0, 0.07):  # three slightly detuned voices = width
        f = freq * 2 ** (detune / 12)
        phase = rng.uniform(0, 2 * np.pi)
        for k in range(1, 7):  # soft saw: a few harmonics at 1/k
            wave += np.sin(2 * np.pi * f * k * t + phase * k) / k
    return _lowpass(wave, 1800) * _env(t.size, 0.35, 0.6) / 9


def _pluck(freq, seconds, rng, brightness=0.996):
    """Karplus–Strong plucked string."""
    n = int(seconds * SR)
    period = max(2, int(SR / freq))
    buf = rng.uniform(-1, 1, period)
    out = np.empty(n)
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = brightness * 0.5 * (buf[i % period] + buf[(i + 1) % period])
    return _lowpass(out, 5200) * _env(n, 0.002, 0.08)


def _kick(seconds=0.32):
    t = np.arange(int(seconds * SR)) / SR
    freq = 45 + 75 * np.exp(-t * 28)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * np.exp(-t * 11)


def _noise_hit(seconds, low, high, decay, rng):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    return _bandpass(rng.uniform(-1, 1, n), low, high) * np.exp(-t * decay)


def _bass(freq, seconds):
    t = np.arange(int(seconds * SR)) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t)
    return _lowpass(tone, 400) * _env(t.size, 0.01, 0.12) * np.exp(-t * 1.6)


def render(duration: float, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int((duration + 3) * SR)
    left, right = np.zeros(n), np.zeros(n)

    def add(signal, start, gain=1.0, pan=0.0):
        i = int(start * SR)
        if i >= n:
            return
        part = signal[: n - i] * gain
        left[i:i + part.size] += part * np.sqrt((1 - pan) / 2) * 1.41
        right[i:i + part.size] += part * np.sqrt((1 + pan) / 2) * 1.41

    bars = int(np.ceil(duration / BAR))
    intro_bars = 2
    outro_at = duration - 2.6
    for bar in range(bars):
        start = bar * BAR
        if start >= outro_at:
            break
        chord, root = PROGRESSION[bar % len(PROGRESSION)]
        full = bar >= intro_bars
        for note in chord:
            add(_pad_note(hz(note), BAR + 0.5, rng), start, 0.55)
        # Arpeggio in 8ths, an octave up, alternating sides.
        pattern = [0, 1, 2, 3, 2, 1, 2, 3]
        for step, idx in enumerate(pattern):
            at = start + step * BEAT / 2
            if at >= outro_at:
                break
            add(_pluck(hz(chord[idx] + 12), 0.55, rng), at, 0.32 if full else 0.24, pan=-0.35 if step % 2 else 0.35)
        if not full:
            continue
        for beat in range(4):
            at = start + beat * BEAT
            if at >= outro_at:
                break
            add(_kick(), at, 0.55)
            if beat in (1, 3):
                add(_noise_hit(0.18, 900, 4000, 22, rng), at, 0.16)
            add(_noise_hit(0.06, 6000, 14000, 60, rng), at + BEAT / 2, 0.10, pan=0.25)
        for at in (start, start + 2 * BEAT, start + 3.5 * BEAT):
            if at < outro_at:
                add(_bass(hz(root), BEAT * 1.4), at, 0.42)

    # Final chord rings out.
    chord, root = PROGRESSION[0]
    for note in chord + [chord[0] + 12]:
        add(_pad_note(hz(note), 3.2, rng), outro_at, 0.6)
        add(_pluck(hz(note + 12), 2.6, rng, brightness=0.998), outro_at + 0.02 * chord.index(note) if note in chord else outro_at, 0.3)
    add(_bass(hz(root), 2.5), outro_at, 0.45)

    stereo = np.stack([left, right], axis=1)[: int(duration * SR)]
    fade_in, fade_out = int(0.6 * SR), int(1.2 * SR)
    stereo[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    stereo[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return (stereo / (np.abs(stereo).max() + 1e-9) * 0.8).astype(np.float32)


def write(duration: float, path: Path) -> Path:
    import soundfile as sf

    sf.write(path, render(duration), SR)
    return path


if __name__ == "__main__":
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 65
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("music.wav")
    print(write(seconds, target))
