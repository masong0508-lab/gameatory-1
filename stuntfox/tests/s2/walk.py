"""Space walks (spacewalk.c): bailing out of the Arwing at any height, the slow fall, floating, the jet pack, getting back,
pause, level end, death, the moon, the rocks, the three sample objectives. Prints the "altitude vs seconds to ground" table.

    SP=.. ROM=x.gba ELF=x.elf [SHOTS=dir] [ONLY=fall,float,pack,back,edge,moon,rocks,clear,outside,obj] python3 tests/s2/walk.py   (from stuntfox/)

The mailbox (stage2.h 80..95) puts the Arwing at a height, starts the objectives, adds credits, reads where he is. Times are the
game's own ticks (60 a second): the frames the mailbox itself takes are not counted.
"""
import math

import h
from h import *

SHOTS = os.environ.get('SHOTS', SP + '/v12/s2/walk_shots')
os.makedirs(SHOTS, exist_ok=True)
ONLY = os.environ.get('ONLY', 'fall,float,pack,back,edge,moon,rocks,clear,outside,obj').split(',')
ck = Check()
SPACE_LO, SPACE_HI = 12000, 24000
merged_state(e)
run(30)
ck(board_now() == 'FLY', 'in the Arwing')
base = e.save_state()
RAG, RS = S['rags'], 184


def shot(name):
    e.frame.save('%s/walk_%s.png' % (SHOTS, name))


def st():
    v = mb(81)
    return dict(on=v & 1, kind=v >> 1 & 7, gnd=v >> 4 & 1, pack=v >> 5 & 1, call=v >> 6 & 3, obj=v >> 8 & 15, step=v >> 12 & 15, t=v >> 16)


def bail_at(alt, pack=0):
    """Load the Arwing at alt (a multiple of 16), hold SELECT till he is out; the altitude he left it at."""
    e.load_state(base)
    run(2)
    mb(82, pack)
    assert mb(83, alt // 16) == alt // 16 * 16, alt
    run(10)
    n = 0
    while not r8(S['bail']) and n < 120:
        e.run(1, ['SELECT'])
        n += 1
    run(2)
    return n


def pos():
    return s2f()['pos']


def heading():
    return s2f()['heading']


def hdist(a, b):
    return math.hypot(b[0] - a[0], b[2] - a[2])


def spd():
    v = mb(93, 0, 200)
    return -1.0 if v is None else v / 256.0


def pelvis():
    k = r8(S['bail']) - 1
    return None if k < 0 else r32(RAG + RS * k + 148)


def his_y():
    w = mb(84)
    return w if w is not None and w >= 0 else pelvis()


# ---- the fall: seconds to the ground from each start, and what he does on the way ----
if 'fall' in ONLY:
    print('altitude vs seconds to ground (the 0.5 s hold of SELECT is not counted; to the first touch of the ground)')
    print('  start alt   at bail   ticks   seconds   peak u/tick   what')
    rows = []
    for alt in (496, 1000, 2000, 5008, 9008, 11504, 12000, 14000, 16000, 20000, 23504):
        n = bail_at(alt)
        t0, y0 = s2f()['ticks'], his_y()
        kind0 = st()['on']
        tg, vmax, ypr, tpr = None, 0.0, None, t0
        yw, tw = y0, t0                                       # (speed over windows of 12+ ticks: the mailbox shifts single samples)
        for i in range(4000):
            run(3)
            y, t = his_y(), s2f()['ticks']
            if y is None:
                break
            if t - tw >= 12:
                vmax = max(vmax, (yw - y) / (t - tw))
                yw, tw = y, t
            if y <= 140:
                tg = t - t0
                break
        rows.append((alt, y0, tg, vmax))
        print('  %8d  %8d  %6s  %8.1f  %12.1f   %s' % (alt, y0, tg, (tg or 0) / 60.0, vmax, 'figure, then the ragdoll under %d' % SPACE_LO if kind0 else 'the ragdoll'),
              flush=True)
        if alt in (2000, 16000, 23504):
            shot('fall_%d' % alt)
    ts = [r[2] for r in rows]
    ck(all(t is not None for t in ts), 'every fall reaches the ground', str(ts))
    ck(all(ts[i] <= ts[i + 1] + 3 for i in range(len(ts) - 1)), 'the lower, the shorter: times never fall as the start rises', str(ts))
    ck(ts[0] < 60, 'from the roofs it is under a second', '%d ticks' % ts[0])
    ck(ts[-1] > 3 * ts[6], 'the fall from near space is a long one (over 3 times the fall from SPACE_LO)', '%d against %d ticks' % (ts[-1], ts[6]))
    ck(rows[-1][3] < 53 and all(r[3] < 53 for r in rows), 'no fall is faster than the ragdoll\'s own 52 units a tick', 'peaks %s' % [round(r[3], 1) for r in rows])
    # he lands as ever: the bounce, then he is up and well
    run(400)
    ck(r8(S['bail']) == 0 and modename() == 'FOOT' and r16(pba('PBA_RESPAWN')) == 0, 'after the last fall (from 23500) he is up on his feet, alive', status()[:60])
    # the two sides of SPACE_LO
    bail_at(11888)
    ck(st()['on'] == 0 and r8(S['bail']) != 0, 'bailing at 11900 is the ragdoll as before (no walk)', str(st()))
    bail_at(12800)
    ck(st()['on'] == 1 and st()['kind'] == 1, 'bailing at 12800 is the slow fall (a walk, falling)', str(st()))
    # the fall is survivable by design: only the FALL DAMAGE setting (off to begin with) makes a long one fatal
    for fall, what in ((0, 'with FALL DAMAGE off (as it begins) the long fall hurts nothing'), (1, 'with FALL DAMAGE on, the same fall kills, as an ordinary death')):
        e.load_state(base)
        run(2)
        mb(83, 20000 // 16)
        run(10)
        mb(D_RESET)
        e.write8(S['rag_fall'], fall)
        n = 0
        while not r8(S['bail']) and n < 120:
            e.run(1, ['SELECT'])
            n += 1
        minhp, died = 999, 0
        for i in range(900):
            run(5)
            minhp = min(minhp, r16((ctl() or PL) + 0x68))
            died |= r16(pba('PBA_RESPAWN')) > 0
            if not r8(S['bail']) and i > 60 and (died or i > 200):
                break
        ck(died == fall and (minhp == 0) == bool(fall), what, 'lowest health %d, died %d' % (minhp, died))
        e.write8(S['rag_fall'], 0)
    # the ground: unchanged, on foot, no walk
    e.load_state(base)
    run(2)
    run(60)
    ck(st()['on'] == 0, 'no walk is on while he is in the Arwing')

# ---- floating: no jet pack ----
if 'float' in ONLY:
    bail_at(26000, 0)
    s = st()
    ck(s['on'] == 1 and s['kind'] == 2 and not s['pack'], 'above SPACE_HI: he floats, no jet pack', str(s))
    run(60)
    y0, v0 = his_y(), spd()
    shot('float_nopack')
    ck(abs(his_y() - y0) < 500 and s2f()['mode'] == 0 and r8(S['bail']) != 0, 'he floats (no fall), the body is the walk\'s', 'y %d' % y0)
    a = pos()
    run(90, ['UP', 'A'])
    b = pos()
    v1 = spd()
    ck(v1 <= v0 + 0.01, 'D-pad and A do nothing without the pack (his drift only slows)', 'speed %.2f -> %.2f' % (v0, v1))
    ck(abs(mb(87)) < 4000, 'no fall: vertical speed tiny', 'v.y %d fine' % mb(87))
    rescued = None
    for i in range(60):
        run(30)
        if st()['on'] == 0:
            rescued = i * 30 + 90
            break
    ck(rescued is not None and rescued < 900, 'never a soft-lock: the Arwing is auto-summoned after a delay and he is aboard', '%s ticks after the bail' % rescued)
    run(30)
    ck(modename() == 'FLY' and r8(S['bail']) == 0, 'in the Arwing, flying again', modename())
    shot('float_rescued')
    # the hint about the pack
    bail_at(26000, 0)
    seen = 0
    for i in range(40):
        run(15)
        if st()['call']:
            shot('float_called')
            seen = 1
            break
    ck(seen, 'the call shows (ARWING COMING)')

# ---- the jet pack ----
if 'pack' in ONLY:
    bail_at(26000, 1)
    run(150, ['L'])
    ck(spd() < 0.5, 'L brakes him to rest', 'speed %.2f' % spd())
    ck(st()['pack'] == 1, 'with the pack bought')
    res = {}
    for k in ('UP', 'DOWN', 'A', 'B', 'LEFT', 'RIGHT'):
        a, h0 = pos(), heading()
        run(60, [k])
        b, h1 = pos(), heading()
        res[k] = (b[0] - a[0], b[1] - a[1], b[2] - a[2], (h1 - h0 + 32768) % 65536 - 32768)
        print('  %-5s moved dx %5d dy %5d dz %5d, heading %+6d, speed %.1f' % ((k,) + res[k] + (spd(),)))
        run(150, ['L'])
    ck(abs(res['UP'][0]) + abs(res['UP'][2]) > 300 and abs(res['UP'][1]) < 60, 'UP flies forward in the plane', str(res['UP']))
    ck(res['DOWN'][0] * res['UP'][0] + res['DOWN'][2] * res['UP'][2] < 0, 'DOWN flies back', str(res['DOWN']))
    ck(res['A'][1] > 400 and res['B'][1] < -400, 'A climbs, B sinks', 'dy %d / %d' % (res['A'][1], res['B'][1]))
    ck(res['LEFT'][3] * res['RIGHT'][3] < 0 and abs(res['LEFT'][3]) > 2000 and abs(res['LEFT'][3]) < 60000, 'LEFT and RIGHT turn him, opposite ways', '%d / %d' % (res['LEFT'][3], res['RIGHT'][3]))
    run(400, ['UP'])
    top = spd()
    ck(top < 15.5, 'a cap on his speed (no record chaos)', 'speed %.1f' % top)
    run(30)
    ck(spd() < top, 'auto-damping: let go, he slows', '%.1f -> %.1f' % (top, spd()))
    run(150, ['L'])
    shot('pack_float')
    # reduced strength in the band: horizontal distance in 30 ticks from rest
    def push(alt):
        bail_at(alt, 1)
        run(100, ['L'])
        a = pos()
        run(30, ['UP'])
        return hdist(a, pos())
    hi, lo = push(26000), push(18000)
    ck(lo < hi * 0.95 and lo > hi * 0.3, 'in the band (18000) the pack is weaker than above SPACE_HI', '%.0f against %.0f units in 30 ticks' % (lo, hi))
    shot('pack_band')
    # a climb out of the band
    bail_at(18000, 1)
    run(300, ['A'])
    ck(his_y() > 18000, 'A beats the thin pull in the band', 'y %d' % his_y())
    # a pack can carry him down to the ground safely again (the figure turns ragdoll under SPACE_LO)
    bail_at(13000, 1)
    run(900)
    ck(r8(S['bail']) == 0 and r16(pba('PBA_RESPAWN')) == 0, 'falling on to the ground with the pack on: he lands and is well', status()[:50])

# ---- getting back ----
if 'back' in ONLY:
    bail_at(26000, 1)
    run(30)
    run(60, ['SELECT'])
    run(30)
    ck(st()['on'] == 0 and modename() == 'FLY' and r8(S['bail']) == 0, 'SELECT held near the Arwing: he climbs aboard', modename())
    shot('back_near')
    # far away: the call brings the Arwing to him
    bail_at(26000, 1)
    run(30)
    mb(91, 600)
    run(50, ['SELECT'])
    s = st()
    ck(s['call'] == 1 or s['on'] == 0, 'SELECT held far from it calls it', str(s))
    run(200)
    ck(st()['on'] == 0 and modename() == 'FLY', 'the Arwing came and he is aboard', modename())
    e.run(60, ['SELECT'])
    e.run(60)
    # far with the pack: after a delay it comes anyway and waits; SELECT then boards him
    bail_at(26000, 1)
    run(30)
    mb(91, 600)
    for i in range(80):
        run(60)
        if st()['call'] == 2 or st()['on'] == 0:
            break
    ck(st()['call'] == 2, 'drifted far from it: the Arwing comes by itself after a delay and waits', str(st()))
    shot('back_waits')
    run(120)
    run(60, ['SELECT'])
    run(30)
    ck(st()['on'] == 0 and modename() == 'FLY', 'and SELECT boards him', modename())
    # the Arwing is lost while he floats: a new one comes when he calls
    bail_at(26000, 1)
    run(30)
    B = S['ship']
    e.write32(B + 4, 0)                                    # (its altitude: into the ground)
    run(120)
    run(60, ['SELECT'])
    for i in range(10):
        run(30)
        if st()['on'] == 0:
            break
    ck(st()['on'] == 0 and modename() == 'FLY', 'its crash is no soft-lock: calling brings a new Arwing and he boards it', '%s %s' % (modename(), st()))
    # the walk's own level end / pause / death
    bail_at(26000, 1)
    run(30)
    e.run(6, ['START'])
    run(30)
    ck(s2f()['paused'] == 1, 'START pauses')
    c = pos()
    t0 = st()['t']
    run(120, ['UP'])
    ck(pos() == c and st()['t'] == t0, 'nothing moves while paused', 't %d -> %d' % (t0, st()['t']))
    shot('pause')
    e.run(6, ['START'])
    run(30)
    a = pos()
    run(30, ['UP'])
    ck(s2f()['paused'] == 0 and pos() != a, 'and goes on after it')

if 'edge' in ONLY:
    bail_at(26000, 1)
    run(30)
    e.write32(PL + 0x90, 9999999)
    for _ in range(10):
        run(30)
        if r16(0x02001e08) == 3:
            break
    ck(r16(0x02001e08) == 3, 'level end reached while he floats')
    shot('level_end')
    run(30)
    run(6, ['SELECT'])
    for _ in range(25):
        run(45)
        if grid() == 1 and u32(0x02001e00) > 0:
            break
    run(120)
    ck(grid() == 1 and st()['on'] == 0 and r8(S['bail']) == 0 and modename() == 'FOOT', 'the next level starts clean (no walk, on foot)', '%s %s' % (modename(), st()))
    ck(st()['pack'] == 1 and words()['mirror'][3] >> 23 & 1, 'the jet pack is still his after a level change (and in the progress copy)', 'word3 %08x' % words()['mirror'][3])
    # death
    bail_at(26000, 1)
    run(30)
    c = ctl() or PL
    e.write8(c + 0x68, 0), e.write8(c + 0x69, 0)
    for _ in range(60):
        run(10)
        if r16(pba('PBA_RESPAWN')) > 0:
            break
    ck(r16(pba('PBA_RESPAWN')) > 0 and st()['on'] == 0 and r8(S['bail']) == 0, 'death ends the walk (Payback\'s respawn takes him)', str(st()))
    for _ in range(60):
        run(10)
        if r16(pba('PBA_RESPAWN')) == 0:
            break
    run(60)
    ck(modename() == 'FOOT' and st()['on'] == 0 and r16(pba('PBA_RESPAWN')) == 0, 'and he is up again, on foot', status()[:50])
    ck(words()['mirror'][3] >> 23 & 1 and st()['pack'], 'after the death too the pack is his and in the progress copy', 'word3 %08x' % words()['mirror'][3])

# ---- the moon ----
if 'moon' in ONLY:
    bail_at(26000, 0)
    ck(mb(85) == 1, 'put down on the moon')
    run(40)
    s = st()
    d0 = mb(95)
    ck(s['kind'] == 3 and s['gnd'] == 1, 'on the moon, standing', str(s))
    ck(2400 * 0.9 < d0 < 2400 + 300, 'on its skin (units from the middle)', '%d' % d0)
    shot('moon_stand')
    a = pos()
    ds = []
    for i in range(12):
        run(30, ['UP'])
        ds.append(mb(95))
    ck(hdist(a, pos()) > 150 and min(ds) > 2400 * 0.95 - 20 and max(ds) < 2400 + 120, 'walks about on the skin, following its faces (pelvis 100 over it, never under)', 'moved %.0f, distance %d..%d' % (hdist(a, pos()), min(ds), max(ds)))
    ck(spd() < 3.6, 'a walk\'s pace', 'speed %.1f' % spd())
    shot('moon_walk')
    run(100, ['RIGHT'])
    shot('moon_turn')
    y0 = mb(95)
    e.run(6, ['A'])
    hi = y0
    for i in range(60):
        e.run(3)
        hi = max(hi, mb(95))
    ck(hi - y0 > 40, 'A jumps (low gravity: a long, high jump)', 'up %d units' % (hi - y0))
    run(200)
    ck(st()['gnd'] == 1 and abs(mb(95) - y0) < 20, 'and he comes down to the skin', 'distance %d against %d' % (mb(95), y0))
    # the pack on the moon: sinking is stopped by the solid skin
    bail_at(26000, 1)
    mb(85)
    run(20)
    for i in range(20):
        run(30, ['B'])
        if mb(95) < 2400 * 0.9:
            break
    ck(mb(95) > 2400 * 0.9, 'B with the pack pressed against the moon: it is solid, he does not sink into it', 'distance %d' % mb(95))
    # the skin from far: the Arwing (hull) is kept out too, see physics.c space_hit; a walk from above: down to the moon with the pack
    bail_at(26000, 1)
    mb(85)
    run(5)
    run(60, ['A'])
    run(300, ['B'])
    ck(st()['kind'] == 3 and mb(95) > 2400 * 0.9, 'flying back down to the moon lands him (low gravity pulls near it)', str(st()))
    shot('moon_pack')

# ---- the rocks: a solid ball in his way ----
if 'rocks' in ONLY:
    SW = S['swk']
    SX, SY, SZ = [r32(S['station_pos'] + 4 * i) for i in range(3)]
    mc = (SX - 17000, SY + 2500, SZ + 13000)
    # the six round the moon (spacewalk.c's belt): offsets and radius
    belt = ((-3600, 1900, 2800, 420), (2900, -1700, 4300, 360), (-2200, -2600, -3900, 500), (4600, 1800, -1200, 300), (-5600, -400, 900, 380), (1200, 3300, -3400, 450))
    worst = 1e9
    for i in (0, 2, 5):
        bail_at(26000, 1)
        c = (mc[0] + belt[i][0], mc[1] + belt[i][1], mc[2] + belt[i][2])
        r = belt[i][3]
        start = (c[0] - r - 650, c[1], c[2])
        for j in range(3):
            e.write32(SW + 4 * j, (start[j] << 8) & 0xffffffff)
        e.write32(SW + 12, 14 << 8), e.write32(SW + 16, 0), e.write32(SW + 20, 0)
        dmin = 1e9
        for k in range(70):
            run(3)
            p = pos()
            dmin = min(dmin, math.dist(p, c))
        worst = min(worst, dmin - r)
        if i == 0:
            shot('rock')
        print('  rock %d (radius %d): nearest he got %.0f from its middle' % (i, r, dmin))
    ck(worst >= -1, 'he flies at a rock at full tilt: it is solid, he never gets inside it', 'closest %.0f units from the surface' % worst)

# ---- the moon and its rocks keep clear of the station and the asteroid field (they hang off station_pos: if the planet or station
# packages move it, spacewalk.c follows, and this is the check that what it follows to is still clear) ----
if 'clear' in ONLY:
    SX, SY, SZ = [r32(S['station_pos'] + 4 * i) for i in range(3)]
    mc = (SX - 17000, SY + 2500, SZ + 13000)
    belt = ((-3600, 1900, 2800, 420), (2900, -1700, 4300, 360), (-2200, -2600, -3900, 500), (4600, 1800, -1200, 300), (-5600, -400, 900, 380), (1200, 3300, -3400, 450))
    mine = [(mc, 2400)] + [((mc[0] + b[0], mc[1] + b[1], mc[2] + b[2]), b[3]) for b in belt]
    theirs = [((SX, SY, SZ), 6000)]                              # (the station: the hub and its ring lie inside 6000 of the middle)
    n = r32(S['nrocks'])
    for i in range(n):
        x, y, z, r = struct.unpack('<4i', e.read(S['rocks'] + 16 * i, 16))
        theirs.append(((x, y, z), r))
    gap = min(math.dist(a, b) - ra - rb for a, ra in mine for b, rb in theirs)
    ck(n > 0 and gap >= 500, 'the moon and its rocks clear of the station and the %d asteroids' % n, 'least gap %.0f units' % gap)

# ---- far outside the city (the Arwing is a long way off the map when he bails): nothing hangs, nothing is lost, and low down it is
# the ragdoll's own throw from where the Arwing is (no moving him toward the city) ----
if 'outside' in ONLY:
    B = S['ship']
    FAR = (300000, 26000, 400000)

    def bail_far(pack, at=FAR):
        e.load_state(base)
        run(2)
        mb(82, pack)
        assert mb(83, at[1] // 16) == at[1] // 16 * 16
        for j, v in enumerate((at[0], at[1], at[2])):
            e.write32(B + 4 * j, (v << 8) & 0xffffffff)
        run(10)
        n = 0
        while not r8(S['bail']) and n < 120:
            e.run(1, ['SELECT'])
            n += 1
        run(2)

    bail_far(0)
    t0, t = s2f()['ticks'], 0
    for _ in range(60):
        run(30)
        t = s2f()['ticks'] - t0
        if modename() == 'FLY' and st()['on'] == 0:
            break
    ck(modename() == 'FLY' and st()['on'] == 0 and t < 14 * 60, 'bailing 500000 units off the map without the pack: the Arwing comes by itself and he is aboard', '%.1f s, %s' % (t / 60.0, modename()))
    bail_far(1)
    gone = 0
    for _ in range(120):
        run(60, ['B'])
        if st()['on'] == 0:
            gone = 1
            break
    k = r8(S['bail']) - 1
    rx, rz = (r32(RAG + RS * k + 144), r32(RAG + RS * k + 152)) if k >= 0 else (-1, -1)
    ck(gone and k >= 0 and 0 <= rx <= 128 * 1024 and 0 <= rz <= 128 * 1024, 'diving with the pack from far outside: handed to the ragdoll inside the city', 'at (%d, %d), bail slot %d' % (rx, rz, k))
    run(900)
    ck(r8(S['bail']) == 0 and modename() == 'FOOT' and r16(pba('PBA_RESPAWN')) == 0, 'and he lands, gets up and is on foot, alive', status()[:60])
    e.load_state(base)
    run(2)
    for i in range(6):
        bail_at(26000, 0) if i == 0 else None
        if i:
            run(30)
            n = 0
            while not r8(S['bail']) and n < 120:
                e.run(1, ['SELECT'])
                n += 1
            run(2)
        for _ in range(80):
            e.run(30, ['SELECT'])
            run(20)
            if modename() == 'FLY' and st()['on'] == 0:
                break
        if modename() != 'FLY' or st()['on']:
            break
    live = sum(1 for j in range(5) if r8(RAG + RS * j + 171))
    ck(i == 5 and modename() == 'FLY' and st()['on'] == 0 and live <= 1, 'six times out, called, aboard again: back in the Arwing each time, no body slot left over', 'round %d, %s, %d slots in use' % (i, modename(), live))
    # low down, off the map's edge: the throw is the ragdoll's as ever (it keeps a body on the map itself; this build's bail adds no clamp
    # of its own under SPACE_LO: the same run on the base ROM gives the same place, 2048 on x)
    e.load_state(base)
    run(2)
    mb(83, 600 // 16)
    e.write32(B, (-6000 << 8) & 0xffffffff)
    e.write32(B + 8, (60000 << 8) & 0xffffffff)
    run(10)
    n = 0
    while not r8(S['bail']) and n < 120:
        e.run(1, ['SELECT'])
        n += 1
    k = r8(S['bail']) - 1
    rx = r32(RAG + RS * k + 144) if k >= 0 else 1 << 30
    ck(k >= 0 and st()['on'] == 0 and abs(rx - 2 * 1024) < 64, 'bailing low off the western edge: the ragdoll as ever (no walk, the same place as on the base ROM)', 'x %d' % rx)
    run(600)
    ck(r8(S['bail']) == 0 and modename() == 'FOOT' and r16(pba('PBA_RESPAWN')) == 0, 'and he is up on foot, alive', status()[:60])

# ---- the three sample objectives ----
if 'obj' in ONLY:
    bail_at(26000, 1)
    c0 = mb(89, 0)
    ck(mb(80, 1) == 1 and st()['obj'] == 1, 'objective 1 starts: reach beacon A')
    run(30)
    shot('obj1_hud')
    mb(88, 0)
    run(30)
    ck(st()['obj'] == 0 and mb(89, 0) == c0 + 150, 'beacon A reached: +150 CR', 'credits %d -> %d' % (c0, mb(89, 0)))
    bail_at(26000, 1)
    c0 = mb(89, 0)
    mb(80, 2)
    run(30)
    mb(85)
    run(40)
    ck(st()['obj'] == 2, 'objective 2: land on the moon, not done in the air or on the wrong side', str(st()))
    mb(88, 3)
    run(40)
    ck(st()['obj'] == 0 and mb(89, 0) == c0 + 300, 'moon post reached on foot: +300 CR', 'credits %d -> %d' % (c0, mb(89, 0)))
    bail_at(26000, 1)
    c0 = mb(89, 0)
    mb(80, 3)
    run(20)
    for i, b in enumerate((1, 2)):
        ck(st()['obj'] == 3 and st()['step'] == i, 'objective 3 step %d' % i, str(st()))
        mb(88, b)
        run(30)
    ck(st()['obj'] == 3 and st()['step'] == 2, 'objective 3: the two beacons done, now back to the Arwing', str(st()))
    shot('obj3_board')
    run(30)
    run(60, ['SELECT'])
    run(30)
    ck(st()['obj'] == 0 and modename() == 'FLY' and mb(89, 0) == c0 + 500, 'boarding finishes it: +500 CR', 'credits %d -> %d, %s' % (c0, mb(89, 0), modename()))

ck.done()
