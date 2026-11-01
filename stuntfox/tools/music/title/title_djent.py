"""Full-length djent version of Payback's title-screen song (song 0) for Star-FlyBack.

Code only. The hook layer is Payback's own samples, played with the original note data (pitch, rhythm,
order, volume effects) by the toolchain's player (render.py); the heavy layer (palm-muted guitars, power
chords, drums, sub) is synthesised around it from the same note data. Everything is read from $PAYBACK_ROM
at run time; nothing derived from the ROM is stored.

    PAYBACK_ROM=/path/Payback.gba python3 remix_title_djent_full.py OUT_BASE [--stems]

Time base: the original runs one row = 4 ticks of the game's 50.0035 Hz sequencer, so a remix 16th is 2 rows,
a bar is 32 rows (about 2.56 s), exactly as the original plays it (felt at 93.75 BPM, E minor).

Form (86 bars, 3:40 + ring-out), original order positions in brackets
    0-6    intro: the original intro figure and the Edim build           [0 1 | 3]
    7-24   groove 1: the stab riff, 8 original patterns A A' A A'' ...   [8 .. 16]
    25-40  menu bed: pads, then the descending pluck figure              [17 18 | 21 22]
    41-50  Em drop, groove 2                                             [23 .. 27]
    51-68  break / big chorus: Am Em Am7 Em7 ... half-time pads, stabs  [31 .. 39]
    69-80  groove 3 (two jumps over the original's middle)               [40-43 | 46 47]
    81-85  outro D5 Bm7 E5 and the last E5 ringing out                   [48]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
from scipy.signal import butter, sosfiltfilt  # noqa: E402

import dsp                              # noqa: E402
import mix                              # noqa: E402
import pbsong                           # noqa: E402
import render                           # noqa: E402
import synth                            # noqa: E402
import djent_synth as dj                # noqa: E402
import origlayers as ol                 # noqa: E402
from synth import Inst                  # noqa: E402

RATE = 44100
ROW = 4.0 / render.GAME_CALL_RATE       # one row at speed 4, as the original player times it (0.0799944 s)
S16 = 2 * ROW
BAR = 16 * S16
NBARS = 86
TAIL = 3.6
TITLE = 'Star-FlyBack Title Remix (djent)'

# runs of original order positions placed contiguously: (remix bar, [orders])
RUNS = [(0, [0, 1]), (5, [3]), (7, list(range(8, 17))), (25, [17, 18]), (33, list(range(21, 28))),
        (51, list(range(31, 40))), (69, [40, 41, 42, 43]), (77, [46, 47]), (81, [48])]
ORDER_BARS = {0: 1, 1: 4, 3: 2, 17: 4, 18: 4, 21: 4, 22: 4, 48: 4}
SPEED8 = {0, 1, 2, 17, 18, 19, 20, 21, 22, 48}
SECTIONS = [('intro', 0, 7), ('groove1', 7, 25), ('menu', 25, 41), ('groove2', 41, 51), ('break', 51, 69),
            ('groove3', 69, 81), ('outro', 81, 86)]
SCALE_PCS = (4, 6, 7, 9, 11, 0, 2)

E1, FS1, G1, A1, B1, C2, D2, E2, G2 = 28, 30, 31, 33, 35, 36, 38, 40, 43
PCM = {'E': 40, 'F#': 42, 'G': 43, 'A': 45, 'B': 47, 'C': 48, 'D': 50, 'D#': 51}
PC_OF = {'E': 4, 'F#': 6, 'G': 7, 'A': 9, 'B': 11, 'C': 0, 'D': 2, 'D#': 3}
CH = {
    'Em': [52, 59, 64, 67, 71], 'Bm': [50, 54, 59, 62, 66], 'Cmaj7': [48, 55, 59, 64, 67],
    'Bsus4': [47, 52, 54, 59, 64], 'Am': [45, 52, 57, 60, 64], 'G': [43, 50, 55, 59, 62],
    'D5': [50, 57, 62, 66, 69], 'Bm7': [47, 54, 57, 62, 66], 'E5': [52, 59, 64, 71, 76], 'Asus2': [45, 52, 57, 59, 64],
}


def T(bar, s=0.0):
    return (bar * 16 + s) * S16


def mono_below(x, f=180.0):
    x = dsp.as_stereo(x)
    mid, side = (x[:, 0] + x[:, 1]) / 2, (x[:, 0] - x[:, 1]) / 2
    side = side - sosfiltfilt(butter(4, f, 'lowpass', fs=RATE, output='sos'), side)
    return np.stack([mid + side, mid - side], 1)


def accent_pc(sample, period):
    """Pitch class (name) the original note sounds at: chord samples by their measured chord root."""
    n = pbsong.note_name(period)
    tab = {8: {'G-2': 'F#', 'A#2': 'A', 'C-3': 'B', 'F-2': 'E', 'D#3': 'D', 'C-2': 'B'},
           15: {'G-2': 'B', 'C-3': 'E'}, 11: {'G-2': 'G', 'C-3': 'C'},
           9: {'G-2': 'G', 'C-3': 'C', 'A-2': 'F#', 'D-3': 'D'}}
    return tab.get(sample, {}).get(n)


def build(out_base, want_stems=False):
    rom_path = os.environ['PAYBACK_ROM']
    song = ol.clean_song(pbsong.load(rom_path, 0))
    r0 = render.render(song, 'payback', stereo=0.4, tail=1.0)
    st = ol.order_times(r0)
    st[49] = r0.duration - 1.0
    rows_t = {}
    for ri in r0.rows:
        rows_t.setdefault(ri.order_index, {}).setdefault(ri.row, ri.time)
    # which remix bar each original order starts at
    bar_of = {}
    for b0, orders in RUNS:
        b = b0
        for o in orders:
            bar_of[o] = b
            b += ORDER_BARS.get(o, 2)
        assert b <= NBARS + 1
    EV = {}
    for n in r0.notes:
        if n.volume > 0 and n.order_index in bar_of:
            EV.setdefault(n.order_index, []).append(n)

    def rowT(oi, row):
        return T(bar_of[oi]) + row * ROW * (2 if oi in SPEED8 else 1)

    m = mix.Mix(bpm=240.0 / BAR, bars=NBARS, title=TITLE, tail=TAIL)
    assert abs(m.bar(1) - BAR) < 1e-9

    m.bus('verb', lambda x: dsp.reverb(x, decay=2.4, wet_only=True, damp=0.55), gain_db=-3)
    m.bus('hall', lambda x: dsp.reverb(x, decay=5.0, wet_only=True, damp=0.4, predelay=0.03), gain_db=-4)
    m.bus('room', lambda x: dsp.reverb(x, decay=0.6, wet_only=True, damp=0.6, predelay=0.006), gain_db=-6)

    # ---- tracks (heavy layer)
    kick = m.track('kick', gain_db=-7, sends={'room': 0.08})
    snare = m.track('snare', gain_db=-3, sends={'room': 0.3, 'verb': 0.1})
    hats = m.track('hats', gain_db=-9, pan=0.12, hp=500, sends={'room': 0.1})
    cym = m.track('cymbals', gain_db=-8, sends={'hall': 0.15, 'room': 0.1})
    toms = m.track('toms', gain_db=-8, sends={'room': 0.2, 'verb': 0.1})
    gtr = m.track('guitar', gain_db=-4.5, eq=[('peak', 140, 1.5, 0.9)], sends={'room': 0.06})
    pcg = m.track('powerchords', gain_db=-5, sends={'room': 0.08, 'verb': 0.05})
    sub = m.track('sub', gain_db=-21.5, duck=dict(key='kick', amount=0.45, release=0.07, shape=1.2))
    air = m.track('air', gain_db=-12, hp=200, sends={'hall': 0.45})
    fx = m.track('fx', gain_db=-9, sends={'hall': 0.25, 'verb': 0.1})
    # ---- tracks (the original's own samples, played with the original note data)
    hk_g = m.track('hook_guitar', gain_db=-4, hp=90, width=1.6, eq=[('peak', 2200, 3.0, 0.8)], drive=1.3,
                   sends={'room': 0.1, 'verb': 0.05})
    hk_v = m.track('hook_vocal', gain_db=-6, hp=140, width=1.5, sends={'verb': 0.22, 'hall': 0.25})
    hk_l = m.track('hook_lead', gain_db=-7, hp=180, width=1.5, sends={'verb': 0.2, 'hall': 0.3})
    hk_f = m.track('hook_fx', gain_db=-10, hp=120, sends={'hall': 0.2})

    memo = {}

    def cached(key, fn, *a, **kw):
        k = (key,) + tuple(id(x) if isinstance(x, np.ndarray) else x for x in a) + tuple(sorted(kw.items()))
        if k not in memo:
            memo[k] = fn(*a, **kw)
        return memo[k]

    PMG = [Inst(dj.palm_mute_guitar, take=0), Inst(dj.palm_mute_guitar, take=1)]
    PCG = Inst(dj.power_chord_guitar)
    PCG_MUTE = Inst(dj.power_chord_guitar, mute=0.8, drive=6.0)
    PCG_RING = Inst(dj.power_chord_guitar, release=1.0)
    SUBI = Inst(dj.dist_sub)
    KICK = Inst(synth.kick, f_start=150.0, f_end=52.0, pitch_time=0.016, decay=0.17, click=0.38, drive=2.6)
    KICK_BIG = Inst(synth.kick, f_start=140.0, f_end=46.0, pitch_time=0.022, decay=0.3, click=0.36, drive=2.8)
    SNARE = Inst(synth.snare, tone=225.0, tone_decay=0.07, noise_decay=0.17, snap=0.82, bright=4300.0)
    RIM = Inst(synth.rim, freq=2050.0)
    CLAP = Inst(synth.clap, tone=1400.0, tail=0.16)
    HAT = Inst(synth.hat, decay=0.05)
    HATO = Inst(synth.hat, open=True, decay=0.22)
    CRASH = Inst(synth.cymbal, dur=2.4, kind='crash')
    RIDE = Inst(synth.cymbal, dur=1.3, kind='ride')
    TOMI = Inst(synth.tom, decay=0.22)
    TOMF = (190.0, 140.0, 105.0, 80.0)
    IMPACT = Inst(synth.impact, dur=3.0)
    REVCYM = Inst(synth.reverse_cymbal, dur=1.28)

    rec = {'kick': [], 'guitar': [], 'power': [], 'hat': [], 'snare': [], 'sub': [], 'tom': [], 'ride': []}
    kick_req = []

    def hz(midi):
        return float(dsp.midi_hz(midi))

    def rd(d):
        return round(d / 0.01) * 0.01

    def want_kick(t, v, big=False):
        kick_req.append((t, v, big))

    # ---------------------------------------------------------------- building blocks
    def chug(t, midi, d16=1.0, vel=1.0, kick_v=0.95, with_sub=True, big=False):
        d = rd(min(0.22, max(0.06, d16 * S16 * 0.66)))
        for take, pan_, off in ((0, -0.85, 0.0), (1, 0.85, 0.006)):
            gtr.note(t + off, PMG[take], midi, d, vel, pan=pan_)
        if with_sub:
            sm_ = midi - 12 if midi >= 40 else midi
            sd = rd(min(0.25, d * 1.1))
            sub.note(t, SUBI, sm_, sd, vel)
            rec['sub'].append((t, sd))
        if kick_v:
            want_kick(t, kick_v, big)
        rec['guitar'].append(t)

    def power(t, root, d, vel=1.0, mute=False, sub_v=0.9, kick_v=None, big=False):
        inst = PCG_MUTE if mute else PCG
        pcg.note(t, inst, root, rd(d), vel)
        sd = rd(min(0.5, max(0.08, d * (0.5 if not mute else 1.0))))
        sub.note(t, SUBI, root if root < 40 else root - 12, sd, sub_v)
        rec['sub'].append((t, sd))
        if kick_v:
            want_kick(t, kick_v, big)
        rec['power'].append(t)

    def snare_hit(t, v=1.0, rim=0.5, clap=0.0):
        snare.hit(t, SNARE, v)
        rec['snare'].append(t)
        if rim:
            snare.hit(t, RIM, v * rim, gain_db=-4)
        if clap:
            snare.hit(t, CLAP, v * clap, gain_db=-3)

    def hat_hit(t, v, open_=False):
        hats.hit(t, HATO if open_ else HAT, v)
        rec['hat'].append(t)

    def hats_grid(b0, nb, v=0.6, open_at=(), skip=()):
        """Steady eighth-note hats (no 16ths, no rolls); the offbeat opens only where asked."""
        for b in range(b0, b0 + nb):
            for s in range(0, 16, 2):
                if (b, s) in skip:
                    continue
                hat_hit(T(b, s), v * (1.0 if s % 4 == 0 else 0.7), (b, s) in open_at)

    def crash(b, s=0, v=0.9):
        cym.hit(T(b, s), CRASH, v)

    def revcym(b, s, v=0.7):
        fx.clip(T(b, s) - 1.28, REVCYM(None, 0.25, v), gain_db=-6)

    def tom_fill(b, s0, pitches, step=2, v=0.8):
        for i, p in enumerate(pitches):
            toms.note(T(b, s0 + i * step), TOMI, None, 0.4, v, hz=TOMF[p])
            rec['tom'].append(T(b, s0 + i * step))

    def pad_chord(b, name, nbars, trk, vel=0.8, attack=1.0, cutoff=5200.0, voices=5, detune=0.2, oct_=0):
        notes = [p + 12 * oct_ for p in CH[name]]
        f = [hz(p) for p in notes]
        a = cached('ss', synth.supersaw, tuple(f), nbars * BAR, vel, voices=voices, detune=detune, attack=attack,
                   release=1.4, cutoff=cutoff, seed=21 + len(f))
        trk.clip(T(b), a, fade=0.01)

    # ---------------------------------------------------------------- the original's samples (hook layer)
    gains = {}
    group_audio = {}
    for g in ('gtr', 'vox', 'lead', 'fx'):
        group_audio[g] = ol.render_group(song, ol.GROUPS[g], stereo=0.4, tail=1.0).audio
    trk_of = {'gtr': hk_g, 'vox': hk_v, 'lead': hk_l, 'fx': hk_f}
    hook_runs = []
    for b0, orders in RUNS:
        i0 = int(round(st[orders[0]] * RATE))
        last = orders[-1]
        t_end = st.get(last + 1, r0.duration - 1.0)
        i1 = int(round(t_end * RATE))
        for g, trk in trk_of.items():
            seg = group_audio[g][i0:i1].astype(np.float64)
            if not np.any(np.abs(seg) > 1e-5):
                continue
            tail = 0.0
            if last == 48:                       # the original's last notes keep ringing into the ending
                seg = group_audio[g][i0:i1 + int(1.0 * RATE)].astype(np.float64)
                seg[-int(1.0 * RATE):] *= np.linspace(1, 0, int(1.0 * RATE))[:, None]
            trk.clip(T(b0), seg, fade=0.004)
        hook_runs.append((b0, orders, st[orders[0]], t_end))
    for g in group_audio:
        group_audio[g] = None

    # the notes the hook layer plays: for the fidelity check
    hook_events = []
    for oi, evs in EV.items():
        for n in evs:
            grp = next((g for g in ('gtr', 'vox', 'lead', 'fx') if n.instrument in ol.GROUPS[g]), None)
            if grp is None:
                continue
            hook_events.append(dict(t=round(rowT(oi, n.row), 4), group=grp, sample=n.instrument, period=n.period,
                                    channel=n.channel, order=oi, row=n.row, volume=n.volume,
                                    note=pbsong.note_name(n.period)))

    # ---------------------------------------------------------------- the heavy layer around the groove stabs
    def accents_of(oi):
        """(time, midi, sample) of the original stab / bass-thump hits of order oi (channel 0)."""
        out = []
        for n in EV.get(oi, []):
            if n.channel == 0 and n.instrument in (8, 15, 11, 9):
                pc = accent_pc(n.instrument, n.period)
                if pc:
                    out.append((rowT(oi, n.row), PCM[pc], n.instrument))
        return sorted(out)

    def pedal_rows(oi):
        return sorted(rowT(oi, n.row) for n in EV.get(oi, []) if n.channel == 0 and n.instrument == 12)

    def kick_rows(oi):
        return sorted(rowT(oi, n.row) for n in EV.get(oi, []) if n.channel == 0 and n.instrument == 14)

    def ped_root(oi):
        ns = [pbsong.note_name(n.period) for n in EV.get(oi, []) if n.channel == 0 and n.instrument == 8]
        return A1 if ns and ns.count('C-3') > len(ns) / 2 else E1

    def pedal_times(kind, b0, orig, bars=2):
        """Sixteenth positions (in the order's frame, may be fractional) of the pedal chugs."""
        s = []
        if kind == 'orig':
            s = [round((t - T(b0)) / S16 * 2) / 2 for t in orig] + [0, 16]
        elif kind == 'poly':            # 3+3+3+3+4 regroup: heads at 0 3 6 9 12 of each bar, chugs between
            for b in range(bars):
                s += [16 * b + h for h in (0, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15)]
        elif kind == 'sev8':            # a 7/8 cell (14 sixteenths) twice, then a 4-sixteenth tail
            for off in (0, 14):
                s += [off + c for c in (0, 3, 5, 6, 9, 11, 12)]
            s += [28, 30, 31]
        elif kind == 'gallop':
            for b in range(bars):
                s += [16 * b + h for h in (0, 2, 3, 6, 8, 10, 11, 14)]
        elif kind == 'poly_b':          # the same 3+3+3+3+4 regroup, other fills: first four groups get a chug on every sixteenth pair
            for b in range(bars):
                s += [16 * b + h for h in (0, 1, 3, 4, 6, 7, 9, 10, 12, 13, 15)]
        elif kind == 'sev8b':           # 7/8 cell with a different internal grouping (2+2+3 | 2+3+2)
            for off in (0, 14):
                s += [off + c for c in (0, 2, 4, 7, 9, 12, 13)]
            s += [28, 29, 31]
        elif kind == 'gallop_b':
            for b in range(bars):
                s += [16 * b + h for h in (0, 3, 4, 7, 8, 11, 12, 14)]
        elif kind == 'orig2':
            s = [round((t - T(b0)) / S16 * 2) / 2 for t in orig] + [0, 8, 16, 24]
        elif kind == 'half':
            s = [0, 8, 16, 24]
        return sorted(set(s))

    def groove(oi, ped, crash_=True, fill=False, hat_open=(), vel=1.0, oct_up=False, big_open=False, toms=(0, 1, 2, 3)):
        b0 = bar_of[oi]
        acc = accents_of(oi)
        orig = pedal_rows(oi)
        root = ped_root(oi)
        hits = {}
        for t, midi, smp in acc:
            hits[round(t / S16 * 2)] = (t, midi + (12 if oct_up and smp == 8 else 0), 1.0, True)
        for s in pedal_times(ped, b0, orig):
            t = T(b0, s)
            k = round(t / S16 * 2)
            if any(abs(k - j) <= 1 for j in hits):
                continue
            hits[k] = (t, root, 0.8, False)
        ks = sorted(hits)
        for i, k in enumerate(ks):
            t, midi, v, is_acc = hits[k]
            nxt = hits[ks[i + 1]][0] if i + 1 < len(ks) else T(b0, 32)
            chug(t, midi, d16=min(2.0, (nxt - t) / S16), vel=v * vel, kick_v=1.0 if is_acc else 0.88)
        for t in kick_rows(oi):
            want_kick(t, 0.9)
        for b in (b0, b0 + 1):
            if not (fill and b == b0 + 1):
                snare_hit(T(b, 8), 0.95, rim=0.5)
        hats_grid(b0, 2, v=0.6, open_at={(b0 + 1, 14)} if not hat_open else hat_open)
        if crash_:
            crash(b0, 0, 0.9)
        if fill:
            tom_fill(b0 + 1, 8, list(toms), step=2, v=0.75)
        if ped == 'sev8':
            for s in range(0, 32, 3):
                cym.hit(T(b0, s), RIDE, 0.26)
                rec['ride'].append(T(b0, s))

    def place_kicks():
        """Double kick locked to the guitar hits; never a third kick in a row at 16th spacing."""
        kick_req.sort()
        run = 1
        prev = None
        for t, v, big in kick_req:
            if prev is not None and t - prev < 0.04:
                continue
            if prev is not None and t - prev < 1.15 * S16:
                run += 1
            else:
                run = 1
            if run > 2:
                run = 0
                prev = t
                continue
            kick.hit(t, KICK_BIG if big else KICK, v)
            rec['kick'].append(t)
            prev = t

    # ================================================================ INTRO (bars 0-6)
    pad_chord(0, 'E5', 1, air, vel=0.6, attack=0.4, cutoff=5200.0)
    for b, nm in ((1, 'D5'), (2, 'Bm7'), (3, 'E5'), (4, 'E5')):
        pad_chord(b, nm, 1, air, vel=0.6, attack=0.5, cutoff=5200.0)
    pad_chord(5, 'Em', 2, air, vel=0.6, attack=0.8, cutoff=5600.0)
    for b, r_ in zip(range(0, 5), (E1, D2 - 12, B1, E1, E1)):   # a short sub pulse once a bar (never a held drone)
        sub.note(T(b), SUBI, r_, 0.5, 0.5)
        rec['sub'].append((T(b), 0.5))
    for s in range(0, 16, 4):
        hat_hit(T(4, s), 0.3)
    for s in range(0, 16, 2):
        hat_hit(T(5, s), 0.4 + 0.02 * s)
    for s in (0, 8):
        want_kick(T(5, s), 0.7)
    for s in (0, 4, 8, 12):
        hat_hit(T(6, s), 0.5)
    for s in (0, 4, 8, 12):
        want_kick(T(6, s), 0.8)
    tom_fill(6, 8, [0, 1, 2, 3], step=2, v=0.6)
    snare_hit(T(6, 8), 0.8, rim=0.4)
    fx.clip(T(5, 0), synth.riser(2 * BAR - S16, 0.8, f0=250.0, f1=9000.0, tone=0.3, freq=82.4), gain_db=-10)
    revcym(7, 0, 0.8)

    # ================================================================ GROOVE 1 (bars 7-24)
    fx.hit(T(7), IMPACT, 0.6, gain_db=-6)
    crash(7, 0, 0.8)
    # order 8: the Em pad of the original, the riff comes in with the drums
    for s in (0, 6, 10):
        chug(T(7, s), E1, d16=2, vel=0.9, kick_v=0.8)
    hats_grid(7, 2, v=0.4)
    snare_hit(T(8, 8), 0.8, rim=0.4)
    # orders 9..16: patterns A A' A A'' A A' A fill
    plan1 = {9: dict(ped='orig'), 10: dict(ped='poly'), 11: dict(ped='gallop_b', oct_up=True), 12: dict(ped='sev8'),
             13: dict(ped='gallop'), 14: dict(ped='poly_b', oct_up=True), 15: dict(ped='sev8b', oct_up=True),
             16: dict(ped='half', fill=True)}
    for oi, kw in plan1.items():
        groove(oi, **kw)
    revcym(25, 0, 0.8)

    # ================================================================ MENU BED (bars 25-40)
    roots_menu = {17: [E1, E1, B1, B1], 18: [E1, E1, B1, B1], 21: [E1, B1, C2, B1], 22: [E1, B1, C2, B1]}
    names_menu = {17: ['Em', 'Em', 'Bm', 'Bm'], 18: ['Em', 'Em', 'Bm', 'Bm'], 21: ['Em', 'Bm', 'Cmaj7', 'Bsus4'],
                  22: ['Em', 'Bm', 'Cmaj7', 'Bm']}
    fx.hit(T(25), IMPACT, 0.5, gain_db=-8)
    crash(25, 0, 0.7)
    for oi in (17, 18, 21, 22):
        for i in range(4):
            b = bar_of[oi] + i
            pad_chord(b, names_menu[oi][i], 1, air, vel=0.6, attack=0.9, cutoff=5200.0)
            r_ = roots_menu[oi][i]
            sub.note(T(b), SUBI, r_, 0.6, 0.55 if oi < 21 else 0.7)
            rec['sub'].append((T(b), 0.6))
    # 17: only the pads; 18: a slow heartbeat of chugs and a quiet ride; 21: heavy half-time; 22: heavier
    for i in range(4):
        b = bar_of[18] + i
        r_ = roots_menu[18][i]
        for s, d, v in ((0, 4, 0.9), (8, 4, 0.8)):
            chug(T(b, s), r_ + (12 if i == 3 and s == 8 else 0), d16=d, vel=v, kick_v=0.7)
        for s in (0, 8):
            cym.hit(T(b, s), RIDE, 0.28)
            rec['ride'].append(T(b, s))
    brk21 = {0: [(0, 5, 1.0), (6, 2, 0.9), (10, 4, 1.0)], 1: [(0, 3, 1.0), (3, 2, 0.9), (6, 2, 0.9), (8, 5, 1.0)],
             2: [(0, 4, 1.0), (4, 2, 0.8), (8, 2, 0.9), (10, 2, 0.8), (12, 2, 0.9)], 3: [(0, 2, 1.0), (2, 2, 0.8), (6, 2, 0.9), (8, 4, 1.0)]}
    for oi in (21, 22):
        for i in range(4):
            b = bar_of[oi] + i
            r_ = roots_menu[oi][i]
            hs = brk21[(i + (2 if oi == 22 else 0)) % 4] if oi == 21 else brk21[(i + 1) % 4]
            for s, d, v in hs:
                chug(T(b, s), r_ + (12 if (s == 6 and i % 2) else 0), d16=d, vel=v * (1.0 if oi == 22 else 0.9),
                     kick_v=1.0 if s in (0, 10) else 0.85, big=(s == 0))
            snare_hit(T(b, 8), 0.95 if oi == 22 else 0.85, rim=0.4)
        hats_grid(bar_of[oi], 4, v=0.5 if oi == 21 else 0.58)
        crash(bar_of[oi], 0, 0.8)
    tom_fill(40, 8, [0, 1, 2, 3], step=2, v=0.75)
    revcym(41, 0, 0.8)

    # ================================================================ EM DROP + GROOVE 2 (bars 41-50)
    fx.hit(T(41), IMPACT, 0.9, gain_db=-4)
    sub.note(T(41), SUBI, E1, 0.6, 0.7)
    rec['sub'].append((T(41), 0.6))
    for s in (0, 8):
        cym.hit(T(41, s), RIDE, 0.3)
        rec['ride'].append(T(41, s))
    for s in (0, 8):
        want_kick(T(41, s), 0.8, big=True)
    snare_hit(T(41, 8), 0.8, rim=0.4)
    for s in range(0, 16, 2):
        hat_hit(T(42, s), 0.45 + 0.02 * s)
    tom_fill(42, 8, [0, 1, 2, 3], step=2, v=0.7)
    revcym(43, 0, 0.8)
    plan2 = {24: dict(ped='gallop_b'), 25: dict(ped='poly_b'), 26: dict(ped='poly', oct_up=True), 27: dict(ped='sev8b', fill=True)}
    for oi, kw in plan2.items():
        groove(oi, **kw)
    revcym(51, 0, 0.9)

    # ================================================================ BREAK / BIG CHORUS (bars 51-68)
    fx.hit(T(51), IMPACT, 1.0, gain_db=-3)
    crash(51, 0, 1.0)
    groove(31, ped='gallop', crash_=False, hat_open={(52, 14)})
    break_roots = {32: [A1, A1, A1, A1], 33: [E2, E2, E2, E2], 34: [A1, A1, A1, A1], 35: [A1, E2, G1 + 12, E2],
                   36: [A1, A1, A1, A1], 37: [E2, E2, E2, E2], 38: [A1, A1, A1, A1], 39: [E2, E2, E2, E2]}
    break_names = {32: ['Am'] * 4, 33: ['Em'] * 4, 34: ['Am'] * 4, 35: ['Asus2', 'Em', 'G', 'Em'], 36: ['Am'] * 4,
                   37: ['Em'] * 4, 38: ['Am'] * 4, 39: ['Em'] * 4}
    BP = [[(0, 6), (8, 3)], [(0, 4), (6, 4), (12, 3)], [(0, 8), (10, 4)], [(0, 3), (3, 3), (8, 5)], [(0, 6), (10, 3)],
          [(0, 5), (6, 2), (8, 5)], [(0, 4), (8, 4), (12, 3)], [(0, 10), (12, 3)], [(0, 2), (2, 2), (4, 4), (10, 3)],
          [(0, 7), (8, 2), (12, 3)], [(0, 4), (4, 4), (10, 4)], [(0, 3), (6, 3), (9, 3), (12, 3)], [(0, 6), (6, 3), (12, 3)],
          [(0, 12)], [(0, 5), (8, 3), (12, 3)], [(0, 3), (4, 3), (8, 6)]]
    for oi in range(32, 40):
        b0 = bar_of[oi]
        acc = accents_of(oi)
        orig = pedal_rows(oi)
        for i in range(2):
            b = b0 + i
            root = break_roots[oi][i * 2]
            pat = BP[((oi - 32) * 2 + i) % len(BP)]
            for s, d in pat:
                power(T(b, s), root, d * S16 * 0.95, vel=1.0, kick_v=1.0, big=(s == 0))
            snare_hit(T(b, 8), 1.0, rim=0.6, clap=0.5)
            for s in range(0, 16, 2):
                hat_hit(T(b, s), (0.7 if s % 4 == 0 else 0.5), open_=(s % 8 == 6 and oi % 2 == 1))
        # the original stab hits as palm-muted chugs on top of the open chords
        ks = [round(t / S16 * 2) for t, _, _ in acc]
        for t, midi, smp in acc:
            chug(t, midi, d16=1.0, vel=0.75, kick_v=0.85, with_sub=False)
        root_ped = A1 if oi % 2 == 0 else E1
        for t in orig:
            k = round(t / S16 * 2)
            if any(abs(k - j) <= 1 for j in ks):
                continue
            chug(t, root_ped, d16=1.0, vel=0.7, kick_v=0.8, with_sub=False)
        for t in kick_rows(oi):
            want_kick(t, 0.85)
        if oi in (32, 34, 36, 38):
            crash(b0, 0, 0.75)
    crash(55, 0, 0.9)
    for oi in (32, 34, 36, 38):
        nm = break_names[oi][0]
        pad_chord(bar_of[oi], 'Am', 2, air, vel=0.6, attack=0.5, cutoff=5800.0)
    for oi in (33, 35, 37, 39):
        pad_chord(bar_of[oi], 'Em', 2, air, vel=0.6, attack=0.5, cutoff=5800.0)
    tom_fill(bar_of[39] + 1, 8, [0, 1, 2, 3], step=2, v=0.8)
    fx.clip(T(bar_of[39]), synth.riser(2 * BAR - S16, 0.9, f0=250.0, f1=9000.0, tone=0.3, freq=82.4), gain_db=-9)
    revcym(69, 0, 0.9)

    # ================================================================ GROOVE 3 (bars 69-80)
    fx.hit(T(69), IMPACT, 1.0, gain_db=-3)
    crash(69, 0, 1.0)
    plan3 = {40: dict(ped='poly', crash_=False, vel=1.0), 41: dict(ped='orig2', oct_up=True), 42: dict(ped='sev8b'),
             43: dict(ped='gallop_b', oct_up=True), 46: dict(ped='poly_b', oct_up=True), 47: dict(ped='orig2', fill=True, toms=(3, 1, 2, 0), vel=1.0)}
    for oi, kw in plan3.items():
        groove(oi, **kw)
    for oi in (40, 42, 46):
        power(T(bar_of[oi], 0), E2, 3 * S16, vel=0.8, kick_v=None, sub_v=0.0)
    revcym(81, 0, 0.8)

    # ================================================================ OUTRO (bars 81-85)
    fx.hit(T(81), IMPACT, 0.8, gain_db=-5)
    crash(81, 0, 1.0)
    o48 = {n.row: n for n in EV.get(48, [])}
    # the original's figure: sample 3 at row 15, 4 at row 23, 17 at row 31 (D5, Bm7, E5), played as power chords
    power(rowT(48, 15), D2, 6 * S16, vel=0.95, kick_v=1.0, big=True)
    for s in (6, 10, 12):
        power(rowT(48, 15) + s * S16, D2, 0.1, vel=0.8, mute=True, kick_v=0.8)
    power(rowT(48, 23), B1 + 12, 5 * S16, vel=0.95, kick_v=1.0, big=True)
    for s in (5, 8, 10):
        power(rowT(48, 23) + s * S16, B1 + 12, 0.1, vel=0.8, mute=True, kick_v=0.8)
    t_e = rowT(48, 31)
    pcg.note(t_e, PCG_RING, E2, 2 * BAR + 0.5, 0.85)
    sub.note(t_e, SUBI, E1, 1.2, 0.9)
    rec['sub'].append((t_e, 1.2))
    rec['power'].append(t_e)
    want_kick(t_e, 1.0, True)
    crash_t = t_e
    cym.hit(crash_t, CRASH, 0.9)
    for t in (rowT(48, 15) + 8 * S16, rowT(48, 23) + 8 * S16):
        snare_hit(t, 0.9, rim=0.5, clap=0.4)
    for b in (81, 82):
        hats_grid(b, 1, v=0.5)
    pad_chord(81, 'D5', 1, air, vel=0.7, attack=0.5, cutoff=5800.0)
    pad_chord(82, 'Bm7', 1, air, vel=0.7, attack=0.5, cutoff=5800.0)
    pad_chord(83, 'Em', 3, air, vel=0.75, attack=0.4, cutoff=6200.0)
    place_kicks()

    # ---- hook level per section (dB per track, steps ramped over 30 ms)
    def sec_auto(trk, vals):
        pts = []
        for (nm, b0, b1) in SECTIONS:
            v = vals.get(nm, vals.get('*', 0.0))
            pts.append((T(b0) + (0.0 if b0 == 0 else 0.03), v))
            pts.append((T(b1) - 0.001, v))
        trk.automate('gain', pts)

    HG = json.loads(os.environ.get('HOOKGAIN', 'null')) or {}
    air.automate('gain', [(0, 0.0), (T(25) - 0.01, 0.0), (T(25), -2.0), (T(51) - 0.01, -2.0), (T(51), -4.0), (T(81) - 0.01, -4.0),
                          (T(81), -3.0), (T(NBARS), -3.0)])
    pcg.automate('gain', [(0, 0.0), (T(81) - 0.01, 0.0), (T(81), -1.0), (t_e + 0.4, -1.0), (t_e + 2.5, -9.0), (T(NBARS) + 2, -12.0)])
    sec_auto(hk_g, HG.get('g', {'*': -1.0, 'break': 0.0, 'groove3': 0.0}))
    sec_auto(hk_v, HG.get('v', {'*': 2.0, 'menu': 4.0, 'break': 5.0, 'intro': 4.0}))
    sec_auto(hk_l, HG.get('l', {'*': 2.0, 'menu': 4.0, 'break': 3.0}))
    sec_auto(hk_f, HG.get('f', {'*': 0.0}))
    # ================================================================ master
    def soft_clip(x):
        p = float(np.percentile(np.abs(x), 99.7))
        return p * np.tanh(x / p)

    ARC = json.loads(os.environ.get('ARCDB', 'null')) or {'intro': 0.0, 'groove1': -2.0, 'menu': 0.5, 'groove2': -1.5,
                                                          'break': 1.4, 'groove3': -0.5, 'outro': 0.0}

    def arc_env(x):
        sr = m.rate
        pts_t, pts_v = [0.0], [ARC['intro']]
        for (nm, b0, b1) in SECTIONS:
            pts_t += [T(b0) + (0.0 if b0 == 0 else 0.4), T(b1) - 0.4]
            pts_v += [ARC[nm], ARC[nm]]
        pts_t.append(len(x) / sr)
        pts_v.append(pts_v[-1])
        g = 10 ** (np.interp(np.arange(len(x)) / sr, pts_t, pts_v) / 20.0)
        return x * g[:, None] if x.ndim == 2 else x * g

    m.master_fx.append(lambda x: soft_clip(mono_below(dsp.highpass(dsp.highpass(x, 22), 22), 180.0)))
    m.master_fx.append(arc_env)   # after the soft clip, so the arc does not change the clipper's shape

    stems = {} if want_stems else None
    audio, rep = m.render(lufs=-14.0, true_peak=-1.9, fade_out=2.6, stems=stems)
    info = m.export(audio, out_base, TITLE, kbps=320)
    rep.update(info)
    meta = dict(sections=SECTIONS, row=ROW, s16=S16, bar=BAR, nbars=NBARS, runs=hook_runs,
                onsets_kick=sorted(set(round(t, 4) for t in rec['kick'])),
                onsets_guitar=sorted(set(round(t, 4) for t in rec['guitar'])),
                onsets_power=sorted(set(round(t, 4) for t in rec['power'])),
                hats=sorted(round(t, 4) for t in rec['hat']), snares=sorted(round(t, 4) for t in rec['snare']),
                toms=sorted(round(t, 4) for t in rec['tom']), subs=[(round(t, 4), round(d, 3)) for t, d in rec['sub']],
                rides=sorted(round(t, 4) for t in rec['ride']),
                hook_events=hook_events,
                accents=[dict(t=round(t, 4), midi=md, order=oi) for oi in sorted(bar_of) for t, md, _ in accents_of(oi)])
    with open(out_base + '_meta.json', 'w') as f:
        json.dump(meta, f)
    if want_stems:
        np.savez_compressed(out_base + '_stems.npz', **{k: v.astype(np.float32) for k, v in stems.items()})
    return rep


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    print(build(args[0] if args else 'djentfull', want_stems='--stems' in sys.argv))
