"""The title songs' extras (tools/music/title): the guitars, distorted bass, scratch and shout the nu metal
theme is made of, added to the shared synth module, and the two small changes it needs of the shared
modules (a scratch that bounces at the ends of its sample, a 24-sample fade-in on every instrument note), made
here so that the radio's remixes, which do not use them, render as they did. Import this first."""
import numpy as np

import dsp
import synth
from dsp import RATE
from synth import _end_fade, _n, _norm

import math  # noqa: E402,F401

_play_sample = dsp.play_sample


def play_sample(pcm, ratio, n_out, loop_start=-1, start=0.0, interp='hermite', bounce=False):
    """dsp.play_sample, and with bounce the position folds back at both ends (ratio may be negative)"""
    if not bounce:
        return _play_sample(pcm, ratio, n_out, loop_start, start, interp)
    pcm = np.asarray(pcm, np.float64)
    n = len(pcm)
    if n == 0:
        return np.zeros(n_out)
    if np.isscalar(ratio):
        p = start + ratio * np.arange(n_out, dtype=np.float64)
    else:
        p = start + np.concatenate([[0.0], np.cumsum(np.asarray(ratio, float)[:n_out - 1])])
    m2 = np.mod(p, 2.0 * (n - 1))
    p = np.where(m2 > n - 1, 2.0 * (n - 1) - m2, m2)
    i = p.astype(np.int64)
    f = p - i
    b = np.concatenate(([0.0], pcm, np.zeros(3)))
    if interp == 'linear':
        return b[i + 1] + (b[i + 2] - b[i + 1]) * f
    xm1, x0, x1, x2 = b[i], b[i + 1], b[i + 2], b[i + 3]
    c1 = 0.5 * (x1 - xm1)
    c2 = xm1 - 2.5 * x0 + 2 * x1 - 0.5 * x2
    c3 = 0.5 * (x2 - xm1) + 1.5 * (x0 - x1)
    return ((c3 * f + c2) * f + c1) * f + x0


dsp.play_sample = play_sample

_inst_call = synth.Inst.__call__


def _inst_faded(self, *a, **k):
    y = np.array(_inst_call(self, *a, **k), np.float32)
    n = min(len(y), 24)
    ramp = np.linspace(0, 1, n, endpoint=False)
    y[:n] *= ramp if y.ndim == 1 else ramp[:, None]
    return y


synth.Inst.__call__ = _inst_faded


# ================================================================ numetal additions
# Guitars, distorted sub, scratch and gang shout for the nu metal sketches. All deterministic.

def _cab(x, bright=1.0, rate=RATE):
    """A 4x12-ish cabinet: low cut, a little low-mid scoop, presence, steep top roll-off."""
    x = dsp.highpass(dsp.highpass(x, 70, 0.7, rate=rate), 70, 0.7, rate=rate)
    x = dsp.eq(x, [('peak', 110, 2.0, 0.9), ('peak', 380, -3.0, 1.0), ('peak', 2300, 3.5 * bright, 1.0),
                   ('peak', 3600, 1.5 * bright, 1.5)], rate)
    return dsp.lowpass(dsp.lowpass(x, 5000, 0.7, rate=rate), 6000, 0.7, rate=rate)


def _amp(x, gain1=3.0, gain2=2.2, rate=RATE):
    """Two gain stages with a low-pass between them, like a high-gain amp."""
    x = dsp.saturate(x * gain1, 1.0)
    x = dsp.lowpass(dsp.highpass(x, 60, rate=rate), 4200, 0.8, rate=rate)
    return dsp.saturate(x * gain2, 1.0)


def palm_mute_guitar(freq, dur, vel=1.0, mute=0.6, seed=0, bright=1.0, rate=RATE):
    """Down-tuned palm-muted chug: two detuned saws and a square, a filter that closes as the
    palm settles, a two-stage amp, then the cabinet. Tight: the gate shuts after `dur`."""
    n = _n(dur + 0.05, rate)
    t = np.arange(n) / rate
    rng = np.random.default_rng(100 + seed)
    d = rng.uniform(0.0008, 0.0022)
    x = (0.5 * dsp.saw(freq * (1 + d), n, rate, phase0=float(rng.uniform())) +
         0.5 * dsp.saw(freq * (1 - d), n, rate, phase0=float(rng.uniform())) +
         0.25 * dsp.square(freq, n, rate, phase0=float(rng.uniform())))
    cut = 500 + (2600 + 1800 * (1 - mute)) * np.exp(-t / (0.035 + 0.05 * (1 - mute)))
    x = dsp.lowpass(x, np.minimum(cut, 9000), 1.1, rate=rate, block=32)
    pick = dsp.highpass(dsp.noise(n, 7 + seed), 2500, rate=rate) * np.exp(-t / 0.003) * 0.5
    x = _amp(x + pick * 0.3)
    env = np.exp(-t / (0.16 + 0.1 * (1 - mute))) * np.minimum(1, t / 0.0012)
    env *= dsp.adsr(n, 0.001, 1.0, 1.0, 0.018, gate=dur, rate=rate, curve=1.0)
    x = _cab(x * env, bright, rate)
    return _end_fade(_norm(x, vel), rate=rate)


def power_chord_guitar(freq, dur, vel=1.0, third=False, seed=0, decay=1.4, extra=(), rate=RATE):
    """Open power chord (root, fifth, octave), double-tracked: two takes hard left and right with
    different detune and a few ms apart. Returns stereo."""
    n = _n(dur + 0.25, rate)
    t = np.arange(n) / rate
    mult = [1.0, 1.4983, 2.0] + ([2.378] if third else []) + list(extra)
    out = np.zeros((n, 2))
    for take, side in enumerate((-1, 1)):
        rng = np.random.default_rng(200 + seed * 7 + take)
        lag = int((0.0025 + 0.002 * take) * rate) * take
        x = np.zeros(n)
        for m in mult:
            for dd in (-1, 1):
                x += dsp.saw(freq * m * (1 + dd * rng.uniform(0.0012, 0.0030)), n, rate, phase0=float(rng.uniform()))
        x = dsp.lowpass(x, 4200, 0.9, rate=rate)
        x = _amp(x / len(mult), 3.0, 2.0, rate)
        env = np.minimum(1, t / 0.002) * np.exp(-t / decay)
        env *= dsp.adsr(n, 0.001, 1.0, 1.0, 0.09, gate=dur, rate=rate, curve=1.0)
        x = _cab(x * env, 1.0, rate)
        if lag:
            x = np.concatenate([np.zeros(lag), x[:-lag]])
        out[:, take] = x
    return _end_fade(_norm(out, vel), ms=10, rate=rate)


def _chorus(x, depth=0.003, rate_hz=(0.35, 0.27), mixamt=0.55, rate=RATE):
    """Stereo chorus of a mono signal: two slow modulated delays."""
    n = len(x)
    t = np.arange(n) / rate
    out = np.zeros((n, 2))
    idx = np.arange(n)
    for ch in range(2):
        dl = (0.012 + 0.004 * ch + depth * np.sin(2 * np.pi * rate_hz[ch] * t + 1.7 * ch)) * rate
        wet = np.interp(idx - dl, idx, x, left=0.0)
        out[:, ch] = (1 - 0.35 * mixamt) * x + mixamt * wet
    return out


def clean_guitar(freq, dur, vel=1.0, brightness=0.55, damp=0.9965, rate=RATE):
    """Plucked string (Karplus-Strong, tuned exactly by running at a multiple of the pitch and
    resampling) through a stereo chorus. dur is how long it is allowed to ring before a short
    release. Returns stereo."""
    N = max(8, int(round(rate / freq)))
    rp = freq * N
    nn = int((dur + 0.12) * rp) + N
    exc = dsp.noise(N, 5)
    exc = exc - exc.mean()
    k = max(1, int(round(1 + (1 - brightness) * 6)))
    exc = np.convolve(np.concatenate([exc, exc[:k]]), np.ones(k) / k, 'same')[:N]
    a = np.zeros(N + 2)
    a[0] = 1.0
    a[N] = -damp / 2
    a[N + 1] = -damp / 2
    xin = np.zeros(nn)
    xin[:N] = exc
    from scipy import signal as _sg
    y = _sg.lfilter([1.0], a, xin)
    n_out = _n(dur + 0.12, rate)
    y = dsp.play_sample(y, rp / rate, n_out)
    t = np.arange(n_out) / rate
    y = dsp.lowpass(y, 5200, 0.7, rate=rate)
    y = dsp.highpass(y, 80, 0.7, rate=rate)
    y *= dsp.adsr(n_out, 0.001, 1.0, 1.0, 0.09, gate=dur, rate=rate, curve=1.0)
    out = _chorus(y, rate=rate)
    return _end_fade(_norm(out, vel), rate=rate)


def lead_guitar(freq, dur, vel=1.0, vibrato=0.14, glide_from=None, rate=RATE):
    """Sustained distorted lead (stereo, two slightly detuned takes) with a delayed vibrato."""
    n = _n(dur + 0.12, rate)
    t = np.arange(n) / rate
    f = np.full(n, float(freq))
    if glide_from:
        k = min(n, _n(0.06, rate))
        f[:k] = np.exp(np.linspace(math.log(glide_from), math.log(freq), k))
    f = f * 2 ** (vibrato / 12 * np.sin(2 * np.pi * 5.3 * t) * np.clip((t - 0.18) / 0.25, 0, 1))
    out = np.zeros((n, 2))
    for ch, dd in enumerate((-0.0016, 0.0016)):
        x = 0.7 * dsp.saw(f * (1 + dd), n, rate, phase0=0.2 * ch) + 0.3 * dsp.square(f * (1 + dd), n, rate)
        x = _amp(dsp.lowpass(x, 3600, 0.9, rate=rate), 2.5, 1.8, rate)
        x *= dsp.adsr(n, 0.004, 0.25, 0.8, 0.1, gate=dur, rate=rate, curve=2.0)
        out[:, ch] = _cab(x, 1.1, rate)
    return _end_fade(_norm(out, vel), rate=rate)


def dist_sub_bass(freq, dur, vel=1.0, grit=0.35, release=0.04, rate=RATE):
    """Distorted sub: a sine with a small pitch thump, plus a saturated copy band-limited to
    the low mids, so the note is felt on big speakers and heard on small ones."""
    n = _n(dur + release, rate)
    t = np.arange(n) / rate
    f = freq * np.ones_like(t)
    ph = np.cumsum(f) / rate
    s = np.sin(2 * np.pi * ph)
    g = dsp.saturate(s * 7.0, 1.0)
    g = dsp.lowpass(dsp.highpass(g, 70, rate=rate), 900, 0.8, rate=rate)
    x = s + grit * g
    x *= dsp.adsr(n, 0.003, 0.4, 0.9, release, gate=dur, rate=rate, curve=2.0)
    return _end_fade(_norm(dsp.saturate(x, 1.2), vel), rate=rate)


def scratch(pcm, ratio0, dur=0.25, vel=1.0, kind='baby', start=0.2, rate_hz=7.0, gate='x', seed=0, rate=RATE):
    """Turntable-style stab from a (4x oversampled) sample: the read position follows a
    time-varying ratio (forward, back, bent or stopping), and a crossfader gate chops it.
    ratio0 = source samples per output sample at normal speed (pitch)."""
    n = _n(dur, rate)
    t = np.arange(n) / rate
    u = t / dur
    if kind == 'baby':
        r = ratio0 * (0.35 + 1.9 * np.sin(2 * np.pi * rate_hz * t))
    elif kind == 'bend':
        r = ratio0 * np.maximum(0.0, 1 - u) ** 1.4 * 1.15
    elif kind == 'rise':
        r = ratio0 * (0.35 + 1.1 * u ** 1.5)
    elif kind == 'flare':
        r = ratio0 * (1.5 * np.cos(2 * np.pi * rate_hz * t) * (1 - 0.6 * u) + 0.4)
    else:
        r = np.full(n, ratio0)
    i0 = start * (len(pcm) - 2)
    y = dsp.play_sample(pcm, r, n, start=i0, bounce=True)
    gs = gate.replace(' ', '')
    steps = np.repeat([1.0 if c == 'x' else 0.0 for c in gs], max(1, n // len(gs)))
    steps = np.concatenate([steps, np.full(n - len(steps), steps[-1])])[:n]
    k = max(2, int(0.0025 * rate))
    g = np.convolve(np.pad(steps, (k, k), mode='edge'), np.ones(k) / k, 'same')[k:-k]
    y = y * g
    y = dsp.lowpass(dsp.highpass(y, 260, 0.8, rate=rate), 6800, 0.8, rate=rate)
    y = dsp.saturate(y * 2.0, 1.4)
    y *= np.exp(-1.2 * u) * np.minimum(1, t / 0.001)
    return _end_fade(_norm(y, vel), ms=6, rate=rate)


def gang_shout(freq=None, dur=0.28, vel=1.0, seed=0, rate=RATE):
    """Rhythmic group shout: three gruff voices (noise plus a rough pulse at E3, B3 and G3)
    through the formants of an open "hey", gated hard. Stereo. Not a word, a crowd."""
    n = _n(dur + 0.12, rate)
    t = np.arange(n) / rate
    out = np.zeros((n, 2))
    f0s = (164.81, 246.94, 196.0)
    pans = (-0.55, 0.0, 0.55)
    for v, (f0, p) in enumerate(zip(f0s, pans)):
        rng = np.random.default_rng(300 + seed * 5 + v)
        jit = 1 + 0.012 * np.sin(2 * np.pi * rng.uniform(5, 9) * t)
        src = 0.9 * dsp.saw(f0 * jit, n, rate, phase0=float(rng.uniform())) + 1.6 * dsp.noise(n, 400 + seed * 5 + v)
        sc = 0.94 + 0.06 * v
        u = np.clip(t / dur, 0, 1)
        f1 = (560 - 150 * u) * sc
        f2 = (1500 + 700 * u) * sc
        f3 = 2650 * sc
        y = (1.0 * dsp.bandpass(src, f1, 5, rate=rate) + 0.8 * dsp.bandpass(src, f2, 7, rate=rate) +
             0.45 * dsp.bandpass(src, f3, 9, rate=rate))
        y *= np.minimum(1, t / 0.006) * np.exp(-t / (dur * 0.7))
        y *= dsp.adsr(n, 0.001, 1.0, 1.0, 0.04, gate=dur, rate=rate, curve=1.0)
        y = dsp.saturate(y * 1.6, 1.8)
        out += dsp.pan(y, p)
    out = dsp.highpass(out, 220, rate=rate)
    return _end_fade(_norm(out, vel), rate=rate)


for _n_ in ('palm_mute_guitar', 'power_chord_guitar', 'clean_guitar', 'lead_guitar', 'dist_sub_bass', 'scratch',
            'gang_shout'):
    setattr(synth, _n_, globals()[_n_])
