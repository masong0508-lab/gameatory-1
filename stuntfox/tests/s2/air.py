"""EV_LAND's airborne distance (merge.c air_run) belongs to one flight: getting into a car or the Arwing starts it at nothing,
whatever the last vehicle left in it.

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/air.py      (from stuntfox/)
"""
import h
from h import *

ck = Check()
merged_state(e)
run(100)
base = e.save_state()
A = S['air_run']


def air():
    return struct.unpack('<H', e.read(A, 2))[0]


def poke(v):
    e.write8(A, v & 255), e.write8(A + 1, v >> 8)


poke(60000)
run(2)
ck(air() >= 59000, 'the counter holds a leftover on foot', 'air_run %d' % air())
c = get_car()
ck(c is not None and modename() == 'DRIVE', 'into a car')
ck(air() < 100, 'a car starts it at nothing', 'air_run %d' % air())
e.load_state(base)
run(2)
poke(60000)
ck(board_now() == 'FLY', 'into the Arwing')
ck(air() < 3000, 'the Arwing starts it at nothing (it has flown a little since)', 'air_run %d' % air())
ck.done()
