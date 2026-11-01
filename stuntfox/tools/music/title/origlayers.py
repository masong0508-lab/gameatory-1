"""Original song 0 split into sample groups, rendered by Payback's own player semantics (render.py).
Code only; samples and note data are read from $PAYBACK_ROM at run time."""
import copy, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import numpy as np
import pbsong, render

# groups of ROM samples (see note.md for how they were identified: spectrograms, harmonic structure, envelopes)
GROUPS = {
    'gtr': (3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 17),   # guitar-like: low harmonic stacks with chord stab / chug envelopes
    'vox': (10, 26, 27, 28, 29, 31),                     # vocal-like: moving formant / vibrato partials, chorused choir pads, the "ooh" echo
    'lead': (1, 2, 30),                                  # synth lead, bell pluck (menu figure), pure-partial pad
    'low': (16, 18, 19),                                 # bass drones
    'fx': (20, 21),                                      # noise sweep, riser
}


def clean_song(song):
    """A copy without the tempo nudge in the groove (F01 / F07 on rows 56-57) so rows sit on a clean 0.08 s grid."""
    s = copy.deepcopy(song)
    for p, rows in s.patterns.items():
        for r in (56, 57):
            for c in range(4):
                cell = rows[r][c]
                if cell.effect == 0xF and cell.param in (1, 7):
                    rows[r][c] = pbsong.Cell(cell.period, cell.instrument, 0, 0)
    return s


def filtered(song, keep):
    """Copy of the song where notes of samples outside `keep` are replaced by a volume-0 cell (so a kept voice on
    that channel is cut exactly where the original would have cut it). Tempo / flow effects are kept."""
    s = copy.deepcopy(song)
    cur = [0] * 4
    seen = {}
    for oi, p in enumerate(s.order):
        rows = s.patterns[p]
        if p in seen:
            continue
        seen[p] = oi
        for r in range(64):
            for c in range(4):
                cell = rows[r][c]
                if cell.instrument:
                    cur[c] = cell.instrument
                if cell.period:
                    ins = cell.instrument or cur[c]
                    if ins not in keep:
                        eff = (cell.effect, cell.param) if cell.effect in (0xB, 0xD, 0xF) else (0xC, 0)
                        rows[r][c] = pbsong.Cell(0, 0, eff[0], eff[1])
                    # a kept note with an offset effect keeps its cell as is
    return s


def render_group(song, keep, rate=44100, stereo=0.4, tail=1.0):
    r = render.render(filtered(song, keep), 'payback', rate=rate, stereo=stereo, tail=tail, stems=False)
    return r


def order_times(r):
    st = {}
    for ri in r.rows:
        if ri.row == 0 and ri.order_index not in st:
            st[ri.order_index] = ri.time
    return st
