"""Fox Station's frame rate: every room, idle and walking (the walker's worst case: the camera glides, the picture changes every
frame), with the talk panel up and with a terminal up, the way fps3.py counts it (the frames Stunt Fox draws, key_calls).
The brief's floor is 20 fps in a room.

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/fps_station.py        (from stuntfox/)
"""
import h
from h import *
import importlib.util
_sp = importlib.util.spec_from_file_location('stn_test', h.START + '/tests/s2/station.py')
T = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(T)

ck = Check()
K = S['key_calls']


def fps(n=240, keys=()):
    a = r32(K)
    run(n, list(keys))
    return (r32(K) - a) * 60.0 / n


T.dock()
run(60)
base = fps(240)
print('hangar idle %.1f' % base)
mb(32)
run(30)
worst = 99
rows = []
for rid in range(1, 9):
    mb(34, rid)
    run(20)
    idle = fps(180)
    mb(35, -300 if rid == 1 else -300), mb(36, 300 if rid != 1 else -300)
    walk = fps(180, ['RIGHT']) if rid != 1 else fps(180, ['LEFT', 'R'])
    mb(34, rid)
    run(10)
    mb(37, 1 if rid == 2 else rid - 1)           # a talk (crew by room), panel on
    run(20)
    talk = fps(120)
    mb(38)
    rows.append((rid, idle, walk, talk))
    worst = min(worst, idle, walk, talk)
    print('room %d idle %.1f walking %.1f talk %.1f' % (rid, idle, walk, talk))
for rid in (2, 4, 6):
    mb(34, rid)
    run(10)
    mb(39, [2, 6, 7][rid // 2 - 1])
    run(20)
    t = fps(120)
    worst = min(worst, t)
    print('room %d terminal %.1f' % (rid, t))
ck(worst >= 20, 'every room holds 20 fps or better', 'worst %.1f' % worst)
ck.done()
