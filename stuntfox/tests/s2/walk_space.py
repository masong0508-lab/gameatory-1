"""The frame rate in space, base against new, over several boots of each. The Arwing is put at the same place and heading in each
build (the moon and its rocks are the walk's own: the scenes that have it in view show what it costs, the rest must cost nothing),
the raiders cleared and the medals taken (which are out, and where the ones over the city lie, depends on the random numbers a boot
drew, not on the build). One boot of a build is not a measure: its start state differs from the other build's (the ship's attitude, the
traffic under it), which moves a scene by a few fps with no code to blame. So each boot waits a different time before the scene, and
the means over the boots are compared, with their standard error.

    SP=.. ROM=x.gba ELF=x.elf OUT=x.json [BOOTS=0,17,34,...] [SCENES=all|key] python3 tests/s2/walk_space.py run     (from stuntfox/; per build)
    python3 tests/s2/walk_space.py cmp base.json new.json      (the table and what the moon itself costs, as the
                                                                 difference to the same place turned away; exits 1 if that is over 0.2 fps
                                                                 for a moon 14000 or more off by more than twice the error, or the game stopped)
Each scene is three windows of 300 frames (fps, as fps3 counts it) and one of 150 under the profiler (cycles a tick).
"""
import json
import math
import subprocess
import sys

if sys.argv[1:2] == ['cmp']:
    a, b = (json.load(open(p)) for p in sys.argv[2:4])
    bad = 0

    def ms(v):
        m = sum(v) / len(v)
        return m, math.sqrt(sum((t - m) ** 2 for t in v) / max(len(v) - 1, 1) / len(v))
    def med(v):
        v = sorted(v)
        return v[len(v) // 2]
    print('%-34s %6s %6s %6s %5s   %9s %9s %7s' % ('scene', 'base', 'new', 'diff', 'se', 'cyc base', 'cyc new', 'added'))
    for k in a:
        (x, sx), (y, sy) = ms(a[k]['fps']), ms(b[k]['fps'])
        cb, cn = med(a[k]['cyc']), med(b[k]['cyc'])      # (the median: a boot that stalls shows as a wild count, and it is a fault to look into, not an average)
        se = math.sqrt(sx * sx + sy * sy)
        flag = ''
        if a[k]['far'] and y - x < -0.2 - 2 * se:
            flag = '  (raw: boots differ between the builds, see below)'
        if b[k].get('stall'):
            flag, bad = flag + '  <-- the game stopped in %d boots' % b[k]['stall'], bad + 1
        print('%-34s %6.1f %6.1f %+6.1f %5.2f   %9.0f %9.0f %+7.0f%s' % (k, x, y, y - x, se, cb, cn, cn - cb, flag))
    print('\nwhat the moon itself costs: (new - base) looking at it, less (new - base) in the same place turned away (boot differences between the builds cancel)')
    for k in a:
        if k + ' away' in a or (k == 'station, looking at the moon'):
            ctl = k + ' away' if k + ' away' in a else 'station, facing away'
            (x, sx), (y, sy) = ms(a[k]['fps']), ms(b[k]['fps'])
            (x0, s0), (y0, s1) = ms(a[ctl]['fps']), ms(b[ctl]['fps'])
            d = (y - x) - (y0 - x0)
            se = math.sqrt(sx * sx + sy * sy + s0 * s0 + s1 * s1)
            flag = ''
            if a[k]['far'] and d < -0.2 - 2 * se:
                flag, bad = '  <-- over 0.2 fps', bad + 1
            print('%-34s %+6.2f fps  se %.2f%s' % (k, d, se, flag))
    sys.exit(1 if bad else 0)

sys.argv = sys.argv[:1] + sys.argv[2:]
import h
from h import *

BOOTS = [int(a) for a in os.environ.get('BOOTS', '0').split(',')]
B = S['ship']
KC = S['key_calls']
FOES = [l.split() for l in subprocess.run(['llvm-nm', '-S', ELF], capture_output=True, text=True).stdout.splitlines() if l.split()[-1:] == ['foes']][0]
FOES = (int(FOES[0], 16), int(FOES[1], 16))
pin = None


def setv(a, v):
    for i in range(3):
        e.write32(a + 4 * i, int(v[i]) & 0xffffffff)


def put(full=False):
    p, f = pin
    for i in range(0, FOES[1], 4):
        e.write32(FOES[0] + i, 0)
    e.write8(S['medals'], 255)
    e.write8(S['medals'] + 1, 15)
    setv(B, (p[0] << 8, p[1] << 8, p[2] << 8))
    if full:
        setv(B + 12, (0, 0, 0))
        setv(B + 24, (-f[2], 0, f[0]))
        setv(B + 36, (0, 16384, 0))
        setv(B + 48, f)


def fps(n=300, prof=False):
    """The Arwing cruises on its own (and the moon is solid: it would fly into it within a window), so its place, only its place, is put
    back every 5 frames. With prof, the cycles a tick takes instead (a count, not a rate that is rounded to whole frames)."""
    a = r32(KC)
    if prof:
        e.prof_on()
    for _ in range(n // 5):
        put()
        e.run(5)
    if prof:
        _, _, busy = e.prof_off()
        return busy / max(r32(KC) - a, 1)
    return (r32(KC) - a) * 60 / n


res = {}
for jit in BOOTS:
    merged_state(e)
    e.run(jit)
    run(30)
    board_now()
    base = e.save_state()
    sx, sy, sz = [r32(S['station_pos'] + 4 * i) for i in range(3)]
    mx, my, mz = sx - 17000, sy + 2500, sz + 13000        # the moon's middle (spacewalk.c)

    def toward(dist, ang):
        a = math.radians(ang)
        return (int(mx + math.sin(a) * dist), my, int(mz + math.cos(a) * dist)), (int(-math.sin(a) * 16384), 0, int(-math.cos(a) * 16384))

    def scene(name, p, f, far):
        global pin
        e.load_state(base)
        run(2)
        pin = (p, f)
        put(True)
        for _ in range(18):
            put()
            e.run(5)
        v = sum(fps() for _ in range(3)) / 3
        c = fps(150, True)
        r = res.setdefault(name, dict(fps=[], cyc=[], far=far, stall=0))
        r['fps'].append(v), r['cyc'].append(c)
        r['stall'] += v < 8 or c > 4e6          # (the game stopped: not a cost but a fault, and counted as one)
        print('boot +%-3d %-34s %5.1f %8.0f cycles a tick' % (jit, name, v, c), flush=True)

    key = os.environ.get('SCENES', 'all') == 'key'
    scene('y 26000 over the city', (sx - 30000, 26000, sz + 30000), (0, 0, -16384), 1)
    scene('station dock approach', (sx + 3000, sy - 140, sz + 9000), (0, 0, -16384), 1)
    scene('station, looking at the moon', (sx + 2000, sy, sz + 3000), (-11585, 0, 11585), 1)
    scene('station, facing away', (sx + 2000, sy, sz + 3000), (11585, 0, -11585), 0)            # (the control of the one above)
    for dist in (4000, 6000, 9000, 11000, 14000, 17000, 20000, 27000, 34000):
        for name, ang in (('+z', 0), ('diag', 45), ('-x', 270)):
            if key and (dist < 14000 or dist == 27000 or name == '+z'):
                continue
            p, f = toward(dist, ang)
            scene('moon ahead %5d %s' % (dist, name), p, f, dist >= 14000)
            if key and name == 'diag' and dist in (14000, 20000, 34000):                      # (the same place, turned away: what the scene costs without the moon)
                scene('moon ahead %5d %s away' % (dist, name), p, (-f[0], 0, -f[2]), 0)
    for dist in (8000, 16000, 30000):                      # the same places, facing away
        if key and dist == 8000:
            continue
        p, f = toward(dist, 0)
        scene('moon behind %5d' % dist, p, (-f[0], 0, -f[2]), dist >= 14000)
    json.dump(res, open(os.path.join(START, os.environ['OUT']), 'w'))
