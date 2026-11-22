#!/usr/bin/env python3
"""rigpages.py ISO NM OUTDIR: exact ROM page working sets of the PS1 runtime, per guest frame (TEST-ONLY build with -DPGTRACE=0x80175000u:
rom_page() stamps a 2048 x u16 table with the guest frame number).  Headless rig (PCSX-ReARMed, HLE BIOS), menu assist to the level, then scripted
play (walk, turn, pause/resume, weapon, walk).  Writes OUTDIR/pages.pkl: {'frames': {gf: sorted pages}, 'marks': [(vf, gf, label)], 'resident': [...], 'fetch': {gf: fetches}}."""
import sys, os, pickle, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'rig'))   # ps1/rig (cores: $RIG_CORES, see its README.md)
from retro_ps1 import Emu
iso, nmf, out = sys.argv[1:4]; PGT = 0x80175000
NM = {}
for l in open(nmf):
    p = l.split()
    if len(p) == 3: NM[p[2]] = int(p[0], 16)
os.makedirs(out, exist_ok=True)
e = Emu('pcsx_rearmed', iso, out, {'pcsx_rearmed_bios': 'HLE'})
r = lambda n: e.r32(NM[n]); EW = 0x801b0000
frames = {}; marks = []; fetch = {}; last_gf = 0; last_miss = 0; t0 = time.time()
def sample():
    global last_gf, last_miss
    gf = r('g_gframes')
    t = np.frombuffer(e.read(PGT, 4096), dtype='<u2')
    lo = last_gf & 0xffff; hi = gf & 0xffff
    if hi >= lo:
        idx = np.nonzero((t >= max(lo, 1)) & (t <= hi))[0]
        for pg in idx:
            frames.setdefault(int(t[pg]) + (gf & ~0xffff), set()).add(int(pg))
    m = r('rom_miss_count')
    if m != last_miss: fetch[gf] = fetch.get(gf, 0) + (m - last_miss); last_miss = m
    last_gf = gf
def run(n, buttons=()):
    for _ in range(n):
        e.run(1, buttons); sample()
def mark(label): marks.append((e.frames, r('g_gframes'), label)); print('MARK vf %d gf %d clk %d miss %d %s (wall %.0f s)' % (e.frames, r('g_gframes'), e.r32(EW + 0x1e00), r('rom_miss_count'), label, time.time() - t0), flush=True)
mark('power on')
while e.frames < 90000 and not e.r32(EW + 0x1e00): run(20)
mark('level clock runs')
if not e.r32(EW + 0x1e00): raise SystemExit('level not reached')
run(1500); mark('level idle 1500 vf done')
run(2400, ['CROSS']); mark('walk 2400 vf done')
run(1200, ['LEFT']); mark('turn left 1200 vf done')
run(1800, ['CROSS']); mark('walk 1800 vf done')
run(300, ['START']); run(1200); mark('pause done (Start 300 vf + 1200)')
run(300, ['CROSS']); run(1500); mark('resume done (Cross 300 vf + 1500)')
run(300, ['UP']); run(1500); mark('weapon Up done (300 + 1500)')
run(300, ['R1']); run(900); mark('R1 (shoot) done')
run(1200, ['CROSS', 'RIGHT']); mark('walk+right 1200 vf done')
run(2400, ['CROSS']); mark('walk 2400 vf done (2)')
base = NM['rom_pg']; lo, hi = NM['__ps1_pcache_start'], NM['__ps1_pcache_end']; res = [pg for pg in range(2048) if e.r32(base + 4 * pg) and not (lo <= e.r32(base + 4 * pg) < hi)]
pickle.dump(dict(frames={k: sorted(v) for k, v in frames.items()}, marks=marks, resident=res, fetch=fetch), open(out + '/pages.pkl', 'wb'))
print('guest frames with page data: %d (gf %d..%d), distinct pages %d, resident %d' % (len(frames), min(frames), max(frames), len(set().union(*frames.values())), len(res)))
