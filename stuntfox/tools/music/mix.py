"""Multitrack arranger and mixer for the remixes, plus helpers that pull Payback's original
songs apart (channels, notes, chords, samples) so a remix can reuse them.

    import mix, synth
    m = mix.Mix(bpm=130, bars=64, title=mix.remix_title(1))
    drums = m.track('drums', gain_db=-2, sends={'verb': 0.05})
    drums.pattern(0, 16, 'x...x...x...x...', synth.Inst(synth.kick))
    bass = m.track('bass', duck='drums', lp=[(m.bar(0), 300), (m.bar(8), 4000)])
    bass.note(m.bar(0), synth.Inst(synth.reese), 'E1', m.beats(4))
    m.bus('verb', lambda x: dsp.reverb(x, 2.5, wet_only=True))
    audio, report = m.render(lufs=-14, true_peak=-1, fade_out=6)
    m.export(audio, '/path/remix_song1')          # .wav + .mp3 (320 kbps, ID3 title)

    o = mix.Original(1)                            # Payback song 1 from $PAYBACK_ROM
    o.bpm, o.notes(channel=0), o.stem(2), o.chords(), o.key(), o.sample_inst(14)

Times are seconds everywhere (Mix.bar/beats/step convert); pitches are MIDI numbers (60 = C4),
note names ('A#3') or Hz via hz=. Rendering is deterministic.
"""
import math
import os
import re
import subprocess
from dataclasses import dataclass

import numpy as np

import dsp
import pbsong
import render
from dsp import RATE

NOTE_RE = re.compile(r'^([A-Ga-g])([#b]?)(-?\d+)$')
_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
PC_NAMES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')


def remix_title(n):
    return 'Star-FlyBack Remix - Song %d' % n


def parse_note(p):
    """MIDI number from 60, 60.5, 'C4', 'A#3', 'Eb2' (C4 = 60)."""
    if isinstance(p, str):
        m = NOTE_RE.match(p.strip())
        if not m:
            raise ValueError('bad note %r' % p)
        pc = _PC[m.group(1).upper()] + {'#': 1, 'b': -1, '': 0}[m.group(2)]
        return 12 * (int(m.group(3)) + 1) + pc
    return float(p)


def note_name(m):
    m = int(round(m))
    return '%s%d' % (PC_NAMES[m % 12], m // 12 - 1)


CHORDS = {'': (0, 4, 7), 'm': (0, 3, 7), '7': (0, 4, 7, 10), 'm7': (0, 3, 7, 10), 'maj7': (0, 4, 7, 11),
          'sus2': (0, 2, 7), 'sus4': (0, 5, 7), 'dim': (0, 3, 6), '5': (0, 7), 'add9': (0, 4, 7, 14),
          'm9': (0, 3, 7, 10, 14)}


def chord(name, octave=3):
    """MIDI notes of a chord name like 'Am', 'F#m7', 'C5', 'Gsus4' rooted in `octave`."""
    m = re.match(r'^([A-G][#b]?)(.*)$', name)
    root = parse_note(m.group(1) + str(octave))
    return [root + i for i in CHORDS[m.group(2)]]


SCALES = {'major': (0, 2, 4, 5, 7, 9, 11), 'minor': (0, 2, 3, 5, 7, 8, 10), 'dorian': (0, 2, 3, 5, 7, 9, 10),
          'phrygian': (0, 1, 3, 5, 7, 8, 10), 'harmonic_minor': (0, 2, 3, 5, 7, 8, 11),
          'minor_pent': (0, 3, 5, 7, 10), 'major_pent': (0, 2, 4, 7, 9)}


def scale(root, mode='minor', octaves=2):
    r = parse_note(root) if isinstance(root, str) else root
    return [r + 12 * o + i for o in range(octaves) for i in SCALES[mode]]


@dataclass
class Note:
    time: float                 # seconds
    dur: float                  # seconds
    midi: float                 # sounding pitch (Payback notes: tuned by the sample's pitch)
    vel: float = 1.0            # 0..1
    beat: float = 0.0           # in the source's beats (4 rows a beat for Payback songs)
    dur_beats: float = 0.0
    ins: int = 0                # Payback sample number (0 = none)
    channel: int = -1
    period: int = 0
    pcs: tuple = ()             # pitch classes sounding (chord samples), else (midi % 12,)

    @property
    def name(self):
        return note_name(self.midi)


def transpose(notes, semis):
    return [Note(**{**n.__dict__, 'midi': n.midi + semis}) for n in notes]


def retime(notes, src_t0, dst_t0, stretch=1.0):
    """Move notes so src_t0 lands on dst_t0, scaling times/durations by `stretch`."""
    return [Note(**{**n.__dict__, 'time': dst_t0 + (n.time - src_t0) * stretch, 'dur': n.dur * stretch})
            for n in notes]


def from_beats(notes, bpm, t0=0.0):
    """Notes whose .beat/.dur_beats are set -> times at a new bpm starting at t0."""
    sp = 60.0 / bpm
    return [Note(**{**n.__dict__, 'time': t0 + n.beat * sp, 'dur': max(n.dur_beats, 0.01) * sp}) for n in notes]


# ---------------------------------------------------------------- the arranger

class Track:
    def __init__(self, mix, name, gain_db=0.0, pan=0.0, width=1.0, hp=None, lp=None, q=0.7071, eq=None,
                 drive=0.0, comp=None, sends=None, duck=None, fx=None, mute=False):
        self.mix = mix
        self.name = name
        self.gain_db = gain_db
        self.pan_ = pan
        self.width = width
        self.hp, self.lp, self.q = hp, lp, q
        self.eq = eq or []
        self.drive = drive
        self.comp = comp                # dict for dsp.compress
        self.sends = dict(sends or {})
        self.duck_ = duck               # track name, list of times, or dict(key=..., amount=...)
        self.fx = list(fx or [])        # callables x(n,2) -> x
        self.mute = mute
        self.events = []                # (time, audio (n,) or (n,2), gain, pan)
        self.autos = {}
        self.onsets = []

    # events
    def clip(self, t, audio, gain_db=0.0, pan=None, rate=None, fade=0.003):
        """Place audio (mono or stereo) at time t; rate: its sample rate if not RATE."""
        a = np.asarray(audio, np.float64)
        if rate and rate != self.mix.rate:
            from scipy.signal import resample_poly
            g = math.gcd(int(rate), int(self.mix.rate))
            a = resample_poly(a, int(self.mix.rate) // g, int(rate) // g, axis=0)
        if fade:
            a = dsp.fade(a, fade, fade, self.mix.rate)
        self.events.append((float(t), a, dsp.undb(gain_db), pan))
        self.onsets.append(float(t))
        return self

    def note(self, t, inst, pitch=None, dur=0.25, vel=1.0, hz=None, pan=None, gain_db=0.0):
        """One note: inst(freq, dur, vel) at time t. pitch MIDI/name, or hz=."""
        f = hz if hz is not None else (None if pitch is None else float(dsp.midi_hz(parse_note(pitch))))
        return self.clip(t, inst(f, dur, vel), gain_db, pan, fade=0)

    def chord(self, t, inst, pitches, dur=0.5, vel=1.0, pan=None, gain_db=0.0):
        """Several pitches at once (each through inst), level-compensated."""
        g = gain_db - 10 * math.log10(max(1, len(pitches)))
        for p in pitches:
            self.note(t, inst, p, dur, vel, pan=pan, gain_db=g)
        return self

    def hit(self, t, inst, vel=1.0, pitch=None, pan=None, gain_db=0.0):
        """A drum hit (inst callable or an array)."""
        if callable(inst):
            f = None if pitch is None else float(dsp.midi_hz(parse_note(pitch)))
            a = inst(f, 0.25, vel)
        else:
            a = np.asarray(inst) * vel
        return self.clip(t, a, gain_db, pan, fade=0)

    def notes(self, notes, inst, transpose=0.0, vel_scale=1.0, time_offset=0.0, legato=1.0):
        """Play a list of Note (or (time, midi, dur[, vel]) tuples)."""
        for n in notes:
            if not isinstance(n, Note):
                n = Note(n[0], n[2], parse_note(n[1]), n[3] if len(n) > 3 else 1.0)
            self.note(n.time + time_offset, inst, n.midi + transpose, n.dur * legato, n.vel * vel_scale)
        return self

    def pattern(self, start, bars, steps, inst, pitch=None, vel=1.0, step_beats=0.25, swing=0.0, accent=1.25,
                dur=None):
        """Step pattern from bar `start` for `bars` bars: 'x' hit, 'X' accent, '.' rest, repeated
        to fill. pitch may be a list cycled per hit. swing delays every other step (0..0.5)."""
        steps = steps.replace(' ', '').replace('|', '')
        per_bar = int(round(self.mix.beats_per_bar / step_beats))
        total = int(round(bars * per_bar))
        hits = 0
        for i in range(total):
            c = steps[i % len(steps)]
            if c not in 'xX':
                continue
            t = self.mix.bar(start) + self.mix.beats(i * step_beats + (swing * step_beats if i % 2 else 0))
            v = vel * (accent if c == 'X' else 1.0)
            p = pitch[hits % len(pitch)] if isinstance(pitch, (list, tuple)) else pitch
            hits += 1
            if dur is None and getattr(inst, 'drum', False) or (dur is None and p is None):
                self.hit(t, inst, min(v, 1.0), p)
            else:
                self.note(t, inst, p, dur or self.mix.beats(step_beats), min(v, 1.0))
        return self

    def automate(self, param, points):
        """param: 'gain' (dB), 'lp', 'hp' (Hz), 'pan' (-1..1), 'send:<bus>' (0..1);
        points [(seconds, value), ...]."""
        self.autos[param] = points
        return self

    def duck(self, key, amount=0.6, attack=0.004, hold=0.015, release=0.18, shape=1.5):
        """Sidechain-style ducking keyed by another track's onsets (name) or a list of times."""
        self.duck_ = dict(key=key, amount=amount, attack=attack, hold=hold, release=release, shape=shape)
        return self

    # processing
    def _bounce(self, n):
        rate = self.mix.rate
        x = np.zeros((n, 2))
        for t, a, g, p in self.events:
            i = int(round(t * rate))
            if i >= n:
                continue
            if a.ndim == 1:
                a = dsp.pan(a, self.pan_ if p is None else p)
            elif self.width != 1.0:
                mid = a.mean(1, keepdims=True)
                a = mid + (a - mid) * self.width
            if i < 0:
                a, i = a[-i:], 0
            j = min(n, i + len(a))
            x[i:j] += a[:j - i] * g
        return x

    def _process(self, x):
        rate = self.mix.rate
        hp = self.autos.get('hp', self.hp)
        lp = self.autos.get('lp', self.lp)
        if hp is not None:
            x = dsp.highpass(x, hp, self.q, rate=rate)
        if lp is not None:
            x = dsp.lowpass(x, lp, self.q, rate=rate)
        if self.eq:
            x = dsp.eq(x, self.eq, rate)
        if self.drive:
            x = dsp.saturate(x, self.drive)
        if self.comp:
            x = dsp.compress(x, rate=rate, **self.comp)
        for f in self.fx:
            x = f(x)
        g = np.full(len(x), dsp.undb(self.gain_db))
        if 'gain' in self.autos:
            g *= dsp.undb(dsp.automation(self.autos['gain'], len(x), rate))
        if 'pan' in self.autos:
            p = dsp.automation(self.autos['pan'], len(x), rate)
            th = (p + 1) * np.pi / 4
            x = x * np.stack([np.cos(th), np.sin(th)], 1) * math.sqrt(2)
        if self.duck_ is not None:
            d = self.duck_ if isinstance(self.duck_, dict) else dict(key=self.duck_)
            key = d['key']
            times = self.mix.tracks_by_name[key].onsets if isinstance(key, str) else key
            g *= dsp.duck_envelope(len(x), times, d.get('amount', 0.6), d.get('attack', 0.004),
                                   d.get('hold', 0.015), d.get('release', 0.18), d.get('shape', 1.5), rate)
        return x * g[:, None]


class Mix:
    def __init__(self, bpm, bars=None, length=None, rate=RATE, beats_per_bar=4, tail=3.0, title=None):
        self.bpm = float(bpm)
        self.rate = rate
        self.beats_per_bar = beats_per_bar
        self.title = title
        self.length = length if length is not None else (self.bar(bars) if bars else None)
        self.tail = tail
        self.tracks = []
        self.tracks_by_name = {}
        self.buses = {}
        self.master_fx = []

    # time
    def beats(self, b):
        return b * 60.0 / self.bpm

    def bar(self, bar, beat=0.0):
        return self.beats(bar * self.beats_per_bar + beat)

    def step(self, s, per_beat=4):
        return self.beats(s / per_beat)

    # structure
    def track(self, name, **kw):
        t = Track(self, name, **kw)
        self.tracks.append(t)
        self.tracks_by_name[name] = t
        return t

    def bus(self, name, fx, gain_db=0.0, duck=None):
        """A send/return bus: fx(x (n,2)) -> wet (n,2) (e.g. dsp.reverb(..., wet_only=True))."""
        self.buses[name] = dict(fx=fx, gain=dsp.undb(gain_db), duck=duck)
        return name

    # output
    def render(self, master=True, lufs=-14.0, true_peak=-1.0, fade_in=0.0, fade_out=0.0, stems=None):
        """Mix everything. Returns (stereo float64 audio, report). stems: a dict to receive each
        track's processed audio (memory heavy for long songs)."""
        end = self.length
        if end is None:
            end = 0.0
            for tr in self.tracks:
                for t, a, _, _ in tr.events:
                    end = max(end, t + len(a) / self.rate)
        n = int(round((end + self.tail) * self.rate))
        out = np.zeros((n, 2), np.float32)
        bus_in = {b: np.zeros((n, 2), np.float32) for b in self.buses}
        for tr in self.tracks:
            if tr.mute or not tr.events:
                continue
            x = tr._process(tr._bounce(n))
            if stems is not None:
                stems[tr.name] = x.astype(np.float32)
            out += x
            for b, amt in tr.sends.items():
                key = 'send:' + b
                if key in tr.autos:
                    bus_in[b] += x * dsp.automation(tr.autos[key], n, self.rate)[:, None]
                else:
                    bus_in[b] += x * amt
            del x
        for b, cfg in self.buses.items():
            w = cfg['fx'](bus_in.pop(b).astype(np.float64)) * cfg['gain']
            if cfg['duck'] is not None:
                d = cfg['duck'] if isinstance(cfg['duck'], dict) else dict(key=cfg['duck'])
                times = self.tracks_by_name[d['key']].onsets if isinstance(d['key'], str) else d['key']
                w *= dsp.duck_envelope(n, times, d.get('amount', 0.5), release=d.get('release', 0.25),
                                       rate=self.rate)[:, None]
            out += w
            del w
        out = out.astype(np.float64)
        for f in self.master_fx:
            out = f(out)
        out = dsp.fade(out, fade_in, fade_out, self.rate)
        rep = dict(duration=round(n / self.rate, 2))
        if master:
            out, mrep = dsp.master(out, lufs, true_peak, self.rate)
            rep.update(mrep)
        return out, rep

    def export(self, audio, base, title=None, kbps=320, wav=True, mp3=True):
        return export(audio, base, title or self.title or os.path.basename(base), kbps, wav, mp3, self.rate)


# ---------------------------------------------------------------- export

def export(audio, base, title, kbps=320, wav=True, mp3=True, rate=RATE, artist='Star-FlyBack'):
    """Write base.wav (16-bit) and/or base.mp3 (libmp3lame CBR, ID3v2 title). Returns paths and
    the MP3's decoded loudness and true peak. MIX_WAV_ONLY=1 in the environment (the ROM build,
    tools/mkradio.py) writes the WAV only, so it needs no ffmpeg."""
    out = {}
    mp3 = mp3 and not os.environ.get('MIX_WAV_ONLY')
    a = np.clip(np.asarray(audio, np.float64), -1, 1)
    if wav:
        render.write_wav(base + '.wav', a, rate)
        out['wav'] = base + '.wav'
    if mp3:
        p = base + '.mp3'
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'f32le', '-ar', str(rate), '-ac', '2',
               '-i', 'pipe:0', '-c:a', 'libmp3lame', '-b:a', '%dk' % kbps, '-id3v2_version', '3',
               '-metadata', 'title=%s' % title, '-metadata', 'artist=%s' % artist, p]
        subprocess.run(cmd, input=a.astype('<f4').tobytes(), check=True)
        out['mp3'] = p
        out.update(check_mp3(p, rate))
    return out


def decode(path, rate=RATE):
    """Decode any audio file with ffmpeg to float (n, 2)."""
    r = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', path, '-f', 'f32le', '-ac', '2',
                        '-ar', str(rate), 'pipe:1'], capture_output=True, check=True)
    return np.frombuffer(r.stdout, '<f4').reshape(-1, 2).astype(np.float64)


def check_mp3(path, rate=RATE):
    x = decode(path, rate)
    tags = subprocess.run(['ffprobe', '-hide_banner', '-loglevel', 'error', '-show_entries',
                           'format_tags=title:format=bit_rate,duration', '-of', 'default=nw=1', path],
                          capture_output=True, text=True).stdout
    return dict(mp3_lufs=round(dsp.loudness_lufs(x, rate), 2), mp3_true_peak_dbtp=round(dsp.true_peak_db(x, rate), 2),
                mp3_info=' '.join(tags.split()))


# ---------------------------------------------------------------- Payback's originals

def sample_pitch(pcm, rate, fmin=30.0, fmax=1500.0):
    """(f0 Hz, confidence 0..1) of a sample by YIN on its steadiest part."""
    x = np.asarray(pcm, np.float64)
    if len(x) < 256:
        return None, 0.0
    w = min(len(x), 4096)
    st = max(0, min(len(x) - w, len(x) // 5))
    seg = x[st:st + w] - x[st:st + w].mean()
    tmax = min(int(rate / fmin), w // 2)
    tmin = max(2, int(rate / fmax))
    W = w - tmax
    if W < 64:
        return None, 0.0
    e = np.concatenate([[0], np.cumsum(seg ** 2)])
    F = np.fft.rfft(seg, 2 * w)
    full = np.fft.irfft(F * np.conj(np.fft.rfft(seg[:W], 2 * w)), 2 * w)[:tmax + 1]
    d = np.array([e[W] + (e[tau + W] - e[tau]) - 2 * full[tau] for tau in range(tmax + 1)])
    d[0] = 0
    cm = d[1:] * np.arange(1, tmax + 1) / np.maximum(np.cumsum(d[1:]), 1e-12)
    cm = np.concatenate([[1], cm])
    cand = np.nonzero(cm[tmin:] < 0.2)[0]
    if len(cand):
        tau = tmin + cand[0]
        while tau + 1 <= tmax and cm[tau + 1] < cm[tau]:
            tau += 1
    else:
        tau = tmin + int(np.argmin(cm[tmin:]))
    conf = float(max(0.0, 1 - cm[tau]))
    if 1 <= tau < tmax:
        a, b, c = cm[tau - 1], cm[tau], cm[tau + 1]
        den = a - 2 * b + c
        tau = tau + (0.5 * (a - c) / den if den else 0)
    return rate / tau, conf


def describe_sample(smp):
    """Features of a Payback sample at its native rate: length, loop, pitch, brightness, noise."""
    rate = pbsong.PAL_CLOCK / pbsong.NATIVE_PERIOD
    x = smp.pcm().astype(np.float64)
    if not len(x):
        return None
    f0, conf = sample_pitch(x, rate)
    spec = np.abs(np.fft.rfft(x[:16384] * np.hanning(min(len(x), 16384)))) + 1e-12
    fr = np.fft.rfftfreq(min(len(x), 16384), 1 / rate)
    centroid = float(np.sum(fr * spec) / np.sum(spec))
    flat = float(np.exp(np.mean(np.log(spec))) / np.mean(spec))
    env = np.abs(x)
    k = max(1, int(0.01 * rate))
    e = np.convolve(env, np.ones(k) / k, 'same')
    pk = int(np.argmax(e))
    after = np.nonzero(e[pk:] < e[pk] * 0.1)[0]
    decay = (after[0] / rate) if len(after) else len(x) / rate
    chord = sample_chord(x, rate, f0) if 0.5 < conf < 0.9 else None
    return dict(seconds=len(x) / rate, looped=smp.looped, f0=f0, pitch_conf=conf,
                tune=(12 * math.log2(f0 / 261.6256) if f0 else None), centroid=centroid, flatness=flat,
                decay=decay, volume=smp.volume, finetune=smp.finetune, chord=chord)


def sample_chord(x, rate, f0=None):
    """If a sample holds a chord (strong spectral peaks that are not harmonics of one note),
    its pitch classes at native rate (C-2 plays C4), strongest first; else None."""
    n = min(len(x), 8192)
    st = min(len(x) - n, len(x) // 6)
    seg = x[st:st + n] * np.hanning(n)
    S = np.abs(np.fft.rfft(seg, 65536))
    f = np.fft.rfftfreq(65536, 1 / rate)
    S[(f < 60) | (f > 2000)] = 0
    peaks = []
    S2 = S.copy()
    for _ in range(8):
        i = int(np.argmax(S2))
        if S2[i] <= 0:
            break
        peaks.append((f[i], S[i]))
        S2[max(0, i - 40):i + 40] = 0
    if not peaks:
        return None
    top = max(a for _, a in peaks)
    strong = [(fr, a) for fr, a in peaks if a > 0.35 * top]
    foreign = [fr for fr, a in strong if not f0 or abs(fr / f0 - round(fr / f0)) > 0.08 or round(fr / f0) > 20]
    pcs = []
    for fr, a in sorted(strong, key=lambda p: -p[1]):
        pc = int(round(12 * math.log2(fr / 261.6256))) % 12
        if pc not in pcs:
            pcs.append(pc)
    return pcs if len(foreign) >= 2 and len(pcs) >= 3 else None


class SampleInst:
    """Play a Payback sample as an instrument: inst(freq, dur, vel). root: the MIDI note the
    sample sounds at its native rate (period 428); freq None plays it at its native rate."""

    def __init__(self, smp, root=60.0, release=0.03, attack=0.0, gate=None, rate=RATE):
        self.smp = smp
        self.pcm = smp.pcm().astype(np.float64)
        self.root = root
        self.release = release
        self.attack = attack
        self.gate = smp.looped if gate is None else gate
        self.rate = rate
        self.native = pbsong.PAL_CLOCK / pbsong.NATIVE_PERIOD
        self.cache = {}
        self.drum = not smp.looped

    def __call__(self, freq=None, dur=0.25, vel=1.0):
        key = (freq, round(dur, 4) if self.gate else 0, vel)
        if key in self.cache:
            return self.cache[key]
        ratio = self.native / self.rate * (1.0 if freq is None else 2 ** ((dsp.hz_midi(freq) - self.root) / 12))
        if self.gate:
            n = int((dur + self.release) * self.rate)
        else:
            n = int(math.ceil(len(self.pcm) / ratio))
        y = dsp.play_sample(self.pcm, float(ratio), n, self.smp.loop_start)
        if self.attack:
            k = min(n, int(self.attack * self.rate))
            y[:k] *= np.linspace(0, 1, k)
        if self.gate:
            k = min(n, int(self.release * self.rate))
            y[n - k:] *= np.linspace(1, 0, k)
        y = (y * vel).astype(np.float32)
        self.cache[key] = y
        return y


class Original:
    """Payback song `number` (from $PAYBACK_ROM or rom=), rendered with stems and taken apart."""

    def __init__(self, number, rom=None, flavour='payback', stereo=0.5):
        self.rom = rom or pbsong.default_rom()
        self.number = number
        self.song = pbsong.load(self.rom, number)
        self.r = render.render(self.song, flavour, stems=True, stereo=stereo, tail=1.5)
        self.rate = self.r.rate
        self.rows = self.r.rows
        self.row_t = np.array([r.time for r in self.rows])
        self.raw_notes = self.r.notes
        from collections import Counter
        c = Counter()
        for a, b in zip(self.rows, self.rows[1:]):
            c[(a.tempo, a.speed)] += b.time - a.time
        (tempo, speed), _ = c.most_common(1)[0]
        self.bpm = tempo * 6.0 / speed          # 4 rows a beat
        self.features = {s.number: describe_sample(s) for s in self.song.samples if s.length}
        self.tune = {k: (round(f['tune']) if f and f['tune'] is not None and f['pitch_conf'] > 0.6
                         and not f['chord'] else 0) for k, f in self.features.items()}
        for k, f in self.features.items():
            if f and f['chord']:        # a chord sample: root = its strongest pitch class near C4
                self.tune[k] = (f['chord'][0] + 6) % 12 - 6

    @property
    def duration(self):
        return self.r.duration

    def time_of(self, order_index, row=0):
        return self.r.row_time(order_index, row)

    def section(self, order_from, order_to=None):
        """(t0, t1) of order positions [order_from, order_to)."""
        t0 = self.time_of(order_from)
        t1 = self.time_of(order_to) if order_to is not None and order_to < len(self.song.order) else self.rows[-1].time + (
            self.rows[-1].time - self.rows[-2].time)
        return t0, t1

    def beat_of(self, t):
        """Beats (4 rows a beat) at time t, by the row timeline."""
        i = int(np.searchsorted(self.row_t, t, side='right')) - 1
        i = max(0, min(i, len(self.row_t) - 2))
        frac = (t - self.row_t[i]) / max(self.row_t[i + 1] - self.row_t[i], 1e-9)
        return (i + frac) / 4.0

    def notes(self, channel=None, t0=None, t1=None, instruments=None, tuned=True, min_vol=1):
        """Note list (mix.Note) with sounding pitch (sample tuning applied when tuned)."""
        out = []
        for e in self.raw_notes:
            if channel is not None and e.channel != channel:
                continue
            if instruments is not None and e.instrument not in instruments:
                continue
            if t0 is not None and e.time < t0 - 1e-9 or t1 is not None and e.time >= t1 - 1e-9:
                continue
            if e.volume < min_vol:
                continue
            midi = pbsong.period_to_midi(e.period) + (self.tune.get(e.instrument, 0) if tuned else 0)
            b = self.beat_of(e.time)
            ch = (self.features.get(e.instrument) or {}).get('chord')
            tr = int(round(pbsong.period_to_midi(e.period))) - 60
            pcs = tuple((p + tr) % 12 for p in ch) if ch else (int(round(midi)) % 12,)
            out.append(Note(e.time, e.duration, midi, e.volume / 64.0, b, self.beat_of(e.time + e.duration) - b,
                            e.instrument, e.channel, e.period, pcs))
        return out

    def stem(self, channel, t0=0.0, t1=None):
        x = self.r.stems[channel]
        return x[int(t0 * self.rate): None if t1 is None else int(t1 * self.rate)]

    def mixdown(self, t0=0.0, t1=None):
        return self.r.audio[int(t0 * self.rate): None if t1 is None else int(t1 * self.rate)]

    def sample(self, k):
        return self.song.sample(k)

    def sample_inst(self, k, **kw):
        """Payback sample k as an instrument, rooted at its measured pitch."""
        kw.setdefault('root', 60 + self.tune.get(k, 0))
        return SampleInst(self.song.sample(k), **kw)

    def pitch_classes(self, t0=None, t1=None, instruments=None, exclude=()):
        h = np.zeros(12)
        for n in self.notes(t0=t0, t1=t1, instruments=instruments):
            if n.ins in exclude:
                continue
            for i, pc in enumerate(n.pcs):
                h[pc] += max(min(n.dur, 2.0), 0.05) * n.vel * (1.0 if i == 0 else 0.7)
        return h

    def key(self, exclude=(), t0=None, t1=None):
        """(name like 'F# minor', correlation) by the Krumhansl-Schmuckler profiles."""
        h = self.pitch_classes(t0, t1, exclude=exclude)
        maj = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        mnr = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        best = None
        for r in range(12):
            for prof, name in ((maj, 'major'), (mnr, 'minor')):
                c = np.corrcoef(h, np.roll(prof, r))[0, 1]
                if best is None or c > best[1]:
                    best = ('%s %s' % (PC_NAMES[r], name), float(c))
        return best

    def chords(self, t0=None, t1=None, beats=4.0, exclude=(), min_share=0.12):
        """Chord guess per `beats` window: [(time, beat, name, pitch classes by weight)]."""
        t0 = self.rows[0].time if t0 is None else t0
        t1 = self.r.duration if t1 is None else t1
        out = []
        b0 = self.beat_of(t0)
        b1 = self.beat_of(t1)
        notes = [n for n in self.notes(t0=t0, t1=t1) if n.ins not in exclude]
        b = b0
        while b < b1 - 1e-6:
            h = np.zeros(12)
            for n in notes:
                lo, hi = max(n.beat, b), min(n.beat + max(n.dur_beats, 0.25), b + beats)
                if hi > lo:
                    for i, pc in enumerate(n.pcs):
                        h[pc] += (hi - lo) * n.vel * (1.0 if i == 0 else 0.7)
            t = self.row_t[min(int(b * 4), len(self.row_t) - 1)]
            out.append((t, b, name_chord(h, min_share), [PC_NAMES[i] for i in np.argsort(-h) if h[i] > 0][:5]))
            b += beats
        return out


def name_chord(h, min_share=0.12):
    """Best chord name for a pitch-class weight vector (triads, sevenths, power chords)."""
    if h.sum() <= 0:
        return 'N.C.'
    hn = h / h.sum()
    best = None
    for r in range(12):
        for q in ('', 'm', '5', 'sus2', 'sus4', '7', 'm7', 'maj7', 'dim'):
            iv = [i % 12 for i in CHORDS[q]]
            inside = sum(hn[(r + i) % 12] for i in iv)
            missing = sum(1 for i in iv if hn[(r + i) % 12] < min_share * 0.5)
            score = inside - 0.15 * missing - 0.02 * len(iv) + 0.05 * hn[r]
            if best is None or score > best[0]:
                best = (score, PC_NAMES[r] + q)
    return best[1]
