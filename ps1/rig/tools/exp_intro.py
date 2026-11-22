#!/usr/bin/env python3
"""exp_intro.py: how long the intro video after the logos takes on the PS1 build, and whether Cross skips it.

  python3 tools/exp_intro.py --disc DISC.cue --syms ELF --out runs/exp_intro --from-state STATE [--branch idle|view|cross]

  --branch idle   STATE = a language-screen state: Cross, then no input until the title menu (or --max-frames)
  --branch view   STATE = a title-menu state: the intro entry, then no input until the title menu comes back
  --branch cross  STATE = a language-screen state: Cross, then Cross again --cross-after GBA frames after the third logo

Logs every --every emulator frames: GBA frame (runtime time base), guest frames, presents, ROM cluster fetches, the cluster
fetched last, DISPCNT, text.  On the GBA original (tools/gba_ref_intro.py) the video runs from the third logo until about
4170 GBA frames later, and A pressed during it brings the title menu."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *


def extra(ap):
    ap.add_argument('--from-state', required=True)
    ap.add_argument('--branch', default='idle', choices=('idle', 'view', 'cross'))
    ap.add_argument('--max-frames', type=int, default=90000)
    ap.add_argument('--every', type=int, default=1200)
    ap.add_argument('--cross-after', type=int, default=600)


def main():
    a = std_args(__doc__, extra)
    g = open_game(a, 'exp_intro_' + a.branch)
    g.load_state_file(a.from_state)
    g.note('started from %s' % a.from_state)
    g.snap('start')
    if a.branch in ('idle', 'cross'):
        g.check(g.at_language() or g.settle(2, 3000) is not None and g.at_language(), 'language screen', g.text()[:60])
        g.tap('CROSS', until=lambda: not g.at_language(), wait=4000, what='language screen to close')
        g.wait_until(lambda: g.dispcnt() == 0x404, 4000, step=2, what='logos')
    else:
        g.ready()
        h = g.title_open('intro')
        g.check(h is not None, 'intro entry opened', h)
    g0, f0 = g.gba_frame(), g.nrun
    g.log('  start: frame %d, GBA frame %d' % (f0, g0))
    m0 = g.v('rom_miss_count')
    crossed = None
    next_log = 0
    seen_clusters = {}
    while g.nrun - f0 < a.max_frames:
        if a.branch == 'cross' and crossed is None and g.gba_frame() >= g0 + 3 * 164 + a.cross_after:
            crossed = (g.nrun, g.gba_frame())
            g.log('  Cross at frame %d, GBA frame +%d' % (g.nrun, g.gba_frame() - g0))
            g.tap('CROSS')
        g.run(60)
        k = g.rom_cluster_last()
        if k is not None:
            seen_clusters[k] = seen_clusters.get(k, 0) + 1
        if g.at_title():
            break
        if g.nrun - f0 >= next_log:
            next_log += a.every
            g.log('  f%d +%d: GBA frame +%d, guest frames %s, presents %s, ROM fetches +%s, last cluster %s, DISPCNT %s, text %r' % (
                g.nrun, g.nrun - f0, g.gba_frame() - g0, g.gframes(), g.v('g_pres'), (g.v('rom_miss_count') or 0) - (m0 or 0),
                None if k is None else '%07x' % k, None if g.dispcnt() is None else hex(g.dispcnt()), g.text()[:40]))
            if (g.nrun - f0) % (a.every * 5) < 60:
                g.snap('+%d frames, GBA +%d' % (g.nrun - f0, g.gba_frame() - g0))
    ok = g.at_title()
    g.ready() if ok else None
    g.snap('end')
    g.check(ok, 'title menu reached', 'after %d emulator frames (%.0f s console time), GBA frame +%d, ROM cluster fetches %s; Cross: %s' % (
        g.nrun - f0, (g.nrun - f0) / g.fps, g.gba_frame() - g0, (g.v('rom_miss_count') or 0) - (m0 or 0), crossed))
    top = sorted(seen_clusters.items(), key=lambda kv: -kv[1])[:12]
    g.note('clusters seen last (sampled every 60 frames): %d different; most often %s' % (len(seen_clusters), ['%07x:%d' % kv for kv in top]))
    return g.finish('exp_intro_' + a.branch)


if __name__ == '__main__':
    sys.exit(main())
