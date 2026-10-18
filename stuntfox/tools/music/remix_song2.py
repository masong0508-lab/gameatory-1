"""Star-FlyBack Remix - Song 2: drum & bass remix of Payback's song 2 (C minor/dorian, 125 BPM
breakbeat), re-produced at 174 BPM for driving and dogfights.

Everything that is the song is read from the user's own ROM at run time:
- the chopped break: every slice re-triggered on the original's own pattern rows and fills;
- the lead (sample 19) playing the original melodies, slides included;
- the stab/arp sample (1): the stab riff, its double-time roll and the arpeggios;
- the chord pad samples (2-8), the gated bell tone (15) with its gate rhythm, the deep drone;
- the bass riff, melodies, chords and fills, note by note from the patterns.
New parts are our own synths: two-step kick/snare/hats, a reese + sub bass playing the original
bass riff, a supersaw pad, a saw lead doubling the melody, an FM bell, risers and impacts.
One tracker row of the original is one 16th here, so riffs keep their rhythm.

    PAYBACK_ROM=/path/to/Payback.gba python3 remix_song2.py OUT_BASE      # OUT_BASE.wav + .mp3

Structure (bar = 1.379 s):
    0 intro   16 build (stab riff, rising chords)   24 double-time roll   28 drop 1 (C pedal riff)
    44 drop 1 melody   60 breakdown (arpeggio)   68 bell melody + build   76 switch-up (half-time)
    84 roller   92 final drop (full melody)   108 outro (arpeggio, break fades)   116 coda   120 end
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
from synth import Inst  # noqa: E402

BPM = 174.0
RATE = dsp.RATE
STEP = 60.0 / BPM / 4               # one original row = one 16th
NATIVE = pbsong.PAL_CLOCK / pbsong.NATIVE_PERIOD
BARS = 124
# sections (first bar)
INTRO, BUILD, ROLL, DROP1, DROP1B, BREAK, BELL, SWITCH, ROLLER, FINALE, OUTRO, CODA, END = (
    0, 16, 24, 28, 44, 60, 68, 76, 84, 92, 108, 116, 120)
KEYS = ('C', 'C', 'F', 'F', 'Eb', 'Eb', 'Bb', 'Bb')     # the main progression, a chord per bar
# the original's pad samples per chord (2 = Cm6/9, 3 = Cm9, 4 = F6/9, 5 = Bbmaj9, 7 = Ebmaj9)
PADS = (3, 2, 4, 4, 7, 7, 5, 5)
VOICE = {'C': ('C3', 'G3', 'C4', 'G4'), 'F': ('F2', 'C3', 'F3', 'C4'), 'Eb': ('Eb3', 'Bb3', 'Eb4', 'Bb4'),
         'Bb': ('Bb2', 'F3', 'Bb3', 'F4')}     # root + fifth: the 3rds, 7ths and 9ths come from Payback's own pads
ROOT = {'C': 'C2', 'F': 'F1', 'Eb': 'Eb2', 'Bb': 'Bb1', 'G': 'G1', 'Ab': 'Ab1'}


LOG = []      # every pitched note placed: (part, time, seconds, sounding MIDI); for the harmony check


def log(part, t, dur, midi):
    LOG.append((part, float(t), float(dur), float(midi)))


def T(bar, step=0.0):
    return (bar * 16 + step) * STEP


def n_of(sec):
    return int(round(sec * RATE))


def ramp_env(n, attack, release, rate=RATE):
    e = np.ones(n)
    a, r = min(n, int(attack * rate)), min(n, int(release * rate))
    if a > 0:
        e[:a] = np.linspace(0, 1, a)
    if r > 0:
        e[n - r:] *= np.linspace(1, 0, r)
    return e


def sweep(x, kind, points, t0=0.0, q=0.7071):
    """Filter a clip with a sweep; points [(seconds from clip start, Hz)]."""
    return dsp.filt(x, kind, [(t - t0, f) for t, f in points], q)


def stereo(x):
    return dsp.as_stereo(x)


# ---------------------------------------------------------------- the original, from the ROM

class Source:
    """Payback song 2: lines, drum rows, gates and samples by order position."""

    def __init__(self, rom=None):
        self.o = mix.Original(2, rom)
        self.s = self.o.song
        self.tune = self.o.tune
        self._ext = {}
        self._shot = {}
        self.cents = {}
        for smp in self.s.samples:
            f = self.o.features.get(smp.number)
            if smp.length and f and (smp.looped or f['pitch_conf'] > 0.6):
                self.cents[smp.number] = self.measure_cents(smp.number)

    def cells(self, positions, ch):
        out = []
        for pos in positions:
            pat = self.s.patterns[self.s.order[pos]]
            out += [pat[r][ch] for r in range(64)]
        return out

    def line(self, positions, ch, speed=6):
        """Monophonic notes as dicts: row, end (rows), trk (tracker MIDI, 60 = C-2), ins, vol 0..1,
        glides [(row, trk, rows to reach, 't' tone porta (3) | 'p' porta up/down (1, 2))], EC cuts."""
        cells = self.cells(positions, ch)
        notes, cur, ins, per = [], None, 0, 0
        for r, c in enumerate(cells):
            e, p = c.effect, c.param
            if c.instrument:
                ins = c.instrument
            if c.period and e not in (3, 5):
                if cur:
                    cur['end'] = min(cur['end'], r)
                vol = (p if e == 0xc else self.s.sample(ins).volume) / 64.0
                cur = dict(row=r, end=float(len(cells)), trk=pbsong.period_to_midi(c.period), ins=ins,
                           vol=min(vol, 1.0), glides=[])
                per = c.period
                notes.append(cur)
            if cur is None:
                continue
            if e == 3 and c.period:
                spd = p or cur.get('spd', 1)
                cur['spd'] = spd
                cur['glides'].append((r, pbsong.period_to_midi(c.period), abs(c.period - per) / (spd * speed), 't'))
                per = c.period
            elif e in (1, 2) and p:
                per = min(856, max(113, per - p * (speed - 1) if e == 1 else per + p * (speed - 1)))
                cur['glides'].append((r, pbsong.period_to_midi(per), 1.0, 'p'))
            elif e == 0xe and p >> 4 == 0xc:
                cur['end'] = min(cur['end'], r + (p & 15) / speed)
            elif e == 0xc and p == 0 and not c.period:
                cur['end'] = min(cur['end'], r)
        return notes

    def drums(self, positions, ch=2):
        """[(row, sample, vol, effect, param)] of a drum channel."""
        out = []
        for r, c in enumerate(self.cells(positions, ch)):
            if c.instrument and c.period:
                vol = (c.param if c.effect == 0xc else self.s.sample(c.instrument).volume) / 64.0
                out.append((r, c.instrument, min(vol, 1.0), c.effect, c.param))
        return out

    def gates(self, positions, ch=1, ins=15, speed=6):
        """The bell's gate: open spans [(row, row_end)] and retrigger rows."""
        spans, trig = [], []
        for r, c in enumerate(self.cells(positions, ch)):
            if c.instrument == ins:
                cut = (c.param & 15) / speed if (c.effect == 0xe and c.param >> 4 == 0xc) else 1.0
                spans.append((r, r + max(cut, 0.5 / speed)))
                if c.period:
                    trig.append(r)
        return spans, trig

    def pads(self, positions, ch):
        """[(row, sample, trk)] of a pad channel."""
        return [(r, c.instrument, pbsong.period_to_midi(c.period)) for r, c in enumerate(self.cells(positions, ch))
                if c.instrument and c.period]

    def pad_pcs(self, k, share=0.06):
        """Pitch classes a chord pad sample holds (sounding at C-3), from its spectrum."""
        x = self.ext(k)[2048:2048 + 32768]
        S = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
        f = np.fft.rfftfreq(len(x), 1 / NATIVE) * 2 ** (self.cents.get(k, 0) / -1200)
        sel = (f > 60) & (f < 1600)
        c = np.zeros(12)
        np.add.at(c, np.round(12 * np.log2(f[sel] / 440) + 69).astype(int) % 12, S[sel])
        c /= c.sum()
        return [i for i in range(12) if c[i] >= share]

    def measure_cents(self, k, peaks=10):
        """How far sample k sits from equal temperament (A440), in cents. Single tones: the
        fundamental found by fitting a harmonic comb to the spectrum near the measured pitch.
        Chord pads: the magnitude-weighted median deviation of their strongest peaks below 1 kHz.
        Payback's samples run 5-30 cents flat."""
        smp = self.s.sample(k)
        x = self.ext(k)[:32768] if smp.looped else self.pcm(k)[:32768]
        x = x[len(x) // 8:] if len(x) > 4096 else x
        nfft = 1 << 18
        S = np.abs(np.fft.rfft(x * np.hanning(len(x)), nfft))
        df = NATIVE / nfft
        feat = self.o.features[k]
        if feat['pitch_conf'] > 0.85 and feat['f0']:
            logS = np.log1p(S / (S.max() + 1e-12) * 1000)
            best = None
            for c in np.arange(-70, 70.5, 0.5):
                f0 = feat['f0'] * 2 ** (c / 1200)
                ks = np.arange(1, 13)
                fk = f0 * ks
                fk = fk[fk < 3500]
                sc = np.interp(fk / df, np.arange(len(logS)), logS).sum()
                if best is None or sc > best[0]:
                    best = (sc, f0)
            m = 12 * math.log2(best[1] / 440.0) + 69
            return float(100 * (m - round(m)))
        f = np.arange(len(S)) * df
        S[(f < 60) | (f > 1000)] = 0
        dev, w = [], []
        guard = max(1, int(8.0 / df))
        for _ in range(peaks):
            i = int(np.argmax(S))
            if S[i] <= 0:
                break
            m = 12 * math.log2(f[i] / 440.0) + 69
            dev.append(100 * (m - round(m)))
            w.append(S[i])
            S[max(0, i - guard):i + guard] = 0
        o = np.argsort(dev)
        cw = np.cumsum(np.array(w)[o])
        return float(np.array(dev)[o][np.searchsorted(cw, cw[-1] / 2)])

    # samples
    def pcm(self, k):
        return self.s.sample(k).pcm().astype(np.float64)

    def ext(self, k, seconds=30.0, xf=0.05):
        """Looped sample k unrolled into a long one-shot. Short loops (single cycles) repeat
        exactly as the tracker plays them; long loops (the chord pads) are overlap-added with
        equal-power crossfades so the loop point never clicks."""
        if k not in self._ext:
            smp = self.s.sample(k)
            x = self.pcm(k)
            ls = max(smp.loop_start, 0)
            body = x[ls:]
            need = int(seconds * NATIVE)
            if len(body) < 2048:
                reps = need // len(body) + 1
                out = np.concatenate([x, np.tile(body, reps)])
            else:
                X = min(int(xf * NATIVE), len(body) // 3)
                th = np.linspace(0, np.pi / 2, X)
                fin, fout = np.sin(th), np.cos(th)
                parts = [x[:-X]]
                prev_tail = x[-X:]
                while sum(len(p_) for p_ in parts) < need:
                    parts.append(prev_tail * fout + body[:X] * fin)
                    parts.append(body[X:-X])
                    prev_tail = body[-X:]
                out = np.concatenate(parts)
            self._ext[k] = out
        return self._ext[k]

    def play(self, k, trk, dur=None, release=0.02, attack=0.0015, curve=None, looped=False, start=0.0):
        """Sample k at tracker note trk (MIDI, 60 = native rate) at 44.1 kHz, mono. dur None plays
        the one-shot to its end; curve: per-sample tracker pitch (slides)."""
        fix = -self.cents.get(k, 0.0) / 100.0       # play in tune with our A440 synths
        trk = trk + fix
        if curve is not None:
            curve = curve + fix
        if dur is None and curve is None and not looped and (k, trk) in self._shot:
            return self._shot[(k, trk)]
        x = self.ext(k) if looped else self.pcm(k)
        if dur is None:
            n = int(len(x) / (NATIVE * 2 ** ((trk - 60) / 12) / RATE))
        else:
            n = n_of(dur + release)
        if curve is not None:
            c = np.concatenate([curve[:n], np.full(max(0, n - len(curve)), curve[-1])])
            ratio = NATIVE * 2 ** ((c - 60) / 12) / RATE
        else:
            ratio = NATIVE * 2 ** ((trk - 60) / 12) / RATE
        y = dsp.play_sample(x, ratio, n, -1, start=start)
        y = y * ramp_env(n, attack, release if dur is not None else 0.004)
        if dur is None and curve is None and not looped:
            self._shot[(k, trk)] = y
        return y


# ---------------------------------------------------------------- line rendering

def curves(notes, n, t0, row_t, tune, attack=0.004, release=0.04, legato=True):
    """Per-sample pitch (MIDI), envelope and seconds since note-on for a monophonic line.
    row_t(row) -> absolute seconds; tune(note) -> semitones to add to the tracker pitch."""
    pitch = np.full(n, np.nan)
    env = np.zeros(n)
    since = np.full(n, 10.0)
    idx = lambda t: int(round((t - t0) * RATE))  # noqa: E731
    for i, nt in enumerate(notes):
        a, b = max(0, idx(row_t(nt['row']))), min(n, idx(row_t(nt['end'])))
        if b <= a or a >= n:
            continue
        nxt = min(n, idx(row_t(notes[i + 1]['row']))) if i + 1 < len(notes) else n
        hold = max(min(n, b + int(release * RATE * 3)), b)
        hold = min(hold, nxt) if nxt > a else hold
        p0 = nt['trk'] + tune(nt)
        pc = np.full(hold - a, p0)
        for gr, gtrk, grows, _ in nt['glides']:
            gs = max(0, idx(row_t(gr)) - a)
            if gs >= len(pc):
                continue
            ge = min(len(pc), gs + max(1, int((row_t(gr + max(grows, 0.05)) - row_t(gr)) * RATE)))
            tgt = gtrk + tune(nt)
            pc[gs:ge] = np.linspace(pc[gs], tgt, ge - gs)
            pc[ge:] = tgt
        pitch[a:hold] = pc
        lvl0 = env[a - 1] if (legato and a > 0) else 0.0
        ka = min(b - a, max(1, int(attack * RATE)))
        seg = np.ones(b - a)
        seg[:ka] = np.linspace(lvl0, 1, ka)
        env[a:b] = seg * nt.get('vel', 1.0)
        kr = min(int(release * RATE), max(0, nxt - b))
        if kr > 0:
            env[b:b + kr] = np.linspace(1, 0, kr) ** 2 * nt.get('vel', 1.0)
        since[a:nxt] = np.arange(nxt - a) / RATE
    # hold the last pitch through gaps so release tails keep their frequency
    ok = ~np.isnan(pitch)
    if not ok.any():
        return np.full(n, 36.0), env, since
    i = np.where(ok, np.arange(n), 0)
    np.maximum.accumulate(i, out=i)
    pitch = pitch[i]
    first = np.argmax(ok)
    pitch[:first] = pitch[first]
    return pitch, env, since


def comb(x, base_ms, depth_ms, rate_hz, mix_=0.5, phase=0.0):
    """Moving comb (flanger) for the neuro bass: x plus x delayed by an LFO-swept time."""
    x = stereo(x)
    n = len(x)
    t = np.arange(n) / RATE
    out = x.copy()
    for ch in range(2):
        d = (base_ms + depth_ms * 0.5 * (1 + np.sin(2 * np.pi * rate_hz * t + phase + ch * 0.9))) * RATE / 1000
        out[:, ch] += mix_ * np.interp(np.arange(n) - d, np.arange(n), x[:, ch], left=0.0)
    return out


def bass_line(src, notes, t0, t1, row_t, kind, **kw):
    """Render the bass riff as one continuous phrase (no clicks between notes). kind: 'sub' or
    'reese'. Returns stereo audio starting at t0."""
    n = n_of(t1 - t0 + 0.3)
    t = np.arange(n) / RATE
    if kind == 'sub':
        tune = lambda nt: src.tune[10]     # noqa: E731  every note in the sub's octave
        for nt in notes:
            for r0, r1, trk in segments(nt):
                log('sub', row_t(r0), row_t(r1) - row_t(r0), trk + tune(nt))
        pitch, env, since = curves(notes, n, t0, row_t, tune, attack=0.003, release=0.03)
        f = dsp.midi_hz(pitch)
        ph = np.cumsum(f) / RATE
        y = np.sin(2 * np.pi * ph) + 0.12 * np.sin(4 * np.pi * ph)
        y = dsp.saturate(y * 1.2, 1.1)
        y = dsp.lowpass(y, 160, 0.7) * env
        return stereo(y)
    tune = lambda nt: src.tune[nt['ins']] if nt['ins'] in (10, 11) else 0   # noqa: E731
    for nt in notes:
        for r0, r1, trk in segments(nt):
            log('reese', row_t(r0), row_t(r1) - row_t(r0), trk + tune(nt) + kw.get('transpose', 0))
    pitch, env, since = curves(notes, n, t0, row_t, tune, attack=0.004, release=0.05)
    f = dsp.midi_hz(pitch + kw.get('transpose', 0))
    voices, det = kw.get('voices', 6), kw.get('detune', 0.32)
    out = np.zeros((n, 2))
    for k in range(voices):
        d = (k - (voices - 1) / 2) / ((voices - 1) / 2) * det / 2
        drift = 1 + 0.0012 * np.sin(2 * np.pi * (0.11 + 0.05 * k) * t + k)
        v = dsp.saw(f * 2 ** (d / 12) * drift, n, phase0=(0.37 * k) % 1)
        out += dsp.pan(v, (-1) ** k * (0.25 + 0.5 * k / voices))
    out /= voices
    cut = dsp.automation(kw.get('cut', 900.0), n, RATE, t0=0.0, exp=True)
    cut = cut * (1 + kw.get('env_mod', 1.5) * np.exp(-since / kw.get('decay', 0.09)))
    if kw.get('lfo'):
        rate_hz, depth = kw['lfo']
        cut = cut * 2 ** (depth * 0.5 * (np.cos(2 * np.pi * rate_hz * t) - 1))
    cut = np.minimum(cut, 12000)
    y = dsp.lowpass(out, cut, kw.get('q', 1.4))
    y = dsp.lowpass(y, cut * 1.5, 0.7)
    y = dsp.saturate(y * kw.get('pre', 2.0), kw.get('drive', 2.2))
    if kw.get('formant'):
        fc = 450 * 2 ** (1.8 * (1 - np.exp(-since / kw['formant'])))
        y = y + 1.4 * dsp.bandpass(y, fc, 3.0)
    if kw.get('comb'):
        y = comb(y, *kw['comb'])
    y = dsp.highpass(y, kw.get('hp', 90), 0.7)
    mid, side = y.mean(1, keepdims=True), (y[:, :1] - y[:, 1:]) / 2
    side = dsp.highpass(side, 300)
    y = np.concatenate([mid + side, mid - side], 1)
    return y * env[:, None]


def lead_line(notes, t0, t1, row_t, tune, cutoff=3200.0, voices=3, detune=0.14, vib=0.12):
    """Our saw lead playing a melody line with its slides, stereo."""
    n = n_of(t1 - t0 + 0.6)
    t = np.arange(n) / RATE
    for nt in notes:
        for r0, r1, trk in segments(nt):
            log('lead', row_t(r0), row_t(r1) - row_t(r0), trk + tune(nt))
    pitch, env, since = curves(notes, n, t0, row_t, tune, attack=0.006, release=0.18)
    pitch = pitch + vib * np.sin(2 * np.pi * 5.3 * t) * np.clip((since - 0.25) / 0.3, 0, 1)
    f = dsp.midi_hz(pitch)
    out = np.zeros((n, 2))
    for k in range(voices):
        d = (k - (voices - 1) / 2) / max(1, (voices - 1) / 2) * detune / 2
        out += dsp.pan(dsp.saw(f * 2 ** (d / 12), n, phase0=0.21 * k), (k - (voices - 1) / 2) * 0.7) / voices
    cut = cutoff * (1 + 1.2 * np.exp(-since / 0.12))
    y = dsp.lowpass(out, np.minimum(cut, 14000), 0.9)
    return y * env[:, None]


def segments(nt):
    """A note split at its tone-porta targets: [(row, row_end, trk)]. Porta up/down passing pitches
    are slides, not notes; a slide starting on the note's own row is a scoop into its target."""
    tg = [g for g in nt['glides'] if g[3] == 't']
    out, r0, p0 = [], nt['row'], nt['trk']
    for gr, gtrk, _, _ in tg:
        if gr - r0 >= 0.5:
            out.append((r0, gr, p0))
        r0, p0 = gr, gtrk
    if nt['end'] - r0 > 0.05:
        out.append((r0, nt['end'], p0))
    return out


def sample_line(src, k, notes, row_t, transpose=0.0, gate=1.0, release=0.04, vel=1.0, min_dur=0.0, part=None):
    """Payback sample k playing a line: [(time, mono audio)], each note retriggered from the
    sample start, slides as pitch curves, cut by the next note like a tracker channel."""
    out = []
    for i, nt in enumerate(notes):
        t = row_t(nt['row'])
        end = row_t(nt['row'] + max((nt['end'] - nt['row']) * gate, 0.05))
        dur = max(end - t, min_dur)
        if i + 1 < len(notes):
            dur = min(dur, row_t(notes[i + 1]['row']) - t)
        curve = None
        if nt['glides']:
            m = n_of(dur + release)
            curve = np.full(m, nt['trk'] + transpose)
            for gr, gtrk, grows, _ in nt['glides']:
                gs = n_of(row_t(gr) - t)
                if gs >= m:
                    continue
                ge = min(m, gs + max(1, n_of(row_t(gr + max(grows, 0.05)) - row_t(gr))))
                curve[gs:ge] = np.linspace(curve[gs], gtrk + transpose, ge - gs)
                curve[ge:] = gtrk + transpose
        y = src.play(k, nt['trk'] + transpose, dur, release, curve=curve,
                     looped=src.s.sample(k).looped)
        snd = src.tune.get(k, 0) + transpose
        for r0, r1, trk in segments(nt):
            if row_t(r0) < t + dur:
                log(part or 's%d' % k, row_t(r0), min(row_t(r1), t + dur) - row_t(r0), trk + snd)
        out.append((t, y * nt['vol'] * vel))
    return out


def rows_at(bar, scale=1.0):
    return lambda r: T(bar) + r * STEP * scale


def bars_of(notes, bars, scale=1.0, shift=0):
    """Copy of a parsed line limited to `bars` bars, shifted by whole bars (rows)."""
    out = []
    for nt in notes:
        if nt['row'] * scale < bars * 16:
            c = dict(nt)
            c['row'] = nt['row'] + shift * 16
            c['end'] = min(nt['end'], bars * 16 / scale) + shift * 16
            c['glides'] = [(r + shift * 16, p, g, k) for r, p, g, k in nt['glides']]
            out.append(c)
    return out

def take(notes, bars_list):
    """Pick source bars (16 rows each) and lay them end to end."""
    out = []
    for i, b in enumerate(bars_list):
        for nt in notes:
            if b * 16 <= nt['row'] < (b + 1) * 16:
                c = dict(nt)
                d = (i - b) * 16
                c['row'] += d
                c['end'] = min(nt['end'], (b + 1) * 16) + d
                c['glides'] = [(r + d, p, g, k) for r, p, g, k in nt['glides']]
                out.append(c)
    return out


# ---------------------------------------------------------------- instruments

KICK = Inst(synth.kick, f_start=185.0, f_end=49.0, pitch_time=0.03, decay=0.32, click=0.32, drive=2.2)
KICK_SOFT = Inst(synth.kick, f_start=150.0, f_end=49.0, pitch_time=0.04, decay=0.5, click=0.1, drive=1.4)
SNARE = Inst(synth.snare, tone=233.0, tone_decay=0.08, noise_decay=0.15, snap=0.74, bright=3900.0)
CLAP = Inst(synth.clap, tone=1568.0, tail=0.14)
HAT = Inst(synth.hat, decay=0.032)
OHAT = Inst(synth.hat, open=True, decay=0.2)
RIM = Inst(synth.rim)
PLUCK = Inst(synth.pluck, cut_hi=6000.0, cut_lo=500.0, fdecay=0.08, decay=0.25)
FMBELL = Inst(synth.fm_bell, ratio=1.0, index=1.8, decay=1.1)      # harmonic: an FM e-piano
SUPER = Inst(synth.supersaw, voices=7, detune=0.28, attack=0.12, release=0.5, cutoff=3600.0)
WARM = Inst(synth.warm_pad, attack=0.6, release=1.2, cutoff=1600.0)


def shaker(vel=1.0, seed=41):
    n = n_of(0.05)
    t = np.arange(n) / RATE
    x = dsp.highpass(dsp.noise(n, seed), 7000) * np.exp(-t / 0.011) * np.minimum(1, t / 0.002)
    return x / (np.max(np.abs(x)) + 1e-9) * vel


SHAKE = [shaker(1.0, 41 + i) for i in range(4)]


# ---------------------------------------------------------------- the arrangement

def build(out_base=None, rom=None, master=True, stems=None, render=True):
    src = Source(rom)
    del LOG[:]
    m = mix.Mix(BPM, bars=BARS, title=mix.remix_title(2), tail=4.0)
    m.bus('verb', lambda x: dsp.reverb(x, decay=2.6, predelay=0.02, damp=0.55, hp=280, wet_only=True), gain_db=-3)
    m.bus('room', lambda x: dsp.reverb(x, decay=0.7, predelay=0.005, damp=0.4, hp=400, wet_only=True), gain_db=-6)
    m.master_fx.append(lambda x: dsp.highpass(x, 20.0, 0.7) * dsp.undb(-4.0))   # DC/rumble, headroom
    m.bus('echo', lambda x: dsp.delay(x, 3 * STEP, feedback=0.38, mix=1.0, lp=4500, hp=300) - stereo(x) * 0.5,
          gain_db=-5)

    kick = m.track('kick', gain_db=-1.0)
    snare = m.track('snare', gain_db=0.0, sends={'room': 0.25, 'verb': 0.05})
    hats = m.track('hats', gain_db=-5.5, pan=0.15, hp=4000, sends={'room': 0.15})
    cym = m.track('cymbals', gain_db=-10.0, hp=500, sends={'verb': 0.15})
    brk = m.track('break', gain_db=-3.5, drive=1.3, eq=[('lowshelf', 140, -7, 0.7), ('peak', 4500, 2.5, 0.8),
                                                        ('peak', 350, -3, 1.0)],
                  comp=dict(threshold_db=-20, ratio=3, attack=0.003, release=0.08), sends={'room': 0.2},
                  duck=dict(key='kick', amount=0.25, release=0.08))
    sub = m.track('sub', gain_db=-10.0, duck=dict(key='kick', amount=0.85, release=0.13, hold=0.02))
    reese = m.track('reese', gain_db=-8.5, duck=dict(key='kick', amount=0.55, release=0.14))
    pads = m.track('pads', gain_db=-7.5, hp=180, sends={'verb': 0.35}, duck=dict(key='kick', amount=0.4, release=0.2))
    spad = m.track('synthpad', gain_db=-17.0, hp=220, sends={'verb': 0.4},
                   duck=dict(key='kick', amount=0.5, release=0.22))
    bell = m.track('bell', gain_db=-15.0, hp=200, pan=-0.2, sends={'echo': 0.25, 'verb': 0.25})
    mel = m.track('melody', gain_db=-6.0, hp=220, lp=9000, sends={'verb': 0.2, 'echo': 0.12},
                  duck=dict(key='kick', amount=0.15, release=0.1))
    lead = m.track('lead', gain_db=-16.0, hp=300, sends={'verb': 0.25, 'echo': 0.15})
    arp = m.track('arp', gain_db=-11.0, hp=250, pan=0.1, sends={'echo': 0.3, 'verb': 0.2},
                  duck=dict(key='kick', amount=0.25, release=0.1))
    pluck = m.track('pluck', gain_db=-18.0, hp=400, pan=-0.25, sends={'echo': 0.35, 'verb': 0.2})
    fmb = m.track('fmbell', gain_db=-15.0, hp=300, sends={'echo': 0.35, 'verb': 0.45})
    drone = m.track('drone', gain_db=-10.0, hp=50, sends={'verb': 0.3})
    fx = m.track('fx', gain_db=-12.0, sends={'verb': 0.3})
    rolls = m.track('rolls', gain_db=-9.0, sends={'room': 0.3, 'verb': 0.1})

    # ------------------------------------------------ material from the ROM
    BREAK_LOOP = src.drums([13])                    # 4-bar break: K . h h S h K . h h K . S h K .
    FILL_STOP = [d for d in src.drums([21]) if d[0] < 8]     # the stop fill (half a bar)
    FILL_28 = [d for d in src.drums([28]) if d[0] < 16]      # snare fill with retriggers
    FILL_DT = [(d[0] - 48,) + d[1:] for d in src.drums([12]) if d[0] >= 48]   # double-time fill (32nds)
    OUT_BREAK = src.drums([29, 30])                 # the break fading out (volumes from the patterns)
    BASS_PEDAL = src.line([13], 0)                  # C pedal riff, 4 bars
    BASS_MAIN = src.line([17, 18], 0)               # riff over C C F F Eb Eb Bb Bb
    BASS_FIN = src.line([24, 25, 26, 27], 0)        # 16 bars, same riff
    MEL_A = src.line([17, 18], 3)                   # melody, 8 bars
    MEL_A2 = src.line([19, 20], 3)
    MEL_B = src.line([24, 25, 26, 27], 1)           # melody with the drop-2 variant, 16 bars
    ARP_A = src.line([22, 23], 0)                   # arpeggio Cm F Eb Bb, 8 bars
    ARP_O = src.line([29, 30], 1)                   # outro arpeggio (fading volumes)
    STAB = src.line([9, 10], 0)                     # stab riff, 8 bars
    STAB_DT = src.line([11, 12], 0)                 # stab riff in double time (rows = 32nds)
    STAB_C = take(STAB, [0, 1, 0, 1, 0, 1, 0, 1])   # its C-only bars (bar 4 has B4/D5 for the build's chords)
    DRONE = src.line([29], 0)                       # sample 19 held low (outro)
    BUILD_PADS = src.pads([9, 10], 3)               # Fmaj7 Gmaj7 Abmaj7 Bbmaj9 (rising)
    DROP_PADS = [(r, 4 if k == 6 else k, trk) for r, k, trk in src.pads([13, 14], 3)]   # 2 3 4 5 4 . 7 8
    GATE, GATE_TRIG = src.gates([13])               # the bell's gate rhythm, 4 bars

    # ------------------------------------------------ helpers that place parts
    def drum_rows(events, bar, scale=1.0, vel=1.0, step=0.0, hp=None, vol_curve=None):
        """Re-trigger break slices: tracker semantics (each slice cut by the next), E9 retrigger,
        ED delay; scale 0.5 = rows are 32nds, 2 = rows are 8ths."""
        row_d = STEP * scale
        hits = []
        for r, k, vol, e, p in events:
            t = T(bar, step) + r * row_d
            if e == 0xe and p >> 4 == 0xd:
                t += (p & 15) / 6 * row_d
                hits.append((t, k, vol))
            elif e == 0xe and p >> 4 == 0x9 and p & 15:
                x = p & 15
                for j in range(0, 6, x):
                    hits.append((t + j / 6 * row_d, k, vol))
            else:
                hits.append((t, k, vol))
        hits.sort()
        for i, (t, k, vol) in enumerate(hits):
            nxt = hits[i + 1][0] if i + 1 < len(hits) else t + 0.4
            y = src.play(k, 76, None)
            whole = len(y) <= n_of(nxt - t)     # plays to its own end: some slices are trimmed hats
            y = y[:max(16, n_of(nxt - t) + n_of(0.002))]
            y = y * ramp_env(len(y), 0.0006, 0.025 if whole else 0.003)
            if hp:
                y = dsp.highpass(y, float(np.exp(np.interp(t, [a for a, _ in hp], np.log([f for _, f in hp])))))
            g = vol * vel * (vol_curve(t) if vol_curve else 1.0)
            brk.clip(t, y * g, fade=0)

    def bell_gate(bar0, bars, vel=1.0):
        """The bell (sample 15 at C-1) chopped by the original's gate rhythm (EC cuts)."""
        span = 64
        n = n_of(T(bar0 + bars) - T(bar0) + 0.05)
        y = np.zeros(n)
        g = np.zeros(n)
        for rep in range(int(math.ceil(bars / 4))):
            off = rep * span
            trig = [off + r for r in GATE_TRIG]
            for j, r in enumerate(trig):
                i0 = n_of((r) * STEP)
                if i0 >= n:
                    break
                i1 = min(n, n_of((trig[j + 1]) * STEP) if j + 1 < len(trig) else n)
                s = src.play(15, 48, None)
                seg = s[:i1 - i0]
                y[i0:i0 + len(seg)] = seg * ramp_env(len(seg), 0.001, 0.004)
            for a, b in GATE:
                i0, i1 = n_of((off + a) * STEP), n_of((off + b) * STEP)
                if i0 < n:
                    g[i0:min(n, i1)] = 1.0
        k = n_of(0.002)
        g = np.convolve(g, np.ones(k) / k, 'same')
        bell.clip(T(bar0), y * g * vel, fade=0.002)

    def pad_clip(k, trk, t, dur, vel=1.0, attack=0.05, release=0.5, track=None):
        """A Payback chord pad sample, crossfade-looped, slightly detuned left/right."""
        for pc in src.pad_pcs(k):
            log('pad%d' % k, t, dur, 60 + (pc + round(trk) - 72) % 12)
        L = src.play(k, trk - 0.06, dur, release, attack=attack, looped=True)
        R = src.play(k, trk + 0.06, dur, release, attack=attack, looped=True)
        (track or pads).clip(t, np.stack([L, R], 1) * vel, fade=0.004)

    def chord_pads(bar0, bars, vel=1.0, synth_pad=False, sp_vel=0.6, pad_map=PADS):
        b = 0
        while b < bars:
            k, L = pad_map[b % 8], 1
            while b + L < bars and pad_map[(b + L) % 8] == k and (b + L) % 8:
                L += 1
            pad_clip(k, 72, T(bar0 + b), T(L) - 0.02, vel)
            b += L
        if synth_pad:
            for b in range(0, bars, 2):
                spad.chord(T(bar0 + b), SUPER, list(VOICE[KEYS[b % 8]]), T(min(2, bars - b)) - 0.08, sp_vel)
                for v in VOICE[KEYS[b % 8]]:
                    log('synthpad', T(bar0 + b), T(min(2, bars - b)) - 0.08, mix.parse_note(v))

    def kick_snare(bar0, bars, kicks=(0, 10), snares=(4, 12), vel=1.0, fills=True, ghosts=True):
        for b in range(bars):
            bar = bar0 + b
            ks, ss = list(kicks), list(snares)
            if fills and b % 8 == 7:
                ss += [14, 15]
            if fills and b % 16 == 15:
                ks, ss = [0, 10], [4, 12, 13, 14, 15]
            for s in ks:
                kick.hit(T(bar, s), KICK, vel)
            for s in ss:
                v = vel if s in (4, 12) else vel * 0.55
                snare.hit(T(bar, s), SNARE, v)
                if s in (4, 12):
                    snare.hit(T(bar, s), CLAP, v * 0.45)
            if ghosts and b % 2 == 1:
                snare.hit(T(bar, 7), SNARE, vel * 0.16)
                snare.hit(T(bar, 9), SNARE, vel * 0.12)

    def hat_groove(bar0, bars, vel=1.0, opens=True, sixteenths=True):
        acc = (0.5, 0.25, 1.0, 0.3, 0.45, 0.25, 0.95, 0.35, 0.5, 0.25, 1.0, 0.3, 0.45, 0.3, 0.9, 0.4)
        for b in range(bars):
            for s in range(16):
                if s in (2, 6, 10, 14):
                    if opens and s == 14 and b % 2 == 1:
                        hats.hit(T(bar0 + b, s), OHAT, 0.55 * vel)
                    else:
                        hats.hit(T(bar0 + b, s), HAT, acc[s] * 0.8 * vel)
                elif sixteenths:
                    hats.hit(T(bar0 + b, s), SHAKE[(b * 16 + s) % 4], acc[s] * 0.6 * vel)

    def break_loop(bar0, bars, vel=1.0, scale=1.0, vol_curve=None, hp=None):
        span = int(round(4 * scale))
        for rep in range(0, bars, span):
            ev = [e for e in BREAK_LOOP if e[0] * scale < (bars - rep) * 16]
            drum_rows(ev, bar0 + rep, scale, vel, vol_curve=vol_curve, hp=hp)

    def roll(bar0, bars, vel0=0.25, vel1=1.0):
        """Snare roll: quarters, 8ths, 16ths, 32nds over 4 bars (or the last part of it)."""
        divs = (4, 8, 16, 32)[-bars:]
        for b, d in enumerate(divs):
            for j in range(d):
                x = (b + j / d) / bars
                rolls.hit(T(bar0 + b, j * 16 / d), SNARE, vel0 + (vel1 - vel0) * x ** 1.3)

    def riser(bar0, bars, gain_db=0.0):
        fx.clip(T(bar0), synth.riser(T(bars), f0=300, f1=9000, tone=0.3), gain_db=gain_db)

    def impact(bar, gain_db=0.0):
        fx.clip(T(bar), synth.impact(3.0, freq=32.7), gain_db=gain_db)
        cym.clip(T(bar), synth.cymbal(2.8), gain_db=0)

    def rev_cym(bar, beats=4, gain_db=0.0):
        d = 60 / BPM * beats
        fx.clip(T(bar) - d, synth.reverse_cymbal(d), gain_db=gain_db)

    def bass(notes, bar0, bars, scale=1.0, sub_vel=1.0, reese_vel=1.0, **kw):
        t0, t1 = T(bar0), T(bar0 + bars)
        rt = rows_at(bar0, scale)
        nn = [dict(nt, end=min(nt['end'], (t1 - T(bar0)) / (STEP * scale))) for nt in notes
              if rt(nt['row']) < t1 - 1e-6]
        if sub_vel:
            sub.clip(t0, bass_line(src, nn, t0, t1, rt, 'sub') * sub_vel, fade=0.003)
        if reese_vel:
            reese.clip(t0, bass_line(src, nn, t0, t1, rt, 'reese', **kw) * reese_vel, fade=0.003)

    def fm(t, midi, dur, vel):
        fmb.note(t, FMBELL, midi, dur, vel)
        log('fmbell', t, dur, midi)

    def place(track, clips, gain=1.0, pan=None, filt=None):
        for t, y in clips:
            if filt:
                y = filt(t, y)
            track.clip(t, y * gain, pan=pan, fade=0.002)

    def melody19(notes, bar0, vel=1.0, transpose=0.0, layer=0.0, scale=1.0):
        rt = rows_at(bar0, scale)
        place(mel, sample_line(src, 19, notes, rt, transpose, release=0.07), vel)
        if layer:
            span = max(nt['end'] for nt in notes)
            ld = lead_line(notes, T(bar0), rt(span), rt, lambda nt: src.tune[19] + transpose + 12)
            lead.clip(T(bar0), ld * layer, fade=0.003)

    def stab_line(notes, bar0, scale=1.0, vel=1.0, gate=1.0, layer=0.0, transpose=0.0):
        rt = rows_at(bar0, scale)
        place(arp, sample_line(src, 1, notes, rt, transpose, gate=gate, release=0.03, min_dur=0.045), vel)
        if layer:
            for nt in notes:
                pluck.note(rt(nt['row']), PLUCK, nt['trk'] + src.tune[1] + transpose + 12, 0.08, layer)
                log('pluck', rt(nt['row']), 0.08, nt['trk'] + src.tune[1] + transpose + 12)

    def sub_roots(bar0, keys, vel=0.6, bars_each=1):
        notes = []
        for i, key in enumerate(keys):
            notes.append(dict(row=i * 16 * bars_each, end=(i + 1) * 16 * bars_each - 0.5,
                              trk=mix.parse_note(ROOT[key]) - src.tune[10], ins=10, vol=1.0, glides=[]))
        t1 = T(bar0 + len(keys) * bars_each)
        sub.clip(T(bar0), bass_line(src, notes, T(bar0), t1, rows_at(bar0), 'sub') * vel, fade=0.01)

    # ================================================= 0 INTRO (16 bars)
    for i, k in enumerate((3, 5, 3, 5, 3, 5, 3, 5)):
        b = INTRO + 2 * i
        v = min(1.0, 0.35 + 0.1 * i)
        pad_clip(k, 72, T(b), T(2) - 0.02, v, attack=0.6 if i == 0 else 0.08, release=0.6)
    fx.clip(T(0), synth.downlifter(T(4), f0=9000, f1=300)[::-1].copy(), gain_db=-10)
    bell_gate(INTRO + 4, 12, 0.8)
    drum_rows([(r, 23, 0.5, 0, 0) for r in range(0, 16 * 8, 4)], INTRO + 4, vel=0.45)     # the ride, quarters
    break_loop(INTRO + 8, 8, 0.85, hp=[(T(INTRO + 8), 2500), (T(BUILD) - 0.2, 250)])
    sub_roots(INTRO + 8, ('C',) * 8, vel=0.35)
    hat_groove(INTRO + 12, 4, 0.6, opens=False)
    stab_line(bars_of(STAB_C, 4), INTRO + 12, vel=0.7)
    riser(INTRO + 12, 4, -4)
    rev_cym(BUILD, 4, -4)

    # ================================================= 16 BUILD (8 bars): stab riff over rising chords
    for r, k, trk in BUILD_PADS:
        nxt = [x[0] for x in BUILD_PADS if x[0] > r]
        dur = ((nxt[0] if nxt else 128) - r) * STEP
        pad_clip(k, trk, T(BUILD) + r * STEP, dur - 0.02, 0.85)
    stab_line(STAB, BUILD, vel=0.9, layer=0.5)
    for b in range(8):
        kick.hit(T(BUILD + b, 0), KICK, 0.9)
        if b % 2 == 1:
            kick.hit(T(BUILD + b, 11), KICK, 0.7)
        snare.hit(T(BUILD + b, 8), SNARE, 0.85)
        snare.hit(T(BUILD + b, 8), CLAP, 0.4)
    hat_groove(BUILD, 8, 0.75)
    break_loop(BUILD, 8, 0.6, scale=2.0)          # the break in half time
    sub_roots(BUILD, ('F', 'F', 'G', 'G', 'Ab', 'Ab', 'Bb', 'Bb'), vel=0.35)
    bell_gate(BUILD, 8, 0.6)
    riser(BUILD + 4, 4, -3)

    # ================================================= 24 DOUBLE-TIME ROLL (4 bars)
    pad_clip(3, 72, T(ROLL), T(4) - 0.1, 0.9, attack=0.02, release=0.3)
    stab_line(STAB_DT, ROLL, scale=0.5, vel=0.9, layer=0.4)
    roll(ROLL, 4, 0.2, 1.0)
    for b in range(2):
        for s in (0, 8):
            kick.hit(T(ROLL + b, s), KICK_SOFT, 0.7)
    drum_rows(FILL_DT, ROLL + 3, scale=0.5, vel=0.9, step=8)
    fx.clip(T(ROLL), synth.riser(T(4) - STEP * 2, f0=400, f1=12000, tone=0.4), gain_db=-1)
    rev_cym(DROP1, 2, -2)

    # ================================================= 28 DROP 1 (16 bars): the C pedal riff
    impact(DROP1)
    for rep in range(4):
        bass(BASS_PEDAL, DROP1 + 4 * rep, 4, cut=[(0, 700), (T(4), 1100)] if rep == 0 else 1100,
             env_mod=1.8, decay=0.08)
    kick_snare(DROP1, 16)
    hat_groove(DROP1, 16)
    break_loop(DROP1, 16, 1.0)
    for rep in range(2):
        for r, k, trk in DROP_PADS:
            nxt = [x[0] for x in DROP_PADS if x[0] > r]
            dur = ((nxt[0] if nxt else 128) - r) * STEP
            pad_clip(k, trk, T(DROP1 + 8 * rep) + r * STEP, dur - 0.02, 0.75)
    bell_gate(DROP1, 16, 0.5)
    stab_line(STAB_C, DROP1 + 8, vel=0.8, layer=0.6)
    cym.clip(T(DROP1 + 8), synth.cymbal(2.4), gain_db=-3)
    fx.clip(T(DROP1 + 15, 8), synth.noise_sweep(T(0, 8), f0=600, f1=10000), gain_db=-6)

    # ================================================= 44 DROP 1B (16 bars): the melody
    impact(DROP1B, -4)
    bass(BASS_MAIN, DROP1B, 8, cut=1000, env_mod=1.8, decay=0.08)      # darker under the melody
    bass(BASS_MAIN, DROP1B + 8, 8, cut=1100, env_mod=2.2, decay=0.08)
    kick_snare(DROP1B, 16)
    hat_groove(DROP1B, 16)
    break_loop(DROP1B, 15, 1.0)
    drum_rows([e for e in BREAK_LOOP if e[0] < 8] + [(x[0] + 8,) + tuple(x[1:]) for x in FILL_STOP],
              DROP1B + 15, vel=1.0)                       # half a bar, then the stop fill
    chord_pads(DROP1B, 16, 0.7, synth_pad=True, sp_vel=0.55)
    melody19(MEL_A, DROP1B, 1.0, layer=0.0)
    melody19(MEL_A2, DROP1B + 8, 1.0, layer=0.8)
    bell_gate(DROP1B, 16, 0.35)
    cym.clip(T(DROP1B + 8), synth.cymbal(2.4), gain_db=-3)

    # ================================================= 60 BREAKDOWN (8 bars): the arpeggio
    fx.clip(T(BREAK), synth.downlifter(T(2), f0=7000, f1=200), gain_db=-6)
    cym.clip(T(BREAK), synth.cymbal(3.0), gain_db=-4)
    lp_arp = lambda t, y: sweep(y, 'lowpass', [(T(BREAK), 900), (T(BELL), 6000), (T(SWITCH), 9000)], t0=t)  # noqa
    place(arp, sample_line(src, 1, ARP_A, rows_at(BREAK)), 0.9, filt=lp_arp)
    place(arp, sample_line(src, 1, ARP_A, rows_at(BELL)), 0.9, filt=lp_arp)
    chord_pads(BREAK, 16, 0.6)
    for b in range(0, 16, 2):
        spad.chord(T(BREAK + b), WARM, list(VOICE[KEYS[b % 8]]), T(2) - 0.05, 0.7)
        for v in VOICE[KEYS[b % 8]]:
            log('warmpad', T(BREAK + b), T(2) - 0.05, mix.parse_note(v))
    sub_roots(BREAK, KEYS + KEYS[:6], vel=0.25)
    bell_gate(BREAK, 16, 0.55)
    drum_rows([(r, 23, 0.5, 0, 0) for r in range(0, 16 * 8, 4)], BREAK + 4, vel=0.3)

    # ================================================= 68 BELL MELODY + BUILD (8 bars)
    for nt in MEL_A:
        for r0, r1, trk in segments(nt):
            fm(rows_at(BELL)(r0), trk + src.tune[19] + 12, max(0.15, (r1 - r0) * STEP), 0.8 * nt['vol'])
    hat_groove(BELL, 8, 0.5, opens=False)
    break_loop(BELL + 4, 4, 0.8, vol_curve=lambda t: min(1.0, 0.3 + 0.7 * (t - T(BELL + 4)) / T(4)),
               hp=[(T(BELL + 4), 1800), (T(SWITCH) - 0.2, 200)])
    roll(BELL + 4, 4, 0.15, 0.95)
    for b in range(2):
        for s in range(0, 16, 4):
            kick.hit(T(BELL + 6 + b, s), KICK_SOFT, 0.55 + 0.1 * b)
    riser(BELL + 4, 4, -2)
    rev_cym(SWITCH, 2, -2)

    # ================================================= 76 SWITCH-UP (8 bars): half-time neuro
    impact(SWITCH)
    half = take(BASS_MAIN, [0, 2, 4, 6])          # one source bar per chord, at half speed
    bass(half, SWITCH, 8, scale=2.0, cut=700, env_mod=2.5, decay=0.18, lfo=(BPM / 60 * 2, 1.6),
         comb=(1.2, 3.0, BPM / 60 / 2, 0.6), drive=3.0, reese_vel=1.1)
    for b in range(8):
        kick.hit(T(SWITCH + b, 0), KICK, 1.0)
        kick.hit(T(SWITCH + b, 3 if b % 2 else 11), KICK, 0.75)
        snare.hit(T(SWITCH + b, 8), SNARE, 1.0)
        snare.hit(T(SWITCH + b, 8), CLAP, 0.5)
        if b % 4 == 3:
            snare.hit(T(SWITCH + b, 14), SNARE, 0.4)
            snare.hit(T(SWITCH + b, 15), SNARE, 0.55)
    hat_groove(SWITCH, 8, 0.8, sixteenths=False)
    break_loop(SWITCH, 8, 0.9, scale=2.0)
    place(arp, sample_line(src, 1, ARP_A, rows_at(SWITCH)), 0.75)
    chord_pads(SWITCH, 8, 0.55)
    cym.clip(T(SWITCH + 4), synth.cymbal(2.0), gain_db=-6)
    fx.clip(T(SWITCH + 7, 8), synth.noise_sweep(T(0, 8), f0=500, f1=12000), gain_db=-4)

    # ================================================= 84 ROLLER (8 bars): talking reese, stab riff
    bass(BASS_MAIN, ROLLER, 8, cut=900, env_mod=3.0, decay=0.06, formant=0.12, drive=2.6,
         comb=(0.8, 2.0, 0.25, 0.4))
    kick_snare(ROLLER, 8)
    hat_groove(ROLLER, 8)
    break_loop(ROLLER, 8, 1.0)
    drum_rows(FILL_DT, ROLLER + 7, scale=0.5, vel=0.8, step=8)
    stab_line(STAB_C, ROLLER, vel=0.8, layer=0.6)
    place(arp, sample_line(src, 1, ARP_A, rows_at(ROLLER)), 0.45)
    chord_pads(ROLLER, 8, 0.6, synth_pad=True, sp_vel=0.4)
    rev_cym(FINALE, 2, -4)

    # ================================================= 92 FINALE (16 bars): the full melody
    impact(FINALE, -2)
    bass(BASS_FIN, FINALE, 16, cut=1050, env_mod=2.0, decay=0.08)
    kick_snare(FINALE, 15)
    kick.hit(T(FINALE + 15, 0), KICK, 1.0)
    snare.hit(T(FINALE + 15, 4), SNARE, 1.0)
    hat_groove(FINALE, 16)
    for b in range(16):
        for s in (0, 4, 8, 12):
            cym.clip(T(FINALE + b, s), synth.cymbal(0.9, kind='ride'), gain_db=-9 if s else -6)
    break_loop(FINALE, 15, 1.0)
    drum_rows(FILL_28, FINALE + 15, vel=1.0)
    melody19(MEL_B, FINALE, 1.0, layer=0.9)
    for nt in MEL_B:
        if nt['row'] >= 128:
            for r0, r1, trk in segments(nt):
                fm(rows_at(FINALE)(r0), trk + src.tune[19] + 24, max(0.12, (r1 - r0) * STEP), 0.35 * nt['vol'])
    place(arp, sample_line(src, 1, ARP_A, rows_at(FINALE + 8)), 0.35)
    chord_pads(FINALE, 16, 0.65, synth_pad=True, sp_vel=0.6)
    bell_gate(FINALE, 16, 0.3)
    cym.clip(T(FINALE + 8), synth.cymbal(2.4), gain_db=-3)

    # ================================================= 108 OUTRO (8 bars): arpeggio, break fades
    cym.clip(T(OUTRO), synth.cymbal(3.0), gain_db=-4)
    place(arp, sample_line(src, 1, ARP_O, rows_at(OUTRO)), 1.6)
    drum_rows(OUT_BREAK, OUTRO, vel=1.0)
    bass(take(BASS_FIN, [0, 1, 2, 3]), OUTRO, 4, cut=[(0, 1200), (T(4), 400)], env_mod=1.5, decay=0.08,
         reese_vel=0.8)
    sub_roots(OUTRO + 4, ('Eb', 'Eb', 'Bb', 'Bb'), vel=0.5)
    kick_snare(OUTRO, 4, fills=False)
    for b in range(4, 6):
        kick.hit(T(OUTRO + b, 0), KICK, 0.7)
        snare.hit(T(OUTRO + b, 8), SNARE, 0.5)
    hat_groove(OUTRO, 6, 0.7)
    chord_pads(OUTRO, 8, 0.7)
    d = DRONE[0]
    dr = dsp.lowpass(src.play(19, d['trk'], T(4) - 0.4, 0.4, attack=0.3, looped=True), 250.0, order=4)
    drone.clip(T(OUTRO), dr * 0.9, fade=0.01)
    log('drone', T(OUTRO), T(4), d['trk'] + src.tune[19])

    # ================================================= 116 CODA (4 bars) and 120 the end
    chord_pads(CODA, 4, 0.8)
    for nt in bars_of(MEL_A, 2):
        for r0, r1, trk in segments(nt):
            fm(rows_at(CODA)(r0), trk + src.tune[19] + 12, max(0.15, (r1 - r0) * STEP), 0.7 * nt['vol'])
    bell_gate(CODA, 4, 0.5)
    sub_roots(CODA, ('C', 'C', 'F', 'F'), vel=0.4)
    # final chord: Cm9 pad, sub C, the stab, a crash and the bell ringing out
    pad_clip(3, 72, T(END), T(2.5), 0.9, attack=0.01, release=2.0)
    sub_roots(END, ('C', 'C'), vel=0.55)
    stab_line([dict(row=0, end=1, trk=72, ins=1, vol=0.3, glides=[])], END, vel=1.0, layer=0.8)
    kick.hit(T(END), KICK, 1.0)
    impact(END, -3)
    bell.clip(T(END), src.play(15, 48, None) * 0.9, fade=0.002)
    for i, v in enumerate((0.5, 0.25, 0.12, 0.06)):          # the original's last sub blips
        sub.clip(T(END + 1, i * 3), stereo(src.play(20, 48, STEP * 1.5, 0.02, looped=True)) * v, fade=0.003)

    if not render:
        return None, {}, m
    audio, rep = m.render(master=master, lufs=-14.0, true_peak=-1.0, fade_out=2.5, stems=stems)
    if out_base:
        rep.update(m.export(audio, out_base, kbps=320))
    return audio, rep, m


if __name__ == '__main__':
    base = sys.argv[1] if len(sys.argv) > 1 else 'remix_song2'
    _, report, _ = build(base)
    print(report)
