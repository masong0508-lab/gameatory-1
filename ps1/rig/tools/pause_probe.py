#!/usr/bin/env python3
"""Probe of the pause menu, from a level state: Start until PAUSED is drawn, then every complete 2D frame the rig sees
(emulator frame, guest frame, presents, entries by kind, text) for --watch frames, the resume entry with Cross, the same
log for --watch frames more, then pictures at growing intervals up to --after frames, to see how long the menu stays
on the picture and when the HUD comes back.  Writes the usual result.json, tty.log and sheet.png.

  python3 tools/pause_probe.py --disc D --syms S --from-state states/level_start.state --out runs/pause_probe
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *


def extra(ap):
    ap.add_argument('--from-state', required=True)
    ap.add_argument('--watch', type=int, default=3000)
    ap.add_argument('--after', type=int, default=40000)


def log_frames(g, frames, tag):
    fd, f0, n = g.frames_drawn, g.nrun, 0
    while g.nrun - f0 < frames:
        g.run(2)
        if g.frames_drawn != fd:
            fd = g.frames_drawn
            f, ent = g._rframes[-1]
            kinds = {}
            for e in ent:
                kinds[e[1]] = kinds.get(e[1], 0) + 1
            t = ' | '.join(l['text'] for l in g.text_lines(ent))
            n += 1
            if n <= 40:
                g.log('  %s f%d gf %s pres %s: complete 2D frame, %d entries by kind %s, text %r; text() now %r' % (
                    tag, f, g.gframes(), g.v('g_pres'), len(ent), dict(sorted(kinds.items())), t[:70], g.text()[:40]))
    g.log('  %s: %d complete 2D frames in %d emulator frames; text() at the end %r' % (tag, n, frames, g.text()[:80]))
    return n


def main():
    a = std_args(__doc__, extra)
    g = open_game(a, 'pause_probe')
    if not start_level(g, a):
        g.check(False, 'level running', g.where())
        return g.finish('pause_probe')
    g.run(600)
    g.snap('level')
    seen = []

    def paused():
        t = g.text()
        if 'paused' in t.lower():
            seen.append((g.nrun, t))
            return True
        return False
    f_start = g.nrun
    w = g.tap('START', until=paused, wait=6000, what='pause menu')
    g.log('START at f%d: PAUSED first seen at f%s, text then %r' % (f_start, seen[0][0] if seen else None, seen[0][1][:100] if seen else ''))
    g.check(bool(seen) and contains(seen[0][1], PAUSE_RESUME), 'pause menu text drawn with its entries', seen[0][1][:90] if seen else 'never')
    g.snap('paused')
    n1 = log_frames(g, a.watch, 'paused')
    s = g.settle(2, 4000)
    g.log('  settle(2) after that: %s frames; text() %r' % (s, g.text()[:80]))
    g.snap('paused + %d' % (g.nrun - f_start))
    sel = g.menu_goto(PAUSE_RESUME, PAUSE_MENU)
    g.log('  menu_goto resume entry: %s taps' % sel)
    f_x = g.nrun
    g.tap('CROSS', until=lambda: g.level_clock() > 0 and not g.on('PAUSED'), wait=6000, what='pause menu to close')
    c0 = g.level_clock()
    n2 = 0
    for k in range(a.watch // 300):         # a picture every 300 frames: is the menu still on it, is the HUD back
        n2 += log_frames(g, 300, 'resumed')
        im = g.snap('Cross +%d' % (g.nrun - f_x))
        g.log('  Cross +%d: view %s, text() %r, clock %d, gf %s, presents %s' % (g.nrun - f_x, view_state(im), g.text()[:60], g.level_clock(), g.gframes(), g.v('g_pres')))
    g.log('  level clock %d at the Cross, %d now' % (c0, g.level_clock()))
    t = a.watch
    while g.nrun - f_x < a.after:
        step = max(500, t)
        g.run(step)
        t += step
        im = g.snap('Cross +%d' % (g.nrun - f_x))
        g.log('  Cross +%d: view %s, text() %r, clock %d, gf %s, presents %s' % (g.nrun - f_x, view_state(im), g.text()[:60], g.level_clock(), g.gframes(), g.v('g_pres')))
    g.note('complete 2D frames seen: %d in %d frames while paused, %d in %d frames after the Cross' % (n1, a.watch, n2, a.watch))
    return g.finish('pause_probe')


if __name__ == '__main__':
    sys.exit(main())
