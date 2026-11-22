# Session for obrun.py: are short pad presses seen?  On the language screen (no menu assist key is due before GBA frame 360)
# press Down / Up alternately for H emulated frames (H from OB_HOLDS) and watch the runtime's pad word (symbol pad_raw, the
# value of the last pad transfer) during the press and 60 frames after it.  Needs --sym with pad_raw and pad_polls.
import os
HOLDS = [int(x) for x in os.environ.get('OB_HOLDS', '3,6,12,30,60').split(',')]
TRIALS = int(os.environ.get('OB_TRIALS', '6'))
BIT = {'DOWN': 0x0040, 'UP': 0x0010}
def gf(): return S.g('io_cyc') // 280896
S.run(600)
S.until(lambda S: gf() >= 130, 20000)
S.shot('before')
res = {}
k = 0
p0, f0 = S.g('pad_polls'), S.e.frames
for h in HOLDS:
    seen = 0; n = 0
    for t in range(TRIALS):
        if gf() >= 335:
            break
        b = 'DOWN' if k % 2 == 0 else 'UP'; k += 1
        hit = False
        for f in range(h):
            S.run(1, [b]); hit = hit or bool(S.g('pad_raw') & BIT[b])
        for f in range(60):
            S.run(1); hit = hit or bool(S.g('pad_raw') & BIT[b])
        S.run(60)
        seen += hit; n += 1
    res[h] = (seen, n)
    S.mark('taps_%dframes' % h, hold_frames=h, hold_ms=round(h * 1000 / S.e.fps), seen=seen, of=n)
S.shot('after')
S.mark('pad_poll_rate', polls=S.g('pad_polls') - p0, emu_s=round((S.e.frames - f0) / S.e.fps, 1), polls_per_s=round((S.g('pad_polls') - p0) * S.e.fps / max(1, S.e.frames - f0), 2), gf=gf())
