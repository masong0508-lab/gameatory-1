"""Star-FlyBack Remix - Song 1: Payback's trance-arpeggio song as a euphoric space-racing anthem.

Everything is generated at run time from the user's own Payback ROM ($PAYBACK_ROM). Song 1 gives
the hooks (arpeggio A, arpeggio B and its canon, the octave-jumping bass riff, the bass-hit riff,
the lead riff, the octave pulse) and its own arpeggio, bass, lead, pad and percussion samples.
Drums, the rolling bass, supersaws, plucks, pads, the lead and the FX are synthesised here.

    PAYBACK_ROM=/path/Payback.gba python3 remix_song1.py OUT_BASE     # OUT_BASE.wav + .mp3

130 BPM, F# minor with the song's Phrygian G. Bars of 4/4 (one bar = 1.846 s):
    0 intro      kick, Payback percussion groove, noise pad; arpeggio A fades in (filter)
   16 verse      the original bass riff (Payback bass sample + sub), arpeggio A, dark pad
   32 build      the bass riff closes its filter, snare roll, riser, supersaw + pluck sweep, gap
   40 drop 1     arpeggio A on a big supersaw pluck over F#m G Em F#m, pumping supersaws, the
                 rolling offbeat bass arrives
   56 breakdown  pads A Em F#m G, arpeggio B as a stereo canon, its melody (augmented) on a bell
   64 build      the melody on a supersaw lead, arpeggio B pluck, kick thumps, roll, riser, gap
   72 drop 2     arpeggio B + its melody on supersaws, everything in
   88 riff       the original lead riff, bass-hit riff and octave pulse, re-produced
   96 outro      arpeggio A again, elements leave; 104: final F#m chord
"""
import dataclasses
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsp    # noqa: E402
import mix    # noqa: E402
import pbsong  # noqa: E402
import synth  # noqa: E402
from dsp import RATE  # noqa: E402
from synth import Inst  # noqa: E402

BPM = 130.0
END = 104                       # bar of the final chord
TAIL = 5.5                      # seconds after it
SECTIONS = [('intro', 0, 16), ('verse', 16, 32), ('build1', 32, 40), ('drop1', 40, 56),
            ('breakdown', 56, 64), ('build2', 64, 72), ('drop2', 72, 88), ('riff', 88, 96),
            ('outro', 96, 104), ('end', 104, 107)]

DROP = ['F#m', 'F#m', 'G', 'G', 'Em', 'Em', 'F#m', 'F#m']     # i - bII - vii - i, 2 bars each
BREAK = ['A', 'A', 'Em', 'Em', 'F#m', 'F#m', 'G', 'G']        # ends on bII: G -> F#m into the drop


def chord_of_bar(b):
    if b < 16 or 88 <= b < 96 or b >= END:
        return 'F#m'
    if b < 32:
        return ['F#m', 'Em'][(b - 16) // 4 % 2]               # the original's F# riff / E riff
    if b < 40:
        return 'F#m' if b < 36 else 'G'
    if b < 56:
        return DROP[(b - 40) % 8]
    if b < 72:
        return BREAK[(b - 56) % 8]
    if b < 88:
        return DROP[(b - 72) % 8]
    return DROP[(b - 96) % 8]


CHORD_PCS = {'F#m': (6, 9, 1), 'G': (7, 11, 2), 'Em': (4, 7, 11), 'A': (9, 1, 4)}
ROOT1 = {'F#m': 30, 'G': 31, 'Em': 28, 'A': 33}                # roots in octave 1 (MIDI)
SAW_CHORD = {'F#m': [54, 57, 61, 66], 'G': [55, 59, 62, 67], 'Em': [52, 55, 59, 64], 'A': [57, 61, 64, 69]}
PAD_CHORD = {'A': [45, 52, 57, 61, 64], 'Em': [40, 47, 52, 55, 59, 66], 'F#m': [42, 49, 54, 57, 61],
             'G': [43, 50, 55, 59, 62, 66]}
SCALE_PCS = (6, 7, 9, 11, 1, 2, 4)                             # F# Phrygian
# Payback's percussion sample 5 is noisy but pitched enough that its C#3/G#3 inflections land on
# G#/F/C against F#m; they are played a semitone lower (rhythm and accents unchanged)
PERC_REMAP = {5: {73: 72, 80: 79}}
ROLL_TONES = (185.0, 196.0, 220.0, 246.9, 277.2, 293.7, 329.6, 370.0)  # snare-roll body, up the scale


# ---------------------------------------------------------------- our instruments

def _end(x, ms=4.0):
    k = min(len(x), int(ms * RATE / 1000))
    if k > 1:
        g = np.cos(np.linspace(0, np.pi / 2, k)) ** 2
        x[-k:] *= g if x.ndim == 1 else g[:, None]
    return x


def _norm(x, vel):
    return x * (vel / (np.max(np.abs(x)) or 1.0))


def kick_drum(freq=None, dur=0.5, vel=1.0, f_end=46.25, f_start=190.0, pitch_time=0.035, decay=0.36, click=0.2,
         drive=1.0, octave=0.28, seed=11):
    """Kick tuned to F#1: a swept sine plus its octave (presence on small speakers without the
    odd harmonics a hard clip adds, whose 5th would be an A# against F#m), a click on F#6."""
    n = int(round(0.5 * RATE))
    t = np.arange(n) / RATE
    f = f_end + (f_start - f_end) * np.exp(-t / pitch_time)
    ph = 2 * np.pi * np.cumsum(f) / RATE
    x = (np.sin(ph) + octave * np.sin(2 * ph)) * np.exp(-6.9 * t / decay) * np.minimum(1, t / 0.0015 + 0.3)
    cn = dsp.highpass(dsp.noise(n, seed), 1800) * np.exp(-t / 0.0025)
    x += click * cn * 3 + click * 0.5 * np.sin(2 * np.pi * 1480.0 * t) * np.exp(-t / 0.0015)
    return _end(_norm(dsp.saturate(x, drive), vel))


def saw_pluck(freq, dur, vel=1.0, voices=7, detune=0.26, width=0.85, cut_hi=9000.0, cut_lo=650.0,
              fdecay=0.11, decay=0.55, q=1.0, seed=41):
    """Supersaw pluck (stereo): seven detuned saws, a fast falling filter, a ringing tail."""
    n = int(round((max(dur, decay) + 0.05) * RATE))
    t = np.arange(n) / RATE
    rng = np.random.default_rng(seed)
    out = np.zeros((n, 2))
    for k in range(voices):
        s = (k - (voices - 1) / 2) / ((voices - 1) / 2)
        out += dsp.pan(dsp.saw(freq * 2 ** (s * detune / 24), n, phase0=float(rng.uniform())), s * width)
    out += 0.35 * dsp.pan(dsp.square(freq * 0.5, n, pw=0.5), 0.0)
    cut = cut_lo + (cut_hi - cut_lo) * np.exp(-t / fdecay)
    out = dsp.highpass(dsp.lowpass(out, cut, q, block=32), 160)
    out *= (np.exp(-6.9 * t / decay) * np.minimum(1, t / 0.002))[:, None]
    return _end(_norm(out, vel))


def roll_bass(freq, dur, vel=1.0, cut=300.0, env_mod=1500.0, fdecay=0.05, q=1.1, sub=0.9, drive=1.5,
              release=0.012):
    """Trance rolling bass note: two saws through an enveloped low-pass plus a sine sub."""
    n = int(round((dur + release) * RATE))
    t = np.arange(n) / RATE
    osc = 0.7 * dsp.saw(freq, n) + 0.3 * dsp.saw(freq * 1.004, n, phase0=0.5)
    y = dsp.lowpass(osc, cut + env_mod * np.exp(-t / fdecay), q, block=32)
    y = dsp.saturate(1.3 * y, drive) + sub * np.sin(2 * np.pi * freq * t)
    y = dsp.highpass(y, 28)
    y *= dsp.adsr(n, 0.003, 0.08, 0.75, release, gate=dur)
    return _end(_norm(y, vel))


def declick(a, fin=0.001, fout=0.005):
    """Raised-cosine fades at both ends of a note (no steps at starts, ends or cuts)."""
    a = np.array(a, np.float64, copy=True)
    for k, rev in ((min(len(a) // 2, int(fin * RATE)), False), (min(len(a) // 2, int(fout * RATE)), True)):
        if k > 1:
            g = np.sin(np.linspace(0, np.pi / 2, k)) ** 2
            if rev:
                a[-k:] *= g[::-1] if a.ndim == 1 else g[::-1, None]
            else:
                a[:k] *= g if a.ndim == 1 else g[:, None]
    return a


def mono_low(x, f=160.0):
    """Fold the side signal below f into the middle (a mono low end for wide sounds)."""
    mid, side = (x[:, 0] + x[:, 1]) / 2, (x[:, 0] - x[:, 1]) / 2
    side = side - dsp.lowpass(dsp.lowpass(side, f), f)
    return np.stack([mid + side, mid - side], 1)


class DC:
    """Any instrument, declicked and cached."""

    def __init__(self, inst, fin=0.0004, fout=0.004):
        self.inst, self.fin, self.fout, self.cache = inst, fin, fout, {}
        self.drum = getattr(inst, 'drum', False)

    def __call__(self, freq=None, dur=0.25, vel=1.0):
        key = (None if freq is None else round(float(freq), 3), round(float(dur), 4), round(float(vel), 3))
        if key not in self.cache:
            self.cache[key] = declick(self.inst(freq, dur, vel), self.fin, self.fout).astype(np.float32)
        return self.cache[key]


def xfade_loop(smp, length=2048):
    """A copy of a looped Payback sample whose loop wraps without a step: the loop's last
    `length` samples crossfade (equal power) into the samples that precede the wrap target."""
    x = smp.data.astype(np.float64)
    n, ls = len(x), smp.loop_start
    L = min(length, (n - ls) // 3)
    th = np.linspace(0, np.pi / 2, L)
    if ls >= L:
        x[n - L:] = x[n - L:] * np.cos(th) + x[ls - L:ls] * np.sin(th)
    else:
        x[n - L:] = x[n - L:] * np.cos(th) + x[ls:ls + L] * np.sin(th)
        ls += L
    return dataclasses.replace(smp, data=x, loop_start=ls)


class Line:
    """A tracker channel: each note cuts the previous one; every note is declicked."""

    def __init__(self, track, fin=0.001, fout=0.006):
        self.track, self.fin, self.fout, self.ev = track, fin, fout, []

    def add(self, t, voice, freq, vel, gate=None, gain_db=0.0, pan=None):
        self.ev.append((t, voice, freq, round(float(vel), 2), gate, gain_db, pan))

    def flush(self):
        ev = sorted(self.ev, key=lambda e: e[0])
        for i, (t, voice, f, v, gate, g, p) in enumerate(ev):
            room = ev[i + 1][0] - t if i + 1 < len(ev) else None
            dur = gate if gate is not None else (room if room is not None else 0.6)
            a = np.asarray(voice(f, dur, v), np.float64)
            if room is not None:
                a = a[:max(2, int(round(room * RATE)))]
            self.track.clip(t, declick(a, self.fin, self.fout), gain_db=g, pan=p, fade=0)
        self.ev = []


# ---------------------------------------------------------------- the song's material

def pb_line(o, order, ch):
    """One channel of one order position: [(row, tracker midi, sample, volume 0..1)]; the
    volume is the row's Cxx when it has one, else the sample's own (Payback's semantics)."""
    out = []
    for e in o.raw_notes:
        if e.order_index == order and e.channel == ch:
            vol = e.param if e.effect == 0xC else o.song.sample(e.instrument).volume
            out.append((e.row, pbsong.period_to_midi(e.period), e.instrument, min(vol, 64) / 64.0))
    return sorted(out)


class Material:
    """Song 1's hooks and samples, read from the ROM."""
    PITCHED = (13, 14, 16, 17, 18, 19, 20, 21, 26, 28)

    def __init__(self, rom=None):
        o = self.o = mix.Original(1, rom)
        self.tune = {k: o.features[k]['tune'] for k in self.PITCHED}
        self.arp_a = pb_line(o, 6, 0)            # F#4 G4 F#4 G4 F#4 G4 G3 F#3, samples 20 19 16 17 18 17
        self.arp_b = pb_line(o, 21, 3)           # F#4 G4 B4 E4 F#4 G4 E4 F#4 (ch3 leads)
        self.arp_b_echo = pb_line(o, 21, 0)      # the same one row later (the canon)
        self.riff_f = pb_line(o, 8, 1)           # bass riff on F# (sample 14)
        self.riff_e = pb_line(o, 9, 1)           # bass riff on E
        self.lead = pb_line(o, 35, 2)            # lead riff (sample 21)
        self.hits = pb_line(o, 39, 0)            # bass-hit riff (28) with percussion (29)
        self.octave = pb_line(o, 39, 3)          # octave pulse F#2 F#3
        self.perc_a = pb_line(o, 0, 0)           # intro groove (5, 4)
        self.perc_b = pb_line(o, 4, 0)           # its variant with the G hits
        self.perc_c = pb_line(o, 14, 1)          # the later drum line (5, 4)
        self.voices = {}

    def melody(self):
        """Arpeggio B in augmentation, the breakdown / drop 2 melody, an octave up: its first
        eight 16ths become a bar of 8ths, then the first four again with the last one held.
        [(beat within 2 bars, midi, beats)]"""
        p = [self.sounding(k, midi) + 12 for row, midi, k, vol in self.arp_b[:8]]
        return [(i * 0.5, q, 0.5) for i, q in enumerate(p)] + \
               [(4.0, p[0], 0.5), (4.5, p[1], 0.5), (5.0, p[2], 1.0), (6.0, p[3], 2.0)]

    def sounding(self, k, tracker_midi):
        """Equal-tempered sounding pitch of a note of pitched sample k."""
        return int(round(tracker_midi)) + int(round(self.tune[k]))

    def voice(self, k, release=0.02, attack=0.0, loop_fix=False):
        """Payback sample k as an instrument: pitched samples take sounding pitch (tuned exactly
        to equal temperament), the others the tracker pitch (C-2 = native rate)."""
        key = (k, release, attack, loop_fix)
        if key not in self.voices:
            smp = self.o.sample(k)
            if loop_fix and smp.looped:
                smp = xfade_loop(smp)
            root = 60 + self.tune[k] if k in self.tune else 60.0
            self.voices[key] = mix.SampleInst(smp, root=root, release=release, attack=attack)
        return self.voices[key]


# ---------------------------------------------------------------- arrangement

def build(rom=None, material=None):
    mt = material or Material(rom)
    m = mix.Mix(BPM, tail=0.0, title=mix.remix_title(1))
    m.length = m.bar(END) + TAIL
    T = m.bar
    S = m.beats(0.25)                       # a 16th
    hz = lambda p: float(dsp.midi_hz(p))    # noqa: E731

    # ---------------- buses
    m.bus('verb', lambda x: mono_low(dsp.reverb(x, decay=2.6, predelay=0.02, damp=0.55, wet_only=True)), gain_db=-3,
          duck=dict(key='kick', amount=0.45, release=0.3))
    m.bus('hall', lambda x: mono_low(dsp.reverb(x, decay=5.0, predelay=0.03, damp=0.45, hp=250, wet_only=True), 220.0),
          gain_db=-2)
    m.bus('echo', lambda x: dsp.delay(x, m.beats(0.75), feedback=0.38, mix=1.0, lp=4200, hp=380) - 0.5 * dsp.as_stereo(x),
          gain_db=-5, duck=dict(key='kick', amount=0.5, release=0.25))

    # ---------------- instruments
    KICK = DC(Inst(kick_drum))
    CLAP = DC(Inst(synth.clap, tone=1108.7, tail=0.24))
    SNARE = DC(Inst(synth.snare, tone=220.0, noise_decay=0.17, snap=0.72))
    HAT = DC(Inst(synth.hat, decay=0.035))
    OHAT = DC(Inst(synth.hat, open=True, decay=0.15))
    RIDE = DC(Inst(synth.cymbal, dur=1.4, kind='ride', seed=51))
    CRASH = DC(Inst(synth.cymbal, dur=2.8, kind='crash', seed=52), fout=0.05)
    BASS = DC(Inst(roll_bass))
    SUB = DC(Inst(synth.sub_bass, release=0.04, drive=0.5), fin=0.002)
    PLUCK = DC(Inst(saw_pluck), fin=0.001)
    PLUCK_SOFT = DC(Inst(saw_pluck, cut_hi=4500.0, decay=0.45, detune=0.2), fin=0.001)
    SAWCH = DC(Inst(synth.supersaw, voices=7, detune=0.3, attack=0.012, decay=0.5, sustain=0.85, release=0.3,
                    cutoff=10000.0), fin=0.002, fout=0.02)
    SAWPAD = DC(Inst(synth.supersaw, voices=7, detune=0.22, attack=0.9, decay=1.0, sustain=0.9, release=1.6,
                     cutoff=2600.0), fin=0.002, fout=0.05)
    WARM = DC(Inst(synth.warm_pad, attack=1.2, release=2.0, cutoff=1500.0), fin=0.002, fout=0.05)
    LEAD = DC(Inst(synth.saw_lead, voices=7, detune=0.22, width=0.9, cutoff=5000.0, q=0.8, attack=0.006,
                   decay=0.3, sustain=0.72, release=0.2, vibrato=0.09, vib_delay=0.3), fin=0.002, fout=0.01)
    BELL = DC(Inst(synth.fm_bell, ratio=3.0, index=0.8, decay=1.4), fin=0.001, fout=0.02)

    # ---------------- tracks (created in mix order)
    kick = m.track('kick', gain_db=-1.5)
    clap = m.track('clap', gain_db=-3.5, hp=180, sends={'verb': 0.18})
    snare = m.track('snare', gain_db=-8, hp=160, sends={'verb': 0.15})
    roll = m.track('roll', gain_db=-13, hp=200, sends={'verb': 0.22})
    hats = m.track('hats', gain_db=-13, pan=0.15, hp=5000)
    ohats = m.track('ohats', gain_db=-12, pan=-0.1, hp=4500, sends={'verb': 0.05})
    ride = m.track('ride', gain_db=-18, pan=0.25, hp=3000)
    crash = m.track('crash', gain_db=-15, hp=500, sends={'verb': 0.15})
    perc = m.track('pb_perc', gain_db=-19, pan=-0.3, hp=180, lp=7500, eq=[('peak', 2000, -4.0, 1.0)], sends={'verb': 0.08},
                   fx=[lambda x: dsp.lowpass(x, 7500)])
    bass = m.track('bass', gain_db=-6.5, duck=dict(key='kick', amount=0.85, release=0.09, hold=0.01))
    sub = m.track('sub', gain_db=-16, lp=180, duck=dict(key='kick', amount=0.9, release=0.12))
    pbbass = m.track('pb_bass', gain_db=-11, lp=2600, hp=35, duck=dict(key='kick', amount=0.8, release=0.1))
    chords = m.track('chords', gain_db=-4, hp=170, eq=[('peak', 650, -2.5, 0.8), ('highshelf', 8000, 2.0, 0.7)], sends={'verb': 0.16},
                     duck=dict(key='kick', amount=0.65, release=0.24), fx=[mono_low])
    pads = m.track('pads', gain_db=-22, hp=90, width=0.6, sends={'hall': 0.3}, duck=dict(key='kick', amount=0.35, release=0.3),
                   fx=[mono_low])
    pluck = m.track('pluck', gain_db=-8, hp=200, eq=[('peak', 800, -2.0, 1.0)], sends={'verb': 0.15, 'echo': 0.22}, duck=dict(key='kick', amount=0.35, release=0.15),
                    fx=[mono_low])
    pbarp = m.track('pb_arp', gain_db=-10, pan=-0.2, hp=150, lp=10000, sends={'verb': 0.15, 'echo': 0.3},
                    duck=dict(key='kick', amount=0.25, release=0.15))
    pbarpb = m.track('pb_arp_b', gain_db=-12, hp=150, lp=10000, sends={'hall': 0.25, 'echo': 0.25},
                     duck=dict(key='kick', amount=0.25, release=0.15))
    lead = m.track('lead', gain_db=-13, hp=150, eq=[('peak', 900, -1.5, 1.0), ('peak', 2200, -3.5, 0.8),
                                                     ('highshelf', 8000, 1.5, 0.7)], sends={'verb': 0.2, 'echo': 0.18},
                   duck=dict(key='kick', amount=0.3, release=0.15), fx=[mono_low])
    bell = m.track('bell', gain_db=-14.5, hp=200, lp=3200, sends={'hall': 0.35, 'echo': 0.3})
    pbpad = m.track('pb_pad', gain_db=-20, hp=60, lp=3000, sends={'hall': 0.3})
    atmos = m.track('atmos', gain_db=-25, hp=400, lp=9000, width=0.8, sends={'hall': 0.3}, fx=[mono_low])
    pblead = m.track('pb_lead', gain_db=-9, hp=90, lp=7000, pan=0.15, sends={'verb': 0.12, 'echo': 0.15},
                     duck=dict(key='kick', amount=0.3, release=0.12))
    pbhits = m.track('pb_hits', gain_db=-11, hp=40, lp=5000, pan=-0.05, duck=dict(key='kick', amount=0.5, release=0.1))
    pboct = m.track('pb_oct', gain_db=-14.5, pan=-0.25, hp=120, lp=8000, sends={'echo': 0.2})
    fx = m.track('fx', gain_db=-15, sends={'verb': 0.25}, fx=[mono_low])
    impact = m.track('impact', gain_db=-13, sends={'hall': 0.15}, fx=[mono_low])

    # ---------------- drums
    def beats(b0, b1, fn):
        for b in range(b0, b1):
            for q in range(4):
                fn(b, q)

    for b0, b1 in ((0, 38), (40, 56), (64, 72), (72, 104)):
        def k_(b, q):
            if (b, q) == (71, 3):
                return
            kick.hit(T(b, q), KICK, 0.8 if 64 <= b < 68 else 0.84 if b < 8 else 0.92 if b < 16 else 1.0)
        beats(b0, b1, k_)
    kick.hit(T(END), KICK, 1.0)
    # build 2 starts with filtered kick thumps that open up
    kick.automate('hp', [(0, 20), (T(64) - 0.01, 20), (T(64), 260), (T(68) - 0.3, 120), (T(68), 20), (T(200), 20)])

    for b0, b1, v in ((12, 16, 0.7), (16, 32, 1.0), (40, 56, 1.0), (72, 100, 1.0)):
        for b in range(b0, b1):
            for q in (1, 3):
                clap.hit(T(b, q), CLAP, v)
                snare.hit(T(b, q), SNARE, 0.8 * v)

    def hat_bars(b0, b1, v=1.0, opens=True):
        for b in range(b0, b1):
            for q in range(4):
                for s, hv in ((0, 0.5), (1, 0.3), (2, 0.42), (3, 0.36)):
                    if s == 2 and opens:
                        continue
                    hats.hit(T(b, q + s / 4), HAT, hv * v)
    hat_bars(4, 8, 0.6, opens=False)
    hat_bars(8, 38, 1.0)
    hat_bars(40, 56)
    hat_bars(68, 72, 0.8, opens=False)
    hat_bars(72, 100)
    hat_bars(100, 102, 0.7, opens=False)
    for b0, b1 in ((8, 36), (40, 56), (72, 102)):
        for b in range(b0, b1):
            for q in range(4):
                ohats.hit(T(b, q + 0.5), OHAT, 0.85)
    for b in list(range(48, 56)) + list(range(72, 96)):
        for q in range(4):
            ride.hit(T(b, q), RIDE, 0.7 if q % 2 else 0.9)
    for b in (16, 40, 48, 72, 80, 88, 96):
        crash.hit(T(b), CRASH, 1.0)
    crash.hit(T(56), CRASH, 0.9)
    crash.hit(T(END), CRASH, 1.0)

    # fills (snare 16ths into a phrase) and the two build rolls
    for b, q0 in ((31, 2), (47, 3), (55, 2), (79, 3), (87, 3), (95, 3)):
        for i in range(int((4 - q0) * 4)):
            roll.hit(T(b, q0 + i / 4), SNARE, 0.45 + 0.5 * i / max(1, (4 - q0) * 4 - 1))

    def snare_roll(b0, b1, end_beat):
        """Quarters, 8ths, 16ths, 32nds over [b0, b1), rising in level and pitch."""
        n_bars = b1 - b0
        t_end = T(b1 - 1, end_beat)
        b = b0
        while True:
            frac = (b - b0) / n_bars
            step = 1.0 if frac < 0.25 else 0.5 if frac < 0.5 else 0.25 if frac < 0.8 else 0.125
            t = T(b0) + m.beats((b - b0) * 4)
            if t >= t_end - 1e-6:
                break
            tone = ROLL_TONES[min(len(ROLL_TONES) - 1, int(frac * len(ROLL_TONES)))]
            roll.hit(t, DC(Inst(synth.snare, tone=tone, noise_decay=0.12, snap=0.75)),
                     0.25 + 0.75 * frac ** 1.5)
            b += step / 4
    snare_roll(32, 40, 3.0)
    snare_roll(66, 72, 3.0)
    roll.automate('hp', [(0, 200), (T(32), 200), (T(39, 3), 900), (T(40), 200), (T(66), 200), (T(71, 3), 900),
                         (T(72), 200), (T(200), 200)])

    # Payback's own percussion groove (samples 5 and 4) as colour
    pl = Line(perc)
    for b0, b1, src, v in ((0, 8, mt.perc_a, 0.9), (8, 16, mt.perc_b, 0.9), (16, 32, mt.perc_c, 0.7),
                           (40, 56, mt.perc_c, 0.6), (72, 88, mt.perc_c, 0.6), (96, 100, mt.perc_a, 0.7)):
        for rep in range(0, b1 - b0, 4):
            for row, midi, k, vol in src:
                b = b0 + rep + row // 16
                if b < b1:
                    p = PERC_REMAP.get(k, {}).get(int(round(midi)), midi)
                    pl.add(T(b, (row % 16) / 4), mt.voice(k), hz(p), v * vol ** 0.7)
    pl.flush()

    # ---------------- bass
    def rolling(b0, b1, stop=None):
        """Rolling offbeat bass on the chord roots: the three 16ths after each kick, the last of
        beats 2 and 4 an octave up."""
        for b in range(b0, b1):
            r = ROOT1[chord_of_bar(b)]
            for q in range(4):
                for s in (1, 2, 3):
                    t = T(b, q + s / 4)
                    if stop is not None and t >= stop - 1e-6:
                        continue
                    p = r + 12 if (s == 3 and q in (1, 3)) else r
                    bass.note(t, BASS, p, S * 0.78, 0.9 if s == 1 else 0.8)
    rolling(40, 56)                         # the rolling bass arrives with each drop
    rolling(72, 88)
    rolling(96, 100)

    # the original octave-jumping riff on Payback's bass sample (an octave up, as the analysis
    # suggests) with our sub under its low notes; it runs into the build, closing its filter
    bl = Line(pbbass, fout=0.008)
    sl = Line(sub, fin=0.003, fout=0.01)
    for b0 in range(16, 36, 4):
        src = mt.riff_f if chord_of_bar(b0) == 'F#m' else mt.riff_e
        for row, midi, k, vol in src:
            t = T(b0 + row // 16, (row % 16) / 4)
            p = mt.sounding(k, midi) + 12
            bl.add(t, mt.voice(14), hz(p), vol ** 0.6)
            if p < 43:      # F#1 / E1 / F#2 / E2: double an octave down at most to octave 1
                sl.add(t, SUB, hz(p if p < 36 else p - 12), 0.85, gate=S * (2.6 if (row % 16) in (0, 12) else 0.9))
    bl.flush()
    sl.flush()
    pbbass.automate('lp', [(0, 2600), (T(32), 2600), (T(36), 500), (T(200), 500)])
    sub.automate('gain', [(0, 0), (T(32), 0), (T(36), -12), (T(36) + 0.5, 0), (T(200), 0)])

    # ---------------- chords and pads
    def saw_chords(b0, b1, vel=0.9, stop=None):
        for b in range(b0, b1, 2):
            dur = m.bar(2) - 0.03
            if stop is not None:
                dur = min(dur, stop - T(b))
            chords.chord(T(b), SAWCH, SAW_CHORD[chord_of_bar(b)], dur, vel)
    saw_chords(32, 40, 0.65, stop=T(39, 3))
    saw_chords(40, 56)
    saw_chords(64, 72, 0.8, stop=T(71, 3))
    saw_chords(72, 88)
    saw_chords(96, 102, 0.75)
    chords.automate('lp', [(0, 450), (T(32), 450), (T(39, 3), 9000), (T(40), 20000), (T(57), 20000), (T(64), 600),
                           (T(71, 3), 9000), (T(72), 20000), (T(96), 20000), (T(102), 900), (T(END) - 0.01, 900),
                           (T(END), 7000), (T(END) + 4.0, 1500), (T(200), 1500)])
    chords.chord(T(END), DC(Inst(synth.supersaw, voices=7, detune=0.3, attack=0.01, decay=0.8, sustain=0.7,
                                  release=2.6, cutoff=6000.0), fin=0.002, fout=0.05),
                 SAW_CHORD['F#m'], 0.6, 0.9)

    for b in range(56, 72, 2):
        c = chord_of_bar(b)
        pads.chord(T(b), WARM, PAD_CHORD[c], m.bar(2) - 0.05, 0.9)
        pads.chord(T(b), SAWPAD, PAD_CHORD[c][1:], m.bar(2) - 0.05, 0.7)
    for b in range(16, 32, 4):      # soft bed under the verse
        pads.chord(T(b), WARM, PAD_CHORD[chord_of_bar(b)], m.bar(4) - 0.05, 0.5)
    pads.chord(T(END), DC(Inst(synth.warm_pad, attack=0.05, release=3.0, cutoff=1800.0), fin=0.002, fout=0.05),
               PAD_CHORD['F#m'], 1.0, 0.9)
    pads.automate('gain', [(0, 0), (T(56), 0), (T(71, 3), 0), (T(72), -6), (T(200), -6)])
    sub.note(T(END), SUB, 30, 1.2, 0.9)

    # Payback's dark pad (13) on the verse roots, swelling like the original's EA/EB slides
    pv = mt.voice(13, release=0.6, attack=1.0, loop_fix=True)
    for b0 in range(16, 32, 4):
        p = 30 if chord_of_bar(b0) == 'F#m' else 28
        pbpad.note(T(b0), pv, p + 12, m.bar(4) - 0.6, 0.8)
    for b in range(56, 64, 2):
        pbpad.note(T(b), pv, ROOT1[chord_of_bar(b)] + 12, m.bar(2) - 0.6, 0.6)

    # noise pads 8 and 2 as air (loops crossfaded)
    n8 = mt.voice(8, release=2.0, attack=3.0, loop_fix=True)
    n2 = mt.voice(2, release=2.0, attack=2.0, loop_fix=True)
    atmos.note(T(0), n8, 72, m.bar(15), 0.8)
    atmos.note(T(56), n8, 72, m.bar(15), 0.8)
    atmos.note(T(88), n2, 72, m.bar(14), 0.6)
    atmos.automate('lp', [(0, 1200), (T(14), 9000), (T(18), 9000), (T(56), 2500), (T(70), 9000), (T(74), 9000),
                          (T(88), 4000), (T(200), 4000)])

    # ---------------- the hooks
    def vel_curve(vol):
        return vol ** 0.6                     # keep the hook's accents (64/16/8/48), less extreme

    def arp_a(b0, b1, payback=True, pluck_vel=None, stop=None):
        """Arpeggio A (Payback channel 0, order 6): the samples cycle 20 19 16 17 18 17 per half
        bar, a slow filter movement that is part of the hook."""
        pa = Line(pbarp)
        for rep in range(0, b1 - b0, 4):
            for row, midi, k, vol in mt.arp_a:
                b = b0 + rep + row // 16
                t = T(b, (row % 16) / 4)
                if b >= b1 or (stop is not None and t >= stop - 1e-6):
                    continue
                p = mt.sounding(k, midi)
                if payback:
                    pa.add(t, mt.voice(k), hz(p), vel_curve(vol))
                if pluck_vel:
                    pluck.note(t, PLUCK, p + 12, S, pluck_vel * (0.55 + 0.45 * vel_curve(vol)))
        pa.flush()

    def arp_b(b0, b1, payback=True, pluck_vel=None, stop=None, pv=1.0, inst=None):
        """Arpeggio B (order 21): channel 3 leads (left), channel 0 echoes it a row later (right)."""
        la, lb = Line(pbarpb), Line(pbarpb)
        for rep in range(0, b1 - b0, 4):
            for src, line, pan, lead_line in ((mt.arp_b, la, -0.5, True), (mt.arp_b_echo, lb, 0.5, False)):
                for row, midi, k, vol in src:
                    b = b0 + rep + row // 16
                    t = T(b, (row % 16) / 4)
                    if b >= b1 or (stop is not None and t >= stop - 1e-6):
                        continue
                    p = mt.sounding(k, midi)
                    if payback:
                        line.add(t, mt.voice(k), hz(p), pv * vel_curve(vol) * (1.0 if lead_line else 0.8), pan=pan)
                    if pluck_vel and lead_line:
                        pluck.note(t, inst or PLUCK, p + 12, S, pluck_vel * (0.6 + 0.4 * vel_curve(vol)))
        la.flush()
        lb.flush()

    arp_a(8, 32)
    arp_a(32, 40, pluck_vel=0.8, stop=T(39, 3))
    arp_a(40, 56, pluck_vel=1.0)
    arp_a(96, 104, pluck_vel=0.7)
    pbarp.automate('lp', [(0, 350), (T(8), 350), (T(16), 9000), (T(96), 9000), (T(104), 700), (T(200), 700)])
    pluck.automate('lp', [(0, 500), (T(32), 500), (T(39, 3), 12000), (T(40), 20000), (T(57), 20000), (T(64), 600),
                          (T(71, 3), 12000), (T(72), 20000), (T(96), 20000), (T(104), 900), (T(200), 900)])
    # the last arpeggio note rings out over the final chord
    pbarp.note(T(END), DC(mt.voice(20), 0.001, 0.006), 66, 0.3, 0.8)

    arp_b(56, 64, pv=0.8)
    arp_b(64, 72, pluck_vel=0.75, stop=T(71, 3), inst=PLUCK_SOFT)
    arp_b(72, 88, pluck_vel=0.65)
    pbarpb.automate('gain', [(0, 0), (T(72) - 0.01, 0), (T(72), -1.5), (T(200), -1.5)])
    pbarpb.automate('lp', [(0, 2600), (T(56), 2600), (T(64), 2600), (T(72), 8000), (T(200), 8000)])

    tune_ = mt.melody()

    def melody(b0, b1, track, inst, octaves=(0,), vel=0.9, stop=None):
        for b in range(b0, b1, 2):
            for beat, p, d in tune_:
                t = T(b) + m.beats(beat)
                if stop is not None and t >= stop - 1e-6:
                    continue
                for o_ in octaves:
                    track.note(t, inst, p + o_, m.beats(d) * 0.92, vel * (1.0 if o_ == 0 else 0.7))
    melody(60, 64, bell, BELL, octaves=(-12,), vel=0.8)
    melody(64, 72, lead, LEAD, octaves=(0,), vel=0.8, stop=T(71, 3))
    melody(72, 88, lead, LEAD, octaves=(0, -12), vel=0.95)
    lead.automate('lp', [(0, 700), (T(64), 700), (T(71, 3), 14000), (T(200), 14000)])

    # ---------------- the lead-riff section: the original's last part, re-produced
    ll = Line(pblead, fout=0.006)
    hl = Line(pbhits, fout=0.008)
    ol = Line(pboct)
    sl = Line(sub, fin=0.003, fout=0.01)
    for b0 in range(88, 96, 4):
        for row, midi, k, vol in mt.lead:
            ll.add(T(b0 + row // 16, (row % 16) / 4), mt.voice(21, release=0.01), hz(mt.sounding(k, midi) + 12),
                   vol ** 0.5)
        for row, midi, k, vol in mt.hits:
            t = T(b0 + row // 16, (row % 16) / 4)
            if k in mt.tune:
                p = mt.sounding(k, midi)
                hl.add(t, mt.voice(k), hz(p), vol ** 0.5)
                sl.add(t, SUB, hz(p - 12), 0.8, gate=S * 1.6)
            else:
                hl.add(t, mt.voice(k), hz(midi), 0.7 * vol ** 0.5)
        for row, midi, k, vol in mt.octave:
            ol.add(T(b0 + row // 16, (row % 16) / 4), mt.voice(k), hz(mt.sounding(k, midi)), vol ** 0.6)
    ll.flush()
    hl.flush()
    ol.flush()
    sl.flush()
    # our saw lead doubles the riff two octaves up, quietly, in the second half
    dbl = DC(Inst(synth.saw_lead, voices=3, detune=0.1, cutoff=4200.0, attack=0.004, decay=0.1, sustain=0.6,
                  release=0.06), fin=0.002, fout=0.006)
    for row, midi, k, vol in mt.lead:
        lead.note(T(92 + row // 16, (row % 16) / 4), dbl, mt.sounding(k, midi) + 24, S * 0.85, 0.45 * vol ** 0.5)

    # ---------------- transitions
    def riser(b0, b1, stop_beat=3.0):
        d = T(b1 - 1, stop_beat) - T(b0)
        fx.clip(T(b0), synth.riser(d, 1.0, freq=92.5, f0=220, f1=9000, tone=0.3), gain_db=-2)
        rc = synth.reverse_cymbal(m.beats(3))
        fx.clip(T(b1) - len(rc) / RATE, rc, gain_db=-3)
    riser(32, 40)
    riser(64, 72)
    for b in (40, 72):
        impact.clip(T(b), synth.impact(3.5, freq=46.25))
    impact.clip(T(56), synth.impact(4.0, freq=46.25), gain_db=-2)
    impact.clip(T(END), synth.impact(4.5, freq=46.25))
    fx.clip(T(56), synth.downlifter(m.bar(2)), gain_db=-4)
    fx.clip(T(88) - m.bar(1), synth.reverse_cymbal(m.bar(1)), gain_db=-6)
    fx.clip(T(16) - m.bar(1), synth.noise_sweep(m.bar(1), f0=400, f1=9000), gain_db=-8)
    fx.clip(T(96), synth.downlifter(m.bar(2)), gain_db=-8)
    # Payback's long noise one-shot (7) as a texture on the big downbeats
    for b in (40, 72):
        fx.clip(T(b), declick(mt.voice(7)(None, 1.0, 0.6), 0.001, 0.05), gain_db=-6)

    m.master_fx.append(lambda x: dsp.highpass(x, 22))
    return m


def bar_times():
    sp = 4 * 60.0 / BPM
    return {name: (b0 * sp, b1 * sp) for name, b0, b1 in SECTIONS}


def main(argv):
    out = argv[1] if len(argv) > 1 else 'remix_song1'
    m = build()
    stems = None
    if '--stems' in argv:
        class _Keep(dict):
            def __setitem__(self, k, v):
                if k in ('kick', 'bass', 'sub', 'pb_bass'):
                    super().__setitem__(k, v)
        stems = _Keep()
    audio, rep = m.render(master=True, lufs=-14.0, true_peak=-1.2, fade_out=0.8, stems=stems)
    rep.update(m.export(audio, out, kbps=320))
    if stems is not None:
        np.savez(out + '_stems.npz', **{k: v.mean(1).astype(np.float32) for k, v in stems.items()})
    rep['sections'] = bar_times()
    print(json.dumps(rep, indent=1, default=str))


if __name__ == '__main__':
    main(sys.argv)
