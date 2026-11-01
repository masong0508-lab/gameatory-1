"""Star-FlyBack Title Remix (nu metal): the full-length theme song.

Run:  PAYBACK_ROM=... python3 remix_title_numetal_full.py OUT_BASE [--window B0 B1]
Everything from Payback (every ROM sample and every note's timing, pitch and volume) is read from
$PAYBACK_ROM at run time; nothing of it is stored. Guitars, bass, drums and the lead are synthesised
(tools/synth.py).

Form: Payback song 0's own order list, bar for bar (115 bars of 2.56 s at 93.75 BPM, 4:54.4 plus ring-out):
  bar   0      E5 pad (order 0)             intro: pads, stabs D5 Bm7 E5 (orders 1-2), Edim build (3)
  bar  11-14   E5 drone / break (4-5)       bar 15-18 bridge E5 A5 (6-7)       bar 19-20 first groove (8)
  bar  21-36   groove 1 (9-16: A A' A A'' A A' A fill)        bar 37-60 menu bed (17-22), chorus on the pluck sequence 53-60
  bar  61-62   Em break (23)                bar 63-76 groove 2 (24-30)          bar 77-78 build (31)
  bar  79-94   half-time break (32-39)      bar 95-110 groove 3 (40-47)         bar 111-114 outro D5 Bm7 E5 E5 (48)
The ROM layer plays the original note data through Payback's own sequencer: same samples, same notes, same
volume and effects, on the 94 BPM grid. The heavy layer (chugs, kick, bass, kit, power chords, clean arps,
lead) is generated from those note events.
"""
import os
import sys

import numpy as np
from scipy import signal as sg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import dsp  # noqa: E402
import mix  # noqa: E402
import romlayer  # noqa: E402
import synth  # noqa: E402
import titlefx  # noqa: E402,F401
from synth import Inst  # noqa: E402

RATE = 44100
BPM = 93.75
S16 = 60.0 / BPM / 4            # 0.16 s
BAR = 16 * S16                  # 2.56 s
NBARS = 115
TITLE = 'Star-FlyBack Title Remix (nu metal)'


def T(b, s=0.0):
    return (b * 16 + s) * S16


def hz(n):
    return float(dsp.midi_hz(mix.parse_note(n)))


def snap(t):
    return round(t / 0.02) * 0.02


# ------------------------------------------------------------------ sections and chords

SECS = [('intro', 0, 9), ('build', 9, 11), ('drone', 11, 15), ('bridge', 15, 19), ('g0', 19, 21),
        ('groove1', 21, 37), ('bed', 37, 53), ('chorus', 53, 61), ('drop', 61, 63), ('groove2', 63, 77),
        ('build2', 77, 79), ('break', 79, 95), ('groove3', 95, 111), ('outro', 111, 115)]


def sec_of(b):
    for n, a, z in SECS:
        if a <= b < z:
            return n
    return 'outro'


CH = {'E5': ('E2', 'E1', ['E3', 'B3', 'E4']), 'D5': ('D2', 'D1', ['D3', 'A3', 'D4']),
      'B5': ('B2', 'B1', ['B2', 'F#3', 'B3', 'A3']), 'Em': ('E2', 'E1', ['E3', 'G3', 'B3']),
      'Bm': ('B2', 'B1', ['B2', 'D3', 'F#3']), 'Cmaj7': ('C3', 'C2', ['C3', 'E3', 'G3', 'B3']),
      'Bsus4': ('B2', 'B1', ['B2', 'E3', 'F#3']), 'A5': ('A2', 'A1', ['A2', 'E3', 'A3']),
      'Am': ('A2', 'A1', ['A2', 'E3', 'A3', 'C4']), 'G5': ('G2', 'G1', ['G2', 'D3', 'G3']),
      'C5': ('C3', 'C2', ['C3', 'G3', 'C4']), 'Amaj7': ('A2', 'A1', ['A2', 'E3', 'G#3']),
      'Em7': ('E2', 'E1', ['E3', 'G3', 'B3', 'D4']), 'Bm7': ('B2', 'B1', ['B2', 'D3', 'F#3', 'A3'])}

BAR_CHORDS = {}


def _set(b0, names):
    for i, n in enumerate(names):
        BAR_CHORDS[b0 + i] = n


_set(0, ['E5'])
_set(1, ['D5', 'B5', 'E5', 'E5'])
_set(5, ['E5', 'B5', 'E5', 'E5'])
_set(9, ['E5'] * 6)
_set(15, ['E5', 'E5', 'A5', 'A5'])            # E5 E5 Edim Edim -> E5 on the heavy layer; A5 Amaj7
_set(19, ['Em', 'Em'])
for b in range(21, 37):
    BAR_CHORDS[b] = 'Em'
_set(37, ['Em', 'Em', 'Bm', 'Bm', 'Em', 'Em7', 'Bm7', 'Bm', 'Em', 'Bm', 'G5', 'C5', 'Em', 'Bm7', 'G5', 'C5',
          'Em', 'Bm', 'Cmaj7', 'Bsus4', 'Em', 'Bm', 'Cmaj7', 'Bm'])
_set(61, ['Em', 'Em'])
for b in range(63, 77):
    BAR_CHORDS[b] = 'Em'
_set(77, ['E5', 'C5'])
_set(79, ['Am', 'Am', 'Em', 'Em', 'Am', 'Am', 'A5', 'G5', 'Am', 'Am', 'Em', 'Em', 'Am', 'Am', 'Em', 'Em'])
for b in range(95, 111):
    BAR_CHORDS[b] = 'Em'
_set(111, ['D5', 'B5', 'E5', 'E5'])

BASS_NOTE = {'E2': 'E1', 'F#2': 'F#1', 'G2': 'G1', 'A2': 'A1', 'B2': 'B1', 'D2': 'D1', 'C3': 'C2'}
PC_CHUG = {4: 'E2', 6: 'F#2', 7: 'G2', 9: 'A2', 11: 'B2', 2: 'D2', 0: 'E2', 10: 'E2', 1: 'E2', 3: 'E2', 5: 'E2', 8: 'E2'}

# ROM groups (sample numbers of Payback song 0)
GROUPS = {
    'stab': {8, 15, 11, 9},                      # struck chord stabs and the bass thump: the title hook
    'pluck': {2, 1},                             # the plucked figure (menu sequence) and the single-voice lead
    'vox': {31, 30, 26, 27, 28, 29},             # sustained voice-like pads / choir
    'pad': {10, 18, 5, 3, 4, 6, 7, 16, 17, 19, 20, 21},   # drones, strings, riser, basses
    'perc': {12, 13},                            # the title's percussion and break chops (ghost layer)
}


def rms_ref(x, win=4410):
    n = len(x) // win
    r = np.sqrt((x[:n * win].reshape(n, win).astype(np.float64) ** 2).mean(1))
    r = r[r > 1e-5]
    return float(np.percentile(r, 90)) if len(r) else 1.0


def amp(x, drive):
    return np.tanh(drive * x) / np.tanh(drive)


def build(rom, win=None):
    D = romlayer.Data(rom)
    rom_out = romlayer.play(D, GROUPS)
    rng = np.random.default_rng(2027)
    m = mix.Mix(bpm=BPM, bars=NBARS, rate=RATE, title=TITLE, tail=3.5)
    m.bus('plate', lambda x: dsp.reverb(x, decay=1.5, mix=0.0, predelay=0.012, damp=0.6, hp=250, wet_only=True), gain_db=-5)
    m.bus('hall', lambda x: dsp.reverb(x, decay=3.4, mix=0.0, predelay=0.025, damp=0.5, hp=300, wet_only=True), gain_db=-6)

    kick = Inst(synth.kick, dur=0.24, f_start=135, f_end=52, pitch_time=0.016, decay=0.19, click=0.5, drive=2.8)
    kick_soft = Inst(synth.kick, dur=0.3, f_start=95, f_end=50, pitch_time=0.03, decay=0.28, click=0.15, drive=1.6)
    snare = Inst(synth.snare, dur=0.26, tone=215, tone_decay=0.07, noise_decay=0.15, snap=0.8, bright=4800)
    snare_soft = Inst(synth.snare, dur=0.2, tone=190, tone_decay=0.05, noise_decay=0.09, snap=0.55, bright=3600)
    clap = Inst(synth.clap, dur=0.3, tail=0.12)
    rim = Inst(synth.rim)
    hat = Inst(synth.hat, decay=0.03, tone=1.15)
    hat_o = Inst(synth.hat, open=True, decay=0.2, tone=1.15)
    crashes = [Inst(synth.cymbal, dur=2.8, seed=15), Inst(synth.cymbal, dur=2.6, seed=21), Inst(synth.cymbal, dur=3.0, seed=27)]
    crash = crashes[0]
    cnt = {'crash': 0, 'imp': 0}
    ride = Inst(synth.cymbal, dur=1.1, kind='ride')
    tom = Inst(synth.tom, decay=0.3)
    chug = [Inst(synth.palm_mute_guitar, seed=1, mute=0.7), Inst(synth.palm_mute_guitar, seed=2, mute=0.7)]
    chug_open = [Inst(synth.palm_mute_guitar, seed=3, mute=0.2), Inst(synth.palm_mute_guitar, seed=4, mute=0.2)]
    hookgt = Inst(synth.palm_mute_guitar, seed=5, mute=0.45, bright=1.3)
    pwr = Inst(synth.power_chord_guitar, seed=1, decay=1.5)
    pwr_s = Inst(synth.power_chord_guitar, seed=2, decay=0.35)
    pwr_m7 = Inst(synth.power_chord_guitar, seed=3, decay=1.5, extra=(1.7818,))
    clean = Inst(synth.clean_guitar, brightness=0.6)
    lead = Inst(synth.lead_guitar)
    sub = Inst(synth.dist_sub_bass)

    tk = {}
    tk['kick'] = m.track('kick', gain_db=-5.5, pan=0, hp=32, comp=dict(threshold_db=-14, ratio=2.5, attack=0.003, release=0.08))
    tk['snare'] = m.track('snare', gain_db=-4.5, sends={'plate': 0.22})
    tk['clap'] = m.track('clap', gain_db=-16, pan=0.1, sends={'plate': 0.3})
    tk['hats'] = m.track('hats', gain_db=-14, pan=0.18, hp=300)
    tk['cym'] = m.track('cym', gain_db=-8, width=1.0, sends={'hall': 0.12}, hp=250)
    tk['toms'] = m.track('toms', gain_db=-8, pan=0, sends={'plate': 0.15})
    tk['bass'] = m.track('bass', gain_db=-10.5, pan=0, hp=28, duck=dict(key='kick', amount=0.35, release=0.1),
                         comp=dict(threshold_db=-16, ratio=3, attack=0.005, release=0.1))
    tk['gL'] = m.track('gtrL', gain_db=2.0, pan=-0.9, hp=90, comp=dict(threshold_db=-24, ratio=3.0, attack=0.002, release=0.06))
    tk['gR'] = m.track('gtrR', gain_db=2.0, pan=0.9, hp=90, comp=dict(threshold_db=-24, ratio=3.0, attack=0.002, release=0.06))
    tk['hook'] = m.track('hook', gain_db=-12, pan=0.0, width=1.0, hp=180, sends={'plate': 0.12})
    tk['pwr'] = m.track('power', gain_db=-6, width=1.0, hp=75, sends={'plate': 0.05}, comp=dict(threshold_db=-24, ratio=2.5, attack=0.004, release=0.1))
    tk['clean'] = m.track('clean', gain_db=-10, width=1.0, hp=120, sends={'plate': 0.22, 'hall': 0.15})
    tk['lead'] = m.track('lead', gain_db=-14, width=0.9, hp=250, sends={'plate': 0.2})
    tk['fx'] = m.track('fx', gain_db=-17, width=1.0, sends={'hall': 0.05})
    # ROM layer
    tk['r_stab'] = m.track('rom stabs', gain_db=2, width=1.0, hp=120, lp=7000, sends={'plate': 0.14},
                           duck=dict(key='kick', amount=0.15, release=0.1))
    tk['r_pluck'] = m.track('rom pluck', gain_db=-9, width=1.0, hp=200, lp=7500, sends={'plate': 0.2})
    tk['r_vox'] = m.track('rom voices', gain_db=-9, width=1.0, hp=140, lp=6500, sends={'hall': 0.22},
                          duck=dict(key='kick', amount=0.2, release=0.2))
    tk['r_pad'] = m.track('rom pads', gain_db=-9, width=1.0, hp=45, lp=6000, sends={'hall': 0.12},
                          duck=dict(key='kick', amount=0.2, release=0.2))

    def g(e):
        return snap(e.time)

    def vj(base, lo=0.84):
        v = base * float(rng.uniform(lo, 1.0))
        return min(1.0, round(v / 0.04) * 0.04)

    # ---- ROM layer onto the tracks ----------------------------------------------------------
    def rom_group(name, pans, norm_db, pre=None):
        chs = rom_out[name]
        ref = rms_ref(np.sum([chs[k] for k in range(4)], 0))
        sc = dsp.undb(norm_db) / ref
        st = None
        for k in range(4):
            y = chs[k].astype(np.float64) * sc
            if pre is not None:
                y = pre(y)
            s = dsp.pan(y, pans[k])
            st = s if st is None else st + s
            chs[k] = None
        return st

    def stab_pre(y):
        y = dsp.highpass(y, 110, rate=RATE)
        y = amp(y * 2.2, 1.6) * 0.55
        return dsp.lowpass(y, 6500, rate=RATE)

    P = [-0.35, 0.35, 0.35, -0.35]
    for nm, tname, pans, nrm, pre in (('stab', 'r_stab', [-0.2, 0.2, 0.2, -0.2], -20.0, stab_pre),
                                     ('pluck', 'r_pluck', [-0.4, 0.4, 0.4, -0.4], -24.0, None),
                                     ('vox', 'r_vox', P, -22.0, None),
                                     ('pad', 'r_pad', P, -22.0, None)):
        st = rom_group(nm, pans, nrm, pre)
        tk[tname].clip(0.0, st, fade=0.0)
        del st

    # ---- building blocks -----------------------------------------------------------------
    def hit_kick(t, v=1.0, soft=False):
        tk['kick'].hit(t, kick_soft if soft else kick, v)

    def hit_snare(t, v=1.0, soft=False):
        tk['snare'].hit(t, snare_soft if soft else snare, v)
        if not soft:
            tk['clap'].hit(t + 0.002, clap, v)

    def chug_at(t, pitch, dur, v, openg=False):
        ins = chug_open if openg else chug
        tk['gL'].note(t, ins[0], pitch, dur, v)
        tk['gR'].note(t + 0.0012, ins[1], pitch, dur, v)

    def bass_at(t, pitch, dur, v):
        tk['bass'].note(t, sub, pitch, dur, v)

    def crash_at(t, v=0.9):
        cnt['crash'] += 1
        tk['cym'].hit(t, crashes[cnt['crash'] % 3], v)

    def impact_at(t, v=0.9):
        cnt['imp'] += 1
        tk['fx'].clip(t, synth.impact(2.8 + 0.2 * (cnt['imp'] % 3), v, [36.0, 41.2, 32.7][cnt['imp'] % 3]))

    def revcym(t_end, dur, v=0.8):
        tk['fx'].clip(t_end - dur, synth.reverse_cymbal(dur, v))

    def power_hit(t, chord_name, dur, v, short=False):
        pw = CH[chord_name][0]
        ins = pwr_m7 if chord_name in ('B5', 'Bm7') else (pwr_s if short else pwr)
        tk['pwr'].clip(t, ins(hz(pw), dur, v))

    ARP = {'E5': ['E3', 'B3', 'E4', 'B4', 'E5', 'B4', 'E4', 'B3'], 'D5': ['D3', 'A3', 'D4', 'A4', 'D5', 'A4', 'D4', 'A3'],
           'B5': ['B2', 'F#3', 'B3', 'D4', 'F#4', 'D4', 'B3', 'F#3'], 'Em': ['E3', 'B3', 'E4', 'G4', 'B4', 'G4', 'E4', 'B3'],
           'Em7': ['E3', 'B3', 'D4', 'G4', 'B4', 'G4', 'D4', 'B3'], 'Bm': ['B2', 'F#3', 'B3', 'D4', 'F#4', 'D4', 'B3', 'F#3'],
           'Bm7': ['B2', 'F#3', 'A3', 'D4', 'F#4', 'D4', 'A3', 'F#3'], 'Cmaj7': ['C3', 'G3', 'B3', 'E4', 'G4', 'E4', 'B3', 'G3'],
           'Bsus4': ['B2', 'F#3', 'B3', 'E4', 'F#4', 'E4', 'B3', 'F#3'], 'A5': ['A2', 'E3', 'A3', 'E4', 'A4', 'E4', 'A3', 'E3'],
           'Am': ['A2', 'E3', 'A3', 'C4', 'E4', 'C4', 'A3', 'E3'], 'G5': ['G2', 'D3', 'G3', 'D4', 'G4', 'D4', 'G3', 'D3'],
           'C5': ['C3', 'G3', 'C4', 'G4', 'C5', 'G4', 'C4', 'G3'], 'Amaj7': ['A2', 'E3', 'G#3', 'E4', 'A4', 'E4', 'G#3', 'E3']}

    ARP_ORD = ([0, 1, 2, 3, 4, 5, 6, 7], [0, 2, 1, 3, 4, 3, 2, 1], [2, 3, 4, 3, 2, 1, 0, 1], [0, 1, 2, 4, 3, 2, 1, 3])

    def clean_arp(b, v0, step=2, order=0):
        """One bar of clean guitar arpeggio (8ths) on the bar's chord; the note order changes bar to bar."""
        notes = ARP[BAR_CHORDS[b]]
        o = ARP_ORD[(b * 7 + b // 4) % 4]
        for i in range(8):
            tk['clean'].note(T(b, i * step), clean, notes[o[i]], 0.62, vj(v0 * (1.0 if i % 4 == 0 else 0.78), 0.8))

    def sub_hold(b, nbars, v, dur_bars=None, name=None):
        nm = name or BAR_CHORDS[b]
        bn = CH[nm][1]
        bass_at(T(b), bn, (dur_bars or nbars) * BAR * 0.97, v)

    def kit_bar(b, kind, level, variant=0):
        """Half-time kit: snare on beat 3 (16th 8), steady 8th hats; no rolls."""
        hit_snare(T(b, 8), vj(level, 0.92), soft=(kind in ('soft',)))
        if kind in ('groove', 'chorus', 'heavy'):
            pats = ['x.x.x.x.x.x.x.x.', 'x.x.x.x.x.x.x.x.', 'x.x.x.x.x.x.x.x.', 'x...x.x.x.x.x.x.']
            p = pats[(variant + b) % 4]
            for s, c in enumerate(p):
                if c == 'x':
                    tk['hats'].hit(T(b, s), hat, vj((0.9 if s % 4 == 0 else 0.62) * level, 0.78))
            if (variant + b) % 3 == 1:
                tk['hats'].hit(T(b, 14), hat_o, 0.7)
        elif kind == 'verse':
            for s in range(0, 16, 4):
                tk['hats'].hit(T(b, s), hat, vj(0.5 * level, 0.7))
        elif kind == 'soft':
            for s in range(0, 16, 4):
                tk['hats'].hit(T(b, s), hat, vj(0.4 * level, 0.7))

    def tom_fill(b, s0, freqs, v=0.9):
        """Steady 8th-note toms (not a roll)."""
        for i, f in enumerate(freqs):
            t = T(b, s0 + 2 * i)
            tk['toms'].note(t, tom, hz=f, dur=0.3, vel=vj(v, 0.85))
            hit_kick(t, vj(0.7, 0.8))

    # ---- the groove: heavy layer built from the original stab / thump / kick / snare note data ----
    def chug_pitch(e):
        return PC_CHUG[int(round(D.midi(e))) % 12]

    HAT_PATS = ['x.x.x.x.x.x.x.x.', 'x...x...x...x...', 'x.x.x.x.x.x.x...', '..x...x...x...x.', 'x.x...x.x.x...x.',
                'x.x.x.x.x.x.x.o.']

    def hat_bar(b, r, lvl, pas):
        pi = int(r.integers(0, 6)) if pas else 0
        if pas == 0:
            pi = 0
        p = HAT_PATS[pi]
        ridebar = (pas >= 2 and r.random() < 0.25)
        for s_, c in enumerate(p):
            if c in 'xo':
                if ridebar and s_ % 4 == 0:
                    tk['cym'].hit(T(b, s_), ride, vj(0.4 * lvl, 0.8))
                elif c == 'o':
                    tk['hats'].hit(T(b, s_), hat_o, 0.7)
                else:
                    tk['hats'].hit(T(b, s_), hat, vj((0.9 if s_ % 4 == 0 else 0.62) * lvl, 0.78))

    def groove_pos(oi, blk, pas, lvl, fill=False):
        b0 = D.bar_of(oi)
        r = np.random.default_rng(7000 + oi * 11 + blk * 101 + pas * 7)
        evs = sorted(D.events({oi}, 0, {8, 15, 11, 9}), key=lambda e: e.time)
        times = [g(e) for e in evs]
        bass_mode = [int(r.integers(0, 4)) for _ in range(2)] if pas else [0, 0]
        # per bar treatment of the guitars: 0 plain, 1 stop-start (silent in the second half), 2 open power chords, 3 steady 8ths
        treat = [0, 0] if not pas else [int(r.choice([0, 0, 0, 1, 2, 3], p=[0.3, 0.2, 0.1, 0.15, 0.15, 0.1])) for _ in range(2)]
        for j_ in range(2):
            if treat[j_] == 2:
                power_hit(T(b0 + j_), 'Em', 1.6, vj(0.8 * lvl, 0.9))
            if treat[j_] == 3:
                for s_ in range(0, 16, 2):
                    if all(abs(T(b0 + j_, s_) - tt) > 0.03 for tt in times):
                        chug_at(T(b0 + j_, s_), 'E2', 0.1, vj(0.5, 0.85))
        for i, e in enumerate(evs):
            t = times[i]
            nxt = times[i + 1] if i + 1 < len(evs) else t + 0.5
            gap = max(nxt - t, 0.08)
            pj = 0 if t < T(b0 + 1) else 1
            pitch = chug_pitch(e)
            u = r.random() if pas else 0.0
            if treat[pj] == 1 and t >= T(b0 + pj, 8):
                u = 0.99                                 # silent guitar, the kick and the ROM stab still play
            elif treat[pj] == 2:
                u = 0.99
                if e.instrument in (8, 15):
                    power_hit(t, 'Em', 0.3, vj(0.6, 0.85), short=True)
            v = vj(lvl, 0.8) * (1.0 if e.instrument in (8, 9) else 0.95)
            dur = min(gap * 0.78, 0.3)
            if u < 0.5:                                  # the plain palm-muted chug on the stab's own pitch
                chug_at(t, pitch, dur, min(1.0, v))
            elif u < 0.62:                               # ringing chug
                chug_at(t, pitch, dur * 1.5, min(1.0, v), True)
            elif u < 0.74:                               # E pedal under the stab
                chug_at(t, 'E2', dur, min(1.0, v))
            elif u < 0.86:                               # a dyad: the pitch and its fifth
                chug_at(t, pitch, dur, min(1.0, v))
                fifth = {'E2': 'B2', 'F#2': 'C#3', 'G2': 'D3', 'A2': 'E3', 'B2': 'F#3', 'D2': 'A2'}[pitch]
                if fifth != 'C#3':
                    chug_at(t, fifth, dur, min(1.0, v * 0.8))
            elif u < 0.94:                               # octave up
                chug_at(t, {'E2': 'E3', 'F#2': 'F#3', 'G2': 'G3', 'A2': 'A3', 'B2': 'B3', 'D2': 'D3'}[pitch], dur, min(1.0, v * 0.9))
            # (else: the guitar rests here; kick, bass and the ROM stab still play)
            bm = bass_mode[pj]
            if bm == 0:
                bass_at(t, BASS_NOTE[pitch], min(gap * 0.85, 0.42), vj(0.9 * lvl, 0.8))
            elif bm == 1:
                bass_at(t, 'E1', min(gap * 0.85, 0.42), vj(0.9 * lvl, 0.8))
            elif bm == 2:
                bass_at(t, 'E1' if i % 2 == 0 else 'E2', min(gap * 0.85, 0.3), vj(0.8 * lvl, 0.8))
            else:
                bass_at(t, {'E2': 'E1', 'F#2': 'B1', 'G2': 'G1', 'A2': 'E1', 'B2': 'B1', 'D2': 'D1'}[pitch], min(gap * 0.85, 0.42), vj(0.9 * lvl, 0.8))
            if (not pas) or r.random() < 0.88 or t == T(b0) or e.instrument == 9:
                hit_kick(t, vj(0.95 * lvl, 0.82))
            if pas > 0 and r.random() < 0.15 * min(pas, 3) and gap > 0.17:
                tg = t - 0.08
                if (tg > times[i - 1] + 0.01) if i else True:
                    chug_at(tg, 'E2', 0.07, 0.45)
            # the hook guitar doubles the stab's own notes (exact pitch)
            if e.instrument in (8, 15) and r.random() < [0.0, 0.5, 0.75][blk] * (0.5 + 0.25 * min(pas, 2)):
                tk['hook'].note(t, hookgt, int(round(D.midi(e))), min(dur, 0.22), vj(0.85, 0.8),
                                pan=float(r.choice([-0.35, 0.35])))
            if e.instrument in (11, 15) and blk == 2 and pas % 2 == 1:
                tk['lead'].note(t, lead, int(round(D.midi(e))), min(gap * 0.95, 0.9), vj(0.8, 0.85))
        for e in D.events({oi}, 0, {14}):                       # the original kick sample's own hits
            if g(e) not in times:
                hit_kick(g(e), vj(0.8 * lvl, 0.82))
        for e in D.events({oi}, 2, {25}):                       # the original snare's hits: soft ghosts
            hit_snare(g(e), vj(0.4, 0.8), soft=True)
        for e in D.events({oi}, 2, {22}):
            crash_at(g(e), 0.7)
        for j in range(2):
            bb = b0 + j
            hit_snare(T(bb, 8), vj(lvl, 0.92))
            hat_bar(bb, r, lvl, pas)
            if pas and r.random() < 0.5:                         # one extra soft kick on a free 16th
                s_ = int(r.choice([3, 5, 11, 13, 15]))
                if g_ok(bb, s_, times):
                    hit_kick(T(bb, s_), vj(0.55, 0.8), soft=True)
            if pas >= 2 and r.random() < 0.4:
                power_hit(T(bb), 'Em', 2.2, vj(0.55, 0.85))
            if pas and r.random() < 0.25:
                crash_at(T(bb), 0.6)
        if fill:
            tom_fill(b0 + 1, 8, [196.0, 164.81, 146.83, 130.81], 0.9)
            for s in range(0, 8, 4):
                hit_kick(T(b0 + 1, s), 0.85)

    def g_ok(bb, s_, times):
        t0_ = T(bb, s_)
        return all(abs(t0_ - tt) > 0.03 for tt in times)

    # ======================================================================== INTRO 0-8
    tk['pwr'].clip(0.0, synth.power_chord_guitar(hz('E2'), 3.6, 0.8, seed=11, decay=2.6))
    bass_at(0.0, 'E1', 2.5, 0.8)
    for b in range(0, 9):
        clean_arp(b, 0.75 if b < 5 else 0.7, order=b)
        if b >= 1:
            sub_hold(b, 1, 0.7 if b < 5 else 0.8)
    for e in D.events({1, 2}, 0):                                 # power chords under the original stabs
        b = int(e.time / BAR)
        power_hit(g(e), BAR_CHORDS[b], 1.8, 0.62)
    for b in range(5, 9):                                          # last four bars: the kit comes in softly
        hit_kick(T(b), 0.55, soft=True)
        hit_kick(T(b, 8), 0.5, soft=True)
        hit_snare(T(b, 8), 0.5, soft=True)
        for s in range(0, 16, 4):
            tk['hats'].hit(T(b, s), hat, 0.35 + 0.04 * (b - 5))
    # ======================================================================== BUILD 9-10 (Edim, riser = ROM sample 21)
    for b in (9, 10):
        clean_arp(b, 0.75, order=b)
        sub_hold(b, 1, 0.85)
        for s in (0, 4, 8, 12):
            hit_kick(T(b, s), 0.62 + 0.06 * (b - 9) + 0.02 * s / 4, soft=True)
        for s in range(0, 16, 2):
            tk['hats'].hit(T(b, s), hat, 0.4 + 0.03 * s / 2 + 0.1 * (b - 9))
        hit_snare(T(b, 8), 0.55 + 0.25 * (b - 9), soft=(b == 9))
    for i, s in enumerate(range(0, 16, 2)):
        chug_at(T(10, s), 'E2', 0.12, vj(0.7 + 0.04 * i, 0.9))
        bass_at(T(10, s), 'E1', 0.14, 0.7)
    tk['fx'].clip(T(10, 0), synth.riser(BAR - S16, 0.7, f0=300.0, f1=8000.0, tone=0.3))
    revcym(T(11), 1.6, 0.7)
    # ======================================================================== DRONE 11-14 (E5, N.C. bars 12 and 14 second half)
    for b in (11, 13):
        crash_at(T(b), 0.8 if b == 11 else 0.6)
        impact_at(T(b), 0.8)
        tk['pwr'].clip(T(b), synth.power_chord_guitar(hz('E2'), 1.2, 0.9, seed=12 + b, decay=1.6))
        sub_hold(b, 1, 0.9, name='E5')
        hit_kick(T(b), 0.95)
        hit_snare(T(b, 8), 0.9)
        tk['pwr'].clip(T(b, 8), synth.power_chord_guitar(hz('E2'), 1.0, 0.8, seed=14 + b, decay=1.0))
        for s in range(0, 16, 2):
            tk['hats'].hit(T(b, s), hat, vj(0.7 if s % 4 == 0 else 0.45, 0.8))
    for b in (12, 14):
        tk['pwr'].clip(T(b), synth.power_chord_guitar(hz('E2'), 1.2, 0.85, seed=16 + b, decay=1.6))
        bass_at(T(b), 'E1', 8 * S16 * 0.9, 0.85)
        hit_kick(T(b), 0.9)
        for s in range(0, 8, 2):
            tk['hats'].hit(T(b, s), hat, vj(0.6 if s % 4 == 0 else 0.4, 0.8))
        hit_snare(T(b, 4), 0.55, soft=True)
        for s in (6,):
            hit_kick(T(b, s), 0.7)
    # ======================================================================== BRIDGE 15-18
    crash_at(T(15), 0.9)
    impact_at(T(15), 0.9)
    for b in range(15, 19):
        nm = BAR_CHORDS[b]
        power_hit(T(b), nm, 2.2, 0.85)
        power_hit(T(b, 8), nm, 1.0, 0.7, short=True)
        sub_hold(b, 1, 0.9)
        hit_kick(T(b), 0.9)
        hit_kick(T(b, 6), 0.7)
        hit_kick(T(b, 8), 0.8)
        kit_bar(b, 'groove', 0.8, variant=b)
        clean_arp(b, 0.55, order=b)
    # ======================================================================== FIRST GROOVE 19-20 (order 8, pattern 7)
    crash_at(T(19), 1.0)
    impact_at(T(19), 0.9)
    for b in (19, 20):
        for s in (0, 2, 4, 6, 8, 10, 12, 14):
            chug_at(T(b, s), 'E2', 0.13, vj(0.9, 0.85))
            bass_at(T(b, s), 'E1', 0.14, vj(0.85, 0.8))
        for s in (0, 3, 6, 8, 11, 14):
            hit_kick(T(b, s), vj(0.9, 0.85))
        kit_bar(b, 'groove', 0.9, variant=b)
    # ======================================================================== GROOVE 1: orders 9-16 (bars 21-36)
    crash_at(T(21), 1.0)
    impact_at(T(21), 0.9)
    revcym(T(21), 1.2, 0.6)
    for pas, oi in enumerate(range(9, 17)):
        groove_pos(oi, 0 if pas < 2 else 1, pas, [0.88, 0.92, 0.96, 1.0, 1.0, 1.0, 1.0, 1.0][pas], fill=(oi == 16))
    for b in (21, 25, 29, 33):
        crash_at(T(b), 0.75)
    # ======================================================================== MENU BED 37-52 (orders 17-20)
    for b in range(37, 53):
        nm = BAR_CHORDS[b]
        clean_arp(b, [0.55, 0.55, 0.6, 0.6][(b - 37) // 4], order=b)
        sub_hold(b, 1, 0.5 if b < 45 else 0.62)
    for b in range(41, 53):                                       # a quiet kit grows in
        k = 'soft'
        if b >= 45:
            k = 'verse'
        kit_bar(b, k, 0.45 + 0.03 * (b - 41), variant=b)
        if b >= 45:
            for s in ([2, 7, 8, 10, 14], [2, 3, 10, 13, 14], [2, 7, 10, 11, 14], [2, 3, 8, 13, 15])[b % 4]:
                hit_kick(T(b, s), vj(0.36 + 0.02 * (b - 45), 0.75), soft=True)
                bass_at(T(b, s), CH[BAR_CHORDS[b]][1], 0.2, vj(0.45, 0.8))
        else:
            hit_kick(T(b), 0.35, soft=True)
        tk['snare'].hit(T(b, 8), rim, 0.5)
    for b in (49, 50, 51, 52):                                    # rising power chords into the chorus
        power_hit(T(b), BAR_CHORDS[b], 2.4, 0.35 + 0.1 * (b - 49))
    revcym(T(53), 2.0, 0.8)
    # ======================================================================== CHORUS 53-60 (orders 21-22: the pluck sequence)
    crash_at(T(53), 1.0)
    impact_at(T(53), 1.0)
    templates = [([0, 3, 6, 8, 11, 14], [3, 2, 2, 3, 2, 2]), ([0, 3, 6, 8, 10, 11, 14], [3, 2, 2, 2, 1, 2, 2]),
                 ([0, 2, 6, 8, 11, 13], [2, 3, 2, 3, 2, 3]), ([0, 3, 4, 8, 10, 14], [3, 1, 3, 2, 3, 2])]
    for b in range(53, 61):
        j = b - 53
        nm = BAR_CHORDS[b]
        hits, lens = templates[(j * 3 + (j // 4) * 2 + (j // 2)) % 4]
        for s, ln in zip(hits, lens):
            big = (s in (0, 8))
            power_hit(T(b, s), nm, ln * S16 * (1.7 if big else 0.9), vj(1.0 if big else 0.88, 0.85), short=not big)
            bass_at(T(b, s), CH[nm][1], ln * S16 * 0.9, vj(0.95, 0.85))
            hit_kick(T(b, s), vj(0.95, 0.85))
        hit_snare(T(b, 8), vj(1.0, 0.95))
        if b >= 59:
            for s in (2, 4, 6, 10, 12, 14):
                if s not in hits:
                    hit_kick(T(b, s), vj(0.62, 0.8))
        for s in range(0, 16, 2):
            if s % 4 == 0 and b >= 57:
                tk['cym'].hit(T(b, s), ride, 0.35)
            else:
                tk['hats'].hit(T(b, s), hat, vj(0.85 if s % 4 == 0 else 0.55, 0.75))
        if b in (57,):
            crash_at(T(b), 0.9)
        clean_arp(b, 0.45, order=b)
    for e in D.events({21, 22}, None, {2}):                       # the original pluck sequence, doubled by the lead guitar
        if e.channel in (2, 3):
            tk['lead'].note(g(e), lead, int(round(D.midi(e))) - (24 if e.order_index == 21 else 12), 2 * S16 * 0.9,
                            0.95 if int(round(e.time / S16)) % 8 == 0 else 0.82)
    crash_at(T(59), 0.7)
    # ======================================================================== DROP 61-62 (order 23, Em)
    crash_at(T(61), 0.9)
    impact_at(T(61), 0.8)
    for b in (61, 62):
        power_hit(T(b), 'Em', 2.4, 0.9)
        sub_hold(b, 1, 0.85)
        hit_kick(T(b), 0.95)
        hit_kick(T(b, 6), 0.7)
        hit_snare(T(b, 8), 0.9)
        kit_bar(b, 'groove', 0.75, variant=b)
        clean_arp(b, 0.5, order=b)
    # ======================================================================== GROOVE 2: orders 24-30 (bars 63-76)
    crash_at(T(63), 1.0)
    impact_at(T(63), 0.9)
    for pas, oi in enumerate(range(24, 31)):
        groove_pos(oi, 1 if pas < 4 else 2, pas + 2, 1.0, fill=(oi == 30))
    for b in (63, 67, 71, 75):
        crash_at(T(b), 0.75)
    # ======================================================================== BUILD2 77-78 (order 31)
    for b in (77, 78):
        nm = BAR_CHORDS[b]
        power_hit(T(b), nm, 2.4, 0.9)
        sub_hold(b, 1, 0.9)
        for s in range(0, 16, 2):
            chug_at(T(b, s), CH[nm][0], 0.12, vj(0.8 + 0.01 * s, 0.9))
            hit_kick(T(b, s), vj(0.75, 0.85))
        hit_snare(T(b, 8), 0.9)
        for s in range(0, 16, 2):
            tk['hats'].hit(T(b, s), hat, vj(0.7 if s % 4 == 0 else 0.45, 0.8))
    revcym(T(79), 1.6, 0.75)
    # ======================================================================== BREAK 79-94 (orders 32-39, half time)
    crash_at(T(79), 0.9)
    impact_at(T(79), 0.9)
    for oi in range(32, 40):
        b0 = D.bar_of(oi)
        r = np.random.default_rng(9000 + oi)
        heavy = oi >= 36
        evs = sorted(D.events({oi}, 0, {8, 15, 11, 9}), key=lambda e: e.time)
        for i, e in enumerate(evs):
            t = g(e)
            b = int(t / BAR)
            root = CH[BAR_CHORDS[min(b, 94)]][0]
            if not heavy and i % 2:
                continue
            gap = (g(evs[i + 1]) - t) if i + 1 < len(evs) else 0.4
            pitch = root if (heavy or i % 4 == 0) else root
            chug_at(t, pitch, min(max(gap, 0.08) * 0.8, 0.32), vj(0.62 if not heavy else 0.88, 0.85), openg=(not heavy))
            bass_at(t, CH[BAR_CHORDS[min(b, 94)]][1], min(max(gap, 0.08) * 0.85, 0.4), vj(0.55 if not heavy else 0.85, 0.8))
            hit_kick(t, vj(0.5 if not heavy else 0.85, 0.82), soft=not heavy)
            if heavy and e.instrument in (8, 15) and r.random() < 0.55:
                tk['hook'].note(t, hookgt, int(round(D.midi(e))), 0.2, vj(0.8, 0.8), pan=float(r.choice([-0.35, 0.35])))
        for j in range(2):
            b = b0 + j
            nm = BAR_CHORDS[b]
            clean_arp(b, 0.5 if not heavy else 0.4, order=b)
            if heavy:
                power_hit(T(b), nm, 2.2, 0.8)
                kit_bar(b, 'groove', 0.78, variant=b)
            else:
                kit_bar(b, 'verse', 0.7, variant=b)
                tk['snare'].hit(T(b, 8), rim, 0.7)
                hit_snare(T(b, 8), 0.45, soft=True)
        if oi in (35, 39):
            crash_at(T(b0 + 1, 8), 0.5)
    crash_at(T(87), 0.9)
    impact_at(T(87), 0.8)
    revcym(T(95), 1.8, 0.8)
    # ======================================================================== GROOVE 3: orders 40-47 (bars 95-110)
    crash_at(T(95), 1.0)
    impact_at(T(95), 1.0)
    for pas, oi in enumerate(range(40, 48)):
        groove_pos(oi, 2, pas + 4, 1.0, fill=(oi == 47))
    for b in (95, 99, 103, 107):
        crash_at(T(b), 0.85)
    # ======================================================================== OUTRO 111-114 (order 48: D5 Bm7 E5 E5)
    crash_at(T(111), 1.0)
    power_hit(T(111, 0), 'D5', 8 * S16 * 0.95, 1.0)
    power_hit(T(112, 0), 'B5', 8 * S16 * 0.95, 1.0)
    power_hit(T(113, 0), 'E5', 2 * BAR + 3.2, 1.0)
    for t, p in ((T(111), 'D1'), (T(112), 'B1'), (T(113), 'E1')):
        bass_at(t, p, 1.2 if p != 'E1' else 2 * BAR + 0.6, 0.95)
    for b in (111, 112):
        for s in (0, 4, 8, 12):
            hit_kick(T(b, s), 0.9)
        hit_snare(T(b, 8), 0.95)
        for s in range(0, 16, 2):
            tk['hats'].hit(T(b, s), hat, vj(0.7 if s % 4 == 0 else 0.45, 0.8))
    hit_kick(T(113), 1.0)
    crash_at(T(113), 1.0)
    impact_at(T(113), 1.0)
    hit_snare(T(113, 8), 0.8)
    for s in (0, 8):
        tk['hats'].hit(T(113, s), hat_o, 0.5)
    for t, nm, d in ((T(111), 'A4', 0.6), (T(112), 'B4', 0.6), (T(113), 'E5', 2 * BAR + 3.0)):
        tk['lead'].note(t, lead, nm, d, 0.9)
    for b in (113, 114):
        clean_arp(b, 0.4, order=b)

    # ---- ROM layer levels per section (dB offsets of the track gains) ------------------------
    ramp = 0.3

    def sec_auto(track, base_db, table, default=0.0):
        base_db = 0.0
        pts = []
        for n_, a, z in SECS:
            v = base_db + table.get(n_, default)
            pts.append((max(0.0, T(a) - ramp * 0.0), v))
            pts.append((T(z) - ramp, v))
        # remove duplicates in time
        out = []
        for t, v in pts:
            if out and t <= out[-1][0]:
                t = out[-1][0] + 1e-3
            out.append((t, v))
        track.automate('gain', out)

    LV = ROMLV
    sec_auto(tk['r_stab'], 2, LV['stab'])
    sec_auto(tk['r_pluck'], -9, LV['pluck'])
    sec_auto(tk['r_vox'], -9, LV['vox'])
    sec_auto(tk['r_pad'], -9, LV['pad'])

    return m, tk, D


# dB offsets of the ROM tracks per section (tuned after listening to the stems' levels)
ROMLV = {
    'stab': {'intro': -6, 'build': -4, 'drone': -4, 'bridge': -4, 'g0': -3, 'groove1': 0, 'bed': -6, 'chorus': -4, 'drop': -3,
             'groove2': 0, 'build2': -3, 'break': -2, 'groove3': 1, 'outro': -4},
    'pluck': {'intro': 0, 'build': 0, 'drone': 0, 'bridge': 2, 'g0': 0, 'groove1': 0, 'bed': 2, 'chorus': -2, 'drop': 0,
              'groove2': 0, 'build2': 0, 'break': 2, 'groove3': 0, 'outro': 0},
    'vox': {'intro': 4.5, 'build': 1, 'drone': 1, 'bridge': 0, 'g0': -4, 'groove1': -5, 'bed': 4, 'chorus': -1, 'drop': 0,
            'groove2': -5, 'build2': -1, 'break': 3, 'groove3': -5, 'outro': 2},
    'pad': {'intro': 4.5, 'build': 0, 'drone': 1, 'bridge': 0, 'g0': -3, 'groove1': -6, 'bed': 3, 'chorus': -2, 'drop': 0,
            'groove2': -6, 'build2': -2, 'break': 1, 'groove3': -6, 'outro': 2},
    'perc': {'intro': -6, 'build': -4, 'drone': -4, 'bridge': -2, 'g0': 0, 'groove1': 0, 'bed': -8, 'chorus': -6, 'drop': -4,
             'groove2': 0, 'build2': -2, 'break': -3, 'groove3': 0, 'outro': -8},
}


def crop(m, t0, t1):
    """Keep only what sounds in [t0, t1): events are shifted to start at 0 (window renders for balancing)."""
    n0, n1 = int(round(t0 * RATE)), int(round(t1 * RATE))
    for tr in m.tracks:
        ev = []
        ons = []
        for t, a, gn, p in tr.events:
            i = int(round(t * RATE))
            if i + len(a) <= n0 or i >= n1:
                continue
            if i < n0:
                a = a[n0 - i:]
                i = n0
            ev.append(((i - n0) / RATE, a[:n1 - i], gn, p))
            ons.append((i - n0) / RATE)
        tr.events = ev
        tr.onsets = ons
        for k, pts in list(tr.autos.items()):
            tr.autos[k] = [(t - t0, v) for t, v in pts]
    m.length = t1 - t0


SECGAIN = [(0, 5, -5.5), (5, 9, -4.5), (9, 11, -3.5), (11, 15, -3.5), (15, 19, -2.5), (19, 21, -1.5), (21, 37, 0.0),
           (37, 45, -9.5), (45, 53, -8.0), (53, 61, 0.5), (61, 63, -2.5), (63, 77, 0.0), (77, 79, -2.0), (79, 87, -8.5),
           (87, 95, -2.5), (95, 111, 0.5), (111, 115, -1.0)]


def section_gain(x):
    """A smooth dB curve per section (the quiet/loud contrast), applied before mastering."""
    ramp = 0.4
    pts = []
    for a, b, v in SECGAIN:
        pts.append((T(a) + (ramp / 2 if a else 0.0), v))
        pts.append((T(b) - ramp / 2, v))
    t = np.arange(len(x)) / RATE
    gdb = np.interp(t, [p[0] for p in pts], [p[1] for p in pts])
    return x * dsp.undb(gdb)[:, None]


def master_mono_low(x, fc=150.0):
    mid = 0.5 * (x[:, 0] + x[:, 1])
    side = 0.5 * (x[:, 0] - x[:, 1])
    sos = sg.butter(8, fc, 'hp', fs=RATE, output='sos')
    side = sg.sosfiltfilt(sos, side)
    return np.stack([mid + side, mid - side], 1)


def softclip(x, thr=0.5):
    a = np.abs(x)
    return np.where(a > thr, np.sign(x) * (thr + (1 - thr) * np.tanh((a - thr) / (1 - thr))), x)


def tp_limiter(x, ceiling_db, lookahead=0.005, release=0.08):
    """Look-ahead brickwall limiter on the 4x oversampled (true) peaks, stereo linked."""
    from scipy.ndimage import minimum_filter1d
    x = np.asarray(x, np.float64)
    n = len(x)
    c = dsp.undb(ceiling_db)
    peak = np.empty(n)
    CH_ = 1 << 20
    for i in range(0, n, CH_):
        a = max(0, i - 64)
        z = min(n, i + CH_ + 64)
        up = sg.resample_poly(x[a:z], 4, 1, axis=0)
        gm = np.abs(up).max(1).reshape(-1, 4).max(1)
        gm = np.maximum(gm, np.concatenate([[0.0], gm[:-1]]))
        peak[i:min(n, i + CH_)] = gm[i - a:i - a + min(CH_, n - i)]
    req = np.minimum(1.0, c / np.maximum(peak, 1e-12))
    L = max(1, int(lookahead * RATE))
    gmin = minimum_filter1d(req, size=2 * L + 1, mode='nearest')
    B = 32
    nb = (n + B - 1) // B
    gp = np.concatenate([gmin, np.ones(nb * B - n)]).reshape(nb, B).min(1)
    rk = 1 - np.exp(-B / (RATE * release))
    sb = np.empty(nb)
    sv = 1.0
    for i in range(nb):
        v = gp[i]
        sv = v if v < sv else sv + (v - sv) * rk
        sb[i] = sv
    gs = np.repeat(sb, B)[:n]
    k = L // 2 * 2 + 1
    gs = np.convolve(np.pad(gs, (k // 2, k // 2), mode='edge'), np.ones(k) / k, mode='valid')
    gs = np.minimum(gs, gmin)
    return x * gs[:, None]


SOFT_THR = 0.4


def master_chain(pre, target=-14.0, tp=-1.5):
    """Bus compression, a soft clipper for the drum and guitar peaks, a true-peak look-ahead limiter, and the
    gain found by secant search so that the integrated loudness lands on the target."""
    x = dsp.compress(pre, threshold_db=-16, ratio=1.8, attack=0.02, release=0.2, knee_db=8)
    ceil = tp - 0.1

    def run(gdb):
        return tp_limiter(softclip(x * dsp.undb(gdb), SOFT_THR), ceil)

    g0, g1 = 8.0, 11.0
    y = run(g0)
    l0 = dsp.loudness_lufs(y, RATE)
    y = run(g1)
    l1 = dsp.loudness_lufs(y, RATE)
    gdb, L = g1, l1
    for _ in range(3):
        if abs(L - target) < 0.03:
            break
        slope = (l1 - l0) / (g1 - g0) if abs(g1 - g0) > 1e-6 and (l1 - l0) != 0 else 0.6
        gn = g1 + (target - l1) / max(slope, 0.2)
        g0, l0 = g1, l1
        g1 = gn
        y = run(g1)
        L = dsp.loudness_lufs(y, RATE)
        l1 = L
        gdb = g1
    y = tp_limiter(master_mono_low(y), ceil)
    L = dsp.loudness_lufs(y, RATE)
    return y, dict(gain_db=round(gdb, 2), lufs=round(L, 2), true_peak_dbtp=round(dsp.true_peak_db(y, RATE), 2))


def main():
    args = sys.argv[1:]
    out_base = args[0]
    rom = os.environ['PAYBACK_ROM']
    win = None
    if '--window' in args:
        i = args.index('--window')
        win = (float(args[i + 1]), float(args[i + 2]))
    if '--master' in args:                    # master stage from a saved pre-master mix
        pre = np.load(out_base + '_pre.npy').astype(np.float64)
        return finish(pre, out_base, False)
    log = set()
    _orig = mix.parse_note

    def _p(pp):
        v = _orig(pp)
        log.add(int(round(float(v))) % 12)
        return v
    mix.parse_note = _p
    m, tk, D = build(rom)
    mix.parse_note = _orig
    if '--audit' in args:
        audit(m, tk, log, out_base)
    if win:
        crop(m, T(win[0]), T(win[1]))
    m.master_fx.append(section_gain)
    m.master_fx.append(master_mono_low)
    if '--pre' in args:                       # save the pre-master mix (float32) for the master stage
        pre, _ = m.render(master=False)
        np.save(out_base + '_pre.npy', pre.astype(np.float32))
        print('pre saved', pre.shape)
        return
    stems = {} if '--stems' in args else None
    pre, _ = m.render(master=False, stems=stems)
    if stems is not None:
        np.save(out_base + '_stems.npy', {k: v for k, v in stems.items()}, allow_pickle=True)
    return finish(pre, out_base, bool(win))


def audit(m, tk, log, out_base):
    import json
    edge, nev, worst = 0.0, 0, ''
    for trk in m.tracks:
        for (t0_, a_, g_, p_) in trk.events:
            a_ = np.abs(np.asarray(a_))
            a_ = a_ if a_.ndim == 1 else a_.max(1)
            if len(a_) < 8 or a_.max() <= 0:
                continue
            r_ = max(a_[0], a_[-1]) / a_.max()
            nev += 1
            if r_ > edge:
                edge, worst = r_, '%s @ %.2f s' % (trk.name, t0_)
    ev = {k: sorted(set(round(t, 4) for t in tk[k].onsets)) for k in ('kick', 'snare', 'bass', 'gL', 'pwr', 'lead', 'hook', 'hats', 'cym', 'toms')}
    json.dump(dict(events=ev, pcs=sorted(log), click_edge=edge, click_events=nev, click_worst=worst), open(out_base + '_events.json', 'w'))


def finish(pre, out_base, win):
    if not win:
        pre = pre[:int(round((T(NBARS) + 3.2) * RATE))]
    target = -14.0
    tp = float(os.environ.get('TP', '-1.5'))
    for it in range(5):
        audio, rep = master_chain(pre, target, tp)
        audio = dsp.fade(audio, 0.0, 0.25, RATE)
        info = mix.export(audio, out_base, TITLE, kbps=320)
        if os.environ.get('MIX_WAV_ONLY'):     # (the ROM build: no MP3 to measure, the loudness is set there)
            print(rep)
            return
        L = info['mp3_lufs']
        print(it, rep, info['mp3_lufs'], info['mp3_true_peak_dbtp'])
        if win or (abs(L + 14.0) <= 0.08 and info['mp3_true_peak_dbtp'] <= -1.2):
            break
        target += (-14.0 - L)
        if info['mp3_true_peak_dbtp'] > -1.2:
            tp -= 0.3
    print(info)


if __name__ == '__main__':
    main()
