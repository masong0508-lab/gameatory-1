"""The jet pack is bought at the Fox Station shipyard: the hangar text, too poor, the confirm, the purchase, "already fitted", and that
it is kept with the other upgrades: in the progress copy (word 3, bit 23) and through a level change. (A true power cycle clears all the
upgrades alike: they live in RAM in this build, the EEPROM save is another package's.) Screenshots under $SHOTS.

    SP=.. ROM=x.gba ELF=x.elf [SHOTS=dir] python3 tests/s2/walk_shop.py        (from stuntfox/)
"""
import h
from h import *

SHOTS = os.environ.get('SHOTS', SP + '/v12/s2/walk_shots')
os.makedirs(SHOTS, exist_ok=True)
ck = Check()


def shot(name):
    e.frame.save('%s/shop_%s.png' % (SHOTS, name))


def pack_bit():
    return words()['mirror'][3] >> 23 & 1


def pack_on():
    return mb(81) >> 5 & 1


def htap(k, after=24):                   # (the hangar polls the pad about every 5 frames: a tap must outlast one)
    tap(k, hold=8, after=after)


merged_state(e)
run(5)
run(90, ['SELECT'])
run(30)
B = S['ship']


def setv(a, v):
    for i in range(3):
        e.write32(a + 4 * i, int(v[i]) & 0xffffffff)


sx, sy, sz = [r32(S['station_pos'] + 4 * i) for i in range(3)]
setv(B, ((sx + 3000) << 8, (sy - 140) << 8, (sz + 9000) << 8))
setv(B + 12, (0, 0, -(90 << 8)))
setv(B + 24, (-16384, 0, 0))
setv(B + 36, (0, 16384, 0))
setv(B + 48, (0, 0, -16384))
run(20, ['A'])
run(40, ['SELECT'])
for k in range(30):
    run(30)
    if r32(S['sg_state']) == 2:
        break
ck(r32(S['sg_state']) == 2, 'the Arwing docks at Fox Station')
run(60)
shot('hangar_before')
c0 = mb(89, 0)
ck(not pack_on() and not pack_bit(), 'no jet pack to start with', 'credits %d' % c0)
htap('DOWN')
htap('A', after=40)                      # SHIPYARD
shot('yard')
for _ in range(5):
    htap('DOWN')
shot('yard_pack_row')
htap('A', after=40)                      # (too poor: 900 CR against what we have)
htap('A', after=40)
shot('yard_poor')
ck(mb(89, 0) == c0 and not pack_on(), 'too few credits: nothing bought', 'credits %d' % mb(89, 0))
mb(89, 10)
c1 = mb(89, 0)
htap('A', after=40)
shot('yard_confirm')
ck(mb(89, 0) == c1 and not pack_on(), 'with enough credits the first A asks first (A AGAIN: BUY, B: NO)')
htap('B', after=30)
ck(mb(89, 0) == c1 and not pack_on(), 'B says no, nothing is spent')
htap('A', after=40)
htap('A', after=40)
shot('yard_bought')
ck(mb(89, 0) == c1 - 900 and pack_on(), 'the second A buys it for 900 CR', 'credits %d -> %d' % (c1, mb(89, 0)))
ck(pack_bit() == 1, 'it is in the progress copy (word 3, bit 23)', 'word3 %08x' % words()['mirror'][3])
htap('A', after=40)
shot('yard_again')
ck(mb(89, 0) == c1 - 900, 'a second try costs nothing ("already fitted")')
htap('B', after=40)
shot('hangar_after')
ck(True, 'hangar text shows JET PACK FITTED (see the screenshots)')
w = words()
run(60)
ck(words()['mirror'][3] == w['mirror'][3], 'the other upgrades\' bits are untouched by it', 'word3 %08x' % w['mirror'][3])

# a level change: the target reached, SELECT, the next map
mb(82, 1)
e.write32(PL + 0x90, 9999999)
for _ in range(10):
    run(30)
    if r16(0x02001e08) == 3:
        break
run(6, ['SELECT'])
for _ in range(25):
    run(45)
    if grid() == 1 and u32(0x02001e00) > 0:
        break
run(120)
ck(grid() == 1 or r16(0x02001e08) != 3, 'a level change happened (the target was reached)', 'map %d' % grid())
ck(pack_on() and pack_bit(), 'the jet pack is still his on the next map')

ck.done()
