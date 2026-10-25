"""The job board's pirates (tag 0) are as they were: dock, take a combat job from the board (a bounty, a city raid or the
carrier), fly out, and the job's own foes come at the Arwing and fire at it (shots with no harm of their own: the board's
6 + 2 a level), they are the board's kind (no tag, no flags, no floor kept), and shooting them down pays the job.

    SP=<harness folder> ROM=x.gba ELF=x.elf python3 tests/s2/legacy.py        (from stuntfox/)
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
tele_ship([X, 2400, Z - 2000], f=(0, -3000, 15900))
run(2)
FOE, SHOT = 48, 24
J_BOUNTY, J_RAID, J_BOSS = 1, 5, 6


def foe(i):
    b = e.read(S['sg_foes'] + FOE * i, FOE)
    hp, kind, cool, ai, fl, tag, flo = struct.unpack_from('<hBBBBHh', b, 36)
    return dict(p=struct.unpack_from('<3i', b, 0), hp=hp, kind=kind, fl=fl, tag=tag, flo=flo)


def foes():
    return [foe(i) for i in range(8) if foe(i)['kind']]


def board_shots():
    n = 0
    for i in range(16):
        b = e.read(S['sg_shots'] + SHOT * i, SHOT)
        life, who, tgt, pad = struct.unpack_from('<BBbb', b, 18)
        n += bool(life) and who == 2 and pad == 0
    return n


def setv(a, v):
    for i in range(3):
        e.write32(a + 4 * i, int(v[i]) & 0xffffffff)


mb(D_RESET)
run(5)
B = S['ship']
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
ck(r32(S['sg_state']) == 2, 'docked')
offers = [struct.unpack('<BBh', e.read(S['offers'] + 4 * i, 4)) for i in range(3)]
pick = next((i for i, o in enumerate(offers) if o[0] in (J_BOUNTY, J_RAID, J_BOSS)), None)
print('offers', offers, 'pick', pick)
if pick is None:                                      # (none of the three is a fight: the board offers again after a job; no luck here)
    print('SKIP  the board offered no fight this time')
    ck.done()
    sys.exit(0)
o = offers[pick]
tap('A', hold=8, after=30)                            # JOB BOARD
for _ in range(pick):
    tap('DOWN', hold=8, after=20)
c0, jd0, fd0 = r32(S['credits']), r32(S['jobs_done']), events()['FOE_DOWN']
tap('A', hold=8, after=30)
for k in range(60):
    run(15)
    if r32(S['sg_state']) == 0:
        break
ck(r32(S['sg_state']) == 0 and r32(S['job']) == o[0], 'launched with the job taken', 'state %d job %d' % (r32(S['sg_state']), r32(S['job'])))
fs = foes()
need = {J_BOUNTY: 2 + o[1], J_RAID: 3 + o[1], J_BOSS: 3}[o[0]]
ck(len(fs) == min(need, 8), 'the job\'s foes are out: %d' % len(fs), 'wanted %d' % min(need, 8))
ck(all(f['tag'] == 0 and f['fl'] == 0 and f['hp'] > 0 for f in fs), 'they are the board\'s kind: no tag, no flags, health')
p0 = [f['p'] for f in fs]
seen = 0
for t in range(200):
    run(8)
    seen = max(seen, board_shots())
    if seen:
        break
ck(seen > 0, 'they fire at the Arwing (shots with no harm of their own, the board\'s)', 'most at once %d' % seen)
ck(sum(a['p'] != b for a, b in zip(foes(), p0)) >= 1, 'and they fly')
n = len(foes())
mb(49)
run(10)
ck(foes() == [] and r32(S['job']) == 0 and r32(S['jobs_done']) == jd0 + 1, 'all of them shot down: the job is done', 'job %d done %d' % (r32(S['job']), r32(S['jobs_done'])))
ck(events()['FOE_DOWN'] - fd0 == n, 'EV_FOE_DOWN once for each', '+%d of %d' % (events()['FOE_DOWN'] - fd0, n))
pay = r32(S['credits']) - c0
ck(pay >= o[2] + 40 * (n - (o[0] == J_BOSS)) and pay <= o[2] + 300 + 40 * n, 'and paid: the job and each pirate', 'credits +%d (job %d, %d foes)' % (pay, o[2], n))
ck.done()
