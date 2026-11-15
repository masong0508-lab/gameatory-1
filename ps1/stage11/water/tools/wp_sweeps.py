#!/usr/bin/env python3
"""wp_sweeps.py WPOSES.H UNDERLAY_DIR MAPS_DIR [NORMAL_DIR]: camera sweeps along a shore (water_check.py --sweeps: 20 steps of 64 units a sweep, aimed at one water cell).
Per step: holes (as wp_pixels.py: magenta where the renderer must have drawn a surface) and, with NORMAL_DIR, the number of water-coloured pixels.
Flicker/dropout = a step whose value leaves the median of its 4 neighbours by more than max(40 px, 50 %) (a hole that appears for one or two steps and goes again,
or a water area that drops out and returns).  Emulator-only screenshots."""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wp_pixels as wp
from PIL import Image
def spikes(v, floor=40):
    out = []
    for i in range(len(v)):
        nb = [v[j] for j in range(max(0, i - 2), min(len(v), i + 3)) if j != i]
        med = float(np.median(nb))
        if abs(v[i] - med) > max(floor, 0.5 * abs(med)): out.append(i)
    return out
def main():
    poses = wp.load_poses(sys.argv[1]); ud = sys.argv[2]; md = sys.argv[3]; nd = sys.argv[4] if len(sys.argv) > 4 else None
    groups = []
    for k, p in enumerate(poses):
        if groups and groups[-1][0] == p[0] and p[1] == 4 and groups[-1][2] == k: groups[-1][2] = k + 1; groups[-1][1].append(k)
        elif p[1] == 4: groups.append([p[0], [k], k + 1])
    tot_holes = tot_spk = tot_wspk = 0
    for m, ks, _ in groups:
        holes = []; water = []
        for k in ks:
            try: u = wp.grab(ud, k, 'a')
            except FileNotFoundError: holes.append(0); water.append(0); continue
            exp, typ, ring, hax, hbz = wp.hits(poses[k], md)
            mag = (u[..., 0] > 200) & (u[..., 2] > 200) & (u[..., 1] < 80)
            holes.append(int((mag & exp).sum()))
            if nd:
                n = wp.grab(nd, k, 'a'); water.append(int(((n[..., 2] > n[..., 0] + 40) & (n[..., 2] > n[..., 1] + 10)).sum()))
        sp = spikes(holes); wsp = spikes(water, 200) if nd else []
        tot_holes += sum(holes); tot_spk += len(sp); tot_wspk += len(wsp)
        print('sweep map %2d steps %d: hole px per step %s  | hole spikes at %s%s' % (m, len(ks), holes, sp, ('  | water-px spikes at %s (water px %s)' % (wsp, water)) if nd else ''))
    print('SWEEP TOTAL: hole px %d, hole spikes %d, water-px spikes %d' % (tot_holes, tot_spk, tot_wspk))
if __name__ == '__main__': main()
