#!/usr/bin/env python3
"""Speed of the build in a few scenes: guest frames, level clock ticks, presented frames, CD sectors and ROM cluster loads
per 60 emulator frames (one second of console time).  Needs --syms for everything but the level clock.

  python3 sessions/speed.py --disc DISC.cue --out runs/speed --syms payback.elf

The fast core is not cycle accurate: CPU time per instruction and CD latency are the core's model, not the console's."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *


def extra(ap):
    ap.add_argument('--frames', type=int, default=2400, help='emulator frames measured per scene')


def main():
    a = std_args(__doc__, extra)
    g = open_game(a, 'speed')
    rows = []

    def scene(name, buttons=(), mult=1):
        g._held = tuple(sorted(buttons))
        r = g.speed(a.frames * mult)
        g.run(1, buttons)
        g._held = ()
        r['scene'] = name
        r['frames'] = a.frames * mult
        rows.append(r)
        g.snap(name)
        g.log('  %-34s %s' % (name, '  '.join('%s %.3f' % (k.replace('_per_60', ''), v) for k, v in r.items() if k.endswith('_per_60'))))
        if r.get('top_clusters'):
            g.log('  %-34s ROM clusters fetched: %d different in %d frames; most often (offset:times) %s' % ('', r['clusters_seen'], r['frames'], ' '.join(r['top_clusters'])))

    ok = g.boot_to_language() is not None
    g.assist_off()
    scene('language screen')
    r = g.pad_language_to_title()
    if r.get('title') is None:
        g.check(False, 'title reached', r)
        return g.finish('speed')
    g.ready()
    scene('title menu')
    g.tap('CROSS', until=g.at_slots); g.ready()
    scene('slot list')
    g.tap('CROSS', until=lambda: g.at_name() or g.at_game_menu()); g.ready()
    if g.at_name():
        scene('name entry')
        g.tap('CROSS', until=g.at_game_menu); g.ready()
    scene('game menu')
    g.menu_goto(GM_RAMPAGE, GAME_MENU)
    g.tap('CROSS', until=g.at_rampage); g.ready()
    scene('rampage setup')
    g.menu_goto(START, [START, 'Cancel'])
    w = g.tap('CROSS', until=lambda: g.level_clock() > 0, wait=14000)
    g.check(w is not None, 'level reached', 'frame %d' % g.nrun)
    if w is not None:
        level_view(g)
        g.run(3000)                      # let the level's own loading settle
        scene('level, standing', mult=2)
        scene('level, walking (Cross)', ['CROSS'], mult=2)
        scene('level, walking and turning', ['CROSS', 'LEFT'], mult=2)
        g.tap('START', until=lambda: g.on('PAUSED'), wait=8000)
        g.settle(2)
        scene('pause menu')
    keys = ['gframes_per_60', 'clock_per_60', 'presents_per_60', 'frames3d_per_60', 'cd_sectors_per_60', 'rom_cluster_loads_per_60', 'cold_loads_per_60', 'interp_enters_per_60']
    print('scene                               ' + ' '.join('%12s' % k.replace('_per_60', '')[:12] for k in keys))
    for r in rows:
        print('%-35s ' % r['scene'] + ' '.join('%12s' % ('%.3f' % r[k] if k in r else '-') for k in keys))
    print('(per 60 emulator frames; full speed would be 60 guest frames and 30 clock ticks)')
    json.dump(rows, open(os.path.join(g.out, 'speed.json'), 'w'), indent=1)
    g.check(True, 'speed table written', os.path.join(g.out, 'speed.json'))
    return g.finish('speed', extra={'rows': rows}, sheet_cols=5)


if __name__ == '__main__':
    sys.exit(main())
