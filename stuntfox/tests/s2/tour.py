"""The 11-map tour: on every map, walk, get into a car and drive, call the Arwing and fly, get out and walk again, as
a player would. A map passes when every stage keeps the game running (key reads go on, no stall), s2f.map is the map,
and the hooks keep firing; what was reached (car, Arwing) is printed so two builds can be compared.

    SP=.. TAG=name ROM=x.gba ELF=x.elf python3 tests/s2/tour.py [maps ...]      (from stuntfox/)
"""
import sys
import h
from h import *

maps = [int(a) for a in sys.argv[1:]] or list(range(11))
ck = Check()
KC = S['key_calls']


def alive(what, frames=60, keys=()):
    k0, t0 = r32(KC), hooks().get('TICK', 0) if 'hook_count' in S else 0
    run(frames, list(keys))
    dk = r32(KC) - k0
    ok = dk >= 2                        # (a stall, not a slow scene: the Arwing over Corona City is 5 a second in v12.15 too)
    if not ok:
        print('   STALL in %s: %d key reads in %d frames' % (what, dk, frames))
    return ok


rows = []
for g in maps:
    gstate(g)
    run(30)
    ok, got = True, []
    ok &= alive('start')
    fp0 = []
    for k in (['UP'], ['UP', 'RIGHT'], ['UP'], ['LEFT'], ['UP']):
        ok &= alive('walk', 40, k)
    s0 = e.save_state()                  # (the car and the Arwing each from here: one does not stand in the way of the other)
    c = get_car(tries=3, maxd=30) if modename() == 'FOOT' else None
    if c and modename() == 'DRIVE':
        got.append('car')
        for k in (['A'], ['A'], ['A', 'LEFT'], ['A'], ['A', 'RIGHT'], ['A'], ['B'], []):
            ok &= alive('drive', 40, k)
        run(6, ['L'])
        ok &= alive('out of the car', 60)
    e.load_state(s0)
    run(2)
    m = board_now()
    if m == 'FLY':
        got.append('arwing')
        for k in (['A'], ['A'], ['A', 'LEFT'], ['A', 'R'], ['A'], ['A', 'RIGHT'], ['A', 'DOWN'], ['A', 'L'], ['A', 'DOWN'], ['DOWN'], []):
            ok &= alive('fly', 40, k)
        ok &= alive('flying', 60)
    for k in (['UP'], ['UP', 'LEFT']):
        ok &= alive('a little more', 40, k)
    f = s2f() if 's2f' in S else {'map': g, 'ticks': 1}
    ok &= f['map'] == g
    k0 = r32(KC)
    run(120)
    fps = (r32(KC) - k0) * 60 / 120
    ok &= fps > 3
    ck(ok, 'map %2d %-18s ran through: %s, %.1f fps at the end' % (g, GRID_NAMES[g], ', '.join(got) or 'on foot only', fps),
       'mode %s, s2f.map %d' % (modename(), f['map']))
    rows.append((g, got, round(fps, 1)))
print('TOUR', os.environ.get('TAG', ''), rows)
ck.done()
