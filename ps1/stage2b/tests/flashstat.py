"""flashstat.py RAW [W H]: luminance flash check on 60 Hz gray frames of the game window (tests/flashcap.sh).
Per frame: mean luminance and share of 16x16 blocks whose mean changed by more than 60/255 against the previous frame.
A 'flash' pair (WCAG 2.3.1 style): two consecutive opposite-direction changes of mean luminance each >= 10% of full scale (25.5/255) ... also reported:
max |delta mean|, max block-change share, number of frames with a change at all (new picture), and the largest delta of any picture change."""
import sys, numpy as np
f = sys.argv[1]; W, H = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (640, 480)
a = np.fromfile(f, np.uint8); n = a.size // (W * H); a = a[:n * W * H].reshape(n, H, W)
m = a.reshape(n, -1).mean(1)
blk = a[:, :H // 16 * 16, :W // 16 * 16].reshape(n, H // 16, 16, W // 16, 16).mean((2, 4))
chg = np.zeros(n, bool); share = np.zeros(n); dm = np.zeros(n)
for i in range(1, n):
    d = np.abs(blk[i] - blk[i - 1]); chg[i] = (np.abs(a[i].astype(np.int16) - a[i - 1]).mean() > 0.05)
    share[i] = (d > 60).mean(); dm[i] = m[i] - m[i - 1]
pic = np.nonzero(chg)[0]
flash = 0; last = 0
for i in pic:
    if last and np.sign(dm[i]) == -np.sign(dm[last]) and abs(dm[i]) >= 25.5 and abs(dm[last]) >= 25.5: flash += 1
    if dm[i] != 0: last = i
print('frames %d (60 Hz) pictures-changed %d  distinct picture rate %.1f /s' % (n, chg.sum(), chg.sum() / (n / 60.0)))
print('mean luminance min %.1f max %.1f' % (m.min(), m.max()))
print('max |frame-to-frame delta of mean| %.2f /255 (%.1f%%)   99.9th pct %.2f' % (np.abs(dm).max(), np.abs(dm).max() / 2.55, np.percentile(np.abs(dm), 99.9)))
print('max share of 16x16 blocks changing > 60 levels in one frame: %.3f' % share.max())
print('opposite-sign pairs of >=10%% luminance swings: %d' % flash)
# alternating pattern test: lag-1 correlation of the deltas of picture changes
dd = dm[chg]; 
if len(dd) > 3: print('lag-1 autocorr of picture-to-picture mean deltas %.2f (negative = strobing)' % np.corrcoef(dd[:-1], dd[1:])[0, 1])
