#!/usr/bin/env python3
"""ob_compare.py OUT.png LABEL[,LABEL...] NAME=RUNDIR [NAME=RUNDIR ...]: side-by-side sheet of the screenshots that obrun.py
sessions took at the same guest moment (same label) on different cores; one row per label, one column per run.  Each
picture is shown at its native size on a 352x240 cell (nothing is rescaled, so resolution and borders stay comparable).
Prints, per label, the frame size of every run and the mean absolute RGB difference to the first run after the best
integer alignment (search +-24 px), computed on the overlap."""
import glob, os, sys
from PIL import Image, ImageDraw, ImageChops, ImageStat

def find(run, label):
    g = glob.glob('%s/shots/*_%s.png' % (run, label))
    return g[0] if g else None

def best_diff(a, b):
    best = None
    for dx in range(-24, 25, 1):
        for dy in range(-16, 17, 1):
            x0, y0 = max(0, dx), max(0, dy)
            x1, y1 = min(a.width, b.width + dx), min(a.height, b.height + dy)
            if x1 - x0 < 200 or y1 - y0 < 150: continue
            ca = a.crop((x0, y0, x1, y1)); cb = b.crop((x0 - dx, y0 - dy, x1 - dx, y1 - dy))
            d = sum(ImageStat.Stat(ImageChops.difference(ca.resize((80, 60)), cb.resize((80, 60)))).mean) / 3
            if best is None or d < best[0]: best = (d, dx, dy, x1 - x0, y1 - y0)
    d, dx, dy, w, h = best
    x0, y0 = max(0, dx), max(0, dy)
    ca = a.crop((x0, y0, x0 + w, y0 + h)); cb = b.crop((x0 - dx, y0 - dy, x0 - dx + w, y0 - dy + h))
    diff = ImageChops.difference(ca, cb)
    mean = sum(ImageStat.Stat(diff).mean) / 3
    big = sum(1 for p in diff.getdata() if p[0] + p[1] + p[2] > 24) * 100.0 / (w * h)
    return mean, big, dx, dy, w, h

out, labels = sys.argv[1], sys.argv[2].split(',')
runs = [a.split('=', 1) for a in sys.argv[3:]]
CW, CH = 352, 256
sheet = Image.new('RGB', (CW * len(runs), CH * len(labels)), (40, 0, 60))
dr = ImageDraw.Draw(sheet)
for r, lab in enumerate(labels):
    ims = []
    for c, (name, run) in enumerate(runs):
        p = find(run, lab)
        im = Image.open(p).convert('RGB') if p else None
        ims.append(im)
        if im:
            sheet.paste(im, (c * CW, r * CH + 14))
        dr.text((c * CW + 2, r * CH + 1), '%s  %s  %s' % (name, lab, '%dx%d' % im.size if im else 'MISSING'), fill=(255, 255, 0))
    line = '%-18s ' % lab + ' '.join('%s %s' % (n, '%dx%d' % im.size if im else '-') for (n, _), im in zip(runs, ims))
    if ims[0]:
        for (n, _), im in zip(runs[1:], ims[1:]):
            if im:
                m, big, dx, dy, w, h = best_diff(ims[0], im)
                line += ' | %s vs %s: mean abs diff %.2f, %.1f %% pixels differ by more than 24 (shift %+d,%+d, overlap %dx%d)' % (n, runs[0][0], m, big, dx, dy, w, h)
    print(line)
sheet.save(out)
