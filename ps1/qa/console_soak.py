#!/usr/bin/env python3
"""A PS1 30-minute *emulated-console-time* soak, not 30 min of GBA clock.

No screenshot/game log is public. This adds a distinct, honest time gate: the
standard rig soak stops when its GAME clock reaches a target, which cannot
certify a minimum console-frame duration on a faster or slower build.
"""
from __future__ import annotations
import os
from pathlib import Path
import random
import sys
RIG = str(Path(__file__).resolve().parents[1] / 'rig')
sys.path.insert(0, RIG)
from payback import *  # noqa
from sessions.soak import ACTIONS, WATCH, INFO  # noqa


def extra(ap):
    ap.add_argument('--from-state', default=None)
    ap.add_argument('--console-frames', type=int, default=108000,
                    help='minimum emulated frames; 108000 is ~30 min at ~60Hz')
    ap.add_argument('--min-game-seconds', type=float, default=600.0,
                    help='independent minimum guest game time, default 10 min')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--step', type=int, default=60)
    ap.add_argument('--stall-frames', type=int, default=6000)


def main():
    a = std_args(__doc__, extra)
    if a.console_frames < 1 or a.step < 1 or a.min_game_seconds < 0 or a.stall_frames < 1:
        raise SystemExit('Invalid console-soak limits')
    g = open_game(a, 'console_soak')
    ok = start_level(g, a)
    g.check(ok, 'level starts for emulated-console-time soak', g.level_report() if ok else '')
    if not ok:
        return g.finish('console_soak')
    g.snap('console_soak_start')
    rng = random.Random(a.seed)
    bag = [buttons for buttons, n in ACTIONS for _ in range(n)]
    start_frame, start_clock = g.nrun, g.level_clock()
    previous_clock = start_clock
    last_clock_change = g.nrun
    stall_max = 0
    snap_step = max(a.step, a.console_frames // 8)
    next_snap = start_frame + snap_step
    initial = g.counters()
    scan = Scan(g, step=a.step)
    stopped_by_end = False
    while g.nrun - start_frame < a.console_frames:
        if g.level_end() != 0:
            stopped_by_end = True
            break
        held = rng.choice(bag)
        n = min(a.step, a.console_frames - (g.nrun - start_frame))
        scan.run(n, held)
        clock = g.level_clock()
        if clock != previous_clock:
            previous_clock, last_clock_change = clock, g.nrun
        stall_max = max(stall_max, g.nrun - last_clock_change)
        if g.nrun >= next_snap:
            g.snap('emulated_frame_%d' % (g.nrun - start_frame))
            next_snap += snap_step
        if stall_max > 4*a.stall_frames:
            break
    g.release()
    used, ticks = g.nrun - start_frame, g.level_clock() - start_clock
    g.snap('console_soak_end')
    g.check(used >= a.console_frames, 'console soak covered requested emulator frames',
            {'requested':a.console_frames,'observed':used})
    g.check(ticks >= a.min_game_seconds*30, 'guest clock advances during console soak',
            {'observed_ticks':ticks, 'minimum_ticks':int(a.min_game_seconds*30)})
    g.check(not stopped_by_end, 'level did not end unexpectedly during console soak')
    g.check(stall_max <= a.stall_frames, 'guest clock never stalled beyond frame limit', stall_max)
    g.check(scan.dark_max <= 60, 'no long all-black frame interval', scan.dark_max)
    g.check(scan.bad_max <= 60, '3D city remains visible during soak', scan.bad_max)
    after=g.counters()
    if initial and after:
        rising={k:after[k]-initial[k] for k in WATCH if k in initial and k in after and after[k]!=initial[k]}
        g.check(not rising, 'fault counters unchanged during console soak', rising)
    g.check(not g.tty_faults(), 'no guest runtime faults during console soak', len(g.tty_faults()))
    g.check(not g.tty_when('CONFLICT'), 'no runtime overlay conflict during console soak',
            len(g.tty_when('CONFLICT')))
    return g.finish('console_soak', extra={
        'emulated_console_frames':used, 'emulated_console_seconds':round(used/g.fps,2),
        'game_seconds':round(ticks/30,2), 'seed':a.seed,
        'max_dark_frames':scan.dark_max,'max_not_city_frames':scan.bad_max,
        'stall_max_frames':stall_max, 'terminated_by_level_end':stopped_by_end,
    })


if __name__ == '__main__':
    sys.exit(main())