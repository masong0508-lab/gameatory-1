"""crack.py DIR: counts thin magenta (DEBUG_UNDERLAY) slivers in DIR/ps1_pose*.png (640x480 window, game area 0..639 x 0..479 minus nothing).
Thin = connected component of near-magenta pixels with area < 600 and min bbox side <= 4 (hairline).  Also reports the biggest non-thin magenta area (real far island)."""
import sys, numpy as np
from PIL import Image
from scipy import ndimage as ndi
d = sys.argv[1]; tot = 0
for k in range(8):
    im = np.asarray(Image.open('%s/ps1_pose%d.png' % (d, k)).convert('RGB').crop((0, 0, 640, 480)), np.int32)
    m = (im[:, :, 0] > 190) & (im[:, :, 2] > 190) & (im[:, :, 1] < 90)
    lab, n = ndi.label(m, np.ones((3, 3))); thin = 0; nth = 0
    for i, sl in enumerate(ndi.find_objects(lab)):
        a = (lab[sl] == i + 1).sum(); h = sl[0].stop - sl[0].start; w = sl[1].stop - sl[1].start
        if a < 600 and min(h, w) <= 4: thin += a; nth += 1
    print('pose %d: magenta px %6d  hairline components %3d  hairline px %5d' % (k, m.sum(), nth, thin)); tot += thin
print('total hairline px', tot)
