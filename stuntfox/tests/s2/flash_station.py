"""Flash check (WCAG 2 general and red flash, every frame of the screen) in Fox Station: a ten-second walk across the hub's camera
borders and ten seconds back, a walker wobbling over a border for ten seconds, every door, a talk, a terminal and the quick menu
in each room, and the way out to the hangar; the playtest monitor (pp.fm_*) is the measure flashcheck.py uses.

    SP=.. ROM=x.gba ELF=x.elf [SHOTS=dir] python3 tests/s2/flash_station.py        (from stuntfox/)
Prints one line a session and ALL OK or FAIL (exit status 1)."""
import importlib.util
import h
from h import *

SHOTS = os.environ.get('SHOTS', SP + '/v12/s2/S/shots')
os.makedirs(SHOTS + '/flash', exist_ok=True)
pp.D = SHOTS
_sp = importlib.util.spec_from_file_location('stn_test', h.START + '/tests/s2/station.py')
T = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(T)
res = []


def tap1(k, hold=8, after=14):
    run(hold, [k])
    run(after)


T.dock()
run(60)
fm_start('st_enter')
for _ in range(4):
    tap1('DOWN')
tap1('A', after=40)
run(60)
res.append(fm_report())

fm_start('st_walk_right_10s')                  # the left end of the hub to the right end: both camera borders
mb(35, -2300), mb(36, 0)
fm_break()
run(600, ['RIGHT'])
res.append(fm_report())
fm_start('st_walk_left_10s')
run(600, ['LEFT'])
res.append(fm_report())
fm_start('st_wobble_10s')                      # back and forth across a border
mb(35, -750), mb(36, 0), fm_break()
for i in range(300):
    run(2, ['LEFT'] if i % 2 else ['RIGHT'])
res.append(fm_report())
fm_start('st_run_diag')                        # running up and down the hall
mb(35, -2300), mb(36, -400), fm_break()
for _ in range(6):
    run(100, ['RIGHT', 'UP', 'R'])
    run(100, ['RIGHT', 'DOWN', 'R'])
res.append(fm_report())

sys.path.insert(0, h.START + '/tools/content')
import stgeo as G                              # noqa: E402
rooms = G.build_rooms()
fm_start('st_rooms')
for rid in range(G.OPS, G.QUARTERS + 1):
    r = rooms[rid]
    mb(34, 1), mb(35, int([-2000, -1330, -660, 10, 680, 1350, 2020][rid - 2])), mb(36, 600), fm_break()
    run(60, ['UP'])                            # through the door
    run(30)
    cr, cx, cz = r.crew[0][0], int(r.crew[0][1]), r.crew[0][2]
    mb(35, cx), mb(36, cz - 260), run(8)
    tap1('A')
    for _ in range(3):
        tap1('A')
    if mb(33, 4) & 255:
        tap1('B')
    for u in r.uses:
        if u[0] == G.U_TERM:
            mb(35, int(u[2])), mb(36, int(u[3]) - 120), run(8)
            tap1('A', after=20)
            tap1('DOWN')
            tap1('RIGHT')
            tap1('B', after=20)
            if mb(33, 4) & 255:
                tap1('B')
    tap1('L', after=20)
    tap1('B', after=20)
    run(40)
mb(34, 1)
tap1('B', after=40)                            # out to the hangar
run(90)
res.append(fm_report())

fm_start('st_mash_terminal')                   # A and B hammered at a console: a page may not come and go faster than the rule allows
mb(32), run(20), mb(34, G.OPS), run(20)
mb(35, int(rooms[G.OPS].uses[0][2])), mb(36, int(rooms[G.OPS].uses[0][3]) - 120), fm_break(), run(8)
for i in range(200):
    run(3, ['A'] if i % 2 == 0 else ['B'])
    run(0)
res.append(fm_report())
fm_start('st_mash_hangar')                     # hub and hangar swapped as fast as the keys go
mb(34, 1), run(20)
for i in range(120):
    run(4, ['B'])
    run(4)
    run(4, ['A'])
    run(4)
res.append(fm_report())
fm_start('st_mash_tabs')                       # the second pages (city board, Kestrel's board) flipped as fast as the keys go
mb(34, G.OPS), run(20), mb(44, 3), mb(45, 3), mb(39, 2), fm_break(), run(8)
for i in range(150):
    run(3, ['RIGHT'] if i % 2 == 0 else ['LEFT'])
    run(0)
mb(34, G.QUARTERS), run(20), mb(44, 6), mb(39, 11), fm_break(), run(8)
for i in range(150):
    run(3, ['RIGHT'] if i % 2 == 0 else ['LEFT'])
    run(0)
res.append(fm_report())
bad = [r for r in res if r[0] > 3 or r[1] > 3]
print('ALL OK' if not bad else 'FAIL')
sys.exit(1 if bad else 0)
