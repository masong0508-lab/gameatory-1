"""Payback song 0 as data and as faithful audio, read from $PAYBACK_ROM at run time (nothing stored).

nominal_song(): the song with the 0.1 s speed hiccups (F01/F07/F04 at rows 56-58 of patterns 9 and 10)
flattened to F04 and the start speed set to 8, so that every order position is a whole number of bars
of 128 ticks (a bar = 32 rows at speed 4 = 2.56 s at 93.75 BPM).

play(): Payback's own sequencer (render.sequence) drives my mixer, which plays only the chosen samples
(`sel`) at the original pitch and volume (voices of other samples still run, so channel stealing is
exactly the original's), on 4x oversampled sample data with seam-free loops, and returns one mono
array per channel on the nominal timeline (tick = exactly 20 ms).
"""
import math
import os
import sys

import numpy as np
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import mix  # noqa: E402
import pbsong  # noqa: E402
import render  # noqa: E402

RATE = 44100
UP = 4
TICK = 0.02
SCALE = 0.02 / (1.0 / render.GAME_CALL_RATE)     # nominal seconds per sequencer second (1.00007)


def nominal_song(rom):
    s = pbsong.load(rom, 0)
    for p in s.patterns.values():
        for cells in p:
            for c in cells:
                if c.effect == 0xF and c.param in (1, 7):
                    c.param = 4
    s.speed = 8
    return s


class Data:
    """The song's note events and section map on the nominal timeline."""

    def __init__(self, rom):
        self.song = nominal_song(rom)
        self.steps, self.rows, notes, self.ended, total = render.sequence(self.song, 'payback')
        self.total = total * SCALE
        self.notes = notes
        for e in notes:
            e.time *= SCALE
            e.duration *= SCALE
        self.feat = {s.number: mix.describe_sample(s) for s in self.song.samples if s.length}
        self.tune = {}
        for k, f in self.feat.items():
            self.tune[k] = (round(f['tune']) if f and f['tune'] is not None and f['pitch_conf'] > 0.6
                            and not f['chord'] else 0)
            if f and f['chord']:
                self.tune[k] = (f['chord'][0] + 6) % 12 - 6
        self.start = {}
        for r in self.rows:
            if r.row == 0 and r.order_index not in self.start:
                self.start[r.order_index] = r.time * SCALE

    def midi(self, e):
        return pbsong.period_to_midi(e.period) + self.tune.get(e.instrument, 0)

    def bar_of(self, oi):
        return int(round(self.start[oi] / 2.56))

    def events(self, orders=None, channel=None, ins=None, min_vol=1):
        out = []
        for e in self.notes:
            if orders is not None and e.order_index not in orders:
                continue
            if channel is not None and e.channel != channel:
                continue
            if ins is not None and e.instrument not in ins:
                continue
            if e.volume < min_vol:
                continue
            out.append(e)
        return out


class _Bank:
    def __init__(self, song):
        self.song = song
        self.c = {}

    def get(self, k):
        if k in self.c:
            return self.c[k]
        s = self.song.sample(k)
        pcm = s.pcm().astype(np.float64)
        if s.looped:
            pre, lp = pcm[:s.loop_start], pcm[s.loop_start:]
            tiled = np.concatenate([pre, np.tile(lp, 8)])
            up = resample_poly(tiled, UP, 1)
            ls = (len(pre) + 2 * len(lp)) * UP
            up = up[:(len(pre) + 6 * len(lp)) * UP]
            n = len(up)
            tail = up[ls:ls + 3]
        else:
            up, ls = resample_poly(pcm, UP, 1), -1
            n = len(up)
            tail = np.zeros(3)
        buf = np.concatenate(([0.0], up, tail))
        self.c[k] = (buf, n, ls, (n - ls) if ls >= 0 else 0)
        return self.c[k]


class _Voice:
    def __init__(self):
        self.on = False
        self.buf = None
        self.n = self.ls = self.ll = 0
        self.pos = 0.0

    def start(self, prep, offset):
        self.buf, self.n, self.ls, self.ll = prep
        self.pos = float(offset) * UP
        self.on = self.n > 0 and self.pos < self.n

    def seek(self, offset):
        if self.buf is not None:
            self.pos = float(offset) * UP
            self.on = self.pos < self.n

    def render(self, n, inc):
        inc = inc * UP
        p = self.pos + inc * np.arange(n, dtype=np.float64)
        valid = None
        if self.ls >= 0:
            m = p >= self.n
            if m.any():
                p[m] = self.ls + np.mod(p[m] - self.ls, self.ll)
            np_ = self.pos + inc * n
            self.pos = np_ if np_ < self.n else self.ls + math.fmod(np_ - self.ls, self.ll)
        else:
            valid = p < self.n
            if not valid.all():
                p = np.where(valid, p, 0.0)
            self.pos += inc * n
            if self.pos >= self.n:
                self.on = False
        i = p.astype(np.int64)
        f = p - i
        b = self.buf
        xm1, x0, x1, x2 = b[i], b[i + 1], b[i + 2], b[i + 3]
        c1 = 0.5 * (x1 - xm1)
        c2 = xm1 - 2.5 * x0 + 2 * x1 - 0.5 * x2
        c3 = 0.5 * (x2 - xm1) + 1.5 * (x0 - x1)
        y = ((c3 * f + c2) * f + c1) * f + x0
        if valid is not None:
            y = np.where(valid, y, 0.0)
        return y


def play(data, groups, rate=RATE, gain=0.5, tail=3.5):
    """groups: {name: set of sample numbers}. Returns {name: {channel: mono float32}} (one sequencer
    pass; every group is mixed in the same loop so the voices are stepped only once)."""
    song = data.song
    bank = _Bank(song)
    steps = data.steps
    nsteps = len(steps)
    n_total = int(round((nsteps * TICK + tail) * rate)) + 1
    names = list(groups)
    out = {g: {k: np.zeros(n_total, np.float32) for k in range(4)} for g in names}
    voices = [_Voice() for _ in range(4)]
    vols = [0.0] * 4
    freqs = [0.0] * 4
    cur = [0] * 4
    ramp_n = max(1, int(render.RAMP * rate))
    fade_n = max(1, int(render.FADE * rate))
    fade_ramp = np.linspace(1.0, 0.0, fade_n, endpoint=False)
    gsel = {k: [g for g in names if k_in(groups[g], k)] for k in range(0, 32)}
    t_idx = 0
    for si, (t, secs, outs) in enumerate(steps):
        ticks = max(1, int(round(secs / (1.0 / render.GAME_CALL_RATE))))
        a = int(round(t_idx * TICK * rate))
        b = min(int(round((t_idx + ticks) * TICK * rate)), n_total)
        t_idx += ticks
        n = b - a
        if n <= 0:
            continue
        for k in range(4):
            trig, freq, vol, stop, ins = outs[k]
            v = voices[k]
            if trig is not None and trig[0] == 'seek':
                v.seek(trig[1])
                trig = None
            if (trig is not None or stop) and v.on and vols[k] > 0:
                gs = gsel.get(cur[k], [])
                if gs:
                    m = min(fade_n, n_total - a)
                    y = v.render(m, freqs[k] / rate) * (vols[k] / 64 * gain)
                    y = (y * fade_ramp[:m]).astype(np.float32)
                    for g in gs:
                        out[g][k][a:a + m] += y
            if stop:
                v.on = False
            if trig is not None:
                smp = song.sample(trig[0])
                if smp is not None and smp.length:
                    v.start(bank.get(smp.number), trig[1])
                    cur[k] = smp.number
                    vols[k] = 0.0 if v.on else vols[k]
                else:
                    v.on = False
            target = float(vol)
            if v.on and freq > 0:
                y = v.render(n, freq / rate)
                gs = gsel.get(cur[k], [])
                if gs:
                    env = np.full(n, target / 64)
                    r = min(ramp_n, n)
                    env[:r] = np.linspace(vols[k] / 64, target / 64, r, endpoint=False)
                    y = (y * env * gain).astype(np.float32)
                    for g in gs:
                        out[g][k][a:b] += y
            vols[k] = target
            freqs[k] = freq
    # ring-out of the voices that are still on at the end of the song (the order list would wrap)
    a = int(round(t_idx * TICK * rate))
    n = n_total - a
    if n > 0:
        env = np.linspace(1.0, 0.0, n)
        for k in range(4):
            v = voices[k]
            gs = gsel.get(cur[k], [])
            if v.on and freqs[k] > 0 and gs:
                y = (v.render(n, freqs[k] / rate) * env * vols[k] / 64 * gain).astype(np.float32)
                for g in gs:
                    out[g][k][a:a + n] += y
    return out


def k_in(sel, k):
    return k in sel
