#!/usr/bin/env python3
"""rigicon.py ISO NM OUTDIR [--state=FILE]
The HUD weapon icon (top left, 320x240 picture box x 4..14, y 11..26) over guest time: one sample per guest frame, with a fixed guest-frame
script (idle, Start, Cross, Up, R1).  Headless rig (PCSX-ReARMed, HLE BIOS; EMULATOR-ONLY).  Prints a timeline: for each guest frame the mean
brightness of the icon box and the number of pixels that differ from the same box 12 pixels further right (background reference is not
available, so the icon's own pixel statistics are printed) and saves enlarged crops at the marks."""
import sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'rig'))   # ps1/rig (cores: $RIG_CORES, see its README.md)
from retro_ps1 import Emu
from PIL import Image
A = [a for a in sys.argv[1:] if not a.startswith('--')]; F = dict(a[2:].split('=', 1) for a in sys.argv[1:] if a.startswith('--') and '=' in a)
iso, nmf, out = A[:3]
NM = {}
for l in open(nmf):
    p = l.split()
    if len(p) == 3: NM[p[2]] = int(p[0], 16)
os.makedirs(out, exist_ok=True)
e = Emu('pcsx_rearmed', iso, out, {'pcsx_rearmed_bios': 'HLE'})
EW, IW = 0x801b0000, 0x801f0000
r = lambda n: e.r32(NM[n]); gf = lambda: r('io_cyc') // 280896
if 'state' in F: e.run(2); e.load_state(open(F['state'], 'rb').read())
else:
    while e.frames < 90000 and not e.r32(EW + 0x1e00): e.run(10)
print('level: guest frame %d video frame %d clk %d' % (gf(), e.frames, e.r32(EW + 0x1e00)), flush=True)
tl = []; crops = []
def box():
    e.shot(out + '/_tmp.png'); im = np.asarray(Image.open(out + '/_tmp.png').convert('RGB')).astype(int)
    b = im[11:27, 4:15]; return b
def seg(name, buttons, n, cap=60000):
    g0 = gf(); v0 = e.frames; last = g0
    while gf() - g0 < n and e.frames - v0 < cap:
        e.run(2, buttons); g = gf()
        if g != last:
            b = box(); tl.append((g, name, int(b.mean()), int(b.max()), int((b.sum(axis=2) > 480).sum()))); last = g
    b = box(); crops.append((name, gf(), Image.fromarray(np.asarray(Image.open(out + '/_tmp.png').convert('RGB'))[0:40, 0:40]).resize((160, 160), Image.NEAREST)))
    print('%-22s done at guest frame %d clk %d: icon box mean %d max %d bright pixels %d' % (name, gf(), e.r32(EW + 0x1e00), b.mean(), b.max(), (b.sum(axis=2) > 480).sum()), flush=True)
seg('start', [], 40); seg('idle 1', [], 120); seg('walk', ['CROSS'], 64); seg('idle 2', [], 40)
seg('START', ['START'], 4); seg('paused', [], 40); seg('CROSS', ['CROSS'], 4); seg('after resume', [], 100)
seg('UP', ['UP'], 4); seg('after up', [], 80); seg('R1', ['R1'], 4); seg('after r1', [], 80)
# timeline: runs of equal (mean, bright) values
runs = []
for g, name, mean, mx, br in tl:
    key = (name, mean // 4, br)
    if runs and runs[-1][0] == key: runs[-1][2] = g
    else: runs.append([key, g, g, mean, mx, br])
for key, g0, g1, mean, mx, br in runs: print('  gf %5d..%5d  %-14s icon box mean %3d max %3d bright pixels %3d' % (g0, g1, key[0], mean, mx, br))
sheet = Image.new('RGB', (160 * len(crops), 160))
for i, (n, g, im) in enumerate(crops): sheet.paste(im, (i * 160, 0))
sheet.save(out + '/icon_marks.png'); os.remove(out + '/_tmp.png')
print('marks: ' + ', '.join('%s@%d' % (n, g) for n, g, _ in crops))
