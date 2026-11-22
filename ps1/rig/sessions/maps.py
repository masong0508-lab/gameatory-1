#!/usr/bin/env python3
"""Session d: step through all 11 maps with R2 (next) and L2 (previous), one start-view picture per map.

  python3 sessions/maps.py --disc DISC.cue --out runs/d [--syms payback.elf] [--from-state states/level_start.state]

The map number comes from the runtime's TTY line 'MAPCHANGE to N rc R ...' (and symbol sf3_map_cur when --syms is given)."""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *


def extra(ap):
    ap.add_argument('--from-state', default=None)
    ap.add_argument('--step-frames', type=int, default=14000, help='budget per map change')


def map_lines(g):
    return [l for l in g.tty().splitlines() if l.startswith('MAPCHANGE to')]


def change(g, button, budget):
    """Click R2/L2 and wait for the runtime's MAPCHANGE line.  Returns (line or None, frames)."""
    n0, f0 = len(map_lines(g)), g.nrun
    g.tap(button, until=lambda: len(map_lines(g)) > n0, wait=budget)
    ls = map_lines(g)
    return (ls[-1] if len(ls) > n0 else None), g.nrun - f0, g.v('st3_render')


def main():
    a = std_args(__doc__, extra)
    g = open_game(a, 'maps')
    ok = start_level(g, a)
    g.check(ok, 'level is running', g.level_report() if ok else g.text()[:100])
    if not ok:
        return g.finish('maps')
    im_prev = g.snap('map 0 (level start)')
    g.check(view_state(im_prev) == 'city', 'map 0: 3D city on screen', 'sf3_map_cur %s' % g.v('sf3_map_cur'))
    c_start = g.level_clock()
    rows = []
    seq = [('R2', (i + 1) % MAPS) for i in range(MAPS)] + [('L2', MAPS - 1), ('R2', 0)]
    for button, want in seq:
        line, used, r0 = change(g, button, a.step_frames)
        m = re.match(r'MAPCHANGE to (\d+) rc (-?\d+) cd sectors (\d+) hlines (\d+) start (-?\d+) (-?\d+) (-?\d+)', line or '')
        if not m:
            im = g.snap('%s: no map change' % button)
            g.check(False, '%s changes to map %d' % (button, want), 'no MAPCHANGE line within %d frames; sf3_map_cur %s; CPU %s' % (used, g.v('sf3_map_cur'), g.cpu_where(4, 9)))
            if g.stalled(3000):
                g.note('the game stands still: stopping the tour')
                break
            continue
        got, rc, sectors = int(m.group(1)), int(m.group(2)), int(m.group(3))
        okv, det = level_view(g, r0)          # two 3D frames of the new map rendered and presented
        im = g.snap('map %d start (%s)' % (got, button))
        vs = view_state(im)
        d = diff(im, im_prev)
        rows.append({'button': button, 'map': got, 'rc': rc, 'cd_sectors': sectors, 'frames_to_line': used, 'view': vs, 'diff_prev': round(d, 1), 'line': line})
        g.check(got == want and rc == 0, '%s changes to map %d' % (button, want), '%s  (%d frames after the press)' % (line[:110], used))
        g.check(okv and d > 3.0, 'map %d: start view drawn and different from the map before' % got, '%s; picture difference to the map before %.1f' % (det, d))
        im_prev = im
    g.check(g.level_clock() > c_start, 'the level clock kept running during the tour', 'clock %d > %d' % (c_start, g.level_clock()))
    faults = g.tty_faults()
    g.check(not faults, 'no fault text on the TTY', faults[:3])
    return g.finish('maps', extra={'maps': rows}, sheet_cols=5)


if __name__ == '__main__':
    sys.exit(main())
