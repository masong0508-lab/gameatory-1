"""Signal processing for the music tools: filters (with sweeps), envelopes, oscillators, delay,
reverb, compressor, limiter, loudness (ITU-R BS.1770-4) and true peak. numpy + scipy.signal.

Audio is float: mono arrays (n,) or stereo (n, 2), at RATE (44100) unless a rate is passed.
Anything that varies over time takes an automation: a constant, a list of (seconds, value)
points (interpolated exponentially for frequencies, linearly otherwise), or an array per sample.
Everything is deterministic: noise comes from numpy's PCG64 with fixed seeds.
"""
import math

import numpy as np
from scipy import signal
from scipy.ndimage import minimum_filter1d

RATE = 44100


# ---------------------------------------------------------------- helpers

def midi_hz(m):
    return 440.0 * 2 ** ((np.asarray(m, float) - 69) / 12)


def hz_midi(f):
    return 69 + 12 * np.log2(np.asarray(f, float) / 440.0)


def db(x):
    return 20 * np.log10(np.maximum(np.abs(x), 1e-12))


def undb(d):
    return 10 ** (np.asarray(d, float) / 20)


def noise(n, seed=0, color='white'):
    """Deterministic noise: white, pink (-3 dB/oct) or brown (-6 dB/oct), peak about 1."""
    rng = np.random.default_rng(seed)
    w = rng.standard_normal(n)
    if color == 'white':
        return w / 3.0
    spec = np.fft.rfft(w)
    f = np.arange(len(spec), dtype=float)
    f[0] = 1
    spec /= np.sqrt(f) if color == 'pink' else f
    x = np.fft.irfft(spec, n)
    return x / (np.max(np.abs(x)) + 1e-12)


def automation(a, n, rate=RATE, t0=0.0, exp=False):
    """Per-sample values (n,) of an automation; t0 is the time of sample 0."""
    if callable(a):
        return np.asarray(a(t0 + np.arange(n) / rate), float)
    if np.isscalar(a):
        return np.full(n, float(a))
    a = list(a) if not isinstance(a, np.ndarray) else a
    if isinstance(a, np.ndarray) and a.ndim == 1 and len(a) == n:
        return a.astype(float)
    pts = sorted((float(t), float(v)) for t, v in a)
    ts = np.array([p[0] for p in pts])
    vs = np.array([p[1] for p in pts])
    t = t0 + np.arange(n) / rate
    if exp:
        return np.exp(np.interp(t, ts, np.log(np.maximum(vs, 1e-6))))
    return np.interp(t, ts, vs)


def as_stereo(x):
    x = np.asarray(x, np.float64)
    return np.stack([x, x], 1) if x.ndim == 1 else x


def pan(x, p):
    """Mono -> stereo, equal power; p -1 (left) .. 1 (right); p may be an automation array."""
    x = np.asarray(x, np.float64)
    if x.ndim == 2:
        x = x.mean(1)
    th = (np.asarray(p, float) + 1) * np.pi / 4
    return np.stack([x * np.cos(th), x * np.sin(th)], 1) * math.sqrt(2)


def fade(x, fade_in=0.0, fade_out=0.0, rate=RATE):
    """Equal-power fades at the ends (seconds)."""
    x = np.array(x, np.float64, copy=True)
    n = len(x)
    if fade_in > 0:
        k = min(n, int(fade_in * rate))
        g = np.sin(np.linspace(0, np.pi / 2, k)) ** 2
        x[:k] *= g if x.ndim == 1 else g[:, None]
    if fade_out > 0:
        k = min(n, int(fade_out * rate))
        g = np.cos(np.linspace(0, np.pi / 2, k)) ** 2
        x[n - k:] *= g if x.ndim == 1 else g[:, None]
    return x


# ---------------------------------------------------------------- envelopes

def adsr(n, a=0.005, d=0.1, s=0.7, r=0.2, gate=None, rate=RATE, curve=3.0):
    """ADSR of n samples; the gate closes after `gate` seconds (default: n minus the release)."""
    t = np.arange(n) / rate
    gate = (n / rate - r) if gate is None else gate
    env = np.empty(n)
    att = t < a
    env[att] = t[att] / max(a, 1e-9)
    dec = (t >= a)
    env[dec] = s + (1 - s) * np.exp(-curve * (t[dec] - a) / max(d, 1e-9))
    lvl = s + (1 - s) * math.exp(-curve * max(gate - a, 0) / max(d, 1e-9)) if gate >= a else gate / max(a, 1e-9)
    rel = t >= gate
    env[rel] = lvl * np.exp(-curve * 2 * (t[rel] - gate) / max(r, 1e-9))
    return env


def exp_decay(n, decay, rate=RATE):
    """exp envelope falling 60 dB in `decay` seconds."""
    return np.exp(-6.9078 * np.arange(n) / (rate * max(decay, 1e-6)))


# ---------------------------------------------------------------- oscillators

def phase_of(freq, n, rate=RATE, phase0=0.0):
    """Phase in cycles (float64) for a frequency automation array or constant."""
    f = np.full(n, float(freq)) if np.isscalar(freq) else np.asarray(freq, float)
    ph = np.cumsum(f) / rate
    return ph - ph[0] + phase0, f


def _polyblep(t, dt):
    y = np.zeros_like(t)
    m = t < dt
    x = t[m] / dt[m]
    y[m] = x + x - x * x - 1
    m2 = t > 1 - dt
    x = (t[m2] - 1) / dt[m2]
    y[m2] = x * x + x + x + 1
    return y


def saw(freq, n, rate=RATE, phase0=0.0):
    """Band-limited sawtooth (PolyBLEP), -1..1."""
    ph, f = phase_of(freq, n, rate, phase0)
    t = ph % 1.0
    dt = np.clip(f / rate, 1e-9, 0.5)
    return 2 * t - 1 - _polyblep(t, dt)


def square(freq, n, rate=RATE, pw=0.5, phase0=0.0):
    """Band-limited pulse (PolyBLEP), duty `pw` (automation ok)."""
    ph, f = phase_of(freq, n, rate, phase0)
    pw = np.broadcast_to(np.asarray(pw, float), (n,))
    t = ph % 1.0
    dt = np.clip(f / rate, 1e-9, 0.5)
    y = np.where(t < pw, 1.0, -1.0)
    y += _polyblep(t, dt)
    y -= _polyblep((t - pw) % 1.0, dt)
    return y


def sine(freq, n, rate=RATE, phase0=0.0):
    ph, _ = phase_of(freq, n, rate, phase0)
    return np.sin(2 * np.pi * ph)


def triangle(freq, n, rate=RATE, phase0=0.0):
    ph, _ = phase_of(freq, n, rate, phase0)
    return 4 * np.abs((ph + 0.25) % 1.0 - 0.5) - 1


# ---------------------------------------------------------------- filters

def biquad_coefs(kind, f0, q=0.7071, gain_db=0.0, rate=RATE):
    """RBJ cookbook biquad (b, a): lowpass highpass bandpass notch peak lowshelf highshelf."""
    f0 = min(max(f0, 5.0), rate * 0.49)
    w0 = 2 * math.pi * f0 / rate
    cw, sw = math.cos(w0), math.sin(w0)
    al = sw / (2 * q)
    A = 10 ** (gain_db / 40)
    if kind == 'lowpass':
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + al, -2 * cw, 1 - al]
    elif kind == 'highpass':
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + al, -2 * cw, 1 - al]
    elif kind == 'bandpass':
        b = [al, 0, -al]
        a = [1 + al, -2 * cw, 1 - al]
    elif kind == 'notch':
        b = [1, -2 * cw, 1]
        a = [1 + al, -2 * cw, 1 - al]
    elif kind == 'peak':
        b = [1 + al * A, -2 * cw, 1 - al * A]
        a = [1 + al / A, -2 * cw, 1 - al / A]
    elif kind in ('lowshelf', 'highshelf'):
        s = 2 * math.sqrt(A) * al
        if kind == 'lowshelf':
            b = [A * ((A + 1) - (A - 1) * cw + s), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - s)]
            a = [(A + 1) + (A - 1) * cw + s, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - s]
        else:
            b = [A * ((A + 1) + (A - 1) * cw + s), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - s)]
            a = [(A + 1) - (A - 1) * cw + s, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - s]
    else:
        raise ValueError(kind)
    b = np.array(b) / a[0]
    a = np.array(a) / a[0]
    return b, a


def filt(x, kind, freq, q=0.7071, gain_db=0.0, rate=RATE, t0=0.0, block=64, order=2):
    """Biquad filter; `freq` may be an automation (a sweep), processed in 64-sample blocks.
    order 4 runs two identical stages (24 dB/oct)."""
    x = np.asarray(x, np.float64)
    if order == 4:
        return filt(filt(x, kind, freq, q, gain_db, rate, t0, block), kind, freq, q, gain_db, rate, t0, block)
    if np.isscalar(freq):
        b, a = biquad_coefs(kind, freq, q, gain_db, rate)
        return signal.lfilter(b, a, x, axis=0)
    n = len(x)
    f = automation(freq, n, rate, t0, exp=True)
    y = np.empty_like(x)
    zi = np.zeros((2,) + x.shape[1:])
    for i in range(0, n, block):
        j = min(n, i + block)
        b, a = biquad_coefs(kind, float(f[i]), q, gain_db, rate)
        y[i:j], zi = signal.lfilter(b, a, x[i:j], axis=0, zi=zi)
    return y


def lowpass(x, freq, q=0.7071, **kw):
    return filt(x, 'lowpass', freq, q, **kw)


def highpass(x, freq, q=0.7071, **kw):
    return filt(x, 'highpass', freq, q, **kw)


def bandpass(x, freq, q=1.0, **kw):
    return filt(x, 'bandpass', freq, q, **kw)


def eq(x, bands, rate=RATE):
    """Static EQ: bands = [(kind, freq, gain_db, q), ...] (kind peak/lowshelf/highshelf/...)."""
    for kind, f, g, q in bands:
        x = filt(x, kind, f, q, g, rate)
    return x


def saturate(x, drive=1.0):
    """tanh soft clip, unity gain for small signals."""
    if drive <= 0:
        return x
    return np.tanh(x * drive) / math.tanh(drive) if drive > 1e-3 else x


# ---------------------------------------------------------------- time effects

def delay(x, time, feedback=0.35, mix=0.25, pingpong=True, lp=5000.0, hp=150.0, rate=RATE, repeats=None):
    """Feedback echo (wet+dry), each repeat darker (lp) and thinner (hp); ping-pong alternates
    the repeats left/right. Output has the input's length."""
    x = as_stereo(x)
    n = len(x)
    d = max(1, int(round(time * rate)))
    k_max = repeats or max(1, int(math.ceil(math.log(1e-3) / math.log(max(min(feedback, 0.95), 1e-3)))))
    src = x.mean(1) if pingpong else x
    tap = highpass(src, hp, rate=rate) if hp else src
    wet = np.zeros_like(x)
    g = 1.0
    for k in range(1, k_max + 1):
        if k * d >= n:
            break
        if lp:
            tap = lowpass(tap, lp, rate=rate)
        seg = tap[:n - k * d] * g
        if pingpong:
            wet[k * d:, (k - 1) % 2] += seg
        else:
            wet[k * d:] += seg
        g *= feedback
    return x * (1 - mix * 0.5) + wet * mix


def reverb_ir(decay=2.0, predelay=0.015, damp=0.5, width=1.0, size=1.0, rate=RATE, seed=7):
    """A stereo impulse response: early reflections + exponentially decaying noise in eight
    octave bands, the highs dying faster (damp 0..1)."""
    n = int(rate * (predelay + decay * 1.2)) + 1
    t = np.arange(n) / rate
    rng = np.random.default_rng(seed)
    ir = np.zeros((n, 2))
    edges = [0, 125, 250, 500, 1000, 2000, 4000, 8000, rate / 2]
    for ch in range(2):
        w = rng.standard_normal(n)
        W = np.fft.rfft(w)
        fr = np.fft.rfftfreq(n, 1 / rate)
        for bi in range(len(edges) - 1):
            m = (fr >= edges[bi]) & (fr < edges[bi + 1])
            bn = np.fft.irfft(np.where(m, W, 0), n)
            dk = decay * (1 - damp * 0.85 * bi / (len(edges) - 2))
            ir[:, ch] += bn * np.exp(-6.9078 * np.maximum(t - predelay, 0) / max(dk, 0.05))
        ir[t < predelay, ch] = 0
    # early reflections
    for i, (dt, g) in enumerate([(0.007, 0.5), (0.011, 0.4), (0.017, 0.33), (0.023, 0.27), (0.031, 0.2)]):
        k = int((predelay + dt * size) * rate)
        if k < n:
            ir[k, i % 2] += g * 3
            ir[min(n - 1, k + int(0.0013 * rate)), (i + 1) % 2] += g * 2
    mid = ir.mean(1, keepdims=True)
    ir = mid + (ir - mid) * width
    ir /= math.sqrt(np.sum(ir ** 2) / 2)
    # gentle fade at the very end
    ir[-int(0.05 * rate):] *= np.linspace(1, 0, int(0.05 * rate))[:, None]
    return ir


_IR_CACHE = {}


def reverb(x, decay=2.0, mix=0.2, predelay=0.015, damp=0.5, width=1.0, hp=200.0, rate=RATE, wet_only=False):
    """Convolution reverb with a synthetic IR (see reverb_ir). Output has the input's length."""
    x = as_stereo(x)
    key = (decay, predelay, damp, width, rate)
    if key not in _IR_CACHE:
        _IR_CACHE[key] = reverb_ir(decay, predelay, damp, width, rate=rate)
    ir = _IR_CACHE[key]
    src = highpass(x, hp, rate=rate) if hp else x
    wet = np.stack([signal.oaconvolve(src[:, 0], ir[:, 0])[:len(x)],
                    signal.oaconvolve(src[:, 1], ir[:, 1])[:len(x)]], 1) * 0.35
    if wet_only:
        return wet
    return x * (1 - mix * 0.3) + wet * mix


# ---------------------------------------------------------------- dynamics

def _block_smooth(target, attack_k, release_k, falling_is_attack=True):
    """One-pole smoothing per block with separate attack/release coefficients (python loop
    over blocks, fast enough at 64-sample blocks)."""
    out = np.empty_like(target)
    s = target[0]
    for i, v in enumerate(target):
        if (v < s) == falling_is_attack:
            s += (v - s) * attack_k
        else:
            s += (v - s) * release_k
        out[i] = s
    return out


def compress(x, threshold_db=-18.0, ratio=2.0, attack=0.01, release=0.15, knee_db=6.0, makeup_db=0.0,
             rate=RATE, block=64, key=None):
    """Feed-forward RMS compressor (stereo linked). key: optional sidechain signal."""
    x = np.asarray(x, np.float64)
    k = as_stereo(x if key is None else key)
    n = len(x)
    nb = (n + block - 1) // block
    pad = np.zeros((nb * block - n, 2))
    kk = np.concatenate([k, pad]) if len(pad) else k
    lvl = db(np.sqrt(np.mean(kk.reshape(nb, block, 2) ** 2, axis=(1, 2))) * math.sqrt(2))
    over = lvl - threshold_db
    gr = np.where(over <= -knee_db / 2, 0.0,
                  np.where(over >= knee_db / 2, over * (1 - 1 / ratio),
                           (1 - 1 / ratio) * (over + knee_db / 2) ** 2 / (2 * max(knee_db, 1e-6))))
    ak = 1 - math.exp(-block / (rate * max(attack, 1e-4)))
    rk = 1 - math.exp(-block / (rate * max(release, 1e-4)))
    g = -_block_smooth(-gr, ak, rk, falling_is_attack=True)
    gs = np.interp(np.arange(n), np.arange(nb) * block + block / 2, g)
    gain = undb(-gs + makeup_db)
    return x * (gain[:, None] if x.ndim == 2 else gain)


def duck_envelope(n, times, amount=0.6, attack=0.004, hold=0.02, release=0.2, shape=1.5, rate=RATE):
    """Sidechain-style gain curve (n,): dips by `amount` at each time and recovers over
    `release`; shape > 1 recovers slowly at first (the classic pump), < 1 quickly."""
    env = np.ones(n)
    a, h, r = max(1, int(attack * rate)), int(hold * rate), max(1, int(release * rate))
    rec = np.linspace(0, 1, r)
    curve = np.concatenate([np.linspace(1, 1 - amount, a, endpoint=False), np.full(h, 1 - amount),
                            1 - amount + amount * rec ** shape])
    for t in times:
        i = int(round(t * rate)) - a
        if i >= n:
            continue
        c = curve
        if i < 0:
            c, i = c[-i:], 0
        j = min(n, i + len(c))
        env[i:j] = np.minimum(env[i:j], c[:j - i])
    return env


def limiter(x, ceiling_db=-1.0, lookahead=0.005, release=0.08, rate=RATE):
    """Look-ahead brickwall limiter on the sample peaks (stereo linked)."""
    x = np.asarray(x, np.float64)
    c = undb(ceiling_db)
    peak = np.max(np.abs(x), axis=1) if x.ndim == 2 else np.abs(x)
    req = np.minimum(1.0, c / np.maximum(peak, 1e-12))
    L = max(1, int(lookahead * rate))
    g = minimum_filter1d(req, size=2 * L + 1, mode='nearest')
    B = 32
    n = len(g)
    nb = (n + B - 1) // B
    gp = np.concatenate([g, np.ones(nb * B - n)]).reshape(nb, B).min(1)
    rk = 1 - math.exp(-B / (rate * release))
    sb = np.empty(nb)
    s = 1.0
    for i in range(nb):
        v = gp[i]
        s = v if v < s else s + (v - s) * rk
        sb[i] = s
    gs = np.repeat(sb, B)[:n]
    k = L // 2 * 2 + 1
    gs = np.convolve(np.pad(gs, (k // 2, k // 2), mode='edge'), np.ones(k) / k, mode='valid')
    gs = np.minimum(gs, g)
    return x * (gs[:, None] if x.ndim == 2 else gs)


def true_peak_db(x, rate=RATE, chunk=1 << 20):
    """True peak (dBTP) by 4x oversampling, chunked."""
    x = as_stereo(x)
    pk = 0.0
    for i in range(0, len(x), chunk):
        seg = x[max(0, i - 64): i + chunk + 64]
        up = signal.resample_poly(seg, 4, 1, axis=0)
        pk = max(pk, float(np.max(np.abs(up))))
    return float(db(pk))


def _kweight(rate):
    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = math.tan(math.pi * f0 / rate)
    Vh = 10 ** (G / 20)
    Vb = Vh ** 0.4996667741545416
    a0 = 1 + K / Q + K * K
    b1 = [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0]
    a1 = [1, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    f0, Q = 38.13547087602444, 0.5003270373238773
    K = math.tan(math.pi * f0 / rate)
    a2 = [1, 2 * (K * K - 1) / (1 + K / Q + K * K), (1 - K / Q + K * K) / (1 + K / Q + K * K)]
    b2 = [1, -2, 1]
    return (b1, a1), (b2, a2)


def loudness_lufs(x, rate=RATE):
    """Integrated loudness (ITU-R BS.1770-4, gated), in LUFS."""
    x = as_stereo(x)
    (b1, a1), (b2, a2) = _kweight(rate)
    y = signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=0), axis=0)
    blk, hop = int(0.4 * rate), int(0.1 * rate)
    if len(y) < blk:
        return -70.0
    sq = np.cumsum(np.concatenate([np.zeros((1, 2)), y ** 2]), axis=0)
    starts = np.arange(0, len(y) - blk + 1, hop)
    z = (sq[starts + blk] - sq[starts]) / blk           # (blocks, 2)
    zs = z.sum(1)
    lk = -0.691 + 10 * np.log10(np.maximum(zs, 1e-20))
    m = lk > -70
    if not m.any():
        return -70.0
    rel = -0.691 + 10 * np.log10(zs[m].mean()) - 10
    m2 = m & (lk > rel)
    return float(-0.691 + 10 * np.log10(zs[m2].mean()))


def master(x, lufs=-14.0, true_peak=-1.0, rate=RATE, comp=True, iterations=8):
    """Bus compression, then gain + limiter until the integrated loudness is `lufs` (+-0.15 LU)
    and the true peak is below `true_peak` dBTP. Returns (audio, report dict)."""
    x = as_stereo(x)
    if comp:
        x = compress(x, threshold_db=-16, ratio=1.8, attack=0.02, release=0.2, knee_db=8, rate=rate)
    ceiling = true_peak - 0.6
    gain_db = lufs - loudness_lufs(x, rate)
    y = x
    for _ in range(iterations):
        y = limiter(x * undb(gain_db), ceiling, rate=rate)
        L = loudness_lufs(y, rate)
        tp = true_peak_db(y, rate)
        if tp > true_peak:
            ceiling -= tp - true_peak + 0.05
            continue
        if abs(L - lufs) <= 0.15:
            break
        gain_db += lufs - L
    y = limiter(y, ceiling, rate=rate)
    rep = dict(lufs=round(loudness_lufs(y, rate), 2), true_peak_dbtp=round(true_peak_db(y, rate), 2),
               gain_db=round(float(gain_db), 2), ceiling_db=round(ceiling, 2))
    return y, rep


# ---------------------------------------------------------------- resampling

def play_sample(pcm, ratio, n_out, loop_start=-1, start=0.0, interp='hermite'):
    """Play mono `pcm` at `ratio` (source samples per output sample, constant or per-sample
    array), looping from loop_start to the end if loop_start >= 0. Returns n_out samples."""
    pcm = np.asarray(pcm, np.float64)
    n = len(pcm)
    if n == 0:
        return np.zeros(n_out)
    if np.isscalar(ratio):
        p = start + ratio * np.arange(n_out, dtype=np.float64)
    else:
        p = start + np.concatenate([[0.0], np.cumsum(np.asarray(ratio, float)[:n_out - 1])])
    if loop_start >= 0:
        ll = n - loop_start
        m = p >= n
        p[m] = loop_start + np.mod(p[m] - loop_start, ll)
        tail = np.tile(pcm[loop_start:], 3 // max(1, ll) + 1)[:3]
        valid = None
    else:
        valid = p < n - 1e-9
        p = np.where(valid, p, 0.0)
        tail = np.zeros(3)
    b = np.concatenate(([0.0], pcm, tail))
    i = p.astype(np.int64)
    f = p - i
    if interp == 'linear':
        y = b[i + 1] + (b[i + 2] - b[i + 1]) * f
    else:
        xm1, x0, x1, x2 = b[i], b[i + 1], b[i + 2], b[i + 3]
        c1 = 0.5 * (x1 - xm1)
        c2 = xm1 - 2.5 * x0 + 2 * x1 - 0.5 * x2
        c3 = 0.5 * (x2 - xm1) + 1.5 * (x0 - x1)
        y = ((c3 * f + c2) * f + c1) * f + x0
    if valid is not None:
        y = np.where(valid, y, 0.0)
    return y
