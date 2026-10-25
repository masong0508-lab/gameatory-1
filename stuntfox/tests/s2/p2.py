"""Probe P2: Payback's banner by number (0x0807a684) is called from 72 places, "Mission complete!" (0x7e6) is the one a
phone mission's completion shows, and the build's veneer in front of it counts exactly those.
  static   every bl to 0x0807a684 in the ROM image, and the number each one loads
  dynamic  a phone answered on map 0: its mission is completed (the score it asks for, written to the man's record), then a second one is left to
           time out; s2_phones goes 0 -> 1 -> 1, and HK_BANNER counts both banners

    SP=.. PAYBACK_ROM=.. ROM=x.gba ELF=x.elf python3 tests/s2/p2.py      (from stuntfox/)
"""
import collections
import struct
import h
from h import *
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

ck = Check()
G = 0x08000000
BANNER = 0x0807a684
rom = open(os.environ['PAYBACK_ROM'], 'rb').read()


def bl(site):
    h1, h2 = struct.unpack_from('<HH', rom, site - G)
    if (h1 & 0xf800) != 0xf000 or (h2 & 0xf800) != 0xf800:
        return None
    off = (h1 & 0x7ff) << 12 | (h2 & 0x7ff) << 1
    off -= (1 << 23) if off & (1 << 22) else 0
    return site + 4 + off


sites = [a for a in range(G, G + 0x120000, 2) if bl(a) == BANNER]
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
arg = collections.Counter()
for s in sites:
    val = 'computed'
    for back in range(2, 18, 2):                    # the nearest instruction before the bl that sets r0
        a = s - back
        ins = list(md.disasm(rom[a - G:a - G + 2], a))
        if not ins:
            continue
        i = ins[0]
        if i.op_str.startswith('r0,') or i.op_str.startswith('r0 '):
            if i.mnemonic == 'movs' and '#' in i.op_str:
                val = int(i.op_str.split('#')[1], 0)
            elif i.mnemonic == 'ldr' and 'pc' in i.op_str:
                disp = int(i.op_str.split('#')[1].rstrip(']'), 0)
                val = struct.unpack_from('<I', rom, ((a + 4) & ~3) + disp - G)[0]
            break
    arg[val] += 1
ck(len(sites) == 72, 'static: 72 calls of the banner by number', '%d' % len(sites))
ck(arg[0x7e6] > 0 and arg[0x7ec] > 0, 'static: the numbers loaded at the calls', 'Mission complete 0x7e6 x%d, 0x7ec x%d, other %d (of which computed %d)' % (
    arg[0x7e6], arg[0x7ec], len(sites) - arg[0x7e6] - arg[0x7ec], arg['computed']))
print('   by number:', [(k if isinstance(k, str) else hex(k), v) for k, v in arg.most_common(10)])


def phones():
    return u16(S['s2_phones'])


gstate(0)
run(60)
START = e.save_state()


def answer(want=7):
    """Answer map 0's phone (the man stands next to it, as a player does) and look at the mission it gives: they are drawn
    by Payback's random numbers, so wait a frame more before each try until it is one that is quick to finish or to fail
    (7: get a score in 74 seconds)."""
    for skew in range(24):
        e.load_state(START)
        run(skew)
        ph = [x for x in goals() if x[1] == 1]
        px, py = ph[0][2], ph[0][3]
        s0 = e.save_state()
        for side, (dx, dy, hd) in {'south': (0, 1.5, 2880), 'east': (1.5, 0, 4320), 'west': (-1.5, 0, 1440), 'north': (0, -1.5, 0)}.items():
            e.load_state(s0)
            if col_top(int(px + dx), int(py + dy)) >= 0x120:
                continue
            tele_man(px + dx, py + dy)
            set_heading(hd)
            e.run(5)
            for _ in range(10):
                e.run(15, ['A'])
                if r32(0x02007134) != 0:
                    break
            if r32(0x02007134) == want:
                return side
    return None


side = answer()
ck(side is not None and r32(0x02007134) == 7, 'a phone on map 0 answered, its mission one that asks for a score', 'from the %s, mission %d' % (side, r32(0x02007134)))
p0, b0 = phones(), hooks()['BANNER']
tgt = [g for g in goals() if g[1] == 10][0][2]      # (the score it asks for: 37,000, 47,000 ...)
e.write32(PL + 0x90, tgt + 2000)
for _ in range(10):
    run(30)
    if r32(0x02007134) == 0:
        break
run(60)
p1, b1 = phones(), hooks()['BANNER']
ck(r32(0x02007134) == 0 and p1 - p0 == 1 and b1 - b0 >= 1, 'dynamic: the mission completed: s2_phones counted it once, the veneer saw the banner', 's2_phones %d -> %d, banners +%d' % (p0, p1, b1 - b0))
run(300)
ck(phones() == p1, 'and nothing else counts later', 's2_phones %d' % phones())
side = answer()
p2, b2 = phones(), hooks()['BANNER']
n = 0
while r32(0x02007134) != 0 and n < 9000:           # (74 seconds, then the mission is over)
    run(60)
    n += 60
run(120)
p3, b3 = phones(), hooks()['BANNER']
ck(side is not None and r32(0x02007134) == 0 and p3 == p2 and b3 - b2 >= 1, 'dynamic: a mission left to time out: the veneer saw its banner, s2_phones did not move',
   'after %d frames: s2_phones %d -> %d, banners +%d' % (n, p2, p3, b3 - b2))
ck.done()
