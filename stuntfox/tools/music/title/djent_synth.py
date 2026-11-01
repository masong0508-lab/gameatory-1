"""Djent / nu-metal instruments for the title-song sketch (additions to synth.py, same conventions).

Everything is synthesised from scratch, deterministic, at dsp.RATE. Payback's own samples are only
ever passed in as arrays (read from $PAYBACK_ROM at run time by the remix script).

    palm_mute_guitar   Karplus-free saw/square guitar: gate, two-stage distortion, cabinet EQ (mono)
    power_chord_guitar root + fifth + octave, double-tracked L/R (stereo)
    clean_guitar       additive plucked guitar with chorus-style detune between the channels (stereo)
    dist_sub           distorted sub bass (mono)
    scratch            a ROM sample with a time-varying resample ratio and a crossfader gate (mono)
    gang_shout         formant-noise shout, several voices (stereo)
    rom_hit / rom_pad / rom_riser   clean playback of ROM samples
"""
import math

import numpy as np
from scipy import signal

import dsp
from dsp import RATE
import synth

NATIVE = 3546894.6 / 428.0          # pbsong.PAL_CLOCK / NATIVE_PERIOD: a sample's own rate (8287 Hz)


def _n(dur):
    return max(1, int(round(dur * RATE)))


def _end_fade(x, ms=4.0):
    return synth._end_fade(x, ms)


def _norm(x, vel):
    return synth._norm(x, vel)


def _sos(kind, f, order=2):
    return signal.butter(order, f, kind, fs=RATE, output='sos')


def cab(x):
    """A 4x12-ish cabinet: low cut, upper-mid presence, steep high cut."""
    x = signal.sosfilt(_sos('highpass', 80, 2), x, axis=0)
    x = dsp.eq(x, [('peak', 220, 2.0, 0.9), ('peak', 750, -3.0, 1.0), ('peak', 2400, 5.5, 0.9), ('peak', 4000, 2.0, 1.0)])
    return signal.sosfilt(_sos('lowpass', 5200, 4), x, axis=0)


# ---------------------------------------------------------------- guitars

def palm_mute_guitar(freq, dur, vel=1.0, take=0, mute=0.75, drive=8.0, bright=1.0, notch_db=14.0, rate=RATE):
    """A palm-muted chug: detuned saw + pulse, a body path (low-passed, mildly driven) and a tight
    path (high-passed before the distortion, the way a boost pedal tightens a 7/8-string), gate
    with a fast mute, pick click, cabinet. `take` 0/1 are two different performances."""
    n = _n(dur + 0.05)
    t = np.arange(n) / RATE
    det = (-1, 1)[take % 2] * 0.0009
    # the saw's discontinuity (the 'clank' of the driven edge) is put at t = 0: a note at 41 Hz would
    # otherwise start its edge up to 24 ms late and the chug would feel behind the grid
    x = 0.65 * dsp.saw(freq * (1 + det), n, phase0=0.985 - 0.01 * take) + 0.5 * dsp.square(
        freq * (1 - det) * 0.5, n, pw=0.42, phase0=0.0)
    # tight path: high-passed, then driven hard (upper-mid clank)
    cut = (1500.0 + 3800.0 * bright * np.exp(-t / 0.035)) * (1.2 - 0.4 * mute)
    xt = dsp.highpass(dsp.highpass(x, 380), 380)
    xt = dsp.lowpass(xt, cut, 0.9, block=32)
    xt = dsp.saturate(xt * drive * 0.9, 1.0)
    xt = dsp.lowpass(xt, 4800, 0.8)
    xt = dsp.saturate(xt * 1.8, 1.0)
    # body path: low-passed, driven less (the fat low-mid)
    cutb = (300.0 + 900.0 * np.exp(-t / 0.03)) * (1.15 - 0.4 * mute)
    xb = dsp.saturate(dsp.lowpass(x, cutb, 0.8, block=32) * 2.2, 1.0)
    pick = dsp.highpass(dsp.noise(n, 700 + take), 2500) * np.exp(-t / 0.005) * 0.5
    y = 0.8 * xt + 0.75 * xb + pick
    # the 5th, 10th and 15th partials of a driven note are its major third: out of key in E minor. Notch them.
    nb = [('peak', freq * k, -notch_db, 6.0) for k in (5, 10, 15) if freq * k < 9000]
    if nb:
        y = dsp.eq(y, nb)
    env = np.minimum(1, t / 0.0015) * (0.40 + 0.60 * np.exp(-t / 0.055))
    rel = 0.012
    g = np.where(t < dur, 1.0, np.exp(-(t - dur) / rel))
    y = cab(y * env * g)
    return _end_fade(_norm(y, vel))


def power_chord_guitar(freq, dur, vel=1.0, mute=0.0, drive=5.0, release=0.14, rate=RATE):
    """Root + fifth + octave through two takes (left / right), each a different detune and phase.
    Each note is driven on its own (parallel amp channels), then summed: a fifth driven together
    with its root throws intermodulation products (A5 grows a G#) that are out of key."""
    n = _n(dur + 5 * release * (1 - 0.7 * mute) + 0.05)     # long enough for the release to die away
    t = np.arange(n) / RATE
    out = np.zeros((n, 2))
    for ch in (0, 1):
        det = (-1, 1)[ch] * 0.0018
        x = np.zeros(n)
        for k, (ratio, g) in enumerate(((1.0, 1.0), (2 ** (7 / 12), 0.9), (2.0, 0.8))):
            v = dsp.saw(freq * ratio * (1 + det * (1 + 0.35 * k)), n, phase0=0.985 - 0.012 * k - 0.01 * ch)
            cut = (1100.0 + 3600.0 * np.exp(-t / 0.05)) * (1.0 - 0.55 * mute)
            v = dsp.lowpass(v, cut, 0.8, block=32)
            v = dsp.saturate(v * drive * 0.45, 1.0)
            v = dsp.highpass(v, 70)
            x += g * dsp.saturate(dsp.lowpass(v, 4600, 0.8) * 1.2, 1.0)
        x = dsp.saturate(x * 0.45, 1.0)
        decay = 0.9 - 0.75 * mute
        env = np.minimum(1, t / 0.002) * (0.55 + 0.45 * np.exp(-t / decay))
        gate = np.where(t < dur, 1.0, np.exp(-(t - dur) / (release * (1 - 0.7 * mute))))
        y = cab(x * env * gate)
        d = int(0.0085 * RATE) * ch
        out[d:, ch] = y[:n - d]
    return _end_fade(_norm(out, vel))


def clean_guitar(freq, dur, vel=1.0, decay=1.3, bright=1.0, rate=RATE):
    """Plucked clean guitar: harmonics that die faster the higher they are, pick-position comb,
    a trace of stretch, +-5 cents between channels (chorus-like width)."""
    n = _n(dur + 0.7)
    t = np.arange(n) / RATE
    kmax = int(min(26, 9500 // max(freq, 20)))
    out = np.zeros((n, 2))
    for ch, cents in enumerate((-5.0, 5.0)):
        f0 = freq * 2 ** (cents / 1200)
        x = np.zeros(n)
        for k in range(1, kmax + 1):
            a = (1.0 / k ** 1.15) * abs(math.sin(math.pi * k * 0.17)) ** 0.6 * (bright if k > 3 else 1.0)
            tau = decay / (1 + 0.55 * k)
            fk = f0 * k * (1 + 0.00012 * k * k)
            x += a * np.sin(2 * np.pi * fk * t + 0.9 * k * ch) * np.exp(-t / tau)
        out[:, ch] = x
    out *= np.minimum(1, t / 0.0025)[:, None]
    out *= np.where(t < dur, 1.0, np.exp(-(t - dur) / 0.22))[:, None]
    out[:, 0] = dsp.highpass(out[:, 0], 90)
    out[:, 1] = dsp.highpass(out[:, 1], 90)
    return _end_fade(_norm(out, vel))


def dist_sub(freq, dur, vel=1.0, drive=2.4, release=0.035, harmonic=0.3, rate=RATE):
    """Sine sub with its 2nd and 3rd harmonics, driven so it still speaks on small speakers."""
    n = _n(dur + release)
    t = np.arange(n) / RATE
    ph = 2 * np.pi * freq * t
    x = np.sin(ph) + harmonic * np.sin(2 * ph + 0.4) + 0.12 * np.sin(3 * ph + 0.9)
    env = np.minimum(1, t / 0.003) * np.where(t < dur, 1.0, np.exp(-(t - dur) / (release * 0.4)))
    x = dsp.saturate(x * env, drive)
    x = signal.sosfilt(_sos('lowpass', 420, 2), x)
    return _end_fade(_norm(x, vel))


# ---------------------------------------------------------------- ROM samples (arrays in, audio out)

def _clean(x, lo=60.0, hi=9000.0):
    x = signal.sosfilt(_sos('highpass', lo, 2), x)
    return signal.sosfilt(_sos('lowpass', hi, 4), x)


def rom_hit(pcm, shift, dur, vel=1.0, start=0.0, hp=60.0, hi=9000.0, fade=0.006, loop_start=-1):
    """A ROM sample played once (or looped) at `shift` semitones from its native rate, cleaned."""
    n = _n(dur)
    ratio = NATIVE / RATE * 2 ** (shift / 12)
    y = dsp.play_sample(pcm, ratio, n, loop_start, start=start * NATIVE)
    k = min(n, _n(fade))
    y[:k] *= np.linspace(0, 1, k)
    y[-k:] *= np.linspace(1, 0, k)
    return _norm(_clean(y, hp, hi), vel)


def rom_pad(pcm, loop_start, shift, dur, vel=1.0, release=0.5, attack=0.03):
    """A looped ROM pad, two copies +-4 cents apart (left/right) so it has width; cleaned."""
    n = _n(dur + release)
    t = np.arange(n) / RATE
    out = np.zeros((n, 2))
    for ch, cents in enumerate((-4.0, 4.0)):
        ratio = NATIVE / RATE * 2 ** ((shift + cents / 100) / 12)
        y = dsp.play_sample(pcm, ratio, n, loop_start, start=0.0, interp='hermite')
        out[:, ch] = _clean(y, 70.0, 7500.0)
    env = np.minimum(1, t / attack) * np.where(t < dur, 1.0, np.exp(-(t - dur) / (release * 0.35)))
    out *= env[:, None]
    return _end_fade(_norm(out, vel))


def rom_riser(pcm, loop_start, dur, vel=1.0, s0=-14.0, s1=10.0):
    """Sample 21 as a riser: the resample ratio sweeps up, a high-pass opens, the level swells."""
    n = _n(dur)
    t = np.arange(n) / RATE
    semi = s0 + (s1 - s0) * (t / dur) ** 1.6
    ratio = NATIVE / RATE * 2 ** (semi / 12)
    y = dsp.play_sample(pcm, ratio, n, loop_start)
    y = _clean(y, 200.0, 9000.0)
    y = dsp.highpass(y, 250 + 4200 * (t / dur) ** 2, 0.9, block=64)
    y *= (t / dur) ** 1.8
    return _end_fade(_norm(y, vel), 10.0)


def scratch(pcm, shift, dur, vel=1.0, bend=(0.0, 0.0), gate=None, baby=0.0, start=0.0, hp=550.0, drive=1.6,
            curve=1.4):
    """Scratch-style stab: the resample ratio is time-varying (a pitch bend, and with baby > 0 a
    forward/back wobble of the record), then a crossfader gate chops it.

    bend: (start, end) extra semitones, shaped by t**curve.  baby: wobble depth, as a share of the
    forward speed (the position oscillates but never leaves the sample).  gate: list of (on, off)
    seconds from the start of the note, or None for open."""
    n = _n(dur)
    t = np.arange(n) / RATE
    semi = shift + bend[0] + (bend[1] - bend[0]) * (t / dur) ** curve
    r = NATIVE / RATE * 2 ** (semi / 12)
    if baby:
        r = r * (1.0 + baby * 3.0 * np.cos(2 * np.pi * (2.2 / dur) * t * 1.0))
    pos = np.concatenate([[0.0], np.cumsum(r[:-1])])
    st = start * NATIVE + max(0.0, -pos.min())
    y = dsp.play_sample(pcm, r, n, -1, start=st)
    if gate:
        g = np.zeros(n)
        for a, b in gate:
            g[_n(a):min(n, _n(b))] = 1.0
        k = int(0.004 * RATE) | 1
        g = np.convolve(g, np.hanning(k) / np.hanning(k).sum(), mode='same')
    else:
        g = np.ones(n)
    k = min(n, _n(0.003))
    g[:k] *= np.linspace(0, 1, k)
    g[-_n(0.01):] *= np.linspace(1, 0, _n(0.01))
    y = _clean(y * g, hp, 9500.0)
    y = dsp.saturate(y * 1.0, drive)
    return _norm(y, vel)


# ---------------------------------------------------------------- voices

_VOW = {'ey': ((530, 1840, 2480), (270, 2290, 3010)), 'oh': ((570, 840, 2410), (450, 800, 2830)),
        'hey2': ((660, 1720, 2410), (300, 2200, 2900))}


def gang_shout(dur=0.24, vel=1.0, vowel='ey', voices=5, f0=150.0, seed=40):
    """A rhythmic gang shout: for each of several voices a falling-pitch glottal saw plus breath
    noise goes through three formants that glide between two vowels, is driven, high-passed and
    offset by a few ms; the voices are spread across the stereo field (stereo)."""
    n = _n(dur + 0.08)
    t = np.arange(n) / RATE
    fa, fb = _VOW[vowel]
    w = np.clip(t / (dur * 0.8), 0, 1)
    out = np.zeros((n, 2))
    for v in range(voices):
        rng = np.random.default_rng(seed + v)
        f = f0 * (1 + 0.16 * (v - (voices - 1) / 2) / max(1, voices - 1)) * (1 - 0.22 * (t / dur))
        f = f * (1 + 0.004 * np.cumsum(rng.standard_normal(n)) / 80.0)
        src = dsp.saw(f, n, phase0=float(rng.uniform())) + 0.55 * dsp.noise(n, seed + 10 + v) * 3
        y = np.zeros(n)
        for i, g in enumerate((1.0, 0.8, 0.4)):
            fc = (fa[i] * (1 - w) + fb[i] * w) * (1 + 0.04 * (v - 2) / 2)
            y += g * dsp.bandpass(src, fc, 5.0 + 2 * i, block=64)
        y = dsp.saturate(y * 1.2, 2.0)
        d = int(0.0035 * v * RATE)
        y = np.concatenate([np.zeros(d), y[:n - d]])
        out += dsp.pan(y, -0.8 + 1.6 * v / max(1, voices - 1))
    env = np.minimum(1, t / 0.006) * np.where(t < dur, 1.0, np.exp(-(t - dur) / 0.03))
    out = dsp.highpass(out * env[:, None], 280)
    return _end_fade(_norm(out, vel))
