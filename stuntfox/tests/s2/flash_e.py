"""The flash check (flashcheck.py's rules: no more than 3 flashes in any second, whole screen, general and red) on the
mission engine's own sessions: the act's start banner and its beacon, a banner for an act completed, a failed one,
the line's status turning amber at 10 s of a challenge, a ring run flown through, and the retry card.

    SP=<harness folder> python3 tests/s2/flash_e.py ROM ELF [outprefix]      (from stuntfox/)
"""
import os
import struct
import subprocess
import sys

START = os.getcwd()
SP = os.environ['SP']
ROMP, ELFP = (os.path.join(START, a) for a in sys.argv[1:3])
OUT = sys.argv[3] if len(sys.argv) > 3 else os.path.join(START, 'build', 'flash_e')
sys.path.insert(0, SP + '/work')
os.chdir(SP + '/work')
# flashcheck.py's measuring functions (lum, the rules), without its own sessions
src = open(SP + '/work/flashcheck.py').read()
head = src[:src.index('ok = True')].replace("ROM = sys.argv[1]", "ROM = %r" % ROMP).replace(
    "OUT = sys.argv[2] if len(sys.argv) > 2 else '../flash'", "OUT = %r" % OUT)
sys.argv = ['flashcheck', ROMP, OUT]
exec(compile(head, 'flashcheck_head', 'exec'))             # defines Emu, merged_state, lum, session, AREA ...

S = {l.split()[2]: int(l.split()[0], 16) for l in subprocess.run(['llvm-nm', ELFP], capture_output=True, text=True).stdout.splitlines()
     if len(l.split()) == 3}
MAGIC = 0x42443253


def mailbox(e):
    def mb(cmd, arg=0):
        a = S['s2_dbg']
        e.write8(a + 4, cmd & 255), e.write8(a + 5, cmd >> 8), e.write8(a + 6, arg & 255), e.write8(a + 7, arg >> 8)
        e.write32(a, MAGIC)
    return mb


def tele_man(e, cx, cy):
    for a in (0x2008df8, 0x2009398, 0x2009478, 0x2009484):
        e.write32(a, int(cx * 2048)), e.write32(a + 4, int(cy * 2048))


def tele_ship(e, p, f=(16384, 0, 0)):
    B = S['ship']
    for i in range(3):
        e.write32(B + 4 * i, (p[i] * 256) & 0xffffffff)
        e.write32(B + 12 + 4 * i, 0)
    r = [f[2], 0, -f[0]]
    for i, v in enumerate(r):
        e.write32(B + 24 + 4 * i, v & 0xffffffff)
    for i, v in enumerate((0, 16384, 0)):
        e.write32(B + 36 + 4 * i, v & 0xffffffff)
    for i, v in enumerate(f):
        e.write32(B + 48 + 4 * i, v & 0xffffffff)


def session2(name, plan, start=None):
    """flashcheck.session, with plan steps that are callables(e) (the mailbox, a teleport) between the runs of frames."""
    e = Emu('gba', ROMP)
    merged_state(e)
    mb = mailbox(e)
    if start:
        start(e, mb)
    prev = prevred = None
    events, reds, big, f = [], [], [], 0
    for n, keys in plan:
        if callable(n):
            n(e, mb)
            continue
        for _ in range(n):
            e.run(1, keys)
            f += 1
            L, R = lum(e.frame)
            if prev is not None:
                d = L - prev
                dark = np.minimum(L, prev) < 0.8
                up, dn = np.mean((d >= 0.1) & dark), np.mean((d <= -0.1) & dark)
                if up >= AREA: events.append((f, 1))
                if dn >= AREA: events.append((f, -1))
                rup, rdn = np.mean(R & ~prevred), np.mean(prevred & ~R)
                if rup >= AREA: reds.append((f, 1))
                if rdn >= AREA: reds.append((f, -1))
                big.append((max(up, dn), f))
            prev, prevred = L, R

    def worst(ev):
        flashes = [ev[i][0] for i in range(1, len(ev)) if ev[i][1] != ev[i - 1][1]]
        m = 0
        for i, t in enumerate(flashes):
            m = max(m, sum(1 for u in flashes[i:] if u - t < 60))
        return m, flashes
    m, fl = worst(events)
    mr, flr = worst(reds)
    big.sort(reverse=True)
    print('%-12s frames %5d  transitions %3d  flashes %3d  most in 1 s: %d  red: %d  %s' %
          (name, f, len(events), len(fl), m, mr, 'FAIL' if m > 3 or mr > 3 else 'ok'))
    print('             biggest changes (share of screen, frame):', ', '.join('%.2f@%d' % b for b in big[:4]))
    e.frame.save('%s_%s_end.png' % (OUT, name))
    return m <= 3 and mr <= 3


def go(*a):
    return lambda e, mb: mb(*a)


def man(x, y):
    return lambda e, mb: tele_man(e, x, y)


def ship(p):
    return lambda e, mb: tele_ship(e, p)


def board(e, mb):
    e.run(40, ['SELECT'])
    e.run(30)


def amber_now(e, mb):                  # (the challenge's clock: 8 s from its limit, as it would be after 52 s)
    t = struct.unpack('<I', e.read(0x02001e00, 4))[0]
    a = S['ms_run']                    # (MisRun: t_start +16, t_step +20, timer +24)
    e.write32(a + 16, (t - 52 * 30) & 0xffffffff)
    e.write32(a + 20, (t - 52 * 30) & 0xffffffff)
    e.write32(a + 24, 8 * 30)


ok = True
# an act: standing in its beacon (the title banner, the line, the beacon), then flown to its end by the autopilot (ACT COMPLETE)
ok &= session2('act', [(60, []), (man(14.5, 58.5), 0), (200, []), (go(4, 1), 0), (900, []), (go(4, 0), 0), (120, [])])
# a failed act: the banner, the retry card, the beacon again
ok &= session2('fail', [(60, []), (go(1, 0), 0), (60, []), (go(3), 0), (240, [])])
# the challenge's clock: the status turns amber once, 10 s before the end, and the limit ends it (CHALLENGE FAILED)
ok &= session2('amber', [(60, []), (go(1, 1), 0), (30, []), (amber_now, 0), (520, [])])
# the ring run, flown through the first rings
ring_steps = [(60, []), (board, 0), (go(1, 4), 0), (20, [])]
for x, y, h in ((64, 70, 1700), (72, 64, 2000)):
    ring_steps += [(ship(((x - 3) * 1024, h, y * 1024)), 0), (60, [])]
ok &= session2('rings', ring_steps)
print('ALL OK' if ok else 'SOME FAILED')
sys.exit(0 if ok else 1)
