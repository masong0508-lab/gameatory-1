# Session for obrun.py: does the picture change only when the program presents a frame?  For OB_FRAMES emulated frames the
# picture of every emulated frame is hashed.  Counted: picture changes, presents (symbol g_pres), picture changes in a frame
# in which g_pres did not move since the previous change ("extra": a half-drawn or torn frame became visible, or the program
# draws into the displayed buffer), and all-black pictures between two non-black ones (flicker).  Needs --sym with g_pres.
import hashlib, os
N = int(os.environ.get('OB_FRAMES', '4200'))
SKIP = int(os.environ.get('OB_SKIP', '600'))
if not S.a.load:
    S.run(SKIP)
last_h = None; last_p = S.g('g_pres'); changes = extra = black = 0; was_black = False; seen_picture = False; sizes = {}
p0 = last_p; extra_frames = []
for f in range(N):
    S.run(1)
    im = S.e.image()
    if im is None:
        continue
    sizes[im.size] = sizes.get(im.size, 0) + 1
    raw = im.convert('RGB').tobytes()
    h = hashlib.md5(raw).digest()
    isblack = max(raw[::7]) < 8
    if h != last_h:
        changes += 1
        p = S.g('g_pres')
        if last_h is not None and p == last_p:
            extra += 1
            if len(extra_frames) < 12:
                extra_frames.append(S.e.frames)
                if len(extra_frames) <= 3:
                    S.shot('extra%d' % len(extra_frames))
        last_p = p; last_h = h
        if isblack and seen_picture:
            black += 1
        seen_picture = seen_picture or not isblack
S.shot('end')
S.mark('flicker', frames=N, picture_changes=changes, presents=S.g('g_pres') - p0, extra_changes=extra, extra_at_frames=extra_frames,
       black_pictures_after_first_picture=black, sizes={'%dx%d' % k: v for k, v in sizes.items()})
