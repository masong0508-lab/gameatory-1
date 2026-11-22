#!/usr/bin/env python3
"""Session f: soak - seeded random input in a level.

  python3 sessions/soak.py --disc DISC.cue --out runs/f [--syms payback.elf] [--from-state states/level_start.state]
                           [--game-seconds 600] [--max-frames 40000] [--seed 1] [--with-l1]

Runs until the level clock has counted --game-seconds x 30 ticks or --max-frames emulator frames are used, whichever comes
first (a build that runs far below full speed will not reach the game time: the session then says how far it got, as a FAIL).
Checks: the level clock never stops for long, no fault text, no rise of the fault counters, the picture is never black for
more than a second, how often the 3D city is missing."""
import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *

ACTIONS = [(['CROSS'], 5), (['CROSS', 'LEFT'], 2), (['CROSS', 'RIGHT'], 2), (['LEFT'], 1), (['RIGHT'], 1), (['SQUARE'], 1),
           (['R1'], 2), (['CROSS', 'R1'], 1), (['UP'], 1), (['DOWN'], 1), ([], 2)]
WATCH = ('ip_undef', 'ip_stat_undef', 'pad_fails', 'mc_err', 'pp_lost', 'sf3_retry', 'pp_nreset')
INFO = ('ip_enters', 'rom_miss_count', 'cold_loads', 'cd_sectors', 'st3_render', 'g_gframes', 'g_pres')


def extra(ap):
    ap.add_argument('--from-state', default=None)
    ap.add_argument('--game-seconds', type=float, default=600.0)
    ap.add_argument('--max-frames', type=int, default=40000)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--with-l1', action='store_true', help='also press L1 (enter/leave vehicles)')
    ap.add_argument('--stall-frames', type=int, default=6000, help='clock standing still this long counts as a stall')


def main():
    a = std_args(__doc__, extra)
    g = open_game(a, 'soak')
    ok = start_level(g, a)
    g.check(ok, 'level is running', g.level_report() if ok else g.text()[:100])
    if not ok:
        return g.finish('soak')
    g.snap('start')
    rng = random.Random(a.seed)
    acts = ACTIONS + ([(['L1'], 1)] if a.with_l1 else [])
    bag = [b for b, w in acts for _ in range(w)]
    c0, f0 = g.level_clock(), g.nrun
    cnt0 = g.counters()
    target = c0 + int(a.game_seconds * 30)
    sc = Scan(g, step=60)
    last_clock, last_change, stall_max, stall_at = c0, g.nrun, 0, None
    log = []
    worst_input = began = None
    next_snap = f0 + a.max_frames // 8
    while g.nrun - f0 < a.max_frames and g.level_clock() < target and g.level_end() == 0:
        b = rng.choice(bag)
        polls = rng.randint(1, 3)
        log.append((g.nrun, '+'.join(b) or '-', polls))
        p0 = g.polls()
        n = 0
        while n < 3000 * polls and g.nrun - f0 < a.max_frames:
            bm, was_bad = sc.bad_max, sc.bad > 0
            sc.run(60, b)
            n += 60
            if sc.bad > 0 and not was_bad:           # a stretch without the 3D view begins: remember what was pressed
                began = (g.nrun, log[-1], log[-2] if len(log) > 1 else None)
            if sc.bad_max > bm:
                worst_input = began
            c = g.level_clock()
            if c != last_clock:
                last_clock, last_change = c, g.nrun
            elif g.nrun - last_change > stall_max:
                stall_max, stall_at = g.nrun - last_change, g.nrun
            if p0 is not None and g.polls() >= p0 + polls:
                break
            if p0 is None and n >= 900 * polls:
                break
        if g.nrun >= next_snap:
            g.snap('clock %d' % g.level_clock())
            next_snap += a.max_frames // 8
        if stall_max > 4 * a.stall_frames:
            g.note('clock has not moved for %d frames: stopping' % stall_max)
            break
    g.release()
    g.snap('end')
    used, ticks = g.nrun - f0, g.level_clock() - c0
    cnt1 = g.counters()
    g.log('  soak: %d emulator frames (%.1f min console time), %d clock ticks (%.1f s game time), %d inputs, seed %d' % (used, used / g.fps / 60, ticks, ticks / 30.0, len(log), a.seed))
    g.check(ticks >= a.game_seconds * 30, 'soak covered %.0f s of game time' % a.game_seconds, 'reached %.1f s of game time in %d frames (%.1f min of console time): %.3f ticks per 60 frames, nominal 30' % (ticks / 30.0, used, used / g.fps / 60, 60.0 * ticks / max(1, used)))
    g.check(stall_max <= a.stall_frames, 'the level clock never stood still for more than %d frames' % a.stall_frames, 'longest stand-still %d frames (ending at frame %s)' % (stall_max, stall_at))
    g.check(sc.dark_max <= 60, 'the picture was never black for more than a second', 'longest black stretch %d frames (ending at frame %s)' % (sc.dark_max, sc.dark_at))
    if sc.bad_max > 60:
        sc.evidence('longest stretch without the 3D view')
    near = [] if sc.bad_from is None else ['f%d %s' % (f, l[:60]) for f, l in g.tty_when(*g.RENDERER_WORDS) if sc.bad_from - 6000 <= f <= (sc.bad_at or g.nrun) + 600]
    g.check(sc.bad_max <= 60, 'the 3D city was never missing for more than a second', 'longest stretch without it %d frames = %.0f s console time (ending at frame %s)%s; pictures sampled %s; renderer lines of the TTY around it: %s' % (
        sc.bad_max, sc.bad_max / g.fps, sc.bad_at, '' if worst_input is None else '; it began at frame %d, during the input (frame, buttons, polls) %s, the one before was %s' % worst_input, sc.states, near or 'none'))
    if cnt0:
        rise = {k: cnt1[k] - cnt0[k] for k in WATCH if k in cnt0 and cnt1[k] != cnt0[k]}
        g.check(not rise, 'fault counters did not rise (%s)' % ', '.join(k for k in WATCH if k in cnt0), rise or 'all unchanged')
        g.note('activity counters over the soak: %s' % {k: cnt1[k] - cnt0[k] for k in INFO if k in cnt0})
    else:
        g.note('no symbols: runtime counters not read')
    faults = g.tty_faults()
    g.check(not faults, 'no fault text on the TTY', faults[:3])
    conf = g.tty_when('CONFLICT')
    back = g.tty_when('re-init after overlay load', 'sf3_ok 1')
    g.check(not conf, 'the 3D renderer was never switched off by an overlay load', ['f%d %s' % (f, l[:70]) for f, l in conf[:3]] + (
        ['back: ' + '; '.join('f%d %s' % (f, l[:40]) for f, l in back if conf and f >= conf[0][0])[:200]] if conf else []))
    p = g.player()
    g.note('end state: %s' % g.level_report())
    open(os.path.join(g.out, 'inputs.txt'), 'w').write('\n'.join('f%d %s x%d polls' % x for x in log) + '\n')
    return g.finish('soak', extra={'frames': used, 'ticks': ticks, 'stall_max': stall_max, 'dark_max': sc.dark_max, 'no_city_max': sc.bad_max, 'states': sc.states, 'seed': a.seed})


if __name__ == '__main__':
    sys.exit(main())
