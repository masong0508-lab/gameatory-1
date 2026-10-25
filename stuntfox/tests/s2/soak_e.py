"""A soak of the mission engine in the emulator: every demo mission on its map started, flown by the autopilot or failed,
over and over, with Payback's goal list the same after every one, no line on the ticker,
no goal or tag of ours left, and no call into Payback's ticker from our code (found by the caller's address at a breakpoint).

    ROM=out.gba ELF=build/merge/stuntfox-merge.elf python3 tests/s2/soak_e.py [rounds]      (from stuntfox/)
"""
import subprocess
import sys

import h
from h import *

ck = Check()
merged_state(e)
run(30)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 6
TICKER_FN = 0x08039870              # (Payback's ticker routine: no call may come from stage-2 code)
mine = []
for o in ('mission', 'hudline', 'msn_draw', 's2core'):
    path = os.path.join(START, 'build', 'merge', o + '.c.o')
    names = {l.split()[2] for l in subprocess.run(['llvm-nm', '--defined-only', path], capture_output=True, text=True).stdout.splitlines()
             if len(l.split()) == 3 and l.split()[1] in 'tT'}
    for l in subprocess.run(['llvm-nm', '-S', '--defined-only', ELF], capture_output=True, text=True).stdout.splitlines():
        p = l.split()
        if len(p) == 4 and p[3] in names:
            mine.append((int(p[0], 16) & ~1, (int(p[0], 16) & ~1) + int(p[1], 16)))


def gl():
    return [(g[0], g[1], g[4], g[5]) for g in goals() if not 0x5000 <= g[0] < 0x5100]


def ours():
    return [g for g in goals() if 0x5000 <= g[0] < 0x5100]


def play(mis, fail_at=None):
    """start `mis`, autopilot it to its end (or fail it after fail_at frames); the frames it took, -1 if it never ended."""
    mb(4, 0)
    assert mb(1, mis) == 1
    if fail_at is None:
        mb(4, 1)
    for f in range(0, 2400, 6):
        run(6)
        if fail_at is not None and f == fail_at:
            mb(3)
        if (mb(7) & 255) not in (2, 5):
            run(6)
            return f
    return -1


mb(10, 1)
bad = []
e.prof_on(bps=[TICKER_FN])
for rnd in range(N):
    for m, mp in ((0, 0), (1, 0), (2, 0), (3, 0), (4, 3), (5, 3)):
        if s2f()['map'] != mp:
            gstate(mp)
            run(30)
            mb(10, 1)
            if mp == 3:
                board_now()
        base = gl()
        d0, f0 = mb(8, 2), mb(8, 3)
        took = play(m, None if rnd % 2 == 0 else 30)
        mb(9)
        run(6)
        if took < 0 or gl() != base or ours() or mb(8, 9) != 0:
            bad.append((rnd, m, took, gl() == base, len(ours()), mb(8, 9)))
        if mp == 0 and m == 3:
            pass
_, _, _ = e.prof_off()
calls = list(e.bplr)
ours_calls = [lr for lr in calls if any(lo <= (lr & ~1) < hi for lo, hi in mine)]
ck(not bad, 'every mission of the demo, %d rounds, started and ended (autopilot or fail): Payback\'s goals as they were, nothing of ours left' % N, str(bad[:4]))
ck(not ours_calls, 'no call into Payback\'s ticker from stage-2 code (%d calls of its own in the soak, from other code)' % len(calls), str([hex(x) for x in ours_calls[:4]]))
ck.done()
