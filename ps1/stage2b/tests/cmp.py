"""cmp.py: PS1 pose shots (HUD off, 640x480 emulator window) against the GBA frames; writes shots/cmp_<tag>.png (GBA | PS1 | diff) and prints
T1 edge F1 (3 px), T2 8x8 block colour error, T3 lower-half ground texel-ish agreement is left to the eye.   python3 -I tests/cmp.py [DIR]"""
import sys, os
import numpy as np
from PIL import Image
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sh = root + '/shots/'
ps = (root + '/' + sys.argv[1] + '/') if len(sys.argv) > 1 else sh      # directory holding ps1_pose<k>.png (and where cmp_<tag>.png go)
PAIRS = [('foot_start', 0, root + '/notes/ref/gba_foot_start.png'), ('street', 1, sh + 'gba_street.png'), ('cross', 2, sh + 'gba_cross.png'),
         ('ramp', 3, sh + 'gba_ramp.png'), ('bridge', 4, sh + 'gba_bridge.png'), ('water', 5, sh + 'gba_water.png')]
def mask():
    m = np.ones((160, 240), bool)
    m[0:46, 150:240] = False; m[0:16, 0:30] = False; m[26:42, 90:150] = False; m[44:114, 160:240] = False; m[70:126, 104:136] = False; m[122:160, :] = False
    return m
def edges(g):
    gx = np.abs(np.diff(g, axis=1))[:-1, :]; gy = np.abs(np.diff(g, axis=0))[:, :-1]
    return (gx + gy) > 40
def dil(e, r=3):
    o = np.zeros_like(e)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1): o |= np.roll(np.roll(e, dy, 0), dx, 1)
    return o
res = {}
for tag, k, gp in PAIRS:
    p = Image.open(ps + 'ps1_pose%d.png' % k).convert('RGB').crop((0, 27, 640, 453)).resize((240, 160), Image.BILINEAR)
    g = Image.open(gp).convert('RGB').resize((240, 160))
    P, G = np.asarray(p, np.float32), np.asarray(g, np.float32); M = mask()
    gp_, gg_ = P.mean(2), G.mean(2); ep, eg = edges(gp_) & M[:-1, :-1], edges(gg_) & M[:-1, :-1]
    tp = (ep & dil(eg)).sum(); prec = tp / max(1, ep.sum()); rec = (eg & dil(ep)).sum() / max(1, eg.sum()); f1 = 2 * prec * rec / max(1e-6, prec + rec)
    blk = []
    for y in range(0, 160, 8):
        for x in range(0, 240, 8):
            if M[y:y + 8, x:x + 8].all(): blk.append(np.abs(P[y:y + 8, x:x + 8].mean((0, 1)) - G[y:y + 8, x:x + 8].mean((0, 1))).mean())
    res[tag] = (f1, float(np.mean(blk)))
    d = np.abs(P - G).clip(0, 255) * M[:, :, None]
    Image.fromarray(np.concatenate([G, P, d], 1).astype(np.uint8)).resize((1440, 320), Image.NEAREST).save(ps + 'cmp_%s.png' % tag)
    print('%-10s T1 edge F1 %.2f   T2 block MAE %.1f/255' % (tag, f1, np.mean(blk)))
