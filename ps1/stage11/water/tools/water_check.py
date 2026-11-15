#!/usr/bin/env python3
"""water_check.py: per-map water / shore / bridge / road / hole classification of the PS1 world data, and (grids 0-3) the comparison with the
Amiga Payback landscape.  Code only: reads the player's own files at run time (world dumps from tools/dumpworld.py, the Amiga folder through
--amiga); writes only what --out / --poses name.  Nothing of the Amiga game or the ROM is kept in the repository.

usage: python3 -I water_check.py MAPS_DIR [--amiga DIR] [--maps 0,1,..] [--out report.json] [--poses wposes.h] [--shots N]
  MAPS_DIR holds world0 .. world10 (dumpworld.py output: world.npz + world.json)

What it computes per map (cell = 1024 units, index [x, z]):
  surface   what the PS1 renderer draws on top of a cell: solid box (base 0) / sunk-or-sloped ramp (its tile ctex) / ground tile ctex at y 0 / HOLE
            (ctex 0xffff, no box, no ramp: nothing is drawn there, the island colour shows)
  water     visible top tile is the water tile 0x317 (ground or ramp) and no solid box on it
  bridge    a deck (raised box or deck ramp) over a water cell
  shore     water cell with a 4-neighbour that is not water and not a hole (edge pairs counted per step height)
  checks    HOLE cells (total, and those touching water), water cells whose neighbour surface differs in height with no wall owner
            (a step between two ground-type cells is drawn only by ramp/box sides, so a step with neither is a crack candidate)
Amiga comparison (grids 0..3 only: the Amiga copy has maps 0,1,2 and the Killing Zone): top-most visible cube texture class 65 = water,
  tops of Road/Bridge on a hollow = deck (amiga_classify.py rules), water surface height (steps -> units: (steps - 256) * 8).
Exit status 0 always; the numbers are the product."""
import sys, os, json, argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
N = 128; CELL = 1024; WATER = 0x317


def ramp_y(r, x, z):
    d = r['dirv']; x0 = r['x0'] * CELL; z0 = r['z0'] * CELL
    if d == 2: ln = (r['z1'] - r['z0']) * CELL; pos = z - z0
    elif d == 3: ln = (r['x1'] - r['x0']) * CELL; pos = x - x0
    elif d == 4: ln = (r['z1'] - r['z0']) * CELL; pos = r['z1'] * CELL - z
    elif d == 5: ln = (r['x1'] - r['x0']) * CELL; pos = r['x1'] * CELL - x
    else: return r['lo']
    return r['lo'] + int((r['hi'] - r['lo']) * pos / ln)


def load_world(d):
    z = np.load(d + '/world.npz'); j = json.load(open(d + '/world.json'))
    return z, j


def ramp_dirs(d):
    """world.json has 'rises' as text; the renderer's direction code is in the blob's ramp record (byte 6, low 3 bits): rebuild from world.bin"""
    import struct
    blob = open(d + '/world.bin', 'rb').read()
    nbox, nlot, nramp = struct.unpack_from('<3I', blob, 4)
    offs = struct.unpack_from('<17I', blob, 36)
    o = offs[2]; out = []
    for k in range(nramp):
        x0, z0, x1, z1, h0, h1, dr, m = struct.unpack_from('<4B2hBB', blob, o + 10 * k)
        out.append(dict(x0=x0, z0=z0, x1=x1, z1=z1, lo=h0, hi=h1, dirv=dr & 7, deck=bool(dr & 0x80), mat=m & 15))
    return out


def surfaces(d):
    z, j = load_world(d)
    ct = z['ctex'].astype(np.int32); dt = z['dtex'].astype(np.int32)
    ramps = ramp_dirs(d)
    kind = np.zeros((N, N), np.int8)           # 0 ground 1 box 2 ramp 3 hole
    ysur = np.zeros((N, N), np.int32)          # surface height under any deck
    tile = ct.copy()
    deck = np.zeros((N, N), bool); deck_y = np.zeros((N, N), np.int32)
    for r in ramps:
        for x in range(r['x0'], r['x1']):
            for zz in range(r['z0'], r['z1']):
                y = ramp_y(r, x * CELL + 512, zz * CELL + 512)
                if r['deck']: deck[x, zz] = True; deck_y[x, zz] = y
                else: kind[x, zz] = 2; ysur[x, zz] = y
    for b in j['boxes']:
        sl = (slice(b['x0'], b['x1']), slice(b['z0'], b['z1']))
        if b['bottom'] == 0: kind[sl] = 1; ysur[sl] = b['top']
        else: deck[sl] = True; deck_y[sl] = b['top']
    hole = (kind == 0) & (ct == 0xffff)
    kind[hole] = 3
    water = (tile == WATER) & (kind != 1) & (kind != 3)
    return dict(z=z, j=j, ct=ct, dt=dt, kind=kind, ysur=ysur, deck=deck & (dt != 0xffff), deck_y=deck_y, hole=hole, water=water, ramps=ramps)


def nbrs(m):
    """4-neighbour OR of a bool grid"""
    o = np.zeros_like(m)
    o[1:] |= m[:-1]; o[:-1] |= m[1:]; o[:, 1:] |= m[:, :-1]; o[:, :-1] |= m[:, 1:]
    return o


def nbrs8(m):
    o = nbrs(m)
    o[1:, 1:] |= m[:-1, :-1]; o[:-1, :-1] |= m[1:, 1:]; o[1:, :-1] |= m[:-1, 1:]; o[:-1, 1:] |= m[1:, :-1]
    return o


def amiga_layers(amiga, g):
    import amiga_classify as ac
    tex = ac.load_textures(amiga)
    sq = ac.parse_map(os.path.join(amiga, ac.MAPS[g]))
    info = ac.classify(amiga, g)
    f = np.array(info['flags']).reshape(N, N)
    top_cls = np.full((N, N), -1, np.int32); top_name = np.empty((N, N), object); wtop = np.full((N, N), -9999, np.int32)
    for i, cubes in enumerate(sq):
        x, y = divmod(i, N); base = 0; tops = []
        top_name[x, y] = ''
        for cu in cubes:
            kind, slope, h1, h2, _ = cu
            th = max(h1, h2) if slope >= 2 else h1
            t = tex[cu[4] & 0xfff] if slope and cu[4] >> 12 & 7 and (cu[4] & 0xfff) < len(tex) else None
            base += th
            if t:
                top_cls[x, y] = t[0]; top_name[x, y] = t[1]
                if t[0] == ac.WATER_CLASS: wtop[x, y] = base
    deck = (f & ac.DECK) > 0
    wet = ((f & ac.WATER) > 0) & deck
    water = (top_cls == ac.WATER_CLASS) | wet
    return dict(flags=f, water=water, deck=deck, wet_deck=wet, top_cls=top_cls, top_name=top_name, wtop=wtop, under=np.array(info['under']).reshape(N, N))


def compare_amiga(S, A):
    r = {}
    pw = S['water'] | (S['deck'] & (S['ct'] == WATER))
    aw = A['water']
    r['water_amiga'] = int(aw.sum()); r['water_ps1'] = int(pw.sum()); r['water_both'] = int((aw & pw).sum())
    r['water_amiga_only'] = int((aw & ~pw).sum()); r['water_ps1_only'] = int((pw & ~aw).sum())
    # amiga-only water cells: what is drawn there?
    ao = aw & ~pw
    kinds = {}
    for x, y in np.argwhere(ao):
        k = ('box' if S['kind'][x, y] == 1 else 'hole' if S['kind'][x, y] == 3 else 'ramp' if S['kind'][x, y] == 2 else 'ground') + ('+deck' if S['deck'][x, y] else '')
        kinds[k] = kinds.get(k, 0) + 1
    r['water_amiga_only_by_ps1'] = kinds
    po = pw & ~aw
    kinds = {}
    for x, y in np.argwhere(po):
        k = str(A['top_name'][x, y])[:14] or 'nothing'
        kinds[k] = kinds.get(k, 0) + 1
    r['water_ps1_only_by_amiga_top'] = dict(sorted(kinds.items(), key=lambda kv: -kv[1])[:6])
    # surface height of water (units) where both agree
    both = aw & pw & (A['wtop'] > -9999) & (S['kind'] != 1)
    ay = (A['wtop'] - 256) * 8
    py = np.where(S['kind'] == 2, S['ysur'], 0)
    dh = np.abs(ay - py)[both]
    r['water_height_cells'] = int(both.sum()); r['water_height_mismatch_gt64'] = int((dh > 64).sum()); r['water_height_max_diff'] = int(dh.max()) if dh.size else 0
    ad = A['deck']; pd = S['deck']
    r['deck_amiga'] = int(ad.sum()); r['deck_ps1'] = int(pd.sum()); r['deck_both'] = int((ad & pd).sum())
    r['deck_amiga_only'] = int((ad & ~pd).sum()); r['deck_ps1_only'] = int((pd & ~ad).sum())
    r['deck_amiga_only_cells'] = [[int(x), int(y)] for x, y in np.argwhere(ad & ~pd)[:40]]
    return r


def classify_map(S):
    r = {}
    w = S['water']; deck = S['deck']; hole = S['hole']
    r['cells_water'] = int(w.sum()); r['cells_bridge_over_water'] = int((deck & (S['ct'] == WATER)).sum()); r['cells_deck'] = int(deck.sum())
    r['cells_hole'] = int(hole.sum()); r['cells_hole_touching_water'] = int((hole & nbrs8(w | (deck & (S['ct'] == WATER)))).sum())
    r['cells_solid_box'] = int((S['kind'] == 1).sum()); r['cells_ramp'] = int((S['kind'] == 2).sum())
    r['cells_sunk_ramp_water'] = int(((S['kind'] == 2) & w).sum())
    land = (~w) & (~hole) & (S['kind'] != 3)
    shore_w = w & nbrs(land & (S['kind'] != 1) | (S['kind'] == 1))
    r['cells_shore_water'] = int(shore_w.sum())
    # water-to-non-water edges by drawn step: water surface y vs neighbour surface y (box top counts, ground 0)
    ytop = np.where(S['kind'] == 1, S['ysur'], np.where(S['kind'] == 2, S['ysur'], 0))
    steps = {}
    owned = 0; unowned = 0
    ex = []
    for x in range(N):
        for z in range(N):
            if not w[x, z]: continue
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = x + dx, z + dz
                if not (0 <= a < N and 0 <= b < N) or w[a, b] or S['kind'][a, b] == 3: continue
                dy = int(ytop[a, b] - ytop[x, z]); steps[dy] = steps.get(dy, 0) + 1
                if dy != 0:
                    # a wall owner: the higher side must be a box or a ramp (their sides are drawn) -- plain ground at y 0 against a lower ramp is owned by the ramp
                    if S['kind'][a, b] in (1, 2) or S['kind'][x, z] == 2: owned += 1
                    else: unowned += 1; ex.append([int(x), int(z), int(a), int(b), dy])
    r['shore_edges'] = int(sum(steps.values())); r['shore_edges_with_step'] = int(sum(v for k, v in steps.items() if k != 0))
    r['shore_step_without_wall_owner'] = unowned; r['shore_step_owner_examples'] = ex[:10]
    return r


def pick_spread(cells, k, rng, minsep=14):
    out = []
    cells = list(cells); rng.shuffle(cells)
    for c in cells:
        if all(max(abs(c[0] - o[0]), abs(c[1] - o[1])) >= minsep for o in out): out.append(c)
        if len(out) >= k: break
    return out


def yaw_of(dx, dz): return int(round(np.arctan2(dx, dz) / (2 * np.pi) * 65536)) & 0xffff


def clear_view(S, cx, cy, cz, tx, ty, tz, m_h=None):
    """no solid box / raised ground between the camera and the target (cell grid walk, ray height against each solid cell's top)"""
    n = 40
    for k in range(1, n):
        t = k / n; x = cx + (tx - cx) * t; y = cy + (ty - cy) * t; z = cz + (tz - cz) * t
        a, b = int(x) // CELL, int(z) // CELL
        if not (0 <= a < N and 0 <= b < N): return False
        if S['kind'][a, b] == 1 and y < S['ysur'][a, b] + 64: return False
        if S['deck'][a, b] and S['deck_y'][a, b] - 400 < y < S['deck_y'][a, b] + 64 and not (abs(a - tx // CELL) <= 0 and abs(b - tz // CELL) <= 0): return False
    return True


def aim(cx, cy, cz, tx, ty, tz):
    dx, dz = tx - cx, tz - cz; h = (dx * dx + dz * dz) ** 0.5
    return yaw_of(dx, dz), int(round(np.arctan2(ty - cy, max(h, 1)) / (2 * np.pi) * 65536))


def view_from(S, tx, ty, tz, rad_cells, dy, kindname, prefer=None):
    """camera spot around target (cell units) with a clear line of sight, on a flat ground or deck-free cell, dy above the target; 8 directions, 2 radii"""
    best = None
    for r in rad_cells:
        for k in range(8):
            ang = (k + (prefer or 0)) * np.pi / 4
            cx = tx + int(round(np.sin(ang) * r * CELL)); cz = tz + int(round(np.cos(ang) * r * CELL))
            a, b = cx // CELL, cz // CELL
            if not (2 <= a < N - 2 and 2 <= b < N - 2): continue
            if S['kind'][a, b] == 1 or S['hole'][a, b]: continue
            base = int(S['deck_y'][a, b]) if S['deck'][a, b] else int(S['ysur'][a, b]) if S['kind'][a, b] == 2 else 0
            cy = max(max(base, ty) + dy, 60)       # the renderer's fly camera is never below y 60
            if not clear_view(S, cx, cy, cz, tx, ty, tz): continue
            return (kindname, cx, cy, cz) + aim(cx, cy, cz, tx, ty, tz)
    return None


def make_poses(m, S, nshots, rng):
    """shore, bridge and edge poses for map m: (kind, x, y, z, yaw, pitch); cameras have a clear line of sight to the target"""
    w = S['water']; kind = S['kind']; deck = S['deck'] & (S['ct'] == WATER)
    out = []
    cand = []
    for x in range(3, N - 3):
        for z in range(3, N - 3):
            if not w[x, z] or deck[x, z]: continue
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = x + dx, z + dz
                if not w[a, b] and kind[a, b] == 0 and not S['hole'][a, b] and not deck[a, b]: cand.append((x, z))
    nsh = max(1, nshots - (2 if deck.any() else 0) - 1)
    for (x, z) in pick_spread(sorted(set(cand)), nsh * 3, rng, 10):
        if len([o for o in out if o[0] == 'shore']) >= nsh: break
        ty = int(S['ysur'][x, z]) if kind[x, z] == 2 else 0
        v = view_from(S, x * CELL + 512, ty, z * CELL + 512, (3, 4), 520, 'shore', rng.randrange(8))
        if v: out.append(v)
    runs = []
    for x in range(N):
        for z in range(N):
            if deck[x, z]:
                for dx, dz in ((1, 0), (0, 1)):
                    if 0 <= x - dx and 0 <= z - dz and not deck[x - dx, z - dz]:
                        n = 0
                        while 0 <= x + dx * n < N and 0 <= z + dz * n < N and deck[x + dx * n, z + dz * n]: n += 1
                        if n >= 3: runs.append((x, z, dx, dz, n))
    nb = 0
    for (x, z, dx, dz, n) in pick_spread(runs, 6, rng, 12):
        if nb >= 2: break
        tx = (x + dx * n // 2) * CELL + 512; tz = (z + dz * n // 2) * CELL + 512; yd = int(S['deck_y'][x + dx * (n // 2), z + dz * (n // 2)])
        v = view_from(S, tx, yd, tz, (4, 5, 6), 650, 'bridge', rng.randrange(8))
        if v: out.append(v); nb += 1
        v = view_from(S, tx, yd - 200, tz, (3, 4), 80, 'bridge_side', rng.randrange(8))     # a low view beside / under the span
        if v: out.append(v)
    if w.any():
        ws = np.argwhere(w & ~deck)
        d = np.minimum(np.minimum(ws[:, 0], N - 1 - ws[:, 0]), np.minimum(ws[:, 1], N - 1 - ws[:, 1]))
        for idx in np.argsort(d)[:60]:
            x, z = ws[int(idx)]
            v = view_from(S, x * CELL + 512, 0, z * CELL + 512, (3, 4), 600, 'edge', 0)
            if v: out.append(v); break
    return out[:nshots + 3]


def make_hole_poses(m, S, rng, k=4):
    """views of the largest clusters of empty ground cells (holes), water-touching ones first"""
    from scipy import ndimage as ndi
    lab, n = ndi.label(S['hole'], np.ones((3, 3))); cl = []
    nearw = nbrs8(S['water'] | (S['deck'] & (S['ct'] == WATER)))
    for i in range(1, n + 1):
        cells = np.argwhere(lab == i); wet = int(nearw[lab == i].sum())
        cl.append((-(wet > 0), -len(cells), cells))
    cl.sort(key=lambda c: (c[0], c[1]))
    out = []
    for _, _, cells in cl[:k]:
        c = cells[len(cells) // 2]
        v = view_from(S, int(c[0]) * CELL + 512, 0, int(c[1]) * CELL + 512, (3, 4, 5), 520, 'hole', rng.randrange(8))
        if v: out.append(v)
    return out


def make_sweeps(m, S, rng, nsweeps=1, steps=20, stepu=64):
    """camera sweeps along a shore: the camera slides sideways by stepu units a step on the land side, always aimed at one water cell: (kind 'sweep', ...) lists"""
    w = S['water']; kind = S['kind']; deck = S['deck']; out = []
    cand = []
    for x in range(6, N - 6):
        for z in range(6, N - 6):
            if not w[x, z] or deck[x, z]: continue
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if not w[x + dx, z + dz] and kind[x + dx, z + dz] == 0 and not deck[x + dx, z + dz]:
                    # a straight shore: the next 2 cells along the tangent have the same land/water pairing
                    tx_, tz_ = -dz, dx
                    if all(w[x + k * tx_, z + k * tz_] and not w[x + dx + k * tx_, z + dz + k * tz_] for k in (-2, -1, 1, 2)): cand.append((x, z, dx, dz))
    for (x, z, dx, dz) in pick_spread(sorted(set(cand)), nsweeps * 4, rng, 16):
        if len(out) >= nsweeps: break
        tx_, tz_ = -dz, dx; ty = int(S['ysur'][x, z]) if kind[x, z] == 2 else 0
        tgt = (x * CELL + 512, ty, z * CELL + 512); seq = []
        for k in range(steps):
            off = (k - steps // 2) * stepu
            cx = (x + 3 * dx) * CELL + 512 + tx_ * off; cz = (z + 3 * dz) * CELL + 512 + tz_ * off; cy = 520
            a, b = cx // CELL, cz // CELL
            if not (0 <= a < N and 0 <= b < N) or kind[a, b] == 1: break
            yw, pt = aim(cx, cy, cz, tgt[0], tgt[1], tgt[2]); seq.append(('sweep', cx, cy, cz, yw, pt))
        if len(seq) == steps: out.append(seq)
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('maps_dir'); ap.add_argument('--amiga'); ap.add_argument('--maps', default='0,1,2,3,4,5,6,7,8,9,10')
    ap.add_argument('--out'); ap.add_argument('--poses'); ap.add_argument('--shots', type=int, default=5); ap.add_argument('--sweeps', type=int, default=0); ap.add_argument('--holes', type=int, default=0); ap.add_argument('--fill', action='store_true', help='apply waterfix.fill_holes (what mkps1world does) before classifying: the after-fix numbers'); ap.add_argument('--sweep-maps', default='0,2,6,7,9,10'); ap.add_argument('--seed', type=int, default=11)
    a = ap.parse_args(); rng = __import__('random').Random(a.seed)
    rep = {}; allp = []
    for m in [int(v) for v in a.maps.split(',')]:
        S = surfaces('%s/world%d' % (a.maps_dir, m))
        if a.fill and S['hole'].any():
            import waterfix
            names = amiga_layers(a.amiga, m)['top_name'] if a.amiga and m <= 3 else None
            ct2, log = waterfix.fill_holes(S['ct'], S['hole'], S['water'] | (S['kind'] == 1) | (S['kind'] == 2), names)
            S['ct'] = ct2; S['hole'] = (ct2 == 0xffff) & (S['kind'] == 3)
        r = classify_map(S)
        if a.amiga and m <= 3:
            r['amiga'] = compare_amiga(S, amiga_layers(a.amiga, m))
        rep[m] = r
        if a.poses and a.holes:
            for p in make_hole_poses(m, S, rng, a.holes): allp.append((m,) + p)
        elif a.poses and not a.sweeps:
            for p in make_poses(m, S, a.shots, rng): allp.append((m,) + p)
        if a.poses and a.sweeps and str(m) in a.sweep_maps.split(','):
            for seq in make_sweeps(m, S, rng, 1): allp.extend((m,) + p for p in seq)
        print('map %2d water %5d shore %4d bridge-over-water %4d deck %4d holes %3d (touching water %3d) sunk-ramp water %4d | shore steps %4d, without wall owner %3d' % (
            m, r['cells_water'], r['cells_shore_water'], r['cells_bridge_over_water'], r['cells_deck'], r['cells_hole'], r['cells_hole_touching_water'], r['cells_sunk_ramp_water'],
            r['shore_edges_with_step'], r['shore_step_without_wall_owner']))
        if 'amiga' in r:
            q = r['amiga']
            print('        Amiga: water %d (both %d, Amiga only %d, PS1 only %d); water height mismatch >64u %d of %d (max %d); decks Amiga %d both %d Amiga-only %d PS1-only %d' % (
                q['water_amiga'], q['water_both'], q['water_amiga_only'], q['water_ps1_only'], q['water_height_mismatch_gt64'], q['water_height_cells'], q['water_height_max_diff'], q['deck_amiga'], q['deck_both'], q['deck_amiga_only'], q['deck_ps1_only']))
    if a.out: json.dump(rep, open(a.out, 'w'), indent=1, default=int)
    if a.poses:
        names = ['shore', 'bridge', 'bridge_side', 'edge', 'sweep', 'hole']
        with open(a.poses, 'w') as f:
            f.write('/* generated by water_check.py: map, kind (0 shore 1 bridge 2 bridge_side 3 edge), x, y, z, yaw, pitch */\n')
            f.write('typedef struct { u8 map, kind; s32 x, y, z; int yaw, pitch; } WPose;\nstatic const WPose wposes[] = {\n')
            for (m, k, x, y, z, yw, pt) in allp: f.write('  { %d, %d, %d, %d, %d, %d, %d },\n' % (m, names.index(k), x, y, z, yw, pt))
            f.write('};\n#define NWPOSE %d\n' % len(allp))
        print('poses', len(allp), '->', a.poses)


if __name__ == '__main__':
    main()
