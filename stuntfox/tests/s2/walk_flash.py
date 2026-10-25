"""Flash check (WCAG 2 general and red flash, every frame of the screen) over the space walks: a fall from the roofs, a long fall
that the ragdoll takes over from the figure, floating and flying with the pack (turns, climbs, the flame), the moon (a walk and a
jump), the way back aboard. Uses the playtest monitor (pp.fm_*), the measure flashcheck.py uses; stage2.md 9.2.

    SP=.. ROM=x.gba ELF=x.elf [OUT=<shots folder>] python3 tests/s2/walk_flash.py        (from stuntfox/)

Prints one line per session and ALL OK or FAIL (exit status 1)."""
import h
from h import *
import pp

OUT = os.environ.get('OUT', SP + '/v12/s2/walk_shots')
os.makedirs(OUT + '/flash', exist_ok=True)
pp.D = OUT
merged_state(e)
run(30)
board_now()
base = e.save_state()
res = []


def bail_at(alt, pack):
    e.load_state(base)
    run(2)
    mb(82, pack)
    mb(83, alt // 16)
    run(10)
    n = 0
    while not r8(S['bail']) and n < 120:
        e.run(1, ['SELECT'])
        n += 1


def session(tag, plan, alt, pack=1, start=None):
    bail_at(alt, pack)
    if start:
        start()
    fm_start(tag)
    fm_break()
    for frames, keys in plan:
        run(frames, list(keys))
    res.append(fm_report())


session('walk_fall_low', [(240, ())], 1500, 0)
session('walk_fall_high', [(1500, ())], 20000, 0)               # figure, then the ragdoll takes over at SPACE_LO
session('walk_float_pack', [(120, ()), (90, ('UP',)), (60, ('LEFT',)), (90, ('A',)), (60, ('B',)), (60, ('RIGHT', 'UP')), (90, ('L',))], 26000)
session('walk_band_pack', [(200, ('UP',)), (200, ('A',)), (100, ('LEFT',))], 18000)
session('walk_float_nopack', [(240, ()), (60, ('UP', 'A')), (120, ())], 26000, 0)
session('walk_moon', [(60, ()), (200, ('UP',)), (20, ('A',)), (150, ()), (100, ('RIGHT',)), (100, ('UP',)), (60, ('A', 'UP'))], 26000, 0,
        start=lambda: mb(85))
session('walk_back', [(60, ()), (90, ('SELECT',)), (120, ())], 26000)
bad = [r for r in res if r[0] > 3 or r[1] > 3]
print('ALL OK' if not bad else 'FAIL')
sys.exit(1 if bad else 0)
