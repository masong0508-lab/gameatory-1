#!/usr/bin/env python3
"""Session b: new game on a blank card, through the slot and mode menus, until the level clock runs and the 3D city is drawn.

  python3 sessions/new_game_to_level.py --disc DISC.cue --out runs/b [--path pad|assist] [--syms payback.elf] [--save-state]

--path pad (default): real pad presses only (the menu assist plan is blanked in RAM when --syms names it).
--path assist: no input at all; the build's own menu assist has to bring the level up.
The exact button script (emulator frame of every press and release) is printed and written to OUT/script.txt."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *


def extra(ap):
    ap.add_argument('--path', default='pad', choices=('pad', 'assist'))
    ap.add_argument('--save-state', action='store_true', help='write STATE_DIR/level_start.state')
    ap.add_argument('--max-frames', type=int, default=90000, help='frame budget of the assist path')


def level_checks(g, a, r0=None):
    t0 = g.nrun
    c0 = g.level_clock()
    w = g.wait_clock(6, 9000)
    g.check(w is not None, 'level clock keeps counting', '+%d ticks in %d frames (clock %d)' % (g.level_clock() - c0, g.nrun - t0, g.level_clock()))
    if 'st3_render' in g.sym:
        g.wait_until(lambda: g.v('st3_render') >= 2, 9000, step=4, what='second 3D frame')
        g.check(g.v('st3_render') >= 1 and g.v('sf3_ok') == 1, '3D renderer is up and has drawn', 'sf3_ok %s, 3D frames %s' % (g.v('sf3_ok'), g.v('st3_render')))
    else:
        g.run(3000)
    okv, det = level_view(g, r0)
    im = g.snap('level start')
    l, w_, c = measures(im)
    g.check(okv, '3D city is on screen', '%s; picture: %.0f %% of the pixels lit, %.0f %% coloured, %.0f %% white' % (det, 100 * l, 100 * c, 100 * w_))
    p = g.player()
    g.check(p is not None and p['kind'] == 'person', 'player entity exists and is on foot', g.level_report())
    g.check(g.map_id() == 0 and g.lives() == 3, 'map 0, three lives', 'map %d lives %d' % (g.map_id(), g.lives()))
    g.note('HUD text: %s' % (' | '.join(sorted(set(g.screen())))[:120] or '(none)'))
    sp = g.speed(1800)
    g.note('speed at level start, per 60 emulator frames: %s' % {k: (round(v, 3) if isinstance(v, float) else v) for k, v in sp.items()})
    g.snap('level +1800')
    return sp


def main():
    a = std_args(__doc__, extra)
    g = open_game(a, 'new_game_to_level')
    f = g.boot_to_language()
    g.snap('language')
    g.check(f is not None, 'language screen drawn', 'frame %s' % f)
    steps = {}
    if a.path == 'pad':
        off = g.assist_off()
        g.note('menu assist: %s' % ('plan blanked in RAM by the rig (%s)' % ', '.join(off) if off else 'no plan named by the symbols: the build\'s assist (if any) stays active'))
        r = g.pad_language_to_title()
        steps.update(r)
        g.check(r.get('title') is not None, 'title menu reached', r)
        if r.get('title') is not None:
            g.ready()
            g.snap('title')
            c0 = g.card_now().summary() if g.card_mode != 'none' else None
            r2 = g.pad_title_to_level()
            steps.update({k: v for k, v in r2.items() if k != 'title'})
            for k in ('slots', 'name', 'game_menu', 'rampage'):
                if k in r2:
                    g.log('  %s screen at frame %d' % (k, r2[k]))
            g.check('slots' in r2, 'the start entry opens the slot list', r2.get('slot_lines'))
            g.check('game_menu' in r2, 'slot (and name entry) lead to the game menu', 'name entry shown: %s' % ('name' in r2))
            g.check('rampage' in r2, 'the rampage entry of the game menu opens its setup page', r2.get('rampage_lines'))
            g.check(r2['level'] is not None, 'level clock runs', 'frame %s' % r2['level'])
    else:
        g.note('no input from here: the build\'s menu assist has to do it')
        w = g.assist_wait(lambda: g.level_clock() > 0, a.max_frames, 'level clock')
        steps['level'] = g.nrun if w is not None else None
        g.check(w is not None, 'level clock runs with no input (menu assist)', 'frame %d, GBA frame %s' % (g.nrun, g.gba_frame()))
    sp = None
    if steps.get('level') is not None:
        g.log('LEVEL clock first seen at emulator frame %d (%.0f s of console time at %.2f fps)' % (steps['level'], steps['level'] / g.fps, g.fps))
        sp = level_checks(g, a, steps.get('st3_before'))
        if a.save_state:
            spath = os.path.join(a.state_dir, 'level_start.state' if a.path == 'pad' else 'level_start_assist.state')
            m = g.save_state_file(spath, 'rampage level on map 0 just started, %s path' % a.path)
            g.check(m is not None, 'level state saved and verified by a reload', spath)
    else:
        g.snap('stuck')
        g.note('stuck on: %s' % (g.text()[:160] or '(no text)'))
    if g.card_mode != 'none':
        c = g.card_now()
        g.note('memory card now: %s' % c.summary())
    faults = g.tty_faults()
    g.check(not faults, 'no fault text on the TTY', faults[:3])
    print('---- button script (emulator frame: buttons held from then on)')
    print(g.script_text() or '(no input)')
    print('----')
    return g.finish('new_game_to_level', extra={'path': a.path, 'steps': steps, 'speed': sp, 'script': g.script,
                                                'end_frame': g.nrun, 'end_ram_sha1': g.ram_sha1()})


if __name__ == '__main__':
    sys.exit(main())
