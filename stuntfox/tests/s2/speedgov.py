"""The Speed governor at Fastest, in the places that sit on a boundary: 90 seconds on foot (walking where it says) with
the governor free to use every row; Payback's tiles go off at row 8 and must not come and go (at most 2 changes of the
tiles in 90 s, at most 8 changes of row), the rows stay within the cap, and no frame count drifts out of the window.

    SP=<harness folder> python3 tests/s2/speedgov.py ROM ELF [scene ...]      (run from the repo's stuntfox/ folder; a scene is g3:walk)
"""
import os
import subprocess
import sys

START = os.getcwd()
SP = os.environ['SP']
rom, elf = (os.path.join(START, a) for a in sys.argv[1:3])
SCENES = sys.argv[3:] or ['g3:walk', 'g4:foot', 'g9:foot']
sys.path[:0] = [SP + '/work', SP + '/v12/s1play5']
os.chdir(SP + '/work')
from retro import Emu                      # noqa: E402
import gridstate                           # noqa: E402

gridstate.ST = os.environ.get('GRID_ST', gridstate.ST)
S = {l.split()[2]: int(l.split()[0], 16) for l in subprocess.run(['llvm-nm', elf], capture_output=True, text=True).stdout.splitlines()
     if len(l.split()) == 3}
bad = 0
for spec in SCENES:
    g, kind = spec[1:].split(':')
    e = Emu('gba', rom)
    gridstate.grid_state(e, int(g))
    e.run(60)
    cap = e.read(S['sp_cap'], 1)[0]
    e.write8(S['sp_cap'], 10)                       # Fastest, as the page sets it
    keys = ['A', 'UP'] if kind == 'walk' else []
    rows, tiles = [], []
    for f in range(5400):
        e.run(1, keys if f > 400 else [])
        if f % 10 == 0:
            rows.append(e.read(S['sp_lv'], 1)[0])
            tiles.append(int.from_bytes(e.read(S['tex_far'], 4), 'little', signed=True) > 1)
    nrow = sum(a != b for a, b in zip(rows, rows[1:]))
    ntile = sum(a != b for a, b in zip(tiles, tiles[1:]))
    ok = nrow <= 8 and ntile <= 2 and max(rows) <= 10
    bad += not ok
    print('%-5s %s  row changes %d  tile changes %d  deepest row %d  rows %s' % ('PASS' if ok else 'FAIL', spec, nrow, ntile, max(rows),
                                                                                   ''.join('%x' % x for x in rows[::30])))
print('ALL PASS' if not bad else '%d FAILED' % bad)
sys.exit(1 if bad else 0)
