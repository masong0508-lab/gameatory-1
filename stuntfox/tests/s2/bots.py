"""Bots for the ring and race challenges of three maps; they write the par times to content/calibration.json.

Two parts, both on the real ROM:

  1. Measure. The vehicles are driven with the player's own keys and the numbers read off the game's clock (30 ticks a second):
     the Arwing's boost speed (A held) and cruise speed (no key), how fast it turns and how long a bank takes to build, a car's
     top speed on a straight street, the man's walk. These replace the default speed table.
  2. Run. Each ring challenge (RINGS) and race (RACE) is started through the mailbox and the vehicle is carried along the course's
     route at the measured speeds: the boost speed along a leg, the cruise speed round a turn of more than 20 degrees (3 cells
     before it and after it), where the ship cannot bank and level in time. The engine does the rest: a ring counts when the ship
     crosses its disc, a checkpoint when the car is in it, the challenge ends when the engine says so. A course whose rings or
     checkpoints the engine does not count in order fails here. The bot's time is the game's clock from the start to the end.
     par = 1.3 x that time, rounded up, and at least the limit V6 asks (tools/content/par.py computes it from the times written here).

What this is not: a pilot. A closed-loop stick-and-throttle bot was tried on the ring courses; steering the Arwing round a 35 degree
turn between rings 6 cells apart while holding height needs bank and pitch together, which the ship's controls turn into a roll,
so a player alternates them and the course takes longer than the line does. The times are therefore the line at measured speeds
(a player who knows the course should reach them with practice, and 1.3 is the margin); they are not a measurement of a person.

    SP=.. ROM=x.gba ELF=x.elf [MAPS=0,3,5] [KINDS=rings,race] [KEYS=m0.gr1,..] [WRITE=1] python3 tests/s2/bots.py      (from stuntfox/)

WRITE=1 puts {"speed", "turn", "bots": {key: {"time", "finished", "kind"}}} into content/calibration.json (the pars follow from the times: par.bot_par)
(keys sorted, so a second run on the same ROM writes the same file).
"""
import json
import math
import h
from h import *

sys.path.insert(0, os.path.join(START, 'tools', 'content'))
import misfmt as F                                   # noqa: E402

maps = [int(a) for a in os.environ.get('MAPS', '0,3,5').split(',') if a]
kinds = os.environ.get('KINDS', 'rings,race').split(',')
only = [a for a in os.environ.get('KEYS', '').split(',') if a]
CAL = os.path.join(START, 'content', 'calibration.json')
CELL = 1024
TICKS = 30.0
ck = Check()
STEER = 1                                            # (RIGHT raises the car's heading angle atan2(z, x): measured, +8 degrees in half a second)


def MS(off):
    return S['ms_run'] + off                         # (MisRun: state @4, count @8, t_start @16, ndone @62)


def blob():
    head = bytes(e.read(S['s2_blob'], 56))
    return bytes(e.read(S['s2_blob'], F.unpack_rec('S2Head', head)['size']))


def wrap(a):
    return (a + 180) % 360 - 180


def ship_state():
    B = S['ship']
    p = [r32(B + 4 * i) / 256.0 for i in range(3)]
    f = [r32(B + 48 + 4 * i) for i in range(3)]
    return p, math.degrees(math.atan2(f[2], f[0])), math.degrees(math.asin(max(-1, min(1, f[1] / 16384.0))))


def clock():
    return s2f()['clock']


# ---- 1. measure ----
def measure_fly():
    gstate(0)
    run(40)
    mb(10, 1)
    board_now()
    if modename() != 'FLY':
        return None
    out = {}
    for name, keys in (('boost', ['A']), ('cruise', [])):
        tele_ship((20 * CELL, 14000, 60 * CELL), (16384, 0, 0))
        run(240, keys)                                   # (up to its speed)
        c0, p0 = clock(), ship_state()[0]
        run(120, keys)
        c1, p1 = clock(), ship_state()[0]
        out[name] = math.hypot(p1[0] - p0[0], p1[2] - p0[2]) / CELL / ((c1 - c0) / TICKS)
    tele_ship((60 * CELL, 14000, 60 * CELL), (16384, 0, 0))
    run(40)
    h0, t0 = ship_state()[1], clock()
    ts, ds = [], []
    for _ in range(16):
        run(6, ['LEFT'])
        ts.append((clock() - t0) / TICKS)
        ds.append(wrap(ship_state()[1] - h0))
    rate = abs(ds[-1] - ds[-5]) / (ts[-1] - ts[-5])      # (degrees a second once the bank is built)
    lag = next((t for t, dd in zip(ts, ds) if abs(dd) > 3), 0.5)
    out['turn_deg_s'], out['bank_lag_s'] = rate, lag
    return out


def measure_man():
    gstate(0)
    run(40)
    mb(10, 1)
    c, best = ctl() or PL, 0.0
    for keys in (['UP'], ['RIGHT'], ['DOWN'], ['LEFT']):  # (the best of four ways: a wall or a kerb stops one)
        for _ in range(3):
            x0, y0, c0 = r32(c + 4) / 2048.0, r32(c + 8) / 2048.0, clock()
            run(45, keys)
            x1, y1, c1 = r32(c + 4) / 2048.0, r32(c + 8) / 2048.0, clock()
            best = max(best, math.hypot(x1 - x0, y1 - y0) / ((c1 - c0) / TICKS))
    return best


def measure_car():
    gstate(0)
    run(40)
    mb(10, 1)
    c = get_car(tries=6, maxd=30)
    if not c or modename() != 'DRIVE':
        return None
    a, best = ctl(), 0.0
    for _ in range(8):                                   # (the best 1.5 s window of 12 s with A held: a car meets corners and traffic)
        x0, y0, c0 = r32(a + 4) / 2048.0, r32(a + 8) / 2048.0, clock()
        run(45, ['A'])
        x1, y1, c1 = r32(a + 4) / 2048.0, r32(a + 8) / 2048.0, clock()
        best = max(best, math.hypot(x1 - x0, y1 - y0) / ((c1 - c0) / TICKS))
    return best


# ---- 2. run ----
def sharp_vertices(pts):
    """The vertices of the polyline pts [(x, y)] where the line turns more than 20 degrees."""
    out = []
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        t = abs(wrap(math.degrees(math.atan2(c[1] - b[1], c[0] - b[0])) - math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))))
        if t > 20:
            out.append(b)
    return out


def carry(pts, heights, v_fast, v_slow, put, limit_s=240):
    """Move the vehicle along pts (cells, cells) with heights (world units) at v_fast cells/s, v_slow within 3 cells of a sharp vertex;
    put(x, y, h, dx, dy, speed) places it. -> (done, ticks)."""
    sharp = sharp_vertices(pts)
    t_start = MS(16)
    c0 = clock()
    seg, along, last, n = 0, 0.0, c0, 0
    still, tk_last = 0, -1
    while clock() - c0 < limit_s * TICKS and n < limit_s * 30:           # (and a frame count: a stopped clock must not hang the run)
        n += 1
        e.write32(t_start, clock() - 1)                  # (the par is a limit for a player, not for the bot)
        tk = s2f()['ticks']                              # (a teleported car has hung the game's fill on some streets with a mission running: stop, do not wait it out)
        still = still + 1 if tk == tk_last else 0
        tk_last = tk
        if still > 60:
            if os.environ.get('TRACE'):
                print('   carry: the game stopped ticking at seg %d' % seg)
            break
        if r8(MS(62)) >= 1 or r8(MS(4)) not in (2, 5):
            if os.environ.get('TRACE'):
                print('   carry stops: state %d ndone %d nfail %d seg %d count %d banner %r' % (r8(MS(4)), r8(MS(62)), r8(MS(63)), seg, r16(MS(8)), bytes(e.read(0x020026e4, 20)).split(b'\0')[0]))
            break
        now = clock()
        dt = max(now - last, 0) / TICKS
        last = now
        a, b = pts[seg], pts[seg + 1]
        L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-6
        px, py = a[0] + (b[0] - a[0]) * along / L, a[1] + (b[1] - a[1]) * along / L
        v = v_slow if any(math.hypot(px - q[0], py - q[1]) < 3.0 for q in sharp) else v_fast
        along += v * dt
        while along >= L and seg + 1 < len(pts) - 1:
            along -= L
            seg += 1
            a, b = pts[seg], pts[seg + 1]
            L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-6
        k = min(along / L, 1.5)
        x, y = a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
        h0, h1 = heights[seg], heights[seg + 1]
        put(x, y, h0 + (h1 - h0) * min(k, 1.0), (b[0] - a[0]) / L, (b[1] - a[1]) / L, v)
        run(2)
    if os.environ.get('TRACE'):
        print('   carried to seg %d of %d, count %d, state %d, mode %s, ndone %d, n %d, dclock %d' % (seg, len(pts) - 1, r16(MS(8)), r8(MS(4)), modename(), r8(MS(62)), n, clock() - c0))
    return r8(MS(62)) >= 1, clock() - c0


def line_estimate(pts, v_fast, v_slow):
    """The seconds carry() would take along pts at these speeds, worked out without the game (for a race whose bot could not finish:
    the same line model, flagged as an estimate in calibration.json)."""
    sharp = sharp_vertices(pts)
    t, pos = 0.0, pts[0]
    for q in pts[1:]:
        L = math.hypot(q[0] - pos[0], q[1] - pos[1])
        steps = max(1, int(L / 0.25))
        for k in range(steps):
            px, py = pos[0] + (q[0] - pos[0]) * (k + .5) / steps, pos[1] + (q[1] - pos[1]) * (k + .5) / steps
            v = v_slow if any(math.hypot(px - c[0], py - c[1]) < 3.0 for c in sharp) else v_fast
            t += L / steps / v
        pos = q
    return t


def rings_bot(d, i, m, sp):
    ob = d['objs'][m['obj0']]
    pl = d['places']
    st0 = pl[m['start']]
    rings = [pl[ob['place'] + j] for j in range(ob['n'])]
    gstate(m['map'])
    run(40)
    mb(10, 1)
    board_now()
    if modename() != 'FLY':
        return None
    pts = [(st0['x8'] / 8.0, st0['y8'] / 8.0)] + [(q['x8'] / 8.0, q['y8'] / 8.0) for q in rings]
    hs = [st0['h']] + [q['h'] for q in rings]
    d0 = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
    n0 = math.hypot(*d0) or 1.0
    pts[0] = (pts[0][0] - d0[0] / n0 * 4, pts[0][1] - d0[1] / n0 * 4)       # (a lead-in before the start ring)

    def put(x, y, hh, dx, dy, v):
        f = (int(16384 * dx), 0, int(16384 * dy))
        tele_ship((x * CELL, hh, y * CELL), f, (int(dx * v * CELL / TICKS * 256), 0, int(dy * v * CELL / TICKS * 256)))
    put(pts[0][0], pts[0][1], hs[0], d0[0] / n0, d0[1] / n0, 0)
    run(20)
    mb(1, i)
    run(3)
    return carry(pts, hs, sp['fly'], sp['cruise'], put)


def car_state():
    B = S['car']
    p = [r32(B + 4 * i) / 256.0 for i in range(3)]
    f = [r32(B + 48 + 4 * i) for i in range(3)]
    return p, math.degrees(math.atan2(f[2], f[0]))


def drive_loop(seq, limit_s=150):
    """Steer the car with A and the D-pad through the checkpoints seq [(x, y)] in order (the engine's count is the one being driven to).
    -> (done, ticks); gives up when it has not come nearer to its checkpoint for 8 s."""
    t_start = MS(16)
    c0 = clock()
    best, t_best, k_last, n, prev = 1e9, c0, -1, 0, None
    while clock() - c0 < limit_s * TICKS and n < limit_s * 20:
        n += 1
        e.write32(t_start, clock() - 1)
        if r8(MS(62)) >= 1 or r8(MS(4)) not in (2, 5):
            break
        k = min(r16(MS(8)), len(seq) - 1)
        p, hd = car_state()
        dx, dz = seq[k][0] * CELL - p[0], seq[k][1] * CELL - p[2]
        dist = math.hypot(dx, dz) / CELL
        if k != k_last or dist < best - 0.3:
            best, t_best, k_last = dist, clock(), k
        elif clock() - t_best > 8 * TICKS:
            break
        err = wrap(math.degrees(math.atan2(dz, dx)) - hd) * STEER
        rate = wrap(hd - prev) * STEER if prev is not None else 0.0              # (degrees a step; the car goes on turning a little after the key is let go)
        prev = hd
        eff = err - rate * 6.0
        keys = [] if abs(err) > 40 else ['A']        # (lift off for a corner: B is the handbrake and spins the car)
        if eff > 6:
            keys.append('RIGHT')
        elif eff < -6:
            keys.append('LEFT')
        if os.environ.get('TRACE') and n % 10 == 0:
            print('   car %d: k %d dist %.1f err %.0f hd %.0f state %d keys %s' % (n, k, dist, err, hd, r8(MS(4)), ''.join(x[0] for x in keys) or '-'))
        run(3, keys)
    return r8(MS(62)) >= 1, clock() - c0


def race_bot(d, i, m, sp, closed=True):
    ob = d['objs'][m['obj0']]
    pl = d['places']
    st0 = pl[m['start']]
    cps = [pl[ob['place'] + j] for j in range(ob['n'])]
    laps = max(1, ob['b'])
    gstate(m['map'])
    run(40)
    mb(10, 1)
    tele_man(st0['x8'] / 8.0, st0['y8'] / 8.0)
    run(20)
    c = get_car(tries=10, maxd=60)
    if not c or modename() != 'DRIVE':
        return None
    seq = cps * laps
    pts = [(st0['x8'] / 8.0, st0['y8'] / 8.0)] + [(q['x8'] / 8.0, q['y8'] / 8.0) for q in seq]
    hs = [0] * len(pts)
    CAR = S['car']

    def put(x, y, hh, dx, dy, v):                        # (the car's state: position, velocity, then right, up and forward vectors)
        f = (int(16384 * dx), 0, int(16384 * dy))
        sp_u = int(v * CELL / TICKS * 256)
        y_now = r32(CAR + 4)                             # (the car's own height: the street is not 80 units up everywhere)
        for k, val in enumerate([int(x * CELL) << 8, y_now, int(y * CELL) << 8, int(dx * sp_u), 0, int(dy * sp_u)]):
            e.write32(CAR + 4 * k, val & 0xffffffff)
        for k, val in enumerate((f[2], 0, -f[0], 0, 16384, 0) + f):
            e.write32(CAR + 24 + 4 * k, val & 0xffffffff)
    d1 = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
    n1 = math.hypot(*d1) or 1.0
    put(pts[0][0], pts[0][1], 0, d1[0] / n1, d1[1] / n1, 0)
    run(10)
    mb(1, i)
    run(3)
    if closed:
        done, ticks = drive_loop(pts[1:], 30)              # (with the keys, as a player would)
        return done, ticks, 'race'
    done, ticks = carry(pts, hs, sp['drive'], sp['drive'] * 0.6, put)       # (the line at the measured speed)
    return done, ticks, 'race-line'


def save():
    if os.environ.get('WRITE'):
        cal = CALD
        cal['bots'] = dict(sorted(cal['bots'].items()))
        with open(CAL, 'w') as f:
            json.dump(cal, f, indent=1, sort_keys=True)
            f.write('\n')


def main():
    d = F.parse(blob())
    keyof = mission_names(d)
    global CALD
    cal = CALD = json.load(open(CAL)) if os.path.exists(CAL) else {}
    merged_state(e)
    run(30)
    base = e.save_state()
    sp = dict(cal.get('speed', {}))
    fl = measure_fly()
    ck(fl is not None and fl['boost'] > 2, 'the Arwing measured: ' + ('%s' % {k: round(v, 2) for k, v in fl.items()} if fl else 'not boarded'))
    e.load_state(base)
    run(1)
    man = measure_man()
    ck(man > 0.5, 'the man walks %.2f cells/s' % man)
    e.load_state(base)
    run(1)
    car = measure_car()
    ck(car is not None and car > 1, 'a car on a straight street: ' + ('%.2f cells/s' % car if car else 'no car near the start'))
    sp.update(fly=round(fl['boost'], 2), cruise=round(fl['cruise'], 2), foot=round(man, 2))
    if car:
        sp['drive'] = round(car, 2)
    sp.setdefault('drive', 9.0)
    cal['speed'] = {k: sp[k] for k in ('foot', 'drive', 'fly')}
    cal['turn'] = dict(deg_s=round(fl['turn_deg_s'], 1), bank_lag_s=round(fl['bank_lag_s'], 2), cruise=sp['cruise'])
    cal.setdefault('bots', {})
    for i, m in enumerate(d['missions']):
        if m['kind'] != F.MK_CHAL or m['map'] not in maps:
            continue
        key = keyof[i]
        if only and key not in only:
            continue
        op = d['objs'][m['obj0']]['op']
        kind = 'rings' if op == F.OP_RINGS else 'race' if op == F.OP_RACE else None
        if kind is None or kind not in kinds:
            continue
        e.load_state(base)
        run(1)
        r = rings_bot(d, i, m, sp) if kind == 'rings' else race_bot(d, i, m, sp)
        if kind == 'race' and (r is None or not r[0]):                  # (the keys could not: the line, from a fresh start)
            e.load_state(base)
            run(1)
            r = race_bot(d, i, m, sp, closed=False)
        if kind == 'race' and (r is None or not r[0]):                  # (no bot finished it: the line model's estimate stands, flagged)
            ob = d['objs'][m['obj0']]
            pl = d['places']
            q0 = pl[m['start']]
            seq = [pl[ob['place'] + j] for j in range(ob['n'])] * max(1, ob['b'])
            pts = [(q0['x8'] / 8.0, q0['y8'] / 8.0)] + [(q['x8'] / 8.0, q['y8'] / 8.0) for q in seq]
            est = line_estimate(pts, sp['drive'], sp['drive'] * 0.6)
            cal['bots'][key] = dict(time=round(est, 1), finished=False, kind='race-est')
            save()
            ck(False, '%s %-19s race: the bot %s; the line model says %.1f s (an estimate, not played)' % (
                key, d['texts'][m['title']], 'could not start (no car)' if r is None else 'did not finish', est))
            continue
        if r is None:
            ck(False, '%s %s: the bot could not start (no %s)' % (key, d['texts'][m['title']], 'Arwing' if kind == 'rings' else 'car'))
            cal['bots'][key] = dict(time=0, finished=False, kind=kind)
            continue
        done, ticks = r[:2]
        how = r[2] if len(r) > 2 else 'rings-line'
        t = ticks / TICKS
        cal['bots'][key] = dict(time=round(t, 1), finished=bool(done), kind=how)
        save()
        ck(done, '%s %-19s %s: %s in %.1f s' % (key, d['texts'][m['title']], kind, 'finished' if done else 'NOT finished', t))
    save()
    ck.done()


main()
