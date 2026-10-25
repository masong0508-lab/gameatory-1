"""Flash check (WCAG 2 general and red flash, every frame of the screen) over the grown Killing Zone: a drive along all of S3,
then through the Pit's gates and the three loops, then a walk out of one; stage2.md 9.2. Uses the playtest monitor (pp.fm_*), the measure flashcheck.py uses.

    SP=<harness folder> ROM=x.gba ELF=x.elf [OUT=<shots folder>] python3 tests/s2/flash_arena.py        (from stuntfox/)

Prints one line per drive and ALL OK or FAIL (exit status 1)."""
from arenah import *                                 # noqa: F401,F403

os.makedirs(OUT + '/flash', exist_ok=True)
pp.D = OUT                                           # (the monitor saves the big changes under D/flash)
start_grid(3)
base = e.save_state()
res = []


def drive(tag, x0, y0, hd, frames, keys=('A',)):
    fm_start(tag)
    put_car(x0, y0, hd)
    fm_break()
    run(frames, list(keys))
    res.append(fm_report())


# on foot first, as the standard captures start, then into a car at the first start
fm_start('kz_foot')
run(240)
for _ in range(4):
    run(60, ['UP'])
res.append(fm_report())
e.load_state(base)
assert jack2(), 'no car to take at the first start'
drive('kz_s3_east', 6.5, 53.5, 0, 1500)
drive('kz_s3_west', 121.5, 54.5, 2, 1500)
for name, (x, y, hd) in (('gn1_in', (65.5, 49.5, 1)), ('gs1_in', (65.5, 100.5, 3)), ('gw1_in', (45.5, 70.5, 0)), ('ge1_in', (95.5, 70.5, 2))):
    drive('kz_' + name, x, y, hd, 700)
drive('kz_pit', 70.5, 75.5, 0, 700)
drive('kz_loops', 8.5, 60.5, 0, 700)                 # through the three loops of the stunt park (the stripes once flashed)
snap('kz_flash_end')
bad = [r for r in res if r[0] > 3 or r[1] > 3]
print('ALL OK' if not bad else 'FAIL')
sys.exit(1 if bad else 0)
