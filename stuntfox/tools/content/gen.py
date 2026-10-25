"""gen: the generated content. Per map: 3 ring courses, 2 rooftop chains, 2 races, a collect hunt, a blast zone, a stunt
zone (10 challenges where the map has what each needs), 6 contracts and 6 medals. Everything is a pure function of the
atlas, the hand content and the seeds in the names; `sfc gen` rewrites content/{maps,missions}/gen/mNN.*, `sfc gen --check`
only compares."""
import math
import os

import misfmt as F
import par as PAR
import places as P
import sfm
from gen_common import GMap, lane_runs, lane_pt
import gen_misc as M
import gen_races as R
import gen_rings as G

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONTENT = os.path.join(ROOT, 'content')

RING_T = ['SKY SLALOM', 'NEEDLE THREAD', 'ROOFLINE RUN', 'CLOUD CIRCUIT', 'WING DANCE', 'THE SQUEEZE', 'STREET SKIM', 'HIGH WIRE',
          'TAIL CHASE', 'WIND TUNNEL', 'SMOKE RINGS', 'HOOP DREAMS']
ROOF_T = ['ROOF HOPPER', 'TILE TOUR', 'ATTIC ATTACK', 'CHIMNEY CHASE', 'ROOFTOP RALLY', 'PIGEON PATROL', 'SHINGLE SKIP', 'SKYLINE STEPS']
RACE_T = ['DOWNTOWN DASH', 'LAP ATTACK', 'BACK ROAD BLITZ', 'TAILGATE RALLY', 'ROUND THE BLOCK', 'SPEED TRAP', 'GREEN LIGHT GP',
          'HAIRPIN HUNT', 'THE LONG WAY', 'LANE LOTTO']
COLLECT_T = ['JUNK HUNT', 'SCRAP SCRAMBLE', 'LOST AND FOUND', 'PARTS RUN', 'TREASURE TRAIL', 'SPARE PARTS']
BLAST_T = ['BOX BREAKER', 'CRATE CRUSHER', 'BOOM SQUAD', 'DEMOLITION DAY', 'SMASH HOUR']
STUNT_T = ['TRICK SHOT', 'SHOW OFF', 'AIR TIME', 'STUNT SCHOOL', 'KICKFLIP ROW', 'GRAVITY CHECK']
TOWER_T = ['TOP OF THE WORLD', 'CLOUD NINE', "EAGLES NEST", 'HIGH ROOST', 'SKY PERCH', 'CROWN JEWEL', 'LOFTY HEIGHTS', 'AERIE']
DASH_T = ['SPEED GATE', 'LIGHTNING LANE', 'BLUR LANE', 'FAST AND FAIR']
MARK_T = ['BULLSEYE', 'DEAD CENTRE', 'SOFT LANDING', 'PERFECT PARK', 'TOUCHDOWN']
JUMP_T = ['BIG AIR', 'LONG JUMP', 'LEAP OF FAITH', 'RAMP RANGER']
MSTUNT_T = ['STUNT STAR', 'SHOWSTOPPER', 'TRICK MEDAL', 'CROWD PLEASER']
COURIER_T = ['COURIER RUN', 'SPECIAL DELIVERY', 'PARCEL PANIC']
BOUNTY_T = ['BOUNTY HUNT', 'WRECK FOR CASH', 'PIRATE BOUNTY']
RTA_T = ['RING TIME ATTACK', 'SPEED RINGS', 'RING RUSH']
FOOT_T = ['LEG WORK', 'ON FOOT DELIVERY', 'HOOF IT']
BCON_T = ['DEMOLITION JOB', 'BLAST CONTRACT', 'BOX BUSTING']
ESC_T = ['TRUCK ESCORT', 'BODYGUARD', 'SAFE PASSAGE']


def pick(pool, level, i, taken=None):
    """A title from the pool by map and index; the next one over when this map already has it."""
    for k in range(len(pool)):
        t = pool[(level * 3 + i + k) % len(pool)]
        if taken is None or t not in taken:
            if taken is not None:
                taken.add(t)
            return t
    return pool[(level * 3 + i) % len(pool)]


def ground_landing(gm, name, k):
    """A landing mark on open ground with a start ring 9 cells off: for maps with too few tall tops. -> True or None."""
    rnd = gm.rng(name)
    for attempt in range(80):
        x, y = rnd.uniform(14, 114), rnd.uniform(14, 114)
        p = gm.spot(x, y, 'car', 2, 10, lambda px, py: all(math.hypot(px - bx, py - by) >= 12 for bx, by in gm.taken))
        if not p:
            continue
        sr = G.start_ring(gm, '', (p[0], p[1], 0), (p[0], p[1], 0), rnd=rnd)
        if not sr:
            continue
        gm.place(name + '.s', sr[0], sr[1], sr[2], sr[3], G.RING_NAME[sr[4]], 'air')
        gm.claim(sr[0], sr[1])
        gm.place(name + '.1', p[0], p[1], 'ground', 2.0, 'pad')
        return True
    return None


def dash_par(length):
    """The limit of a speed gate: the stretch at the car's top speed (calibration.json's) with a little over the least V6 allows."""
    top = PAR.load(os.path.join(CONTENT, 'calibration.json'))['speed']['drive']
    return int(math.ceil(length / top * 1.3 + 6))


def hand_info(root=CONTENT):
    """{level: dict(beacons=[(x, y)], lands=[(x, y)], names=set())} of the hand-written content."""
    camp = sfm.parse_campaign(os.path.join(root, 'campaign.sfc'))
    sfm.CONSTS.clear()
    sfm.CONSTS.update(camp['consts'])
    maps = {}
    d = os.path.join(root, 'maps')
    for f in sorted(os.listdir(d)):
        if f.endswith('.places'):
            P.parse_file(os.path.join(d, f), maps)
    ms = []
    d = os.path.join(root, 'missions')
    for f in sorted(os.listdir(d)):
        if f.endswith('.sfm'):
            sfm.parse_file(os.path.join(d, f), ms)
    out = {}
    for m in ms:
        info = out.setdefault(m.map, dict(beacons=[], lands=[], names=set()))
        mp = maps.get(m.map)

        def xy(ref):
            pd = ref if isinstance(ref, P.PlaceDef) else mp.lookup(ref)
            return (pd.x, pd.y)
        if m.start is not None:
            info['beacons'].append(xy(m.start))
        for o in m.objs:
            if o.op == F.OP_LAND:
                for ref in o.places:
                    info['lands'].append(xy(ref))
    for lv, mp in maps.items():
        out.setdefault(lv, dict(beacons=[], lands=[], names=set()))['names'] = set(mp.p) | set(mp.zones)
    return out


def build_map(level, a, hand):
    gm = GMap(level, a, hand)
    lv = level
    rings_made = 0
    courses = []
    # ---- ring courses ----
    for i in range(3):
        got = G.course(gm, 'gr', i)
        courses.append(got)
        if not got:
            continue
        name = 'gr%d' % (i + 1)
        rng, n = G.put_course(gm, name, *got)
        strict = ' strict' if i == 2 else ''
        gm.mission('chal', name, 'THE SQUEEZE' if i == 2 else pick(RING_T[:5] + RING_T[6:], lv, i, gm.titles),
                   ['rings %s%s "FLY THE RINGS"' % (rng, strict)], pay=150 + 50 * i, score=20 + 10 * i, fail='time', start=name + '.s',
                   mode='fly', par='auto')
        rings_made += 1
    courses.append(G.course(gm, 'kr', 3))                      # (the rings contract's own course)
    # ---- rooftop chains ----
    used_roofs = []
    for i in range(2):
        got = G.chain(gm, 'gl', i, hops=5 if i == 0 else 4, used=used_roofs)
        if not got:
            continue
        sr, seq = got
        name = 'gl%d' % (i + 1)
        n = G.put_chain(gm, name, sr, seq)
        used_roofs += [(r.pad[0] + .5, r.pad[1] + .5) for r in seq]
        ops = ['land %s.%d "ROOF %d OF %d"' % (name, j, j, n) for j in range(1, n + 1)]
        gm.mission('chal', name, pick(ROOF_T, lv, i, gm.titles), ops, pay=150 + 50 * i, score=20, fail='time', start=name + '.s', mode='fly', par='auto')
    # ---- races ----
    used = []
    for i in range(2):
        got = R.race(gm, 'gk%d' % (i + 1), i, used, 'L' if i == 0 else None)
        if not got:
            got = R.race(gm, 'gk%d' % (i + 1), i + 5, used, None)
        if not got:
            continue
        rng, n, t = got
        name = 'gk%d' % (i + 1)
        gm.mission('chal', name, pick(RACE_T, lv, i, gm.titles), ['race %s "RACE THE LANES"' % rng], pay=200 + 50 * i, score=30, fail='time',
                   start=name + '.s', mode='drive', par='auto')
    # ---- collect ----
    got = M.collect(gm, 'gc1', 0)
    if got:
        gm.mission('chal', 'gc1', pick(COLLECT_T, lv, 0, gm.titles), ['collect %s "GRAB THE PARTS"' % got[0]], pay=150, score=20, fail='time',
                   start='gc1.s', mode='foot', par='auto')
    else:
        gm.problems.append('no hunt on foot within %d cells of walking' % M.HUNT_ROUTE_MAX)
    # ---- blast ----
    bz = M.blast_zones(gm)
    if bz:
        b = M.put_blast(gm, 'gb1', bz[0])
        if b:
            zn, n, sp, md = b
            gm.place('gb1.s', sp[0], sp[1], 'ground', 1.5, 'pad', 'car' if md == 'car' else 'foot')
            gm.claim(*sp)
            gm.mission('chal', 'gb1', pick(BLAST_T, lv, 0, gm.titles), ['blast %s n=%d "BREAK THE BOXES"' % (zn, n)], pay=250, score=30, fail='time',
                       start='gb1.s', mode='drive' if md == 'car' else 'foot', par=60)
    # ---- stunt and jump zones ----
    rw = M.ramp_windows(gm)
    got = M.put_zone_start(gm, 'gs1', rw[0]) if rw else None
    if got:
        zn, sp = got
        gm.place('gs1.s', sp[0], sp[1], 'ground', 1.5, 'pad', 'car')
        gm.claim(*sp)
        gm.mission('chal', 'gs1', pick(STUNT_T, lv, 0, gm.titles), ['stunt points=2000 zone=%s "SHOW SOME TRICKS"' % zn], pay=200, score=30, fail='time',
                   start='gs1.s', mode='drive', par=75)
    # ---- extra courses until 8 challenges ----
    k = 3
    while gm.count['chal'] < 8 and k < 8:
        got = G.course(gm, 'gr', k)
        k += 1
        if got:
            name = 'gr%d' % k
            rng, n = G.put_course(gm, name, *got)
            gm.mission('chal', name, pick(RING_T, lv, k, gm.titles), ['rings %s "FLY THE RINGS"' % rng], pay=200, score=20, fail='time',
                       start=name + '.s', mode='fly', par='auto')
    # ---- medals: three tops, a speed gate, a jump, a stunt zone ----
    tops = M.tower_tops(gm, 6)
    ti = 0
    for i in range(3):
        while ti < len(tops):
            rf = tops[ti]
            ti += 1
            px, py = rf.pad[0] + .5, rf.pad[1] + .5
            sr = G.start_ring(gm, '', (px, py, rf.h), (px, py, rf.h), rnd=gm.rng('gm%d' % (i + 1)))
            if not sr:
                continue
            name = 'gm%d' % (i + 1)
            gm.place(name + '.s', sr[0], sr[1], sr[2], sr[3], G.RING_NAME[sr[4]], 'air')
            gm.claim(sr[0], sr[1])
            gm.place(name + '.1', px, py, rf.h, 1.8, 'pad', 'roof')
            gm.mission('medal', name, pick(TOWER_T, lv, i, gm.titles), ['land %s.1 "LAND ON THE TOP"' % name], pay=200, score=20, start=name + '.s', mode='fly',
                       par='auto')
            break
    got = R.dash(gm, 'gm4', 0, used)
    if got:
        rng, n, L = got
        gm.mission('medal', 'gm4', pick(DASH_T, lv, 0, gm.titles), ['check %s "BEAT THE CLOCK"' % rng], pay=200, score=20, fail='time', start='gm4.s',
                   mode='drive', par=dash_par(L))
    jw = rw[1] if len(rw) > 1 else (rw[0] if rw else None)
    got = M.put_zone_start(gm, 'gm5', jw) if jw else None
    if got:
        zn, sp = got
        gm.place('gm5.s', sp[0], sp[1], 'ground', 1.5, 'pad', 'car')
        gm.claim(*sp)
        gm.mission('medal', 'gm5', pick(JUMP_T, lv, 0, gm.titles), ['jump cells=6 "JUMP THE GAP"'], pay=200, score=20, fail='time', start='gm5.s', mode='drive', par=60)
    sw = rw[2] if len(rw) > 2 else (rw[0] if rw else None)
    got = M.put_zone_start(gm, 'gm6', sw) if sw else None
    if got:
        zn, sp = got
        gm.place('gm6.s', sp[0], sp[1], 'ground', 1.5, 'pad', 'car')
        gm.claim(*sp)
        gm.mission('medal', 'gm6', pick(MSTUNT_T, lv, 0, gm.titles), ['stunt points=3000 zone=%s "SHOW SOME TRICKS"' % zn], pay=200, score=20, fail='time',
                   start='gm6.s', mode='drive', par=90)
    # ---- fill the medals up to 6 with more tops, then dashes ----
    j = 7
    while gm.count['medal'] < 6 and j < 14:
        if ti < len(tops):
            rf = tops[ti]
            ti += 1
            px, py = rf.pad[0] + .5, rf.pad[1] + .5
            sr = G.start_ring(gm, '', (px, py, rf.h), (px, py, rf.h), rnd=gm.rng('gm%d' % j))
            if sr:
                name = 'gm%d' % j
                gm.place(name + '.s', sr[0], sr[1], sr[2], sr[3], G.RING_NAME[sr[4]], 'air')
                gm.claim(sr[0], sr[1])
                gm.place(name + '.1', px, py, rf.h, 1.8, 'pad', 'roof')
                gm.mission('medal', name, pick(TOWER_T, lv, j, gm.titles), ['land %s.1 "LAND ON THE TOP"' % name], pay=200, score=20, start=name + '.s',
                           mode='fly', par='auto')
        else:
            got = R.dash(gm, 'gm%d' % j, j, used) if j % 2 else None
            if got:
                rng, n, L = got
                name = 'gm%d' % j
                gm.mission('medal', name, pick(DASH_T, lv, j, gm.titles), ['check %s "BEAT THE CLOCK"' % rng], pay=200, score=20, fail='time',
                           start=name + '.s', mode='drive', par=dash_par(L))
            elif ground_landing(gm, 'gm%d' % j, j):
                gm.mission('medal', 'gm%d' % j, pick(MARK_T, lv, j, gm.titles), ['land gm%d.1 "LAND ON THE MARK"' % j], pay=200, score=20,
                           start='gm%d.s' % j, mode='fly', par='auto')
        j += 1
    contracts(gm, courses[3], bz, lv)
    for want in ('kc', 'kb', 'kr', 'kd', 'kx', 'kt'):
        if want not in gm.made:
            gm.problems.append('no contract %s' % want)
    return gm


def contracts(gm, kcourse, bz, lv):
    a = gm.a
    # courier: pick up at one end of a long lane run, drop at the other
    runs = sorted(lane_runs(a, 20), key=lambda r: (-(r[3] - r[2]), r[0], r[1]))
    rnd = gm.rng('kc')
    if runs:
        r = runs[rnd.randrange(min(4, len(runs)))]
        n = r[3] - r[2]
        p, q = lane_pt(r, r[2] + 3), lane_pt(r, min(r[3] - 3, r[2] + 3 + 70))
        sp, sq = R.snap(gm, *p), R.snap(gm, *q)
        gm.place('kc.1', sp[0], sp[1], sp[2], 2.5, 'pick', 'car')
        gm.place('kc.2', sq[0], sq[1], sq[2], 2.5, 'car')
        gm.mission('contract', 'kc', pick(COURIER_T, lv, 0, gm.titles), ['deliver kc.1..kc.2 mode=drive "DELIVER THE PARCEL"'], giver='pip', pay=250,
                   score=20, fail='time,vehlost', mode='drive', par='auto')
    # bounty: three pirate cars on nearby lanes
    pts = M.lane_points(gm, gm.rng('kb'), 3)
    if pts:
        for i, (x, y) in enumerate(pts, 1):
            s = R.snap(gm, x, y)
            gm.place('kb.%d' % i, s[0], s[1], s[2], 3, 'spawn', 'car')
        gm.mission('contract', 'kb', pick(BOUNTY_T, lv, 0, gm.titles), ['destroy kb.1..kb.3 type=0 "WRECK THE CARS"'], giver='dusty', pay=350, score=30,
                   fail='time', mode='drive', par='auto')
    # rings time attack
    if kcourse:
        s, body = kcourse
        allr = [s] + list(body)
        for i, (x, y, h, rr, ax) in enumerate(allr, 1):
            gm.place('kr.%d' % i, x, y, h, rr, G.RING_NAME[ax], 'air')
        gm.mission('contract', 'kr', pick(RTA_T, lv, 0, gm.titles), ['rings kr.1..kr.%d "FLY THE COURSE"' % len(allr)], giver='nova', pay=300, score=30,
                   fail='time', mode='fly', par='auto')
    # delivery on foot
    rnd = gm.rng('kd')
    for attempt in range(40):
        cx, cy = rnd.randint(20, 108), rnd.randint(20, 108)
        mark = len(gm.pl)
        got = M.scatter(gm, 'kd', (cx - 14, cy - 14, cx + 14, cy + 14), 3, 'foot', rnd, 8.0)
        if got:
            gm.mission('contract', 'kd', pick(FOOT_T, lv, 0, gm.titles), ['deliver kd.1..kd.3 mode=foot "DELIVER IT"'], giver='quill', pay=200, score=20,
                       fail='time', mode='foot', par='auto')
            break
        del gm.pl[mark:]
        for i in range(1, 4):
            gm.names.discard('kd.%d' % i)
    # blast contract: the second box cluster, else the first, else carry crates
    w = bz[1] if len(bz) > 1 else (bz[0] if bz else None)
    done = False
    if w:
        b = M.put_blast(gm, 'kx', w)
        if b:
            zn, n, sp, md = b
            gm.mission('contract', 'kx', pick(BCON_T, lv, 0, gm.titles), ['blast %s n=%d "BREAK THE BOXES"' % (zn, n)], giver='dusty', pay=300, score=30,
                       fail='time', mode='drive', par=75)
            done = True
    if not done:
        for attempt in range(40):
            cx, cy = rnd.randint(20, 108), rnd.randint(20, 108)
            mark = len(gm.pl)
            got = M.scatter(gm, 'kx', (cx - 12, cy - 12, cx + 12, cy + 12), 3, 'foot', rnd, 6.0)
            if got:
                sp = gm.spot(cx, cy, 'foot', 1, 10)
                if not sp:
                    del gm.pl[mark:]
                    for i in range(1, 4):
                        gm.names.discard('kx.%d' % i)
                    continue
                gm.place('kx.drop', sp[0], sp[1], 'ground', 2.0, 'point', 'foot')
                gm.mission('contract', 'kx', pick(BCON_T, lv, 1, gm.titles), ['crates kx.1..kx.3 drop=kx.drop "CARRY THE CRATES"'], giver='dusty', pay=300,
                           score=30, fail='time', mode='foot', par='auto')
                break
            del gm.pl[mark:]
            for i in range(1, 4):
                gm.names.discard('kx.%d' % i)
    # escort a truck down a lane run
    runs2 = [r for r in lane_runs(a, 30)]
    rnd = gm.rng('ke')
    rnd.shuffle(runs2)
    for r in runs2:
        L = min(r[3] - r[2] - 6, 60)
        if L < 30:
            continue
        p, q = lane_pt(r, r[2] + 3), lane_pt(r, r[2] + 3 + L)
        sp, sq = R.snap(gm, *p), R.snap(gm, *q)
        if not (sp and sq):
            continue
        gm.place('kt.s', sp[0], sp[1], sp[2], 3, 'spawn', 'car')
        gm.place('kt.e', sq[0], sq[1], sq[2], 3, 'car')
        gm.mission('contract', 'kt', pick(ESC_T, lv, 0, gm.titles), ['escort kt.s kt.e type=15 "ESCORT THE TRUCK"'], giver='rook', pay=450, score=40,
                   fail='escort,time', mode='drive', par='auto')
        break


def main(maps, check, atlases):
    hand = hand_info()
    levels = maps or sorted(atlases)
    bad = 0
    for lv in levels:
        if lv not in atlases:
            print('gen: no atlas for map %d' % lv)
            bad += 1
            continue
        gm = build_map(lv, atlases[lv], hand.get(lv, {}))
        for p in gm.problems:
            print('gen map %d: %s' % (lv, p))
            bad += 1 if p.startswith('no hunt') else 0
        c = gm.count
        print('gen map %2d: %d chal %d contract %d medal' % (lv, c['chal'], c['contract'], c['medal']))
        for sub, name, text in (('maps', 'm%02d.places' % lv, gm.places_text()), ('missions', 'm%02d.sfm' % lv, gm.sfm_text())):
            d = os.path.join(CONTENT, sub, 'gen')
            path = os.path.join(d, name)
            if check:
                old = None
                if os.path.exists(path):
                    with open(path) as f:
                        old = f.read()
                if old != text:
                    print('gen: %s differs' % path)
                    bad += 1
            else:
                os.makedirs(d, exist_ok=True)
                with open(path, 'w') as f:
                    f.write(text)
    return 1 if bad else 0
