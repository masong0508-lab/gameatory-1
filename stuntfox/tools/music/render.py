"""Render Payback's songs (pbsong.Song) to 44.1 kHz stereo float, faithfully.

Two sequencer flavours share one mixer:

  'payback'    (default) what the game plays. Payback's player (0x08075dd0, Apex's MOD player)
               mixes at 16777216/699 = 24001.7 Hz and runs its sequencer once per 480 samples,
               i.e. at a fixed 50.0035 Hz whatever the tempo. Rows advance by a 2^28 fixed-point
               accumulator stepped by tempo*2^31/(1000*speed) (integer maths as in the ROM), so
               rows come exactly at ProTracker's rate, but the per-call effects run at 50 Hz.
               Per call: porta up/down (1, 2) except on the call that reads a row, tone porta
               (3, 5) and volume slides (5, 6, A) on every call, ECx note cut. Per row: 3 sets
               target/speed (3 with no note does nothing), 9 sample offset (no memory, also
               without a note), C volume, D break, EA/EB fine volume, E1/E2 fine porta, EC0, F
               speed/tempo (F00 ignored). Payback ignores arpeggio (0), vibrato (4, and 6's
               vibrato), tremolo, B, E9, ED, E6, EE: so does this flavour. Finetune is added to
               the period as Payback does. game_pitch=True also quantises pitch to Payback's
               byte step table (rate = step * 24001.7 / 128), for A/B tests against the game.
  'protracker' the composer's module as ProTracker 2.3 plays it: ticks at tempo*2/5 Hz, speed
               ticks a row, every effect (arpeggio, porta, tone porta, vibrato, tremolo, offset
               with memory, volume slides, B/D jumps, E1-EE including pattern loop/delay, retrig,
               note cut/delay, F00 stops) and the proper finetune tables.

Mixer: 4-point Hermite (or linear / nearest) resampling with loops, per-tick volume ramps and a
short fade of the previous voice on retrigger (no clicks), Amiga LRRL panning softened by
`stereo` (0 = mono, 1 = hard). Returns audio plus per-channel stems, the row timeline and every
note event (time, channel, sample, period, volume, duration) so a remix can reuse the parts.

    from render import render
    r = render(pbsong.load(rom, 1))           # r.audio (N, 2) float32, r.rate, r.rows, r.notes
    r = render(song, stems=True)              # r.stems[ch] mono float32 per channel

CLI: python3 render.py ROM SONG out.wav [--flavour protracker] [--seconds 60] [--stereo 0.5]
"""
import math
import sys
import wave
from dataclasses import dataclass, field

import numpy as np

import pbsong

GAME_MIX_RATE = 16777216 / 699            # timer 0 reload 0xfd45
GAME_CALL_RATE = GAME_MIX_RATE / 480      # timer 1 counts 480 samples per sequencer call
PERIOD_MIN, PERIOD_MAX = 0x71, 0x358      # 113 .. 856, the clamps both players use
SINE = (0, 24, 49, 74, 97, 120, 141, 161, 180, 197, 212, 224, 235, 244, 250, 253,
        255, 253, 250, 244, 235, 224, 212, 197, 180, 161, 141, 120, 97, 74, 49, 24)
RAMP = 0.0015                             # volume ramp per step, seconds
FADE = 0.003                              # fade of a voice cut off by a retrigger, seconds


@dataclass
class RowInfo:
    time: float
    order_index: int
    pattern: int
    row: int
    speed: int
    tempo: int


@dataclass
class NoteEvent:
    time: float
    channel: int
    instrument: int             # sample number 1..31
    period: int                 # as played (finetune applied)
    volume: int                 # 0..64 at the start
    order_index: int
    pattern: int
    row: int
    effect: int
    param: int
    duration: float = 0.0       # until the next note on the channel, a cut, silence or the end
    offset: int = 0             # start offset in the sample (9xx)

    @property
    def midi(self):
        return pbsong.period_to_midi(self.period)

    @property
    def name(self):
        return pbsong.note_name(self.period)


@dataclass
class Render:
    audio: np.ndarray           # (N, 2) float32
    rate: int
    duration: float
    rows: list
    notes: list
    stems: dict = field(default_factory=dict)   # channel -> mono float32 (before panning)
    flavour: str = 'payback'
    ended: bool = True          # the order list wrapped (False: stopped by max_seconds)

    def row_time(self, order_index, row=0):
        """Time of the first visit of (order position, row), or None."""
        for r in self.rows:
            if r.order_index == order_index and r.row == row:
                return r.time
        return None


# ---------------------------------------------------------------- sequencers
# A step is (seconds, [ChannelOut x4]). ChannelOut: trigger (sample number, offset) or None,
# frequency in Hz, volume 0..64, stop (bool: the voice stops now).

class _Ch:
    def __init__(self):
        self.eff = self.param = 0
        self.ins = 0            # current sample number
        self.vol = 0
        self.period = 0
        self.target = 0
        self.pspeed = 0
        self.ft = 0
        self.vib_pos = self.vib_speed = self.vib_depth = self.vib_wave = 0
        self.trem_pos = self.trem_speed = self.trem_depth = self.trem_wave = 0
        self.offset = 0
        self.loop_row = self.loop_count = 0
        self.delay = None       # (tick, period, ins) for ED
        self.base_ins = 0


def _wave(wave_type, pos):
    """ProTracker's vibrato/tremolo waveforms: sine, ramp down, square; pos 0..63."""
    pos &= 63
    idx, half = pos & 31, pos >= 32
    w = wave_type & 3
    if w == 0:
        v = SINE[idx]
    elif w == 1:
        v = 255 - idx * 8 if half else idx * 8
    else:
        v = 255
    return -v if half else v


class PaybackSeq:
    """Payback's player, call for call (see the module doc)."""

    def __init__(self, song, start_order=0, game_pitch=False):
        self.s = song
        self.game_pitch = game_pitch
        self.accum = 0x10000000 - 0x02aaa000
        self.inc = 0x02aaa000
        self.speed, self.tempo = song.speed, song.tempo
        self.oi, self.row = start_order, 0
        self.ch = [_Ch() for _ in range(4)]
        for c in self.ch:
            c.ins = 1           # play() leaves the instrument bytes at 0, i.e. sample 1
        self.ended = False
        self.wrapped_by_break = False
        self.call_seconds = 1.0 / GAME_CALL_RATE

    def freq(self, period):
        if period <= 0:
            return 0.0
        if self.game_pitch:
            return float(self.s.step_table[min(period, len(self.s.step_table) - 1)]) * GAME_MIX_RATE / 128
        return pbsong.PAL_CLOCK / period

    def _inc(self):
        return ((((3 * self.tempo) << 18) // (self.speed * 3000)) << 13) & 0xffffffff

    def step(self, log_row, log_note, t):
        out = [None] * 4
        self.accum = (self.accum + self.inc) & 0xffffffff
        due = self.accum > 0x0fffffff
        trig = [None] * 4
        stop = [False] * 4
        for c in self.ch:
            e, p = c.eff, c.param
            if not (e or p):
                continue
            if e == 1 and not due:
                c.period = max(c.period - p, PERIOD_MIN)
            elif e == 2 and not due:
                c.period = min(c.period + p, PERIOD_MAX)
            elif e in (3, 5):
                if c.period < c.target:
                    c.period += c.pspeed
                    if c.period >= c.target:
                        c.period = c.target
                        if e == 3:
                            c.eff = c.param = 0
                elif c.period > c.target:
                    c.period -= c.pspeed
                    if c.period <= c.target:
                        c.period = c.target
                        if e == 3:
                            c.eff = c.param = 0
                elif e == 3:
                    c.eff = c.param = 0
            if e in (5, 6, 0xa):
                if p & 0xf0:
                    c.vol = min(c.vol + (p >> 4), 64)
                else:
                    c.vol = max(c.vol - (p & 15), 0)
            elif e == 0xe and (p & 0xf0) == 0xc0:
                x = (p & 15) - 1
                if x > 0:
                    c.param = 0xc0 | x
                else:
                    c.vol = 0
                    c.eff = c.param = 0
        if due:
            self.accum = (self.accum + 0xf0000000) & 0xffffffff
            pat = self.s.order[self.oi]
            log_row(RowInfo(t, self.oi, pat, self.row, self.speed, self.tempo))
            brk = -1
            for k, c in enumerate(self.ch):
                cell = self.s.patterns[pat][self.row][k]
                c.eff, c.param = cell.effect, cell.param
                e, p = c.eff, c.param
                if cell.instrument:
                    c.ins = cell.instrument
                    smp = self.s.sample(c.ins)
                    c.vol = smp.volume
                period = cell.period
                if period:
                    period += self.s.sample(c.ins).finetune
                    if e not in (3, 5):
                        c.period = period
                        trig[k] = (c.ins, 0)
                        log_note(NoteEvent(t, k, c.ins, period, c.vol, self.oi, pat, self.row, e, p))
                if e == 3:
                    if period:
                        if p:
                            c.pspeed = p
                        c.target = min(max(period, PERIOD_MIN), PERIOD_MAX)
                    else:
                        c.eff = c.param = 0
                elif e == 9 and p:
                    smp = self.s.sample(c.ins)
                    if p * 256 + 1 >= smp.length:
                        c.vol = 0
                    else:
                        trig[k] = (c.ins, p * 256) if trig[k] else ('seek', p * 256)
                elif e == 0xc:
                    c.vol = p
                elif e == 0xd:
                    brk = (p >> 4) * 10 + (p & 15)
                elif e == 0xe:
                    x = p & 15
                    sub = p >> 4
                    if sub == 0xa:
                        c.vol = min(c.vol + x, 64)
                    elif sub == 0xb:
                        c.vol = max(c.vol - x, 0)
                    elif sub == 1:
                        c.period = max(c.period - x, PERIOD_MIN)
                    elif sub == 2:
                        c.period = min(c.period + x, PERIOD_MAX)
                    elif sub == 0xc and x == 0:
                        c.eff = c.param = 0
                        c.vol = 0
                elif e == 0xf and p:
                    if p <= 0x1f:
                        self.speed = p
                    else:
                        self.tempo = p
                    self.inc = self._inc()
            if brk >= 0:
                self.oi += 1
                self.row = brk
                if self.oi >= len(self.s.order):
                    self.oi = 0
                    self.ended = self.wrapped_by_break = True
            else:
                self.row += 1
                if self.row > 63:
                    self.row = 0
                    self.oi += 1
                    if self.oi >= len(self.s.order):
                        self.oi = 0
                        self.ended = True
        for k, c in enumerate(self.ch):
            out[k] = (trig[k], self.freq(c.period), c.vol, stop[k], c.ins)
        return self.call_seconds, out


class ProTrackerSeq:
    """ProTracker 2.3 semantics (see the module doc)."""

    def __init__(self, song, start_order=0, game_pitch=False):
        self.s = song
        self.speed, self.tempo = song.speed, song.tempo
        self.oi, self.row = start_order, 0
        self.tick = 0
        self.ch = [_Ch() for _ in range(4)]
        self.ended = False
        self.wrapped_by_break = False
        self.pdelay = 0
        self.pdelay_left = 0
        self.next_jump = None
        self.visited = set()
        self.cur = None         # (oi, pattern, row) being played

    @staticmethod
    def ft_period(period, ft):
        if not period:
            return 0
        if ft == 0:
            return period
        # the period of the nearest note, retuned by ft/8 semitone like ProTracker's tables
        m = round(12 * math.log2(856 / period))
        return int(round(856 * 2 ** (-m / 12) * 2 ** (-ft / 96)))

    def freq(self, period):
        return pbsong.PAL_CLOCK / period if period > 0 else 0.0

    def _row(self, log_row, log_note, t, trig, stop):
        pat = self.s.order[self.oi]
        self.cur = (self.oi, pat, self.row)
        log_row(RowInfo(t, self.oi, pat, self.row, self.speed, self.tempo))
        brk = jump = None
        for k, c in enumerate(self.ch):
            cell = self.s.patterns[pat][self.row][k]
            e, p = cell.effect, cell.param
            c.eff, c.param = e, p
            c.delay = None
            if cell.instrument:
                c.ins = cell.instrument
                smp = self.s.sample(c.ins)
                c.vol = min(smp.volume, 64)
                c.ft = smp.finetune
            if e == 0xe and p >> 4 == 5:
                c.ft = (p & 15) - 16 if p & 8 else p & 15
            if cell.period:
                per = self.ft_period(cell.period, c.ft)
                if e in (3, 5):
                    c.target = per
                    if e == 3 and p:
                        c.pspeed = p
                elif e == 0xe and p >> 4 == 0xd and p & 15:
                    c.delay = (p & 15, per, c.ins)
                else:
                    c.period = per
                    off = 0
                    if e == 9:
                        if p:
                            c.offset = p * 256
                        off = c.offset
                        smp = self.s.sample(c.ins)
                        if off >= smp.length:
                            off = smp.loop_start if smp.looped else -1
                    if off < 0:
                        stop[k] = True
                    else:
                        trig[k] = (c.ins, off)
                        log_note(NoteEvent(t, k, c.ins, per, c.vol, self.oi, pat, self.row, e, p, offset=off))
                    if c.vib_wave < 4:
                        c.vib_pos = 0
                    if c.trem_wave < 4:
                        c.trem_pos = 0
            elif e == 9 and p:
                c.offset = p * 256
            if e == 3 and p and not cell.period:
                c.pspeed = p
            if e == 4:
                if p >> 4:
                    c.vib_speed = p >> 4
                if p & 15:
                    c.vib_depth = p & 15
            elif e == 7:
                if p >> 4:
                    c.trem_speed = p >> 4
                if p & 15:
                    c.trem_depth = p & 15
            elif e == 0xb:
                jump = p
            elif e == 0xc:
                c.vol = min(p, 64)
            elif e == 0xd:
                brk = (p >> 4) * 10 + (p & 15)
                if brk > 63:
                    brk = 0
            elif e == 0xf:
                if p == 0:
                    self.ended = True
                elif p < 0x20:
                    self.speed = p
                else:
                    self.tempo = p
            elif e == 0xe:
                sub, x = p >> 4, p & 15
                if sub == 1:
                    c.period = max(c.period - x, PERIOD_MIN)
                elif sub == 2:
                    c.period = min(c.period + x, PERIOD_MAX)
                elif sub == 4:
                    c.vib_wave = x
                elif sub == 7:
                    c.trem_wave = x
                elif sub == 6:
                    if x == 0:
                        c.loop_row = self.row
                    else:
                        if c.loop_count == 0:
                            c.loop_count = x
                            brk = ('loop', c.loop_row)
                        else:
                            c.loop_count -= 1
                            if c.loop_count:
                                brk = ('loop', c.loop_row)
                elif sub == 0xa:
                    c.vol = min(c.vol + x, 64)
                elif sub == 0xb:
                    c.vol = max(c.vol - x, 0)
                elif sub == 0xc and x == 0:
                    c.vol = 0
                elif sub == 0xe and not self.pdelay_left:
                    self.pdelay = x
        self.next_jump = (jump, brk)

    def _advance(self):
        jump, brk = self.next_jump
        if isinstance(brk, tuple):
            self.row = brk[1]
            return
        if jump is not None:
            if jump <= self.oi:
                self.ended = True
            self.oi = jump
            self.row = brk if brk is not None else 0
        elif brk is not None:
            self.oi += 1
            self.row = brk
        else:
            self.row += 1
            if self.row > 63:
                self.row = 0
                self.oi += 1
        if self.oi >= len(self.s.order):
            self.oi = 0
            self.ended = True

    def step(self, log_row, log_note, t):
        trig = [None] * 4
        stop = [False] * 4
        outp = [c.period for c in self.ch]
        outv = [c.vol for c in self.ch]
        if self.tick == 0 and not self.pdelay_left:
            self._row(log_row, log_note, t, trig, stop)
            outp = [c.period for c in self.ch]
            outv = [c.vol for c in self.ch]
        else:
            for k, c in enumerate(self.ch):
                e, p = c.eff, c.param
                if e == 1:
                    c.period = max(c.period - p, PERIOD_MIN)
                elif e == 2:
                    c.period = min(c.period + p, PERIOD_MAX)
                elif e in (3, 5) and c.target:
                    if c.period < c.target:
                        c.period = min(c.period + c.pspeed, c.target)
                    elif c.period > c.target:
                        c.period = max(c.period - c.pspeed, c.target)
                outp[k] = c.period
                if e == 0 and p and c.period:
                    outp[k] = c.period * 2 ** (-((0, p >> 4, p & 15)[self.tick % 3]) / 12)
                elif e in (4, 6):
                    outp[k] = c.period + _wave(c.vib_wave, c.vib_pos) * c.vib_depth / 128
                    c.vib_pos = (c.vib_pos + c.vib_speed) & 63
                if e in (5, 6, 0xa):
                    if p >> 4:
                        c.vol = min(c.vol + (p >> 4), 64)
                    else:
                        c.vol = max(c.vol - (p & 15), 0)
                outv[k] = c.vol
                if e == 7:
                    outv[k] = min(max(c.vol + _wave(c.trem_wave, c.trem_pos) * c.trem_depth / 64, 0), 64)
                    c.trem_pos = (c.trem_pos + c.trem_speed) & 63
                if e == 0xe:
                    sub, x = p >> 4, p & 15
                    if sub == 9 and x and self.tick % x == 0:
                        trig[k] = (c.ins, 0)
                    elif sub == 0xc and self.tick == x:
                        c.vol = outv[k] = 0
                    elif sub == 0xd and c.delay and self.tick == c.delay[0]:
                        _, per, ins = c.delay
                        c.period = outp[k] = per
                        trig[k] = (ins, 0)
                        oi, pat, row = self.cur
                        log_note(NoteEvent(t, k, ins, per, c.vol, oi, pat, row, e, p))
                        c.delay = None
        # tick 0 retrig for E9 counts too (ProTracker retriggers on tick 0 with the note)
        out = [(trig[k], self.freq(outp[k]), outv[k], stop[k], self.ch[k].ins) for k in range(4)]
        secs = 2.5 / self.tempo
        self.tick += 1
        if self.tick >= self.speed:
            self.tick = 0
            if self.pdelay_left:
                self.pdelay_left -= 1
                if not self.pdelay_left:
                    self._advance()
            elif self.pdelay:
                self.pdelay_left = self.pdelay
                self.pdelay = 0
            else:
                self._advance()
        return secs, out


# ---------------------------------------------------------------- mixer

def _prep(smp):
    """Padded float buffer: 1 lead sample, the data, 3 samples of loop (or zeros) after."""
    d = smp.pcm().astype(np.float64)
    if smp.looped:
        lp = d[smp.loop_start:]
        tail = np.tile(lp, 3 // max(1, len(lp)) + 1)[:3]
    else:
        tail = np.zeros(3)
    return np.concatenate(([0.0], d, tail))


class _Voice:
    __slots__ = ('buf', 'n', 'ls', 'll', 'pos', 'on')

    def __init__(self):
        self.on = False
        self.buf = None
        self.n = self.ls = self.ll = 0
        self.pos = 0.0

    def start(self, prep, smp, offset):
        self.buf = prep
        self.n = smp.length
        self.ls = smp.loop_start
        self.ll = smp.loop_len
        self.pos = float(offset)
        self.on = smp.length > 0 and offset < smp.length

    def seek(self, offset):
        if self.buf is not None:
            self.pos = float(offset)
            self.on = offset < self.n

    def render(self, n, inc, interp):
        """n output samples at `inc` source samples per output sample (float64)."""
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
        if interp == 'nearest':
            y = b[i + 1]
        elif interp == 'linear':
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


def sequence(song, flavour='payback', start_order=0, game_pitch=False, max_seconds=None):
    """Run a sequencer without mixing: (steps, rows, notes, ended)."""
    seq = (PaybackSeq if flavour == 'payback' else ProTrackerSeq)(song, start_order, game_pitch)
    rows, notes, steps = [], [], []
    t = 0.0
    limit = max_seconds if max_seconds else 3600.0
    while not seq.ended and t < limit:
        secs, out = seq.step(rows.append, notes.append, t)
        steps.append((t, secs, out))
        t += secs
    return steps, rows, notes, seq.ended, t


def _durations(notes, steps, alive, total):
    """A note lasts until the next note on its channel, or until the channel falls silent."""
    st = np.array([s[0] for s in steps])
    for k in range(4):
        evs = [e for e in notes if e.channel == k]
        dead = np.nonzero(~alive[k])[0]
        for j, ev in enumerate(evs):
            si = int(np.searchsorted(st, ev.time - 1e-9))
            nxt = evs[j + 1].time if j + 1 < len(evs) else total
            d = dead[np.searchsorted(dead, si):][:1]
            end = st[d[0]] if len(d) else total
            ev.duration = max(min(end, nxt) - ev.time, 0.0)


def render(song, flavour='payback', rate=44100, interp='hermite', stereo=0.5, game_pitch=False,
           channels=(0, 1, 2, 3), max_seconds=None, start_order=0, stems=False, gain=0.5, tail=0.0):
    """Render a song. See the module doc. tail: seconds the voices ring on (fading) after the end."""
    steps, rows, notes, ended, total = sequence(song, flavour, start_order, game_pitch, max_seconds)
    n_total = int(round((total + tail) * rate)) + 1
    preps = {s.number: _prep(s) for s in song.samples if s.length}
    pans = np.array([-1, 1, 1, -1], float) * stereo
    gl = np.cos((pans + 1) * np.pi / 4)
    gr = np.sin((pans + 1) * np.pi / 4)
    ramp_n = max(1, int(RAMP * rate))
    fade_n = max(1, int(FADE * rate))
    mono = {k: np.zeros(n_total, np.float32) for k in channels}
    voices = [_Voice() for _ in range(4)]
    vols = [0.0] * 4
    freqs = [0.0] * 4
    fade_ramp = np.linspace(1.0, 0.0, fade_n, endpoint=False)
    alive = np.zeros((4, len(steps)), bool)
    for si, (t, secs, out) in enumerate(steps):
        a = int(round(t * rate))
        b = min(int(round((t + secs) * rate)), n_total)
        n = b - a
        if n <= 0:
            continue
        for k in range(4):
            trig, freq, vol, stop, ins = out[k]
            v = voices[k]
            if trig is not None and trig[0] == 'seek':
                v.seek(trig[1])
                trig = None
            if (trig is not None or stop) and v.on and k in mono and vols[k] > 0:
                # fade the old voice out under the new one
                m = min(fade_n, n_total - a)
                y = v.render(m, freqs[k] / rate, interp) * (vols[k] / 64 * gain)
                mono[k][a:a + m] += (y * fade_ramp[:m]).astype(np.float32)
            if stop:
                v.on = False
            if trig is not None:
                smp = song.sample(trig[0])
                if smp is not None and smp.length:
                    v.start(preps[smp.number], smp, trig[1])
                    vols[k] = 0.0 if v.on else vols[k]
                else:
                    v.on = False
            target = float(vol)
            alive[k, si] = v.on and target > 0
            if v.on and freq > 0 and k in mono:
                y = v.render(n, freq / rate, interp)
                env = np.full(n, target / 64)
                r = min(ramp_n, n)
                env[:r] = np.linspace(vols[k] / 64, target / 64, r, endpoint=False)
                mono[k][a:b] += (y * env * gain).astype(np.float32)
            elif v.on and freq > 0:
                v.render(n, freq / rate, interp)
            vols[k] = target
            freqs[k] = freq
    _durations(notes, steps, alive, total)
    if tail > 0:
        a = int(round(total * rate))
        n = n_total - a
        env = np.linspace(1.0, 0.0, n)
        for k in channels:
            v = voices[k]
            if v.on and freqs[k] > 0:
                mono[k][a:a + n] += (v.render(n, freqs[k] / rate, interp) * env * vols[k] / 64 * gain).astype(np.float32)
    audio = np.zeros((n_total, 2), np.float32)
    for k in channels:
        audio[:, 0] += mono[k] * gl[k]
        audio[:, 1] += mono[k] * gr[k]
    return Render(audio, rate, n_total / rate, rows, notes, mono if stems else {}, flavour, ended)


def write_wav(path, audio, rate=44100, normalize_db=None):
    """16-bit WAV. normalize_db: scale the peak to this level (e.g. -1.0) first."""
    a = np.asarray(audio, np.float64)
    if normalize_db is not None:
        pk = np.max(np.abs(a)) or 1.0
        a = a * (10 ** (normalize_db / 20) / pk)
    if a.ndim == 1:
        a = a[:, None]
    pcm = np.clip(np.round(a * 32767), -32768, 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(a.shape[1])
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm.tobytes())


def main(argv):
    import argparse
    import time
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('rom')
    ap.add_argument('song', type=int)
    ap.add_argument('out')
    ap.add_argument('--flavour', default='payback', choices=('payback', 'protracker'))
    ap.add_argument('--seconds', type=float)
    ap.add_argument('--stereo', type=float, default=0.5)
    ap.add_argument('--interp', default='hermite', choices=('hermite', 'linear', 'nearest'))
    ap.add_argument('--game-pitch', action='store_true')
    ap.add_argument('--tail', type=float, default=1.5)
    a = ap.parse_args(argv)
    t = time.time()
    s = pbsong.load(a.rom, a.song)
    r = render(s, a.flavour, interp=a.interp, stereo=a.stereo, game_pitch=a.game_pitch,
               max_seconds=a.seconds, tail=a.tail)
    write_wav(a.out, r.audio, r.rate, normalize_db=-1.0)
    print('%s: %.1f s, %d rows, %d notes, rendered in %.1f s' % (a.out, r.duration, len(r.rows), len(r.notes),
                                                             time.time() - t))


if __name__ == '__main__':
    main(sys.argv[1:])
