#!/usr/bin/env python3
"""ba_montage.py OUT.png TITLE_DIRS...: before/after sheet.  usage: ba_montage.py OUT before_normal before_underlay after_normal after_underlay k0,k1,...
Columns: before, before with the island underlay painted magenta (a hole = magenta where a surface must be), after, after underlay.  Emulator-only screenshots."""
import sys
from PIL import Image, ImageDraw
out, bn, bu, an_, au, ks = sys.argv[1:7]; ks = [int(v) for v in ks.split(',')]
W, H = 400, 300
M = Image.new('RGB', (W * 4, H * len(ks) + 18), (20, 20, 20)); d = ImageDraw.Draw(M)
for i, t in enumerate(('before', 'before (underlay magenta)', 'after', 'after (underlay magenta)')): d.text((i * W + 6, 3), t, fill=(255, 255, 255))
for r, k in enumerate(ks):
    for c, dirn in enumerate((bn, bu, an_, au)):
        M.paste(Image.open('%s/p%02d_a.png' % (dirn, k)).convert('RGB').resize((W, H)), (c * W, 18 + r * H))
M.save(out)
