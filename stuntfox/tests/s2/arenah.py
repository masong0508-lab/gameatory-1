"""The small harness the arena probes share: the emulator on the ROM and ELF named by $ROM and $ELF (paths from the repo's
stuntfox/ folder), the earlier playtest helpers (jack2, put_car, tele_man, ents, goals, fm_start ...) pointed at them, and the
on-foot rampage states of any grid.

    SP=<harness folder> ROM=x.gba ELF=x.elf python3 tests/s2/<probe>.py       (run from the repo's stuntfox/ folder)
"""
import math
import os
import sys
import types

START = os.getcwd()
SP = os.environ['SP']
ROM, ELF = (os.path.join(START, os.environ[k]) for k in ('ROM', 'ELF'))
OUT = os.environ.get('OUT', START)
PLAY = SP + '/v12/s1play5'
sys.path[:0] = [SP + '/work', PLAY]
os.chdir(SP + '/work')
_src = open(PLAY + '/pp.py').read()
for _old, _new in (("ROM=SP+'/v12/s1fin/m.gba'", 'ROM=%r' % ROM), ("ELF=SP+'/v12/s1fin/m.elf'", 'ELF=%r' % ELF),
                   ("OUT=D+'/shots'", 'OUT=%r' % OUT)):
    assert _old in _src
    _src = _src.replace(_old, _new)
pp = types.ModuleType('pp')                      # (the helpers import it by name)
sys.modules['pp'] = pp
exec(compile(_src, 'pp.py', 'exec'), pp.__dict__)
from pp5 import *                                # noqa: E402,F401,F403  (ppx, pp: e, S, run, status, ents, epos, jack2, put_car ...)
import gridstate                                 # noqa: E402

os.makedirs(OUT, exist_ok=True)
CELL = 1024                                      # one cell in the car's units


def heading(dx, dy):
    """Payback's heading word (5760 to a turn, 0 along +y, a quarter turn along +x) for a step of (dx, dy)."""
    return int(math.atan2(dx, dy) / (2 * math.pi) * 5760) % 5760


def car_cell():
    c = car()
    return c[0] / CELL, c[2] / CELL


def start_grid(g):
    """On foot in grid g at its first rampage start."""
    gridstate.grid_state(e, g)
    e.run(2)
