"""Star-FlyBack Remix - Song 4: a cinematic big-beat/breaks remix of Payback's song 4 (the slow
breakbeat in D minor at 135 BPM), built from the song itself as read from the user's ROM.

    PAYBACK_ROM=/path/to/Payback.gba python3 remix_song4.py OUT_BASE     # OUT_BASE.wav + OUT_BASE.mp3

Nothing of Payback is stored here: every note, sample and chord is read from $PAYBACK_ROM.
From the original: the one-bar breakbeat (sample 9, fitted to the bar and chopped for fills), the
main riff (pluck 11 over bass 12) and its chromatic walk-down, the pluck melody, the two-note
call, the D power-chord stab (21), the intro chord swells (19 F/E, 18 Dm), the drone (7), the airy
pad (8, including the breakdown's shift to E), the crash-section chord hits (15, 16), the
breakdown's E pulses and the percussion pattern (6). Ours: big-beat kick, snare and clap, hats and
cymbals, a 303-style acid line and sub that play the original bass line, a wobbling reese, brass
stabs, strings, a saw lead, a bell, timpani, risers and impacts.

Structure (135 BPM, 1 bar = 1.78 s): intro 0, build 8, drop 16, melody 32, crash 40, breakdown in
E 48, breakdown on C and build 56, drop 64 (melody) and 72 (riff, wobble), finale 80 (stabs and
melody), outro 88, final hit 96.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsp     # noqa: E402
import mix     # noqa: E402
import pbsong  # noqa: E402
import synth   # noqa: E402
from dsp import RATE  # noqa: E402
from synth import Inst  # noqa: E402

BPM = 135.0
BEAT = 60.0 / BPM
STEP = BEAT / 4
BAR = BEAT * 4
BARS = 96
TAIL = 6.0
NAT = pbsong.PAL_CLOCK / pbsong.NATIVE_PERIOD
LOG = []            # (part, time, dur, midi) of every pitched note, for the harmony check
KICKS = []          # kick times, for the sidechain check
TUNE = [0.0]        # semitones from A440 that Payback's samples sit at; our synths follow them


def T(bar, step=0.0):
    return (bar * 16 + step) * STEP


def P(m):
    """Remix pitch -> sounding MIDI (our synths are tuned to the samples)."""
    return mix.parse_note(m) + TUNE[0]


def hz(m):
    return float(dsp.midi_hz(P(m)))


def log(part, t, dur, midis):
    for m in (midis if isinstance(midis, (list, tuple)) else [midis]):
        LOG.append((part, float(t), float(dur), float(mix.parse_note(m))))


# ---------------------------------------------------------------- Payback's samples, tuned

def measure_cents(smp):
    """Tuning of a pitched sample against A440, in cents: the amplitude-weighted median of its
    strongest spectral peaks' offsets. Payback's samples sit 10-30 cents flat (they were made for
    8363 Hz and the GBA player uses the PAL 8287 Hz)."""
    x = smp.pcm().astype(np.float64)
    st = len(x) // 8 if len(x) > 4000 else 0
    seg = x[st:st + 32768]
    N = 1 << 17
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1 / NAT)
    S[(f < 25) | (f > 3000)] = 0
    guard = max(2, int(8 * N / len(seg)))
    peaks, S2 = [], S.copy()
    for _ in range(8):
        i = int(np.argmax(S2))
        if S2[i] <= 0:
            break
        a, b, c = np.log(S[i - 1:i + 2] + 1e-12)
        d = 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c else 0.0
        peaks.append(((i + d) * NAT / N, S[i]))
        S2[max(0, i - guard):i + guard] = 0
    top = max(a for _, a in peaks)
    cs = sorted((100 * (m - round(m)), a) for fr, a in peaks if a > 0.3 * top
                for m in [69 + 12 * math.log2(fr / 440.0)])
    w = np.cumsum([a for _, a in cs])
    return float(cs[int(np.searchsorted(w, w[-1] / 2))][0])


class Smp:
    """Payback sample k as an instrument: pitch = the remix's note name (tracker note plus the
    sample's measured offset), tuned to TUNE, declicked. cut: one-shots stop after dur, as the
    tracker cuts a note when the next one starts on its channel."""

    def __init__(self, o, k, pitched=True, cut=False, release=0.03, attack=0.0, decay=None):
        smp = o.sample(k)
        self.cents = measure_cents(smp) if pitched else 0.0
        root = 60 + o.tune.get(k, 0) + self.cents / 100 - TUNE[0] if pitched else 60.0
        self.si = mix.SampleInst(smp, root=root, release=release, attack=attack)
        self.cut = cut
        self.decay = decay
        self.drum = self.si.drum and not cut
        self.cache = {}

    def __call__(self, freq=None, dur=0.25, vel=1.0):
        key = (None if freq is None else round(float(freq), 3), round(dur, 4) if (self.cut or self.si.gate) else 0)
        y = self.cache.get(key)
        if y is None:
            y = self.si(freq, dur, 1.0).astype(np.float64)
            if self.cut:
                y = y[:int((dur + 0.01) * RATE)]
            if self.decay:
                y = y * np.exp(-np.arange(len(y)) / (self.decay * RATE))
            y = dsp.fade(y, 0.0015, 0.008)
            self.cache[key] = y
        return y * vel


class Break:
    """The one-bar breakbeat loop (sample 9). Recorded at about 133 BPM, it is resampled to exactly
    one bar at 135 (+26 cents), so its hits sit on the 16ths; cut into 16 slices for chops."""

    def __init__(self, o):
        pcm = o.sample(9).pcm().astype(np.float64)
        n = int(round(BAR * RATE))
        self.bar = dsp.fade(dsp.play_sample(pcm, len(pcm) / n, n), 0.001, 0.004)
        self.k = n / 16.0
        self.slices = [self.bar[int(round(i * self.k)):int(round((i + 1) * self.k))].copy() for i in range(16)]

    def chop(self, seq, sub=1):
        """One bar from slice indices, `sub` cells per 16th (None = rest)."""
        n = int(round(BAR * RATE))
        out = np.zeros(n)
        cell = self.k / sub
        for j, s in enumerate(seq):
            if s is None:
                continue
            a = int(round(j * cell))
            y = dsp.fade(self.slices[s][:int(cell)], 0.0008, 0.004)
            out[a:a + len(y)] += y[:n - a]
        return out


# ---------------------------------------------------------------- our instruments

def brass(freq, dur, vel=1.0, voices=6, detune=0.16, bright=5200.0, body=1400.0, attack=0.012, fdecay=0.2,
          release=0.16, scoop=0.3, width=0.7, rate=RATE):
    """Synth-brass stab: detuned saws scooping up into the note, a filter that blares open on the
    attack and settles, light saturation (stereo)."""
    n = int((dur + release) * rate) + 1
    t = np.arange(n) / rate
    f = freq * 2 ** (-scoop / 12 * np.exp(-t / 0.03))
    out = np.zeros((n, 2))
    for k in range(voices):
        s = (k - (voices - 1) / 2) / ((voices - 1) / 2)
        out += dsp.pan(dsp.saw(f * 2 ** (s * detune / 24), n, rate, phase0=0.17 * k + 0.05), s * width) / voices
    rise = np.clip(t / (attack * 2.0), 0, 1)
    cut = (body + (bright - body) * np.exp(-t / fdecay)) * (0.25 + 0.75 * rise)
    out = dsp.lowpass(out, np.minimum(cut, 16000), 0.9, rate=rate, block=32)
    env = dsp.adsr(n, attack, 0.25, 0.7, release, gate=dur, rate=rate)
    out = dsp.saturate(out * env[:, None] * 1.4, 1.3)
    out = dsp.highpass(out, 90, rate=rate)
    return synth._end_fade(synth._norm(out, vel), rate=rate)


def _line(notes, n, glide=0.06, gap=0.004):
    """Frequency and gate arrays of a monophonic line. notes: (t, dur, midi, vel, slide)."""
    f = np.zeros(n)
    g = np.zeros(n)
    notes = sorted(notes)
    for i, (t, d, m, v, sl) in enumerate(notes):
        a = int(t * RATE)
        if a >= n:
            break
        nxt = notes[i + 1][0] if i + 1 < len(notes) else t + d + 1.0
        bi = min(n, int(nxt * RATE))
        h = float(dsp.midi_hz(m))
        f[a:bi] = h
        if sl and i > 0:
            k = min(bi - a, int(glide * RATE))
            f[a:a + k] = np.exp(np.linspace(math.log(float(dsp.midi_hz(notes[i - 1][2]))), math.log(h), k))
        end = t + d if (i + 1 < len(notes) and notes[i + 1][4]) else min(t + d, nxt - gap)
        g[a:min(n, int(end * RATE))] = v
    first = int(notes[0][0] * RATE)
    f[:first] = f[first]
    k = int(0.003 * RATE)
    g = np.convolve(g, np.ones(k) / k, 'same')
    return f, g


def acid_line(notes, length, cutoff=260.0, env_mod=2400.0, q=5.0, decay=0.16, drive=2.4, cut_auto=None, t0=0.0):
    """303-style line rendered in one pass (continuous oscillator, no clicks between notes):
    resonant low-pass, envelope retriggered on each non-slide note, accents (vel > 1) harder.
    cut_auto: [(abs seconds, Hz)] for the base cutoff."""
    n = int(length * RATE) + 1
    f, g = _line([(t, d, m, min(v, 1.0), sl) for t, d, m, v, sl in notes], n)
    env = np.zeros(n)
    tt = np.arange(n) / RATE
    ns = sorted(notes)
    for i, (t, d, m, v, sl) in enumerate(ns):
        if sl:
            continue
        a = int(t * RATE)
        b = n
        for t2, _, _, _, sl2 in ns[i + 1:]:
            if not sl2:
                b = min(n, int(t2 * RATE))
                break
        acc = v > 1.0
        env[a:b] = (1.6 if acc else 1.0) * np.exp(-(tt[a:b] - t) / (decay * (0.7 if acc else 1.0)))
    base = dsp.automation(cut_auto, n, RATE, t0=t0, exp=True) if cut_auto else np.full(n, cutoff)
    cut = np.clip(base + env_mod * env * (base / 400.0) ** 0.5, 40, 15000)
    y = dsp.lowpass(dsp.saw(f, n), cut, q, block=32)
    y = dsp.highpass(dsp.saturate(y * 1.6, drive), 30)
    y *= g
    return y / (np.max(np.abs(y)) + 1e-9)


def sub_line(notes, length):
    """Sine sub with a touch of 2nd harmonic following the roots (one pass, click-free)."""
    n = int(length * RATE) + 1
    f, g = _line(notes, n, glide=0.03, gap=0.006)
    ph = np.cumsum(f) / RATE
    y = (np.sin(2 * np.pi * ph) + 0.1 * np.sin(4 * np.pi * ph)) * g
    return dsp.saturate(y, 0.8) / 1.05


def reese_line(notes, length, t0, cutoff=500.0, depth=2.2, q=1.6, detune=0.22):
    """Detuned-saw reese whose low-pass wobbles with an LFO locked to the bar grid. notes:
    (t, dur, midi, vel, lfo cycles per beat) with t relative to t0 (absolute start, for the LFO
    phase)."""
    n = int(length * RATE) + 1
    f, g = _line([(t, d, m, v, False) for t, d, m, v, _ in notes], n, gap=0.01)
    rate_cpb = np.zeros(n)
    ns = sorted(notes)
    for i, (t, d, m, v, r) in enumerate(ns):
        a = int(t * RATE)
        b = min(n, int(ns[i + 1][0] * RATE)) if i + 1 < len(ns) else n
        rate_cpb[a:b] = r
    rate_cpb[:int(ns[0][0] * RATE)] = ns[0][4]
    beats = (t0 + np.arange(n) / RATE) / BEAT
    lfo = 0.5 - 0.5 * np.cos(2 * np.pi * beats * rate_cpb)
    x = np.zeros(n)
    for k, d in enumerate((-detune / 2, 0.0, detune / 2)):
        x += dsp.saw(f * 2 ** (d / 12), n, phase0=0.31 * k)
    x /= 3
    x = dsp.lowpass(x, np.clip(cutoff * 2 ** (depth * lfo), 40, 12000), q, block=32)
    x = dsp.saturate(x * 1.8, 1.8) + 0.55 * np.sin(2 * np.pi * np.cumsum(f) / RATE)
    x = dsp.highpass(x, 28) * g
    return x / (np.max(np.abs(x)) + 1e-9)


def strings(chord, dur, vel=0.8, attack=0.6, release=1.4, cutoff=3200.0, warm=0.5):
    """Cinematic string pad: a supersaw section plus a warm triangle layer (stereo)."""
    fr = [hz(m) for m in chord]
    a = synth.supersaw(fr, dur, 1.0, voices=7, detune=0.22, attack=attack, release=release, cutoff=cutoff)
    b = synth.warm_pad(fr, dur, 1.0, attack=attack * 1.2, release=release, cutoff=cutoff * 0.6)
    n = max(len(a), len(b))
    out = np.zeros((n, 2))
    out[:len(a)] += a
    out[:len(b)] += warm * b
    return synth._norm(out, vel)


def swell(y, att, hold, rel, floor=0.25):
    """The intro pads' volume ramps: from `floor` up over att, hold, then down to 0 over rel."""
    n = len(y)
    t = np.arange(n) / RATE
    e = np.where(t < att, floor + (1 - floor) * t / att, 1.0)
    e = np.where(t > att + hold, np.clip(1 - (t - att - hold) / rel, 0, 1), e)
    return y * (e if y.ndim == 1 else e[:, None])


# ---------------------------------------------------------------- the original, as note lists

class Src:
    def __init__(self, o):
        self.o = o
        self.by_pos = {}
        for n in o.notes():
            pos = int(n.beat // 16)
            self.by_pos.setdefault(pos, []).append(n)

    def get(self, pos, ins=None, ch=None):
        """Notes of order position pos: (beat in the pattern 0..16, dur beats, midi, vel, ins)."""
        out = []
        for n in self.by_pos.get(pos, []):
            if ins is not None and n.ins not in ins or ch is not None and n.channel not in ch:
                continue
            out.append((n.beat - 16 * pos, max(n.dur_beats, 0.05), int(round(n.midi)), n.vel, n.ins))
        return sorted(out)


# ---------------------------------------------------------------- the arrangement

def build(out_base=None, render=True, stems=None):
    del LOG[:]
    o = mix.Original(4)
    src = Src(o)
    tuned = [measure_cents(o.sample(k)) for k in (7, 8, 11, 12, 18, 19, 21)]
    TUNE[0] = float(np.median(tuned)) / 100.0

    m = mix.Mix(BPM, bars=BARS, tail=TAIL, title=mix.remix_title(4))
    m.bus('verb', lambda x: dsp.reverb(x, decay=2.0, predelay=0.012, damp=0.55, wet_only=True), gain_db=-3,
          duck=dict(key='kick', amount=0.3, release=0.25))
    m.bus('hall', lambda x: dsp.reverb(x, decay=3.4, predelay=0.03, damp=0.5, wet_only=True), gain_db=-2)
    m.bus('echo', lambda x: dsp.delay(x, BEAT * 0.75, feedback=0.38, mix=1.0, lp=4200, hp=250) - 0.5 * x,
          gain_db=-4)

    # samples
    s_pluck = Smp(o, 11)
    s_pluck_dec = Smp(o, 11, decay=0.55)
    s_bass = Smp(o, 12, cut=True)
    s_stab = Smp(o, 21)
    s_drone = Smp(o, 7, release=0.8)
    s_air = Smp(o, 8, release=1.5, attack=0.4)
    s_air_e = Smp(o, 8, release=0.3, attack=0.4)
    s_19 = Smp(o, 19, release=0.05)
    s_18 = Smp(o, 18, release=0.05)
    s_15 = Smp(o, 15)
    s_16 = Smp(o, 16)
    s_perc = Smp(o, 6, pitched=False)
    s_snr2 = Smp(o, 2, pitched=False)
    s_snr4 = Smp(o, 4, pitched=False)
    s_noise = Smp(o, 1, pitched=False)
    brk = Break(o)

    # our instruments
    kick = Inst(synth.kick, f_start=185.0, f_end=hz('A1'), pitch_time=0.032, decay=0.42, click=0.3, drive=2.2)
    kick_big = Inst(synth.kick, f_start=150.0, f_end=hz('D1') * 1.0, pitch_time=0.06, decay=1.2, click=0.2, drive=2.6,
                    dur=1.4)
    snare = Inst(synth.snare, tone=hz('D3'), noise_decay=0.22, snap=0.72, bright=3600.0)
    clap = Inst(synth.clap, tail=0.24)
    hat = Inst(synth.hat, decay=0.04)
    ohat = Inst(synth.hat, open=True, decay=0.26)
    crash = Inst(synth.cymbal, dur=2.8)
    ride = Inst(synth.cymbal, dur=1.4, kind='ride')
    bra = Inst(brass)
    bra_long = Inst(brass, attack=0.25, fdecay=0.8, bright=3800.0, body=1800.0, release=0.6, scoop=0.1)
    bra_long_short = bra_long.with_(release=0.15)
    lead = Inst(synth.saw_lead, detune=0.12, voices=3, cutoff=3800.0, attack=0.006, release=0.12, vibrato=0.08,
                vib_delay=0.25, width=0.5)
    bell = Inst(synth.fm_bell, ratio=3.0, index=2.0, decay=1.4)        # harmonic partials only
    pluck2 = Inst(synth.pluck, cut_hi=5500.0, cut_lo=500.0, fdecay=0.06, decay=0.22, q=1.2)

    # tracks
    tk = dict(
        kick=m.track('kick', gain_db=-7.0),
        brk=m.track('break', gain_db=0.5, hp=75, drive=1.3, eq=[('peak', 320, -3.0, 1.0), ('highshelf', 7000, 2.0, 0.7)],
                    comp=dict(threshold_db=-20, ratio=3.0, attack=0.004, release=0.09), sends={'verb': 0.06}),
        snare=m.track('snare', gain_db=-3.5, sends={'verb': 0.22}),
        clap=m.track('clap', gain_db=-7.5, sends={'verb': 0.25}),
        hats=m.track('hats', gain_db=-7.0, pan=0.3),
        ohat=m.track('ohat', gain_db=-11.0, pan=-0.3, sends={'verb': 0.1}),
        ride=m.track('ride', gain_db=-14.0, pan=-0.35),
        crash=m.track('crash', gain_db=-10.0, sends={'hall': 0.12}),
        perc=m.track('perc', gain_db=-11.0, pan=0.45, hp=150, sends={'verb': 0.08}),
        roll=m.track('roll', gain_db=-12.0, sends={'verb': 0.25}),
        toms=m.track('toms', gain_db=-10.0, sends={'hall': 0.3}),
        acid=m.track('acid', gain_db=-9.0, hp=35, duck=dict(key='kick', amount=0.5, release=0.14),
                     sends={'echo': 0.05, 'verb': 0.04}),
        sub=m.track('sub', gain_db=-16.0, lp=140, duck=dict(key='kick', amount=0.85, release=0.17)),
        reese=m.track('reese', gain_db=-11.0, duck=dict(key='kick', amount=0.6, release=0.16), sends={'verb': 0.05}),
        bass12=m.track('bass12', gain_db=-17.0, hp=70, duck=dict(key='kick', amount=0.4, release=0.12)),
        pluck=m.track('pluck', gain_db=-5.0, pan=-0.2, hp=180, sends={'echo': 0.16, 'verb': 0.1}),
        lead=m.track('lead', gain_db=-12.0, hp=150, sends={'echo': 0.2, 'hall': 0.12},
                     duck=dict(key='kick', amount=0.2, release=0.12)),
        bell=m.track('bell', gain_db=-21.0, sends={'echo': 0.3, 'hall': 0.3}),
        stab=m.track('stab', gain_db=-6.0, hp=70, sends={'verb': 0.18}),
        brass=m.track('brass', gain_db=-6.5, sends={'verb': 0.16, 'hall': 0.06},
                      duck=dict(key='kick', amount=0.25, release=0.12)),
        hits=m.track('hits', gain_db=-8.0, hp=120, sends={'hall': 0.2}),
        strings=m.track('strings', gain_db=-12.0, hp=140, sends={'hall': 0.25},
                        duck=dict(key='kick', amount=0.35, release=0.2)),
        pads=m.track('pads', gain_db=-11.0, hp=90, sends={'hall': 0.25}),
        drone=m.track('drone', gain_db=-13.0, hp=35),
        air=m.track('air', gain_db=-14.0, hp=110, sends={'hall': 0.2},
                    duck=dict(key='kick', amount=0.3, release=0.2)),
        fx=m.track('fx', gain_db=-12.0, sends={'hall': 0.3}),
        pluck2=m.track('pluck2', gain_db=-17.0, pan=0.25, hp=250, sends={'echo': 0.12, 'verb': 0.08},
                       duck=dict(key='kick', amount=0.2, release=0.1)),
    )
    m.master_fx.append(lambda x: dsp.highpass(x, 22.0))
    # the E sections' reverb must not smear into the C/D sections that follow
    tk['strings'].automate('send:hall', [(0, 0.25), (T(55, 8), 0.25), (T(56) - 0.1, 0.0), (T(56) + 0.2, 0.25),
                                         (T(62, 12), 0.25), (T(64) - 0.1, 0.0), (T(64) + 0.2, 0.25)])
    for name, amt in (('air', 0.2), ('toms', 0.3)):
        tk[name].automate('send:hall', [(0, amt), (T(55), amt), (T(56) - 0.4, 0.0), (T(56) + 0.2, amt)])
    tk['brass'].automate('send:hall', [(0, 0.06), (T(55), 0.06), (T(56) - 0.1, 0.0), (T(56) + 0.2, 0.06),
                                       (T(62, 12), 0.06), (T(64) - 0.1, 0.0), (T(64) + 0.2, 0.06)])

    # ------------------------------------------------ helpers placing the original's material
    def pluck_from(pos, bar, chans=None, ins=(11,), inst=None, part='pluck', track=None, transpose=0, vel=1.0,
                   bars=4, legato=1.0):
        inst = inst or s_pluck
        track = track or tk['pluck']
        for b, d, mi, v, _ in src.get(pos, ins=set(ins), ch=chans):
            if b >= bars * 4:
                continue
            t = T(bar) + b * BEAT
            dur = d * BEAT * legato
            p = mi + transpose
            track.note(t, inst, P(p) if not isinstance(inst, Smp) else p, dur, v * vel)
            log(part, t, dur, p)
            if part == 'pluck':
                tk['pluck2'].note(t, pluck2, P(p), min(dur, 0.2), v * vel)

    def bass_notes(pos, bar, chans=(2, 3)):
        """The original bass line (sample 12) of a position: (t, dur, midi, vel) in remix time."""
        ns = src.get(pos, ins={12}, ch=set(chans))
        out = []
        for i, (b, d, mi, v, _) in enumerate(ns):
            nb = ns[i + 1][0] if i + 1 < len(ns) else b + d
            out.append((T(bar) + b * BEAT, (nb - b) * BEAT, mi, v))
        return out

    def stab(bar, vel=1.0):
        t = T(bar)
        tk['stab'].note(t, s_stab, 50, BAR * 1.02, vel)
        log('stab', t, BAR, [50, 57, 69])

    def brass_chord(t, chord, dur, vel=0.8, inst=None):
        tk['brass'].chord(t, inst or bra, [P(p) for p in chord], dur, vel)
        log('brass', t, dur, chord)

    def strings_chord(t, chord, dur, vel=0.8, track='strings', **kw):
        tk[track].clip(t, strings(chord, dur, vel, **kw), fade=0)
        log(track, t, dur, chord)

    def air(bar, midi, bars=4, vel=1.0, inst=None, end=0.0):
        t = T(bar)
        tk['air'].note(t, inst or s_air, midi, bars * BAR - end, vel)
        pcs = {72: ['C4', 'D4', 'F4', 'G4', 'A4'], 71: ['B3', 'C#4', 'E4', 'F#4', 'G#4'], 67: ['G4', 'A4', 'C4', 'D4', 'E4']}[midi]
        log('air', t, bars * BAR, pcs)

    def drone(bar, bars=4, vel=1.0):
        t = T(bar)
        tk['drone'].note(t, s_drone, 38, bars * BAR, vel)
        log('drone', t, bars * BAR, ['D2', 'A2'])

    def brk_bar(bar, vel=1.0):
        tk['brk'].clip(T(bar), brk.bar * vel, fade=0)

    def brk_chop(bar, seq, sub=1, vel=1.0):
        tk['brk'].clip(T(bar), brk.chop(seq, sub) * vel, fade=0)

    def drums(bar, kpat, snare_on=True, hats='8', vel=1.0, ride_on=False, clap_on=True):
        tk['kick'].pattern(bar, 1, kpat, kick, vel=vel)
        if snare_on:
            tk['snare'].pattern(bar, 1, '....x.......x...', snare, vel=0.95 * vel)
            if clap_on:
                tk['clap'].pattern(bar, 1, '....x.......x...', clap, vel=0.9 * vel)
        if hats == '8':
            tk['hats'].pattern(bar, 1, '..x...x...x...x.', hat, vel=0.85 * vel)
        elif hats == '16':
            tk['hats'].pattern(bar, 1, 'x.X.x.X.x.X.x.Xx', hat, vel=0.6 * vel, accent=1.5)
        if ride_on:
            tk['ride'].pattern(bar, 1, 'x...x...x...x...', ride, vel=0.8 * vel)

    def perc_from(pos, bar, bars=4, vel=1.0):
        for b, d, mi, v, ins in src.get(pos, ins={6}, ch={2}):
            if b < bars * 4:
                tk['perc'].note(T(bar) + b * BEAT, s_perc, mi, d * BEAT, v * vel)

    def snare_roll(bar0, bars, v0=0.25, v1=1.0, rates=(2, 4, 8)):
        """A roll over `bars` bars getting denser (hits per beat per stage) and louder."""
        stages = len(rates)
        per = bars / stages
        for si, r in enumerate(rates):
            nb = int(round(per * 4 * r))
            for j in range(nb):
                t = T(bar0) + si * per * BAR + j * BEAT / r
                frac = (t - T(bar0)) / (bars * BAR)
                tk['roll'].hit(t, snare, v0 + (v1 - v0) * frac)

    fx = tk['fx']

    # ------------------------------------------------ 0-8 intro: the original's swells over the drone
    drone(0, 4, 0.8)
    drone(4, 4, 0.9)
    chord_of = {(19, 53): ['F3', 'A3', 'C4'], (19, 52): ['E3', 'G#3', 'B3'], (18, 69): ['D3', 'F3', 'A3']}
    voic = {(19, 53): ['F3', 'C4', 'F4', 'A4'], (19, 52): ['E3', 'B3', 'E4', 'B4'], (18, 69): ['D3', 'A3', 'D4', 'F4']}

    def intro_swells(pos, bar, vel=1.0, strings_vel=0.55, end=None):
        for b, d, mi, v, ins in src.get(pos, ins={18, 19}):
            t = T(bar) + b * BEAT
            inst = s_19 if ins == 19 else s_18
            hold = min(4 * BEAT, (end - t) if end else 4 * BEAT)
            rel = 8 * STEP if hold >= 4 * BEAT else 0.12
            y = swell(inst(float(dsp.midi_hz(mi)), hold + rel, 1.0), 7 * STEP, hold - 7 * STEP, rel)
            tk['pads'].clip(t, y * vel, fade=0)
            log('pads', t, hold, chord_of[(ins, mi)])
            strings_chord(t, voic[(ins, mi)], hold - 0.05 - (0.3 if hold < 4 * BEAT else 0), strings_vel, attack=0.7,
                          release=0.45 if hold >= 4 * BEAT else 0.25, cutoff=2400.0)

    intro_swells(0, 0, 1.0, 0.45)
    intro_swells(1, 4, 1.0, 0.6, end=T(8))
    fx.clip(0.0, synth.impact(4.0, 0.5, freq=hz('D1')), gain_db=-6)
    for b in range(4, 8):
        brk_bar(b, 0.5)
    tk['brk'].automate('hp', [(0, 2500.0), (T(4), 2500.0), (T(8) - 0.05, 300.0), (T(8), 75.0), (T(48), 75.0),
                              (T(48) + 0.01, 75.0)])
    fx.clip(T(6), synth.riser(2 * BAR, 0.7, freq=hz('D2')), gain_db=-4)
    fx.clip(T(7), synth.reverse_cymbal(BAR, 0.6), gain_db=-6)

    # ------------------------------------------------ 8-16 build: the D stabs, the call, acid creeping in
    for b in range(8, 16):
        stab(b, 0.5 + 0.35 * (b - 8) / 7)
        brass_chord(T(b), ['D3', 'A3', 'D4', 'F4'], BEAT * 1.5, 0.3 + 0.4 * (b - 8) / 7)
        bv = 0.45 + 0.35 * (b - 8) / 7
        brk_bar(b, bv) if b != 15 else brk_chop(b, [0, 1, 2, 3, 4, 5, 6, 7, 12, 13, 12, 13, 4, 4, 4, 4], vel=bv)
    tk['kick'].pattern(8, 4, 'x.......x.......', kick, vel=0.75)
    drums(12, 'x.....x...x.....', hats='8', vel=0.75)
    drums(13, 'x.....x...x..x..', hats='8', vel=0.8)
    tk['kick'].pattern(14, 2, 'x...x...x...x...', kick, vel=0.95)
    tk['hats'].pattern(14, 2, '..x...x...x...x.', hat, vel=0.8)
    snare_roll(14, 2, 0.15, 0.8, rates=(2, 4, 8))
    strings_chord(T(8), ['D3', 'A3', 'D4', 'F4'], 8 * BAR - 0.3, 0.5, attack=4.0, release=1.2, cutoff=2600.0)
    tk['strings'].automate('gain', [(0, 0.0), (T(8) - 0.01, 0.0), (T(8), -6.0), (T(15), 0.0), (T(16), 0.0)])
    pluck_from(6, 12, chans={3}, inst=s_pluck_dec, part='call', vel=0.9)
    acid_build = []
    for b in range(12, 16):
        for s_, mi, acc in ((0, 38, 1.2), (2, 50, 1.0), (3, 38, 1.0), (6, 38, 1.0), (8, 50, 1.2), (10, 38, 1.0),
                            (11, 48, 1.0), (14, 38, 1.0)):
            acid_build.append((T(b, s_) - T(12), STEP * 1.6, mi + TUNE[0], acc, False))
    for t, d, mi, v, sl in acid_build:
        log('acid', T(12) + t, d, round(mi - TUNE[0]))
    tk['acid'].clip(T(12), acid_line(acid_build, 4 * BAR + 0.5, cut_auto=[(T(12), 120.0), (T(16), 700.0)], t0=T(12),
                                     env_mod=1600.0), fade=0)
    fx.clip(T(12), synth.riser(4 * BAR, 0.8, freq=hz('D2')), gain_db=-5)
    fx.clip(T(15), synth.reverse_cymbal(BAR, 0.8), gain_db=-4)

    # ------------------------------------------------ drop sections: the main riff
    KPAT = ['x.....x...x.....', 'x.....x...x..x..', 'x.....x...x.....', 'x.....x...x.x.x.']
    RIFF_CH = {'Dm': ['D3', 'D4', 'F4', 'A4'], 'F/C': ['C3', 'C4', 'F4', 'A4'], 'C': ['C3', 'C4', 'E4', 'G4']}

    def riff_section(bar0, positions, brass_full, wobble=False, call=False, acid_open=(500.0, 1400.0),
                     strings_vel=0.7, hats='8'):
        acid_notes, sub_notes, reese_notes = [], [], []
        for i, pos in enumerate(positions):
            bar = bar0 + 4 * i
            pluck_from(pos, bar, chans={2, 3} if pos in (12, 13, 18, 20, 22, 23) else {3})
            bn = bass_notes(pos, bar)
            for t, d, mi, v in bn:
                tk['bass12'].note(t, s_bass, mi, max(d, STEP) * 0.95, 0.9)
                log('bass12', t, d * 0.95, mi)
                acc = 1.2 if abs((t - T(bar)) / STEP % 16) < 0.01 or mi in (41, 45) else 1.0
                am = mi + (12 if wobble else 0)
                acid_notes.append((t - T(bar0), d * 0.9, am + TUNE[0], acc, False))
                log('acid', t, d * 0.9, am)
                if wobble:
                    reese_notes.append((t - T(bar0), d, mi + TUNE[0], 1.0, 2.0))
                    log('reese', t, d, mi)
                else:
                    sub_notes.append((t - T(bar0), d, mi + TUNE[0], 1.0, False))
                    log('sub', t, d, mi)
            # brass figure
            chords = ['Dm', 'Dm', 'F/C', 'C']
            hits = ([(0, 0, 0.35), (2, 0, 0.35)] if not brass_full else
                    [(0, 0, 0.35), (1, 0, 0.18), (1, 6, 0.15), (2, 0, 0.35), (3, 0, 0.2), (3, 3, 0.14), (3, 6, 0.14),
                     (3, 14, 0.22)])
            for k, s_, dur in hits:
                ch = 'Dm' if (k, s_) == (3, 14) else chords[k]
                brass_chord(T(bar + k, s_), RIFF_CH[ch], dur, 0.85 if s_ == 0 else 0.7)
            if strings_vel:
                for k, (voicing, steps) in enumerate(((['D3', 'F3', 'A3', 'D4'], 16), (['D3', 'F3', 'A3', 'D4'], 16),
                                                      (['C3', 'F3', 'A3', 'C4'], 16), (['C3', 'G3', 'C4', 'E4'], 8))):
                    strings_chord(T(bar + k), voicing, steps * STEP - 0.3, strings_vel, attack=0.08, release=0.25,
                                  cutoff=2800.0)
            for k in range(4):
                tk['kick'].pattern(bar + k, 1, KPAT[k], kick)
                drums(bar + k, '................', hats='16' if (wobble or hats == '16') else '8')
                if k == 3 and i % 2 == 1:
                    tk['ohat'].hit(T(bar + k, 14), ohat, 0.8)
            perc_from(13 if pos in (12, 13, 18, 20) else 6, bar, vel=0.8)
            if call:
                pluck_from(6, bar, chans={3}, inst=lead, part='lead', track=tk['lead'], transpose=-12, vel=0.7)
        L = 4 * len(positions) * BAR + 0.5
        tk['acid'].clip(T(bar0), acid_line(acid_notes, L, cutoff=acid_open[0],
                                           cut_auto=[(T(bar0), acid_open[0]), (T(bar0) + L, acid_open[1])], t0=T(bar0)),
                        fade=0)
        if sub_notes:
            tk['sub'].clip(T(bar0), sub_line(sub_notes, L), fade=0)
        if reese_notes:
            tk['reese'].clip(T(bar0), reese_line(reese_notes, L, T(bar0)), fade=0)

    # 16-32 drop 1
    riff_section(16, [12, 13], brass_full=True)
    riff_section(24, [12, 13], brass_full=True, call=True, acid_open=(700.0, 1800.0), hats='16')
    for b in range(16, 32):
        brk_bar(b) if b not in (23, 31) else brk_chop(b, [0, 1, 2, 3, 4, 5, 0, 1, 4, 5, 12, 13, 12, 12, 4, 4])
    fx.clip(T(16), synth.impact(3.5, 0.9, freq=hz('D1')), gain_db=-4)
    for b in (16, 24):
        tk['crash'].hit(T(b), crash, 0.9)
    fx.clip(T(31), synth.reverse_cymbal(BAR, 0.6), gain_db=-6)

    # ------------------------------------------------ melody sections (the pluck melody, pos 19)
    MEL_CH = [('Dm7', ['D3', 'A3', 'C4', 'F4'], 38), ('Csus2', ['C3', 'G3', 'C4', 'D4'], 36),
              ('Dm7', ['D3', 'A3', 'C4', 'F4'], 38), ('F/C', ['C3', 'F3', 'A3', 'C4'], 36)]
    BRASS_MEL = {'Dm7': ['D4', 'F4', 'A4', 'C5'], 'Csus2': ['C4', 'G4', 'D5'], 'F/C': ['C4', 'F4', 'A4', 'C5']}
    ACID_PAT = [(0, 0, 1.2), (2, 12, 1.0), (3, 0, 1.0), (5, 0, 1.0), (6, 12, 1.0), (8, 0, 1.2), (10, 0, 1.0),
                (11, 12, 1.0), (13, 0, 1.0), (14, 7, 1.0)]

    def melody_section(bar0, reps, lead_on=False, brass_on=True, strings_vel=0.7, mel_pos=19, mel_ch={1},
                       drums_on=True, bass_on=True, ride_on=False, air_on=True, acid_cut=(600.0, 1500.0), hats='8'):
        acid_notes, sub_notes = [], []
        for r in range(reps):
            bar = bar0 + 4 * r
            pluck_from(mel_pos, bar, chans=mel_ch)
            if lead_on:
                pluck_from(mel_pos, bar, chans=mel_ch, inst=lead, part='lead', track=tk['lead'], transpose=-12)
            if air_on:
                air(bar, 72, 4, 0.9)
            for k, (name, voicing, root) in enumerate(MEL_CH):
                tb = T(bar + k)
                if strings_vel:
                    strings_chord(tb, voicing, BAR - 0.25, strings_vel, attack=0.25, release=0.8, cutoff=3000.0)
                if brass_on:
                    brass_chord(tb, BRASS_MEL[name], 0.3, 0.75)
                    brass_chord(T(bar + k, 10), BRASS_MEL[name], 0.14, 0.55)
                if bass_on:
                    for s_, off, acc in ACID_PAT:
                        p = root + off
                        if off == 7:              # the line's last note: the chord's colour tone
                            p = root + {'Dm7': 3, 'Csus2': 7, 'F/C': 5}[name]
                        acid_notes.append((T(bar + k, s_) - T(bar0), STEP * 1.5, p + TUNE[0], acc, False))
                        log('acid', T(bar + k, s_), STEP * 1.5, p)
                    sub_notes.append((tb - T(bar0), BAR - 0.02, root + TUNE[0], 1.0, False))
                    log('sub', tb, BAR - 0.02, root)
                if drums_on:
                    tk['kick'].pattern(bar + k, 1, KPAT[k], kick)
                    drums(bar + k, '................', hats='16' if (hats == '16' and r % 2 == 1) else '8',
                          ride_on=ride_on)
            if drums_on:
                perc_from(19, bar, vel=0.8)
        L = 4 * reps * BAR + 0.5
        if bass_on:
            tk['acid'].clip(T(bar0), acid_line(acid_notes, L, cut_auto=[(T(bar0), acid_cut[0]), (T(bar0) + L, acid_cut[1])],
                                               t0=T(bar0), q=4.5, env_mod=2000.0), fade=0)
            tk['sub'].clip(T(bar0), sub_line(sub_notes, L), fade=0)

    # 32-40 melody
    melody_section(32, 2, hats='16')
    for b in range(32, 40):
        brk_bar(b) if b != 39 else brk_chop(b, [0, 1, 2, 3, 4, 5, 6, 7, 12, 13, 14, 15, 4, 5, 4, 4])
    tk['crash'].hit(T(32), crash, 0.8)

    # ------------------------------------------------ 40-48 crash section (pos 22, 23): riff + chord hits
    riff_section(40, [22, 23], brass_full=True, acid_open=(800.0, 2200.0), strings_vel=None, hats='16')
    for pos, bar in ((22, 40), (23, 44)):
        for b, d, mi, v, ins in src.get(pos, ins={15, 16, 1}):
            t = T(bar) + b * BEAT
            if ins == 1:
                tk['perc'].note(t, s_noise, mi, 0.5, 0.8)
                continue
            inst = s_15 if ins == 15 else s_16
            tk['hits'].note(t, inst, mi, 2.0, 1.0)
            ch = ['D4', 'G4', 'A4'] if ins == 15 else ['E4', 'G4', 'A4']
            log('hits', t, 1.2, ch)
            brass_chord(t, ch, 0.3, 0.8)
    for b in range(40, 48):
        brk_bar(b) if b != 47 else brk_chop(b, [0, 1, 2, 3, 4, 5, 6, 7] + [4] * 8, 1)
    tk['crash'].hit(T(40), crash, 0.9)
    fx.clip(T(47), synth.reverse_cymbal(BAR, 0.7), gain_db=-4)

    # ------------------------------------------------ 48-56 breakdown in E (pos 14): pulses, strings, timpani
    fx.clip(T(48), synth.impact(5.0, 1.0, freq=hz('E1')), gain_db=-3)
    tk['crash'].hit(T(48), crash, 0.8)
    fx.clip(T(48), synth.downlifter(2 * BAR, 0.6), gain_db=-8)
    reese_notes, sub_notes = [], []
    for rep, bar in enumerate((48, 52)):
        pulses = src.get(14, ins={12}, ch={1})
        for i, (b, d, mi, v, _) in enumerate(pulses):
            t = T(bar) + b * BEAT
            nb = pulses[i + 1][0] if i + 1 < len(pulses) else 16.0
            dur = (nb - b) * BEAT
            tk['bass12'].note(t, s_bass, mi, min(dur, 0.5), 0.9)
            last = rep == 1 and b >= 12
            tk['toms'].hit(t, synth.tom(hz('E2'), 0.5 if last else 1.1, 1.0 if b % 4 == 0 else 0.75,
                                        decay=0.3 if last else 0.8))
            reese_notes.append((t - T(48), dur * 0.97, mi + TUNE[0], 1.0, 0.5 if rep == 0 else 1.0))
            log('reese', t, dur * 0.97, mi)
            log('bass12', t, min(dur, 0.5), mi)
        air(bar, 71, 4, 1.0, inst=s_air_e, end=0.35)
        for b in range(4):
            tk['perc'].note(T(bar + b), s_snr4, 71, 0.6, 0.7)
    tk['reese'].clip(T(48), reese_line(reese_notes, 8 * BAR + 0.5, T(48), cutoff=300.0, depth=2.6), fade=0)
    strings_chord(T(48), ['E2', 'B2', 'E3', 'B3', 'E4'], 4 * BAR - 0.4, 0.75, attack=2.0, release=1.5, cutoff=2400.0)
    strings_chord(T(52), ['E2', 'B2', 'E3', 'G#3', 'B3', 'E4'], 4 * BAR - 1.0, 0.85, attack=1.0, release=0.5,
                  cutoff=3000.0)
    strings_chord(T(50), ['B3', 'E4', 'G#4', 'B4'], 6 * BAR - 1.2, 0.45, track='strings', attack=3.0, release=0.6,
                  cutoff=1600.0, warm=1.0)
    for b in range(52, 56):
        tk['brk'].clip(T(b), brk.bar * 0.8, fade=0)
        tk['snare'].hit(T(b, 8), snare, 0.85)
        tk['clap'].hit(T(b, 8), clap, 0.7)
        tk['kick'].pattern(b, 1, 'x.........x.....', kick, vel=0.85)
    tk['brk'].automate('lp', [(0, 20000.0), (T(52), 500.0), (T(56) - 0.1, 3000.0), (T(56), 20000.0), (T(60), 20000.0),
                              (T(60) + 0.01, 600.0), (T(64) - 0.05, 9000.0), (T(64), 20000.0), (T(88), 20000.0),
                              (T(92), 700.0)])
    brass_chord(T(55, 4), ['E3', 'B3', 'E4', 'G#4'], 3 * BEAT - 0.3, 0.75, inst=bra_long_short)

    # ------------------------------------------------ 56-64 back to the home colour (pos 16), then the build
    air(56, 72, 6, 1.0)
    tk['sub'].clip(T(56), sub_line([(0.0, 6 * BAR - 0.3, 36 + TUNE[0], 0.8, False)], 6 * BAR), fade=0)
    log('sub', T(56), 6 * BAR - 0.3, 36)
    strings_chord(T(56), ['C3', 'F3', 'A3', 'D4'], 6 * BAR - 0.5, 0.65, attack=1.5, release=1.0, cutoff=2600.0)
    pluck_from(19, 56, chans={1}, inst=bell, part='bell', track=tk['bell'], transpose=0, vel=0.7)
    for b in range(56, 60):
        tk['perc'].note(T(b), s_snr4, 72, 0.6, 0.6)
    strings_chord(T(62), ['F3', 'A3', 'C4', 'F4'], BAR - 0.2, 0.7, attack=0.3, release=0.2, cutoff=3000.0)
    strings_chord(T(63), ['E3', 'G#3', 'B3', 'E4'], BAR - 0.3, 0.8, attack=0.3, release=0.25, cutoff=3500.0)
    brass_chord(T(63), ['E3', 'B3', 'E4', 'G#4'], BAR - 0.3, 0.8, inst=bra_long_short)
    for b in range(60, 64):
        brk_bar(b, 0.9) if b < 63 else brk_chop(b, [0, 1, 2, 3, 4, 4, 4, 4, 12, 12, 12, 12, 4, 4, None, None])
    tk['kick'].pattern(60, 2, 'x...x...x...x...', kick, vel=0.9)
    tk['kick'].pattern(62, 1, 'x.x.x.x.x.x.x.x.', kick, vel=0.9)
    tk['kick'].pattern(63, 1, 'x.x.x.x.x.x.....', kick, vel=0.95)
    snare_roll(60, 3.75, 0.15, 1.0, rates=(1, 2, 4, 8))
    acid_b = []
    for b in range(60, 64):
        for s_, mi, acc in ((0, 38, 1.2), (2, 50, 1.0), (3, 38, 1.0), (6, 38, 1.0), (8, 50, 1.2), (10, 38, 1.0),
                            (11, 48, 1.0), (14, 38, 1.0)):
            if b == 63 and s_ >= 12:
                continue
            if b == 63 and mi == 48:
                mi = 50                   # no C under the E chord
            acid_b.append((T(b, s_) - T(60), STEP * 1.6, mi + TUNE[0], acc, False))
            log('acid', T(b, s_), STEP * 1.6, mi)
    tk['acid'].clip(T(60), acid_line(acid_b, 4 * BAR, cut_auto=[(T(60), 150.0), (T(64), 1500.0)], t0=T(60)), fade=0)
    fx.clip(T(60), synth.riser(4 * BAR - STEP * 4, 1.0, freq=hz('D2')), gain_db=-1)
    fx.clip(T(63), synth.reverse_cymbal(BAR, 0.9), gain_db=-3)

    # ------------------------------------------------ 64-80 drop 2: melody with lead, then riff with wobble
    fx.clip(T(64), synth.impact(4.0, 1.0, freq=hz('D1')), gain_db=-2)
    melody_section(64, 2, lead_on=True, strings_vel=0.55, ride_on=True, acid_cut=(800.0, 2000.0))
    for b in range(64, 72):
        brk_bar(b) if b != 71 else brk_chop(b, [0, 1, 2, 3, 4, 5, 6, 7, 12, 13, 12, 13, 4, 4, 4, 4])
    riff_section(72, [18, 20], brass_full=True, wobble=True, call=True, acid_open=(900.0, 2400.0), strings_vel=0.35)
    for b in range(72, 80):
        brk_bar(b) if b != 79 else brk_chop(b, [0, 1, 2, 3, 4, 5, 0, 1] + [4, 4, 4, 4, 4, 4, 4, 4], 1)
    for b in (64, 72):
        tk['crash'].hit(T(b), crash, 1.0)
    fx.clip(T(79), synth.reverse_cymbal(BAR, 0.8), gain_db=-4)

    # ------------------------------------------------ 80-88 finale: the stabs with the melody on top
    fx.clip(T(80), synth.impact(4.0, 0.9, freq=hz('D1')), gain_db=-3)
    melody_section(80, 2, lead_on=True, brass_on=False, strings_vel=0.45, ride_on=True, air_on=False,
                   acid_cut=(1000.0, 2600.0))
    for b in range(80, 88):
        stab(b, 0.95)
        brass_chord(T(b), ['D3', 'A3', 'D4', 'F4', 'C5'], 0.4, 0.9)
        brass_chord(T(b, 6), ['D4', 'A4', 'D5'], 0.14, 0.6)
        brass_chord(T(b, 10), ['D4', 'A4', 'D5'], 0.14, 0.65)
        brk_bar(b) if b != 87 else brk_chop(b, [0, 1, 2, 3, 4, 5, 6, 7, 12, 13, 12, 13] + [4] * 8, 1)
    tk['crash'].hit(T(80), crash, 1.0)
    tk['crash'].hit(T(84), crash, 0.8)
    fx.clip(T(87), synth.reverse_cymbal(BAR, 0.6), gain_db=-6)

    # ------------------------------------------------ 88-96 outro: melody alone, then the intro's swells
    fx.clip(T(88), synth.downlifter(2 * BAR, 0.7), gain_db=-8)
    tk['crash'].hit(T(88), crash, 0.6)
    pluck_from(28, 88, chans={0})
    air(88, 72, 4, 0.9)
    drone(88, 4, 0.7)
    drone(92, 4, 0.8)
    for k, (name, voicing, root) in enumerate(MEL_CH):
        strings_chord(T(88 + k), voicing, BAR - 0.2, 0.5, attack=0.4, release=0.9, cutoff=2600.0)
    tk['sub'].clip(T(88), sub_line([(0.0, 4 * BAR - 0.3, 38 + TUNE[0], 0.7, False)], 4 * BAR), fade=0)
    log('sub', T(88), 4 * BAR - 0.3, 38)
    for b in range(88, 92):
        brk_bar(b, 0.9)
        tk['kick'].pattern(b, 1, 'x.......x.......', kick, vel=0.8)
        tk['hats'].pattern(b, 1, '..x...x...x...x.', hat, vel=0.6)
    intro_swells(3, 92, 1.0, 0.6, end=T(96))
    brass_chord(T(95, 4), ['E3', 'B3', 'E4', 'B4'], 3 * BEAT - 0.3, 0.8, inst=bra_long_short)
    fx.clip(T(94), synth.riser(2 * BAR, 0.8, freq=hz('D2')), gain_db=-4)
    fx.clip(T(95), synth.reverse_cymbal(BAR, 0.9), gain_db=-3)

    # ------------------------------------------------ 96: the final hit on D
    tf = T(96)
    stab(96, 1.0)
    brass_chord(tf, ['D2', 'A2', 'D3', 'F3', 'A3', 'D4'], 1.6, 1.0, inst=bra.with_(release=1.0))
    strings_chord(tf, ['D2', 'A2', 'D3', 'F3', 'A3', 'D4'], 2.5, 0.8, attack=0.02, release=2.5, cutoff=3000.0)
    tk['sub'].clip(tf, sub_line([(0.0, 2.2, 26 + TUNE[0], 1.0, False)], 2.6) * np.exp(-np.arange(int(2.6 * RATE) + 1)
                                                                                          / (1.2 * RATE)), fade=0)
    log('sub', tf, 2.2, 26)
    tk['kick'].hit(tf, kick_big, 1.0)
    tk['crash'].hit(tf, crash, 1.0)
    tk['toms'].hit(tf, synth.tom(hz('D2'), 2.0, 1.0, decay=1.6))
    fx.clip(tf, synth.impact(5.5, 1.0, freq=hz('D1')), gain_db=0)
    tk['brk'].clip(tf, dsp.fade(brk.slices[0], 0.001, 0.01), fade=0)

    KICKS[:] = tk['kick'].onsets
    if not render:
        return None
    audio, rep = m.render(master=True, lufs=-14.0, true_peak=-1.4, fade_in=0.005, fade_out=1.5, stems=stems)
    if out_base:
        rep.update(m.export(audio, out_base, kbps=320))
    rep['tune_cents'] = round(TUNE[0] * 100, 1)
    return audio, rep


if __name__ == '__main__':
    base = sys.argv[1] if len(sys.argv) > 1 else 'remix_song4'
    _, report = build(base)
    print(report)
