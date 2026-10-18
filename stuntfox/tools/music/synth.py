"""Our own instruments, synthesised from scratch (no samples from anywhere), deterministic.

Every instrument is a function returning float audio at dsp.RATE: mono (n,) or, for wide
sounds, stereo (n, 2). Pitched ones take (freq, dur, vel, ...), drums take (dur, vel, ...) and
also accept freq (used as the tuning where it makes sense, else ignored). The returned audio
may run past `dur` by the release tail. Peaks are about `vel` (0..1).

    from synth import *
    k = kick()                                   # one kick, array
    lead = Inst(saw_lead, detune=0.12)           # a playable instrument: lead(freq, dur, vel)
    mix.Track.note(...) takes Inst objects (or any callable inst(freq, dur, vel)).

Drums: kick snare clap hat (closed/open) cymbal (crash/ride) tom rim
Bass:  sub_bass reese acid
Leads: saw_lead square_lead pluck arp fm_bell
Pads:  supersaw (chords, stereo) warm_pad
FX:    riser downlifter impact reverse_cymbal noise_sweep
"""
import math

import numpy as np

import dsp
from dsp import RATE


def _n(dur, rate=RATE):
    return max(1, int(round(dur * rate)))


def _end_fade(x, ms=4.0, rate=RATE):
    k = min(len(x), int(ms * rate / 1000))
    if k > 1:
        g = np.linspace(1, 0, k)
        x[-k:] *= g if x.ndim == 1 else g[:, None]
    return x


def _norm(x, vel):
    pk = np.max(np.abs(x)) or 1.0
    return x * (vel / pk)


# ---------------------------------------------------------------- drums

def kick(dur=0.45, vel=1.0, freq=None, f_start=170.0, f_end=48.0, pitch_time=0.04, decay=0.4,
         click=0.25, drive=1.8, rate=RATE, seed=11):
    """Sine kick with a pitch drop, click and saturation. freq tunes the body (f_end)."""
    if freq:
        f_end = freq
    n = _n(dur, rate)
    t = np.arange(n) / rate
    f = f_end + (f_start - f_end) * np.exp(-t / pitch_time)
    body = np.sin(2 * np.pi * np.cumsum(f) / rate)
    env = np.exp(-6.9 * t / decay) * np.minimum(1, t / 0.0015 + 0.3)
    x = body * env
    if click:
        cn = dsp.highpass(dsp.noise(n, seed), 1800, rate=rate) * np.exp(-t / 0.0025)
        x += click * cn * 3 + click * 0.5 * np.sin(2 * np.pi * 1500 * t) * np.exp(-t / 0.0015)
    x = dsp.saturate(x, drive)
    return _end_fade(_norm(x, vel), rate=rate)


def snare(dur=0.32, vel=1.0, freq=None, tone=190.0, tone_decay=0.1, noise_decay=0.2, snap=0.7,
          bright=3200.0, rate=RATE, seed=12):
    """Two-mode body plus band-limited noise snap."""
    if freq:
        tone = freq
    n = _n(dur, rate)
    t = np.arange(n) / rate
    f1 = tone * (1 + 0.25 * np.exp(-t / 0.01))
    body = (np.sin(2 * np.pi * np.cumsum(f1) / rate) + 0.5 * np.sin(2 * np.pi * np.cumsum(f1 * 1.72) / rate))
    body *= np.exp(-6.9 * t / tone_decay)
    nz = dsp.noise(n, seed)
    nz = dsp.lowpass(dsp.bandpass(nz, bright, 0.9, rate=rate) + 0.2 * dsp.highpass(nz, 1500, rate=rate), 10000, rate=rate)
    nz *= np.exp(-6.9 * t / noise_decay) * np.minimum(1, t / 0.001)
    x = (1 - snap) * body * 1.3 + snap * nz * 3
    x = dsp.saturate(x, 1.2)
    return _end_fade(_norm(x, vel), rate=rate)


def clap(dur=0.4, vel=1.0, freq=None, tone=1150.0, tail=0.22, rate=RATE, seed=13):
    """Four quick noise bursts and a short tail, band-passed."""
    if freq:
        tone = freq
    n = _n(dur, rate)
    t = np.arange(n) / rate
    env = np.zeros(n)
    for k, dt in enumerate((0.0, 0.009, 0.018, 0.029)):
        m = t >= dt
        env[m] = np.maximum(env[m], (0.8 if k < 3 else 1.0) * np.exp(-(t[m] - dt) / 0.0045))
    m = t >= 0.029
    env[m] = np.maximum(env[m], np.exp(-6.9 * (t[m] - 0.029) / tail))
    nz = dsp.noise(n, seed)
    x = dsp.bandpass(nz, tone, 1.4, rate=rate) * env + 0.06 * dsp.lowpass(dsp.highpass(nz, 2500, rate=rate), 8000, rate=rate) * env
    return _end_fade(_norm(x, vel), rate=rate)


_METAL = np.array([205.3, 304.4, 369.6, 522.7, 540.0, 800.0])


def _metal(n, scale=1.0, rate=RATE):
    y = np.zeros(n)
    for k, f in enumerate(_METAL * scale):
        y += dsp.square(f, n, rate, phase0=0.13 * k)
    return y / len(_METAL)


def hat(dur=None, vel=1.0, freq=None, open=False, decay=None, tone=1.0, rate=RATE, seed=14):
    """808-style hat: six detuned squares plus noise, high-passed. open=True rings longer."""
    decay = decay or (0.32 if open else 0.045)
    dur = dur or decay * 1.6
    n = _n(dur, rate)
    t = np.arange(n) / rate
    m = _metal(n, tone * (freq / 1000.0 if freq else 1.0), rate)
    nz = dsp.noise(n, seed)
    x = 0.7 * dsp.bandpass(m, 10000, 1.0, rate=rate) + 0.5 * dsp.highpass(nz, 8000, rate=rate)
    x = dsp.highpass(x, 6500, rate=rate)
    x *= np.exp(-6.9 * t / decay) * np.minimum(1, t / 0.0008)
    return _end_fade(_norm(x, vel), rate=rate)


def cymbal(dur=2.6, vel=1.0, freq=None, kind='crash', rate=RATE, seed=15):
    """Crash (wash) or ride (ping + wash): inharmonic partials plus noise; stereo."""
    n = _n(dur, rate)
    t = np.arange(n) / rate
    rng = np.random.default_rng(seed)
    out = np.zeros((n, 2))
    nparts = 60
    fr = np.sort(rng.uniform(3000, 13000, nparts)) * (freq / 1000.0 if freq else 1.0)
    for ch in range(2):
        y = np.zeros(n)
        ph = rng.uniform(0, 1, nparts)
        for f, p in zip(fr, ph):
            y += np.sin(2 * np.pi * (f * t + p)) * rng.uniform(0.3, 1.0)
        y /= nparts ** 0.5
        nz = dsp.highpass(dsp.noise(n, seed + 1 + ch), 5000, rate=rate)
        wash = 0.5 * y + 1.2 * nz
        if kind == 'ride':
            ping = sum(np.sin(2 * np.pi * f * t) for f in (620.0, 1385.0, 2913.0)) * np.exp(-6.9 * t / 0.5)
            env = np.exp(-6.9 * t / (dur * 0.9))
            x = 0.35 * wash * env * 0.6 + 0.25 * ping
        else:
            env = np.exp(-6.9 * t / (dur * 0.95)) * np.minimum(1, t / 0.002)
            x = wash * env
        out[:, ch] = dsp.highpass(x, 400, rate=rate)
    return _end_fade(_norm(out, vel), rate=rate)


def tom(freq=110.0, dur=0.5, vel=1.0, decay=0.35, rate=RATE, seed=16):
    n = _n(dur, rate)
    t = np.arange(n) / rate
    f = freq * (1 + 0.5 * np.exp(-t / 0.03))
    x = np.sin(2 * np.pi * np.cumsum(f) / rate) * np.exp(-6.9 * t / decay)
    x += 0.15 * dsp.bandpass(dsp.noise(n, seed), freq * 4, 1.0, rate=rate) * np.exp(-t / 0.01)
    return _end_fade(_norm(dsp.saturate(x, 1.3), vel), rate=rate)


def rim(dur=0.08, vel=1.0, freq=None, rate=RATE, seed=17):
    n = _n(dur, rate)
    t = np.arange(n) / rate
    f = freq or 1700.0
    x = (np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * f * 2.3 * t)) * np.exp(-t / 0.008)
    x += dsp.highpass(dsp.noise(n, seed), 2000, rate=rate) * np.exp(-t / 0.003)
    return _end_fade(_norm(x, vel), rate=rate)


# ---------------------------------------------------------------- bass

def sub_bass(freq, dur, vel=1.0, attack=0.004, release=0.05, drive=0.6, harmonic=0.08, glide_from=None,
             glide=0.05, rate=RATE):
    """Clean sine sub with a touch of 2nd harmonic and saturation."""
    n = _n(dur + release, rate)
    f = np.full(n, float(freq))
    if glide_from:
        k = min(n, _n(glide, rate))
        f[:k] = np.exp(np.linspace(math.log(glide_from), math.log(freq), k))
    ph = np.cumsum(f) / rate
    x = np.sin(2 * np.pi * ph) + harmonic * np.sin(4 * np.pi * ph)
    x *= dsp.adsr(n, attack, 0.1, 1.0, release, gate=dur, rate=rate)
    x = dsp.saturate(x, drive) if drive else x
    return _end_fade(x * vel, rate=rate)


def reese(freq, dur, vel=1.0, detune=0.2, voices=3, cutoff=900.0, q=1.2, sub=0.6, drive=1.6,
          lfo_rate=0.0, lfo_depth=0.0, attack=0.01, release=0.08, rate=RATE):
    """Detuned saws (detune in semitones across the voices) through a low-pass, sub under it.
    lfo_rate/lfo_depth wobble the cutoff (Hz, octaves)."""
    n = _n(dur + release, rate)
    x = np.zeros(n)
    for k in range(voices):
        d = (k - (voices - 1) / 2) / max(1, (voices - 1) / 2) * detune / 2
        x += dsp.saw(freq * 2 ** (d / 12), n, rate, phase0=0.37 * k)
    x /= voices
    if lfo_rate and lfo_depth:
        t = np.arange(n) / rate
        cut = cutoff * 2 ** (lfo_depth * np.sin(2 * np.pi * lfo_rate * t))
        x = dsp.lowpass(x, cut, q, rate=rate)
    else:
        x = dsp.lowpass(x, cutoff, q, rate=rate)
    x = dsp.saturate(x * 1.5, drive)
    x += sub * np.sin(2 * np.pi * freq * np.arange(n) / rate)
    x *= dsp.adsr(n, attack, 0.2, 0.9, release, gate=dur, rate=rate)
    return _end_fade(_norm(x, vel), rate=rate)


def acid(freq, dur, vel=1.0, cutoff=320.0, env_mod=2800.0, q=7.0, decay=0.18, wave='saw', accent=False,
         slide_from=None, slide=0.06, drive=2.2, release=0.03, rate=RATE):
    """303-style line: saw/square through a resonant low-pass swept by a decaying envelope.
    slide_from: previous note's frequency to glide from; accent: harder and brighter."""
    n = _n(dur + release, rate)
    t = np.arange(n) / rate
    f = np.full(n, float(freq))
    if slide_from:
        k = min(n, _n(slide, rate))
        f[:k] = np.exp(np.linspace(math.log(slide_from), math.log(freq), k))
    osc = dsp.saw(f, n, rate) if wave == 'saw' else dsp.square(f, n, rate)
    em = env_mod * (1.6 if accent else 1.0)
    cut = cutoff + em * np.exp(-t / (decay * (0.7 if accent else 1.0)))
    y = dsp.lowpass(osc, np.minimum(cut, 16000), q, rate=rate, block=32)
    y = dsp.highpass(dsp.saturate(y * (1.6 if accent else 1.0), drive), 25, rate=rate)
    y *= dsp.adsr(n, 0.002, 0.3, 0.85, release, gate=dur, rate=rate)
    return _end_fade(_norm(y, vel * (1.0 if accent else 0.85)), rate=rate)


# ---------------------------------------------------------------- leads and plucks

def saw_lead(freq, dur, vel=1.0, detune=0.1, voices=3, cutoff=5500.0, q=0.9, attack=0.008, decay=0.2,
             sustain=0.8, release=0.15, vibrato=0.0, vib_rate=5.5, vib_delay=0.2, glide_from=None, glide=0.05,
             width=0.6, rate=RATE):
    """Detuned saw lead (stereo). vibrato in semitones."""
    n = _n(dur + release, rate)
    t = np.arange(n) / rate
    f = np.full(n, float(freq))
    if glide_from:
        k = min(n, _n(glide, rate))
        f[:k] = np.exp(np.linspace(math.log(glide_from), math.log(freq), k))
    if vibrato:
        f *= 2 ** (vibrato / 12 * np.sin(2 * np.pi * vib_rate * t) * np.clip((t - vib_delay) / 0.2, 0, 1))
    out = np.zeros((n, 2))
    for k in range(voices):
        d = (k - (voices - 1) / 2) / max(1, (voices - 1) / 2) * detune / 2 if voices > 1 else 0
        v = dsp.saw(f * 2 ** (d / 12), n, rate, phase0=0.21 * k)
        p = (k - (voices - 1) / 2) / max(1, (voices - 1) / 2) * width if voices > 1 else 0
        out += dsp.pan(v, p) / voices
    out = dsp.lowpass(out, cutoff, q, rate=rate)
    env = dsp.adsr(n, attack, decay, sustain, release, gate=dur, rate=rate)
    return _end_fade(_norm(out * env[:, None], vel), rate=rate)


def square_lead(freq, dur, vel=1.0, pw=0.5, pwm=0.15, pwm_rate=0.8, cutoff=4500.0, attack=0.005, decay=0.15,
                sustain=0.75, release=0.12, octave_mix=0.0, rate=RATE):
    """Pulse lead with PWM; octave_mix adds a square an octave down."""
    n = _n(dur + release, rate)
    t = np.arange(n) / rate
    w = np.clip(pw + pwm * np.sin(2 * np.pi * pwm_rate * t), 0.05, 0.95)
    x = dsp.square(freq, n, rate, pw=w)
    if octave_mix:
        x += octave_mix * dsp.square(freq / 2, n, rate)
    x = dsp.highpass(dsp.lowpass(x, cutoff, 0.8, rate=rate), 25, rate=rate)
    x *= dsp.adsr(n, attack, decay, sustain, release, gate=dur, rate=rate)
    return _end_fade(_norm(x, vel), rate=rate)


def pluck(freq, dur, vel=1.0, cut_hi=7000.0, cut_lo=350.0, fdecay=0.12, decay=0.45, q=1.5, detune=0.06,
          rate=RATE):
    """Bright synth pluck: saw+square, filter envelope falling fast, amp decay."""
    n = _n(max(dur, decay) + 0.05, rate)
    t = np.arange(n) / rate
    x = 0.6 * dsp.saw(freq * 2 ** (detune / 24), n, rate) + 0.4 * dsp.square(freq * 2 ** (-detune / 24), n, rate)
    cut = cut_lo + (cut_hi - cut_lo) * np.exp(-t / fdecay)
    x = dsp.lowpass(x, cut, q, rate=rate, block=32)
    x *= np.exp(-6.9 * t / decay) * np.minimum(1, t / 0.002)
    return _end_fade(_norm(x, vel), rate=rate)


def arp(freq, dur, vel=1.0, decay=0.16, cutoff=5000.0, fenv=3000.0, q=2.0, wave='square', pw=0.35, rate=RATE):
    """Short trance arpeggio blip."""
    n = _n(max(dur, decay * 1.5) + 0.02, rate)
    t = np.arange(n) / rate
    x = dsp.square(freq, n, rate, pw=pw) if wave == 'square' else dsp.saw(freq, n, rate)
    x += 0.3 * dsp.saw(freq * 2, n, rate)
    cut = cutoff + fenv * np.exp(-t / 0.03)
    x = dsp.highpass(dsp.lowpass(x, np.minimum(cut, 16000), q, rate=rate, block=32), 25, rate=rate)
    x *= np.exp(-6.9 * t / decay) * np.minimum(1, t / 0.001)
    return _end_fade(_norm(x, vel), rate=rate)


def fm_bell(freq, dur, vel=1.0, ratio=3.5, index=4.0, decay=1.2, rate=RATE):
    """Two-operator FM bell."""
    n = _n(max(dur, decay), rate)
    t = np.arange(n) / rate
    ienv = index * np.exp(-t / (decay * 0.4))
    x = np.sin(2 * np.pi * freq * t + ienv * np.sin(2 * np.pi * freq * ratio * t))
    x *= np.exp(-6.9 * t / decay) * np.minimum(1, t / 0.002)
    return _end_fade(_norm(x, vel), rate=rate)


# ---------------------------------------------------------------- pads

def supersaw(freq, dur, vel=1.0, voices=7, detune=0.3, attack=0.35, decay=0.5, sustain=0.85, release=1.0,
             cutoff=4500.0, q=0.8, width=0.9, rate=RATE, seed=21):
    """Supersaw pad (stereo). freq may be one frequency or a list (a chord)."""
    freqs = [freq] if np.isscalar(freq) else list(freq)
    n = _n(dur + release, rate)
    rng = np.random.default_rng(seed)
    out = np.zeros((n, 2))
    for f0 in freqs:
        for k in range(voices):
            d = (k - (voices - 1) / 2) / max(1, (voices - 1) / 2) * detune / 2
            v = dsp.saw(f0 * 2 ** (d / 12), n, rate, phase0=float(rng.uniform()))
            p = (k - (voices - 1) / 2) / max(1, (voices - 1) / 2) * width
            out += dsp.pan(v, p)
    out /= voices * len(freqs) ** 0.5
    out = dsp.lowpass(out, cutoff, q, rate=rate)
    out = dsp.highpass(out, 120, rate=rate)
    env = dsp.adsr(n, attack, decay, sustain, release, gate=dur, rate=rate, curve=2.0)
    return _end_fade(_norm(out * env[:, None], vel), rate=rate)


def warm_pad(freq, dur, vel=1.0, attack=0.8, release=1.5, cutoff=1800.0, rate=RATE):
    """Soft triangle + filtered saw pad (stereo, slow chorus). freq may be a chord list."""
    freqs = [freq] if np.isscalar(freq) else list(freq)
    n = _n(dur + release, rate)
    t = np.arange(n) / rate
    out = np.zeros((n, 2))
    for i, f0 in enumerate(freqs):
        for ch, s in enumerate((-1, 1)):
            f = f0 * 2 ** (s * 0.07 / 12 * (1 + 0.3 * np.sin(2 * np.pi * (0.3 + 0.07 * i) * t)))
            out[:, ch] += 0.6 * dsp.triangle(f, n, rate, phase0=0.1 * i) + 0.4 * dsp.saw(f, n, rate, phase0=0.3 * i)
    out = dsp.lowpass(out, cutoff, 0.7, rate=rate)
    out *= dsp.adsr(n, attack, 0.5, 0.9, release, gate=dur, rate=rate, curve=2.0)[:, None]
    return _end_fade(_norm(out, vel), rate=rate)


# ---------------------------------------------------------------- effects

def riser(dur=4.0, vel=1.0, freq=None, f0=250.0, f1=7000.0, tone=0.35, rate=RATE, seed=31):
    """Noise through a rising band-pass plus a rising saw, getting louder (stereo)."""
    n = _n(dur, rate)
    t = np.arange(n) / rate
    sweep = f0 * (f1 / f0) ** (t / dur)
    out = np.zeros((n, 2))
    for ch in range(2):
        nz = dsp.noise(n, seed + ch)
        out[:, ch] = dsp.bandpass(nz, sweep, 1.8, rate=rate) * 2.5
    if tone:
        base = freq or 110.0
        tf = base * 4 ** (t / dur)
        out += tone * dsp.pan(dsp.lowpass(dsp.saw(tf, n, rate), sweep, 0.9, rate=rate), 0)
    out *= ((t / dur) ** 2)[:, None]
    return _end_fade(_norm(out, vel), ms=10, rate=rate)


def downlifter(dur=2.0, vel=1.0, freq=None, f0=6000.0, f1=200.0, rate=RATE, seed=32):
    """Falling noise sweep, fading out (stereo)."""
    n = _n(dur, rate)
    t = np.arange(n) / rate
    sweep = f0 * (f1 / f0) ** (t / dur)
    out = np.stack([dsp.bandpass(dsp.noise(n, seed + ch), sweep, 1.5, rate=rate) for ch in range(2)], 1)
    out *= (np.exp(-3 * t / dur) * np.minimum(1, t / 0.01))[:, None]
    return _end_fade(_norm(out, vel), rate=rate)


def noise_sweep(dur=1.0, vel=1.0, freq=None, f0=500.0, f1=12000.0, q=2.5, rate=RATE, seed=33):
    """Short filtered-noise whoosh between two frequencies (either direction)."""
    n = _n(dur, rate)
    t = np.arange(n) / rate
    sweep = f0 * (f1 / f0) ** (t / dur)
    x = dsp.bandpass(dsp.noise(n, seed), sweep, q, rate=rate)
    x *= np.sin(np.pi * t / dur) ** 2
    return _end_fade(_norm(x, vel), rate=rate)


def impact(dur=3.0, vel=1.0, freq=None, rate=RATE, seed=34):
    """Low boom with a noise crack and a long dark tail (stereo)."""
    n = _n(dur, rate)
    t = np.arange(n) / rate
    f = (freq or 30.0) + 50 * np.exp(-t / 0.15)
    boom = np.sin(2 * np.pi * np.cumsum(f) / rate) * np.exp(-6.9 * t / (dur * 0.7))
    crack = dsp.lowpass(dsp.noise(n, seed), 3000, rate=rate) * np.exp(-t / 0.06)
    x = dsp.saturate(boom * 1.2 + crack * 0.8, 1.5)
    out = dsp.reverb(dsp.pan(x, 0), decay=dur * 0.8, mix=0.5, damp=0.7)
    return _end_fade(_norm(out, vel), ms=20, rate=rate)


def reverse_cymbal(dur=2.0, vel=1.0, freq=None, rate=RATE, seed=35):
    """A crash played backwards, swelling into the next downbeat (stereo)."""
    c = cymbal(dur, 1.0, kind='crash', rate=rate, seed=seed)[::-1].copy()
    return _end_fade(_norm(c, vel), ms=3, rate=rate)


# ---------------------------------------------------------------- playable wrapper

DRUMS = {kick, snare, clap, hat, cymbal, rim, riser, downlifter, noise_sweep, impact, reverse_cymbal}


_CACHE = {}
_CACHE_BYTES = [0]
CACHE_LIMIT = 768 << 20         # bytes of synthesised notes kept (oldest dropped first)


class Inst:
    """A playable instrument: inst(freq, dur, vel) -> audio, with fixed parameters. Notes are
    cached across all Inst objects with the same function and parameters, so building a new
    Inst per note costs nothing. Drum functions get vel (and freq if given), not dur."""

    def __init__(self, fn, cache=True, **params):
        self.fn = fn
        self.params = params
        self.use_cache = cache
        self.drum = fn in DRUMS
        self.name = getattr(fn, '__name__', 'inst')
        self._key = (self.name, repr(sorted(params.items())))

    def __call__(self, freq=None, dur=0.25, vel=1.0):
        key = self._key + (None if freq is None else round(float(freq), 3), 0 if self.drum else round(float(dur), 4),
                           round(float(vel), 3))
        if self.use_cache and key in _CACHE:
            return _CACHE[key]
        if self.drum:
            kw = dict(self.params)
            kw.setdefault('vel', vel)
            if freq is not None and 'freq' not in kw:
                kw['freq'] = freq
            y = self.fn(**kw)
        else:
            y = self.fn(freq, dur, vel, **self.params)
        y = np.asarray(y, np.float32)
        if self.use_cache:
            _CACHE[key] = y
            _CACHE_BYTES[0] += y.nbytes
            while _CACHE_BYTES[0] > CACHE_LIMIT and len(_CACHE) > 1:
                old = next(iter(_CACHE))
                _CACHE_BYTES[0] -= _CACHE.pop(old).nbytes
        return y

    def with_(self, **kw):
        p = dict(self.params)
        p.update(kw)
        return Inst(self.fn, self.use_cache, **p)


def demo(path=None):
    """Render every instrument once into a 44.1 kHz stereo array (and a WAV if path)."""
    parts = [kick(), snare(), clap(), hat(), hat(open=True), cymbal(), cymbal(kind='ride'), tom(),
             sub_bass(55, 0.5), reese(55, 1.0), acid(110, 0.25), acid(110, 0.25, accent=True, slide_from=82.4),
             saw_lead(440, 0.5), square_lead(440, 0.5), pluck(440, 0.4), arp(880, 0.15), fm_bell(660, 1.0),
             supersaw([220, 277.2, 329.6], 1.5), warm_pad([220, 261.6, 329.6], 1.5), riser(2.0), downlifter(1.5),
             noise_sweep(0.8), impact(2.5), reverse_cymbal(1.5)]
    gap = np.zeros((int(0.15 * RATE), 2))
    out = np.concatenate(sum(([dsp.as_stereo(p) * 0.7, gap] for p in parts), []))
    if path:
        import render
        render.write_wav(path, out, RATE)
    return out
