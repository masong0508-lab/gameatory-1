"""holes2's measure (pixels no polygon painted: the back page is filled with a marker colour before every frame and what is still marker
colour when the page is shown is a hole) over the space walks' own scenes: the fall over the city, floating, the moon, flying past
a ring and the rocks.

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/walk_holes.py        (from stuntfox/)
"""
import ctypes as C

import h
from h import *

merged_state(e)
run(30)
board_now()
base = e.save_state()
vram = e.mptr(6, 0x18000)
M = 254
prev = None
ck = Check()


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


def go(name, n, keys):
    global prev
    tot = big = fr = worst = 0
    prev = None
    for f in range(n):
        page = (e.read(0x04000000, 2)[0] >> 4) & 1
        if page != prev:
            shown = 0 if page == 0 else 0xA000
            if prev is not None and f > 3:
                buf = bytes(vram[shown:shown + 0x9600])
                cnt = buf.count(M)
                tot += cnt
                fr += 1
                worst = max(worst, cnt)
                if cnt > 500:
                    big += 1
            C.memset(C.addressof(vram) + (0xA000 if page == 0 else 0), M, 0x9600)
            prev = page
        e.run(1, keys(f))
    print('%-34s frames %4d  average hole pixels %4d  worst frame %5d  frames over 500: %d' % (name, fr, tot // max(fr, 1), worst, big), flush=True)
    return tot // max(fr, 1), big


res = []
bail_at(5000, 0)
res.append(go('falling over the city (5000)', 300, lambda f: []))
bail_at(26000, 1)
res.append(go('floating, flying with the pack', 500, lambda f: ['UP', 'LEFT'] if f % 200 < 80 else ['A'] if f % 200 < 140 else []))
bail_at(26000, 0)
mb(85)
run(20)
res.append(go('moon: walking and jumping', 500, lambda f: ['UP'] if f % 150 < 100 else ['A', 'UP']))
bail_at(26000, 1)
mb(88, 0)
run(10)
res.append(go('beside a ring', 200, lambda f: []))
ck(all(b == 0 for a, b in res), 'no frame has more than 500 hole pixels', str(res))
ck.done()
