"""The frame rate of the space walks' own scenes (fps3's way: game frames a second over 300 frames, Payback's key reads counted):
the Arwing at the same height as a reference, then floating, flying with the pack, the moon (standing, walking, with the rocks and
rings in view) and the figure falling over the city.

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/walk_fps.py        (from stuntfox/)
"""
import h
from h import *

merged_state(e)
run(30)
board_now()
base = e.save_state()
KC = S['key_calls']


def fps(frames=300, keys=()):
    a = r32(KC)
    e.run(frames, list(keys))
    return (r32(KC) - a) * 60 / frames


def bail_at(alt, pack=1):
    e.load_state(base)
    run(2)
    mb(82, pack)
    mb(83, alt // 16)
    run(10)
    n = 0
    while not r8(S['bail']) and n < 120:
        e.run(1, ['SELECT'])
        n += 1
    run(30)


def line(name, v):
    print('%-34s %5.1f   %s' % (name, sum(v) / len(v), ' '.join('%.1f' % x for x in v)), flush=True)


e.load_state(base)
run(2)
mb(83, 26000 // 16)
run(60)
line('Arwing at 26000 (reference)', [fps() for _ in range(3)])
bail_at(26000)
line('floating, pack, still', [fps() for _ in range(3)])
line('flying, pack (D-pad, turning)', [fps(300, ['UP', 'LEFT']) for _ in range(3)])
bail_at(26000, 0)
mb(85)
run(60)
line('moon: standing', [fps() for _ in range(3)])
line('moon: walking', [fps(300, ['UP']) for _ in range(3)])
bail_at(26000, 1)
mb(88, 0)
run(30)
line('beside a ring (beacon A)', [fps() for _ in range(3)])
bail_at(26000, 1)
mb(85)
run(30)
run(10, ['A'])
line('moon: jumping up for the rocks', [fps(300, ['A']) for _ in range(2)])
bail_at(5000, 0)
line('falling over the city (from 5000)', [fps(60) for _ in range(3)])
bail_at(14000, 0)
line('falling over the city (from 14000)', [fps(150) for _ in range(3)])
