"""Combat in the city (package K), no other package built in: the foe API through the debug mailbox (sgx.c's sg_dbg, commands
48-61), the foes' table read back from the game's memory, a boss's phases and cascade, the courier's escape, the pods, and the
events EV_DOCK, EV_LAUNCH, EV_FOE_DOWN, EV_ARWING_DOWN and EV_PICKUP (counted through the mailbox; the arguments are checked by
tests/s2/combat_ev.py on the override build).

    SP=<harness folder> ROM=x.gba ELF=x.elf python3 tests/s2/combat.py        (from stuntfox/)
"""
import h
from h import *

ck = Check()
merged_state(e)
run(30)
ck(board_now() == 'FLY', 'in the Arwing')
e.write8(S['sg_shield_k'], 255)
me = epos(PL)
X, Z = int(me[0] * 1024), int(me[1] * 1024)
FOE = 48                                              # sizeof(Foe)
KIND = {'RAIDER': 1, 'CARRIER': 2, 'TURRET': 3, 'ACE': 4, 'COURIER': 5, 'HULL': 6, 'BAY': 7}
NPARTS = [2, 2, 4, 2, 4, 0, 2, 0, 6]
HP = [40, 60, 70, 80, 90, 50, 100, 30, 150]
NAMES = ['GULLWING', 'DROPSHIP', 'SIEGE BARGE', 'CARRIER', 'FRIGATE', 'KESTREL', 'IRON COMET', 'COURIER', 'MOTHERSHIP']


def foe(i):
    b = e.read(S['sg_foes'] + FOE * i, FOE)
    p = struct.unpack_from('<3i', b, 0)
    hp, kind, cool, ai, fl, tag = struct.unpack_from('<hBBBBH', b, 36)
    return dict(p=p, hp=hp, kind=kind, ai=ai, fl=fl, tag=tag)


def foes():
    return [foe(i) for i in range(8) if foe(i)['kind']]


def place(y=2400):
    tele_ship([X, y, Z - 2000], f=(0, -3000, 15900))
    run(2)


def credits():
    return r32(S['credits'])


def clean():
    place()
    mb(58, 0)                                         # (the tagged foes, pods too)
    mb(49)
    run(2)
    return mb(50, 0)


ck(clean() == 0, 'no foes to begin with')

# ---- the API: spawn kinds, refuse the rest ----
ok = True
for k in (1, 2, 3, 4, 5):
    clean()
    i = mb(51, k)
    f = foe(i) if i is not None and 0 <= i < 8 else None
    ok &= bool(f and f['kind'] == k and f['tag'] == 0x5f00 + k and f['hp'] > 0 and mb(50, 0x5f00 + k) == 1 and mb(50, 0) == 1)
ck(ok, 'sg_foe_spawn: a raider, carrier, turret, ace and courier come up with their tag and health')
clean()
ck([mb(51, k) for k in (0, 6, 7)] == [-1, -1, -1] and mb(50, 0) == 0, 'sg_foe_spawn refuses kinds none, hull and bay (a boss\'s body and parts are the boss call\'s)')
for _ in range(8):
    mb(51, 1 + _ % 2)
ck(mb(50, 0) == 8 and mb(51, 1) == -1, 'eight slots, the ninth is refused', 'foes %s' % mb(50, 0))
mb(58, 0x5f01)
ck(mb(50, 0x5f01) == 0 and 0 < mb(50, 0) < 8, 'sg_foe_clear(tag) takes that tag\'s foes only', 'left %s' % mb(50, 0))
ck(mb(58, 0) == 0, 'sg_foe_clear(0) takes all the tagged')

# ---- the job board's own foes are not ours: tag 0 stays out of the tagged calls ----
clean()
mb(51, 1)
slot = next(i for i in range(8) if foe(i)['kind'])
e.write8(S['sg_foes'] + FOE * slot + 42, 0), e.write8(S['sg_foes'] + FOE * slot + 43, 0)     # (make it the board's: tag 0)
ck(mb(57, 1) == 0 and mb(58, 0) == 1, 'a foe with tag 0 is not touched by hold or clear', 'alive(0) %s' % mb(57, 0))
clean()

# ---- hold: held foes stand still, released ones move ----
for k in (1, 4, 2):
    mb(51, k)
run(30)
mb(57, 1)
p0 = [f['p'] for f in foes()]
run(90)
p1 = [f['p'] for f in foes()]
ck(p0 == p1 and len(p0) == 3, 'sg_foe_hold(0, 1): three held foes stay where they are for 90 frames')
mb(57, 0)
run(90)
p2 = [f['p'] for f in foes()]
ck(sum(a != b for a, b in zip(p1, p2)) >= 2, 'released, they move again', '%d of 3 moved' % sum(a != b for a, b in zip(p1, p2)))

# ---- the city floor: tagged foes stay over the roofs while they chase the Arwing through the city ----
clean()
for k in (1, 4, 5, 2):
    mb(51, k)
low = 99999
for t in range(60):
    place(900 + 80 * (t % 10))
    run(10, ['A'])
    for i in range(8):
        r = mb(60, i)
        if r is not None and r >= 0:
            low = min(low, r)
ck(low >= 0, 'tagged foes keep over the roofs (at the least a floor above them)', 'lowest margin %d' % low)

# ---- the courier gets away at the edge of space ----
clean()
c = mb(51, 5)
e.write32(S['sg_foes'] + FOE * c + 4, 11800 + 100)     # (p.y a hair under SPACE_LO)
mb(57, 0)
for _ in range(60):
    run(10)
    if mb(59, 0x5f05):
        break
fc = foe(c)
ck(mb(59, 0x5f05) == 1 and (fc['fl'] & 2), 'a courier that reaches space is gone and escaped', 'fl %d y %d' % (fc['fl'], fc['p'][1]))
clean()

# ---- every boss: slots, health, one at a time, parts, kill, cascade, pod ----
for b in range(9):
    clean()
    ev = events()
    h0 = mb(48, b)
    n = mb(50, 0)
    body = [f for f in foes() if f['kind'] in (6, 2, 4, 5) and f['fl'] >> 4 == b + 1]
    ck(h0 is not None and h0 >= 0 and n == 1 + NPARTS[b] and len(body) == 1 and mb(52) == HP[b] and mb(50, 0x5ff0 + b) == n,
       '%-12s up: %d slots, body health %d' % (NAMES[b], n, HP[b]), 'ret %s foes %s hp %s' % (h0, n, mb(52)))
    ck(mb(48, (b + 1) % 9) == -1 and mb(50, 0) == n, '%-12s a second boss is refused' % NAMES[b])
    parts = [f for f in foes() if f['kind'] in (3, 7)]
    ck(all(f['ai'] == h0 and f['tag'] == 0x5ff0 + b for f in parts) and len(parts) == NPARTS[b], '%-12s its parts belong to the body' % NAMES[b])
    run(120)
    ck(mb(52) == HP[b], '%-12s body health stays while no one shoots' % NAMES[b])
    if b == 8:                                        # the mothership: turrets, then bays, then the core
        ck(mb(56, 1) == -1 and mb(56, 2 << 8 | 1) == -1, 'MOTHERSHIP: the core is shielded by its guns, the bays by the turrets')
        for t in range(4):
            r = mb(56, 1 << 8 | 255)
        ck(r == 1 and mb(56, 1 << 8) == -2 and mb(56, 1) == -1, 'MOTHERSHIP: four turrets down, the core is still shielded by the bays')
        mb(56, 2 << 8 | 255)
        mb(56, 2 << 8 | 255)
        ck(mb(56, 1) == 0 and mb(52) == HP[b] - 1, 'MOTHERSHIP: bays down, the core takes a hit', 'hp %s' % mb(52))
    else:
        if NPARTS[b]:
            n0 = mb(50, 0)
            ck(mb(56, (2 if b == 1 else 1) << 8 | 255) == 1 and mb(50, 0) == n0 - 1 and mb(52) == HP[b], '%-12s one part shot off: the rest stands' % NAMES[b])
        ck(mb(56, 1) == 0 and mb(52) == HP[b] - 1, '%-12s a hit on the body hurts it' % NAMES[b], 'hp %s' % mb(52))
    ev0, c0 = events(), credits()
    r = mb(56, 255)
    run(3)
    ev1 = events()
    ck(r == 1 and mb(50, 0) == 0 and mb(52) == -1, '%-12s body down: it and all its parts go' % NAMES[b], 'ret %s foes %s' % (r, mb(50, 0)))
    ck(ev1['FOE_DOWN'] - ev0['FOE_DOWN'] >= 1 and credits() > c0, '%-12s EV_FOE_DOWN raised, credits paid' % NAMES[b],
       'events +%d credits +%d' % (ev1['FOE_DOWN'] - ev0['FOE_DOWN'], credits() - c0))
    ck(mb(61) == 1, '%-12s an escape pod is dropped' % NAMES[b], 'pods %s' % mb(61))
    if b in (0, 8):                                   # (fly through it: once is enough to test the pickup)
        px, py, pz = mb(61, 1), mb(61, 2), mb(61, 3)
        c1, p0 = credits(), events()['PICKUP']
        tele_ship([px, py, pz], f=(0, 0, 16384))
        run(4)
        ck(mb(61) == 0 and credits() - c1 >= 150 and events()['PICKUP'] - p0 == 1, '%-12s the pod is taken: +150 credits, EV_PICKUP' % NAMES[b],
           'credits +%d pods %s' % (credits() - c1, mb(61)))

# ---- the same through real shots: laser records written into the game's shot table (sg_shots: position at 0, velocity at 12,
# 14 and 16, life at 18, who at 19, target at 20), flown and tested by shots_tick, the bosses held where they were put; the
# mothership is shot as a player must (turrets, then bays, then the core) and a shielded part takes nothing ----
SHOT = 24


def fire(src, vel):
    for k in range(16):
        a = S['sg_shots'] + SHOT * k
        if e.read(a + 18, 1)[0] == 0:
            for j in range(3):
                e.write32(a + 4 * j, src[j] & 0xffffffff)
                e.write8(a + 12 + 2 * j, vel[j] & 255), e.write8(a + 13 + 2 * j, (vel[j] >> 8) & 255)
            e.write8(a + 18, 60), e.write8(a + 19, 0), e.write8(a + 20, 255), e.write8(a + 21, 0)
            return True
    return False


def real_kill(b, maxv=60):
    clean()
    mb(48, b)
    mb(57, 1)
    run(8)
    for v in range(maxv):
        f = {i: x for i, x in enumerate(foe(i) for i in range(8)) if x['kind']}
        body = [x for x in f.values() if x['kind'] in (6, 2, 4, 5) and x['fl'] >> 4 == b + 1]
        if not body:
            return v
        order = [x for x in f.values() if x['kind'] == 3] or [x for x in f.values() if x['kind'] == 7] if b == 8 else []
        for n, t in enumerate((order or body)[:4] * 4):
            p = t['p']
            fire((p[0] + 1500, p[1], p[2]), (-170, 0, 0))
        run(4)
    return -1


for b in range(9):
    ev0, c0 = events(), credits()
    v = real_kill(b)
    run(3)
    ev1 = events()
    ck(v >= 0 and mb(50, 0) == 0, '%-12s shot down with real shots' % NAMES[b], 'volleys %d foes left %s' % (v, mb(50, 0)))
    d = ev1['FOE_DOWN'] - ev0['FOE_DOWN']
    ck(d >= (1 + NPARTS[b] if b == 8 else 1) and credits() > c0, '%-12s real shots: EV_FOE_DOWN raised%s, credits paid' % (NAMES[b], ' for each of its guns and the core' if b == 8 else ''),
       'events +%d credits +%d' % (d, credits() - c0))

# ---- KILL (dbg 49) takes every foe and boss ----
clean()
mb(48, 4)
mb(51, 1)
d0 = events()['FOE_DOWN']
n = mb(49)
run(3)
ck(n >= 2 and mb(50, 0) == 0 and events()['FOE_DOWN'] - d0 >= 2, 'dbg 49 kills every foe and boss', 'killed %s, FOE_DOWN +%d' % (n, events()['FOE_DOWN'] - d0))

# ---- the pods run out ----
clean()
mb(48, 7)
mb(49)
ck(mb(61) == 1, 'a pod from the courier')
mb(58, 0)
ck(mb(61) == 0, 'sg_foe_clear(0) takes the pods too')

# ---- docking, launching and going down ----
clean()
mb(D_RESET)
run(5)
B = S['ship']
sx, sy, sz = [r32(S['station_pos'] + 4 * i) for i in range(3)]


def setv(a, v):
    for i in range(3):
        e.write32(a + 4 * i, int(v[i]) & 0xffffffff)


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
ck(r32(S['sg_state']) == 2, 'the Arwing docks', 'state %d' % r32(S['sg_state']))
ck(events()['DOCK'] == 1, 'EV_DOCK raised once', 'x%d' % events()['DOCK'])
run(60)
for k in range(4):
    tap('DOWN', hold=8, after=24)
tap('A', hold=8, after=60)                            # LAUNCH (the fifth row, with no station built in)
for k in range(40):
    run(15)
    if r32(S['sg_state']) == 0:
        break
ck(r32(S['sg_state']) == 0 and events()['LAUNCH'] == 1, 'EV_LAUNCH raised once, the Arwing is out', 'state %d launches %d' % (r32(S['sg_state']), events()['LAUNCH']))
run(60)
d0 = events()['ARWING_DOWN']
e.write8(S['sg_shield_k'], 4)                         # (it can be hurt again)
place()
for k in (1, 4, 1):
    mb(51, k)
for t in range(80):                                   # (a sliver of shield left, three pirates shooting at it)
    e.write8(S['shield'], 1), e.write8(S['shield'] + 1, 0)
    run(15)
    if events()['ARWING_DOWN'] != d0:
        break
ck(events()['ARWING_DOWN'] - d0 == 1 and r32(S['sg_state']) == 4, 'EV_ARWING_DOWN raised once when the shield is gone', 'x%d state %d' % (events()['ARWING_DOWN'] - d0, r32(S['sg_state'])))

ck.done()
