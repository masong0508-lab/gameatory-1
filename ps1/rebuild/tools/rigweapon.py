#!/usr/bin/env python3
"""rigweapon.py ISO NM STATE OUTDIR [--settle=N]
Does Up / Down ("next / previous weapon") change anything in the guest?  Headless rig (PCSX-ReARMed, HLE BIOS; EMULATOR-ONLY), deterministic:
from one save state three branches are run for the same number of guest frames: no key (control), Up held 4 guest frames, Down held 4 guest
frames.  Guest RAM (EWRAM 256 KiB + IWRAM 32 KiB) and the HUD corner of the picture are compared between the branches."""
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'rig'))   # ps1/rig (cores: $RIG_CORES, see its README.md)
from retro_ps1 import Emu
A = [a for a in sys.argv[1:] if not a.startswith('--')]; F = dict(a[2:].split('=', 1) for a in sys.argv[1:] if a.startswith('--') and '=' in a)
iso, nmf, state, out = A[:4]; SETTLE = int(F.get('settle', 120)); AFTER = int(F.get('after', 40))
NM = {}
for l in open(nmf):
    p = l.split()
    if len(p) == 3: NM[p[2]] = int(p[0], 16)
os.makedirs(out, exist_ok=True)
e = Emu('pcsx_rearmed', iso, out, {'pcsx_rearmed_bios': 'HLE'})
EW, IW = 0x801b0000, 0x801f0000
r = lambda n: e.r32(NM[n]); gf = lambda: r('io_cyc') // 280896
def run_g(n, buttons=(), cap=60000):
    g0 = gf(); v0 = e.frames
    while gf() - g0 < n and e.frames - v0 < cap: e.run(2, buttons)
e.run(2); e.load_state(open(state, 'rb').read())
print('state loaded: guest frame %d clk %d' % (gf(), e.r32(EW + 0x1e00)), flush=True)
run_g(SETTLE); print('settled: guest frame %d clk %d video frame %d keys %03x' % (gf(), e.r32(EW + 0x1e00), e.frames, r('io_keys')), flush=True)
s1 = e.save_state()
def branch(name, key):
    e.load_state(s1)
    if key: run_g(4, [key]); run_g(AFTER - 4)
    else: run_g(AFTER)
    e.shot('%s/weapon_%s.png' % (out, name))
    ram = np.frombuffer(e.read(EW, 0x40000) + e.read(IW, 0x8000), dtype=np.uint8).copy()
    st = dict(gf=gf(), clk=e.r32(EW + 0x1e00), conf=r('cold_conflicts'), ipe=r('ip_enters'), ips=r('ip_stat_steps'), miss=r('rom_miss_count'), render=r('st3_render'), sf3_ok=r('sf3_ok'))
    print('branch %-8s %s' % (name, st), flush=True); return ram, st
ctl, sc = branch('control', None); up, su = branch('up', 'UP'); dn, sd = branch('down', 'DOWN'); r1, sr = branch('r1', 'R1')
def addr(i): return (0x02000000 + i) if i < 0x40000 else (0x03000000 + i - 0x40000)
res = {'control': sc, 'up': su, 'down': sd, 'r1': sr}
for name, ram in (('up', up), ('down', dn), ('r1', r1)):
    d = np.nonzero(ram != ctl)[0]; res['diff_' + name] = int(len(d))
    print('%s vs control: %d guest RAM bytes differ' % (name, len(d)))
    for i in d[:48]: print('   %08x: control %02x  %s %02x' % (addr(int(i)), ctl[i], name, ram[i]))
both = np.nonzero((up != ctl) & (dn != ctl) & (up != dn))[0]
print('bytes that differ from the control in BOTH key branches and between Up and Down (weapon-index candidates): %d' % len(both))
for i in both[:32]: print('   %08x: control %02x up %02x down %02x' % (addr(int(i)), ctl[i], up[i], dn[i]))
from PIL import Image
ims = {n: np.asarray(Image.open('%s/weapon_%s.png' % (out, n)).convert('RGB')).astype(int) for n in ('control', 'up', 'down', 'r1')}
for n in ('up', 'down', 'r1'):
    d = np.abs(ims[n] - ims['control']).sum(axis=2); ys, xs = np.nonzero(d > 24)
    res['pixels_' + n] = int(len(ys)); print('picture %s vs control: %d pixels differ%s' % (n, len(ys), '' if not len(ys) else ' (bounding box x %d..%d y %d..%d)' % (xs.min(), xs.max(), ys.min(), ys.max())))
json.dump(res, open(out + '/weapon.json', 'w'), indent=1)
