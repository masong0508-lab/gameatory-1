#!/usr/bin/env python3
"""rigmiss.py ISO NM OUTDIR FRAMES [--state-in FILE]: trace of the ROM page cache misses (cd_fetch) of the PS1 runtime in the headless rig.
Samples rom_miss_count and the page cache's slot table every video frame (a fetch takes about 12 video frames in this core, so none is missed) and prints,
per phase (guest frame ranges), how many fetches each 16 KiB ROM cluster (4 pages, the unit cd_fetch reads) caused.  EMULATOR-ONLY (PCSX-ReARMed timing)."""
import sys, os, json, collections, pickle
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'rig'))   # ps1/rig (cores: $RIG_CORES, see its README.md)
from retro_ps1 import Emu
A = [a for a in sys.argv[1:] if not a.startswith('--')]; F = [a for a in sys.argv[1:] if a.startswith('--')]
iso, nmf, out, N = A[0], A[1], A[2], int(A[3])
STATE_IN = ([f.split('=', 1)[1] for f in F if f.startswith('--state-in=')] or [''])[0]
NM = {}
for l in open(nmf):
    p = l.split()
    if len(p) == 3: NM[p[2]] = int(p[0], 16)
os.makedirs(out, exist_ok=True)
e = Emu('pcsx_rearmed', iso, out, {'pcsx_rearmed_bios': 'HLE'})
if STATE_IN: e.run(2); e.load_state(open(STATE_IN, 'rb').read())
r = lambda n: e.r32(NM[n])
resident = set()
def read_resident():
    base = NM['rom_pg']; s = set()
    lo, hi = NM['__ps1_pcache_start'], NM['__ps1_pcache_end']
    for pg in range(2048):
        v = e.r32(base + 4 * pg)
        if v and not (lo <= v < hi): s.add(pg)
    return s
trace = []; last = r('rom_miss_count'); v0 = e.frames
nslot = (NM['__ps1_pcache_end'] - NM['__ps1_pcache_start']) // 4096; ngrp = nslot // 4; seen = [None] * ngrp
def groups():
    o = e.read(NM['slot_owner'], 4 * nslot); own = [int.from_bytes(o[4 * i:4 * i + 4], 'little') for i in range(nslot)]
    return [tuple(own[4 * g:4 * g + 4]) for g in range(ngrp)]
for i in range(N):
    e.run(1)
    G = groups()
    for g in range(ngrp):
        if G[g] != seen[g] and max(G[g]):          # this 4-slot group was refilled: a completed cd_fetch of one 16 KiB cluster
            trace.append((e.frames, r('g_gframes'), (max(G[g]) - 1) & ~3, 1, e.r32(0x801b1e00), G[g]))
        seen[g] = G[g]
resident = read_resident()
pickle.dump(dict(trace=trace, resident=sorted(resident), frames=(v0, e.frames)), open(out + '/misstrace.pkl', 'wb'))
print('video frames %d..%d, cluster fetches seen %d, rom_miss_count %d -> %d, resident pages %d' % (v0, e.frames, len(trace), last, r('rom_miss_count'), len(resident)))
gfs = [t[1] for t in trace]
if trace:
    g0, g1 = trace[0][1], trace[-1][1]
    print('guest frames %d..%d' % (g0, g1))
    # phases by guest frame window of 50
    for a in range(g0 - g0 % 50, g1 + 1, 50):
        T = [t for t in trace if a <= t[1] < a + 50]
        if not T: continue
        c = collections.Counter(t[2] for t in T)
        vf = T[-1][0] - T[0][0]
        print('gf %4d..%4d: %4d fetches in %6d video frames, %2d distinct 16 KiB clusters: %s' % (a, a + 49, sum(t[3] for t in T), vf, len(c), ' '.join('%03x:%d' % (k, v) for k, v in sorted(c.items()))))
