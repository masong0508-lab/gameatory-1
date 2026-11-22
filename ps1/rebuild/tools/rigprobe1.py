#!/usr/bin/env python3
"""rigprobe1.py ISO OUTDIR [FRAMES] [STEP]: boot the image in the headless libretro rig (PCSX-ReARMed core, HLE BIOS) WITHOUT pad input and
sample the runtime's own counters from PS1 RAM (addresses from payback-rc4.nm.txt).  Emulator-only."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'rig'))   # ps1/rig (cores: $RIG_CORES, see its README.md)
from retro_ps1 import Emu
iso, out = sys.argv[1], sys.argv[2]; N = int(sys.argv[3]) if len(sys.argv) > 3 else 30000; STEP = int(sys.argv[4]) if len(sys.argv) > 4 else 600
NM = {}
for l in open(os.path.splitext(iso)[0] + '.nm.txt'):
    p = l.split()
    if len(p) == 3: NM[p[2]] = int(p[0], 16)
e = Emu('pcsx_rearmed', iso, out, {'pcsx_rearmed_bios': 'HLE'})
t0 = time.time()
def st():
    r = lambda n: e.r32(NM[n])
    return dict(vf=e.frames, gf=r('g_gframes'), f=r('io_cyc') // 280896, clk=e.r32(0x801b1e00), plan=r('plan_sel') if r('plan_sel') < 0x80000000 else r('plan_sel') - (1 << 32), off=r('assist_off'), padid=e.r8(NM['pad_id']),
                polls=r('pad_polls'), fails=r('pad_fails'), raw=e.r16(NM['pad_raw']), keys=r('io_keys'), tg_a0=r('tg_a0'), sf3=r('sf3_ok'), pres=r('g_pres'), cold=r('cold_loads'), conf=r('cold_conflicts'), cds=r('cd_sectors'),
                miss=r('rom_miss_count'), ipe=r('ip_enters'), ips=r('ip_stat_steps'), cur=e.r8(0x801f7e68))
last = None
for i in range(0, N, STEP):
    e.run(STEP)
    s = st(); print(' '.join('%s %s' % (k, v) for k, v in s.items()), 'wall %.1f' % (time.time() - t0), flush=True)
    e.shot('%s/f%06d.png' % (out, e.frames))
    if s['clk'] and last is None: last = e.frames; N2 = e.frames + 1800
    if last is not None and e.frames >= N2: break
print('done', e.frames)
