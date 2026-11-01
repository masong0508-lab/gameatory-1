"""Shore scan: every water/land cell pair of the shipped worlds, for a height that jumps where a man (or the camera
that follows him) crosses it.  Reads the worlds out of a built ROM (world_table, found through the ELF).

  watercheck.py ROM ELF [--grid G] [-v]

Classes (a pair is one water cell and one of its four neighbours):
  UP_STEP    a way out (swim table bit) onto a bank higher than the water by more than FLUSH: he would be lifted
  DROP_STEP  ... onto one lower by more than FLUSH: dropped
  LEVEL      two water cells whose surfaces differ: the swimmer's height has to change between them
  SUNK       dry ground beside the water whose edge lies under the surface (a ramp running down below it)
  OPEN_CLIFF a bank higher than a man climbs (CLIMB) with no wall, rail or way out (he is only stopped; listed, not a glitch)
The runtime eases UP_STEP, DROP_STEP and LEVEL (merge.c swim_out, swim_tick: a few ticks, never one frame).  This
scan reads only the world data, which the fix leaves alone: it lists the places that NEED easing (SNAP: every up, drop,
level and sunk pair, the same on the base and the fixed build) and those the easing cannot cover (UNEASABLE: a step beyond
CLIMB / DROP that has a way out).  It cannot see the runtime fix, so it proves nothing about it: that is measured by
walking and swimming across the edges and counting frame jumps by class (a walk-in run per grid)."""
import argparse, struct, subprocess, sys

N, HBIAS = 128, 40
EDGE = ((0, -1), (1, 0), (0, 1), (-1, 0))
FLUSH, CLIMB, DROP = 16, 256, 512


def syms(elf):
    nm = subprocess.run(['llvm-nm', elf], capture_output=True, text=True).stdout
    return {l.split()[2]: int(l.split()[0], 16) for l in nm.splitlines() if len(l.split()) == 3}


def world(d, o):
    H = [struct.unpack_from('<I', d, o + 4 * k)[0] for k in range(26)]
    cell = [struct.unpack_from('<hhBB', d, o + H[15] + 6 * i) for i in range(N * N)]
    deck = [struct.unpack_from('<4b', d, o + H[21] + 4 * i) for i in range(N * N)]
    deck2 = [struct.unpack_from('<4b', d, o + H[23] + 4 * i) for i in range(N * N)]
    swim = list(d[o + H[25]:o + H[25] + N * N])
    wall = list(d[o + H[22]:o + H[22] + N * N])
    return cell, deck, deck2, swim, wall


def edge_h(c, e):
    """ground height at the two ends of edge e of cell c"""
    lo, hi, sh = c[0], c[1], c[2]
    out = []
    for cx, cz in (((0, 0), (1, 0)), ((1, 0), (1, 1)), ((0, 1), (1, 1)), ((0, 0), (0, 1)))[e]:
        rise = {2: cz, 3: cx, 4: 1 - cz, 5: 1 - cx}.get(sh)
        out.append(hi if rise is None else lo + (hi - lo) * rise)
    return out


def scan(cell, deck, deck2, swim, wall):
    r = {k: [] for k in ('pairs', 'UP_STEP', 'DROP_STEP', 'LEVEL', 'SUNK', 'OPEN_CLIFF', 'glitch')}
    for x in range(1, N - 1):
        for z in range(1, N - 1):
            i = x * N + z
            if cell[i][2] != 6:
                continue
            s = cell[i][1]
            for e, (dx, dz) in enumerate(EDGE):
                j = (x + dx) * N + z + dz
                c = cell[j]
                at = (x, z, e)
                if c[2] == 6:
                    if x + dx < x or (dx == 0 and z + dz < z):
                        continue                       # (each water pair once)
                    if c[1] != s:
                        r['LEVEL'].append(at + (s, c[1]))
                    continue
                if any(deck[j]) or any(deck2[j]):
                    continue                           # (a bridge or walkway: its own deck, not the ground)
                r['pairs'].append(at)
                h = edge_h(c, e ^ 2)
                way = swim[i] >> e & 1
                if min(h) < s - FLUSH and max(h) <= s:
                    r['SUNK'].append(at + (min(h), s))
                hi, lo = max(h), min(h)            # (an edge sloping along the water: he climbs where he can)
                if way and lo - s > FLUSH:
                    r['UP_STEP'].append(at + (lo, s))
                    if lo - s > CLIMB + 8:
                        r['glitch'].append(('UP_STEP',) + at + (lo, s))
                if way and s - hi > FLUSH:
                    r['DROP_STEP'].append(at + (hi, s))
                    if s - hi > DROP + 8:
                        r['glitch'].append(('DROP_STEP',) + at + (hi, s))
                if not way and not swim[i] & 32 and lo - s > CLIMB and not (wall[j] & 15 or wall[j] >> 4):
                    r['OPEN_CLIFF'].append(at + (lo, s))
    r['snap'] = [('UP',) + k for k in r['UP_STEP']] + [('DROP',) + k for k in r['DROP_STEP']] \
        + [('LEVEL',) + k for k in r['LEVEL']] + [('SUNK',) + k for k in r['SUNK']]
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('elf')
    ap.add_argument('--grid', type=int)
    ap.add_argument('-v', action='store_true')
    a = ap.parse_args()
    d = open(a.rom, 'rb').read()
    wt = syms(a.elf)['world_table']
    tot = snap = 0
    for g in range(11) if a.grid is None else [a.grid]:
        h = struct.unpack_from('<I', d, wt - 0x08000000 + 4 * g)[0] - 0x08000000
        r = scan(*world(d, h))
        print('grid %2d pairs %5d  up %3d drop %3d level %3d sunk %3d cliff %3d  SNAP %d  UNEASABLE %d' % (
            g, len(r['pairs']), len(r['UP_STEP']), len(r['DROP_STEP']), len(r['LEVEL']), len(r['SUNK']),
            len(r['OPEN_CLIFF']), len(r['snap']), len(r['glitch'])))
        tot += len(r['glitch'])
        snap += len(r['snap'])
        if a.v:
            for k in r['glitch']:
                print('    ', k)
    print('places that need easing (SNAP) in all:', snap, ' uneasable:', tot)
    return 1 if tot else 0


if __name__ == '__main__':
    sys.exit(main())
