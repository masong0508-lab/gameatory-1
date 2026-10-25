"""fps3's three standard scenes, two builds against each other, with the noise measured instead of assumed.

Two runs of the same scene part ways as soon as one of them takes a different number of cycles anywhere: traffic and
pedestrians then differ, and a scene moves by up to a fps without any cost in the code. So the cost of a build is looked for
in three ways that do not rest on one run each:

  ab     the scenes on both builds from many start states (the same ROM started OFFSET frames later), the difference taken
         per start state, its mean and its standard error over the start states (not over the windows of one run: those
         share their traffic), and the same for the SECOND build against itself started one frame later, which is the
         floor the first difference has to be compared with.
  toggle one build, content on against content off from the same saved state (the blob's pointer cleared in RAM): the
         only thing that differs is the stage-2 work, so the difference over many states is the cost of the content and
         nothing else but the divergence.
  cost   the CPU cycles the build is busy over the first TICKS ticks of Payback after a saved state (before the two runs
         part ways), in total and in the functions of the stage-2 files, per scene, with the player left where the scene
         puts him, and standing in a challenge's beacon (the worst case: the line and the beacon drawn).

    SP=<harness folder> python3 tests/s2/fpsab_pair.py ab     ROM_A ELF_A ROM_B ELF_B [WINDOWS] [OFFSETS comma list]
    SP=<harness folder> python3 tests/s2/fpsab_pair.py toggle ROM ELF [WINDOWS] [OFFSETS]
    SP=<harness folder> python3 tests/s2/fpsab_pair.py cost   ROM ELF [TICKS] [OFFSETS]
"""
import math
import os
import struct
import subprocess
import sys

START = os.getcwd()
SP = os.environ['SP']
sys.path.insert(0, SP + '/work')
mode = sys.argv[1]
os.chdir(SP + '/work')
from retro import Emu          # noqa: E402
from mstate import merged_state  # noqa: E402

OFFS = [0, 3, 7, 12, 17, 23, 30, 40, 51, 63, 76, 90, 105, 121, 138, 156]
SCENES = ('foot idle', 'foot walk', 'arwing street')
OBJS = ('mission.c.o', 'msn_draw.c.o', 'hudline.c.o', 's2core.c.o')


def path(p):
    return p if os.path.isabs(p) else os.path.join(START, p)


def syms(elf):
    out = {}
    for line in subprocess.run(['llvm-nm', '-S', '--defined-only', elf], capture_output=True, text=True).stdout.splitlines():
        p = line.split()
        if len(p) == 4:
            out[p[3]] = (int(p[0], 16) & ~1, int(p[1], 16))
        elif len(p) == 3:
            out[p[2]] = (int(p[0], 16) & ~1, 0)
    return out


class Run:
    def __init__(self, rom, elf, off):
        self.rom, self.S = path(rom), syms(path(elf))
        self.e = Emu('gba', self.rom)
        merged_state(self.e)
        self.e.run(off)

    def r32(self, a):
        return struct.unpack('<i', self.e.read(a, 4))[0]

    def fps(self, frames=300, keys=()):
        k = self.S['key_calls'][0]
        a = self.r32(k)
        self.e.run(frames, list(keys))
        return (self.r32(k) - a) * 60 / frames

    def scenes(self, n):
        out = {}
        out['foot idle'] = [self.fps() for _ in range(n)]
        out['foot walk'] = [self.fps(300, ['A']) for _ in range(n)]
        self.e.run(40, ['SELECT'])
        self.e.run(30)
        out['arwing street'] = [self.fps() for _ in range(n)]
        return out

    def first_beacon(self):
        """(x, y) in cells of the start beacon of the first challenge of map 0, read from the blob in the ROM."""
        S, e = self.S, self.e
        head = bytes(e.read(S['s2_blob'][0], 56))
        nmis, off_mis, off_place = struct.unpack_from('<H', head, 8)[0], struct.unpack_from('<I', head, 20)[0], struct.unpack_from('<I', head, 28)[0]
        mis = bytes(e.read(S['s2_blob'][0] + off_mis, nmis * 24))
        for i in range(nmis):
            f = struct.unpack_from('<HBBBBHHHHBBHHHH', mis, i * 24)
            if f[1] == 0 and f[2] == 2 and f[11] != 0xffff:
                x8, y8 = struct.unpack_from('<HH', bytes(e.read(S['s2_blob'][0] + off_place + f[11] * 8, 8)), 0)
                return x8 / 8.0, y8 / 8.0
        raise SystemExit('no challenge on map 0')

    def tele(self, cx, cy):
        for a in (0x2008df8, 0x2009398, 0x2009478, 0x2009484):
            self.e.write32(a, int(cx * 2048))
            self.e.write32(a + 4, int(cy * 2048))
        self.e.write32(0x02009394 + 4, int(cx * 2048))
        self.e.write32(0x02009394 + 8, int(cy * 2048))

    def content_off(self):
        self.e.write32(self.S['H'][0], 0)             # (mission.c's blob pointer and state: ms_tick returns at once, as with no blob)
        self.e.write8(self.S['H_state'][0], 2)


def stats(d):
    n = len(d)
    m = sum(d) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1)) if n > 1 else 0.0
    return m, sd, sd / math.sqrt(n) if n else 0.0


def report(name, rows, label):
    """rows: [(offset, {scene: mean})] for two arms: dict arm -> rows"""
    for sc in SCENES:
        diffs = [b[sc] - a[sc] for (_, a), (_, b) in zip(rows[0], rows[1])]
        m, sd, se = stats(diffs)
        ma = sum(a[sc] for _, a in rows[0]) / len(rows[0])
        mb = sum(b[sc] for _, b in rows[1]) / len(rows[1])
        print('%-6s %-14s %s %.2f -> %.2f   diff %+.2f  sd %.2f over %d start states, se %.2f   (min %+.1f max %+.1f)'
              % (name, sc, label, ma, mb, m, sd, len(diffs), se, min(diffs), max(diffs)), flush=True)


def arg_offs(i):
    return [int(x) for x in sys.argv[i].split(',')] if len(sys.argv) > i else OFFS


if mode == 'ab':
    ra, ea, rb, eb = sys.argv[2:6]
    n = int(sys.argv[6]) if len(sys.argv) > 6 else 2
    offs = arg_offs(7)
    rows = {'A': [], 'B': [], 'B1': []}
    for off in offs:
        for arm, (r, el, o) in (('A', (ra, ea, off)), ('B', (rb, eb, off)), ('B1', (rb, eb, off + 1))):
            run = Run(r, el, o)
            res = run.scenes(n)
            rows[arm].append((off, {k: sum(v) / len(v) for k, v in res.items()}))
        print('offset %3d  ' % off + '  '.join('%s %s' % (arm, ' '.join('%.2f' % rows[arm][-1][1][sc] for sc in SCENES)) for arm in ('A', 'B', 'B1')), flush=True)
    report('A->B', [rows['A'], rows['B']], 'A %s B %s' % (os.path.basename(ra), os.path.basename(rb)))
    report('floor', [rows['B'], rows['B1']], 'B at off, B at off+1')
elif mode == 'toggle':
    rom, elf = sys.argv[2:4]
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    offs = arg_offs(5)
    rows = {'on': [], 'off': []}
    for off in offs:
        base = Run(rom, elf, off)
        st = base.e.save_state()
        for arm in ('on', 'off'):
            base.e.load_state(st)
            if arm == 'off':
                base.content_off()
            res = base.scenes(n)
            rows[arm].append((off, {k: sum(v) / len(v) for k, v in res.items()}))
        print('offset %3d  on %s  off %s' % (off, ' '.join('%.2f' % rows['on'][-1][1][sc] for sc in SCENES),
                                             ' '.join('%.2f' % rows['off'][-1][1][sc] for sc in SCENES)), flush=True)
    report('on-off', [rows['off'], rows['on']], 'content off -> on')
elif mode == 'cost':
    import numpy as np
    rom, elf = sys.argv[2:4]
    ticks = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    offs = arg_offs(5)
    S = syms(path(elf))
    names = {}
    for o in OBJS:
        for line in subprocess.run(['llvm-nm', '-S', '--defined-only', os.path.join(START, 'build', 'merge', o)], capture_output=True, text=True).stdout.splitlines():
            p = line.split()
            if len(p) == 4 and p[2] in 'tT' and p[3] in S and S[p[3]][1] == int(p[1], 16):
                names[p[3]] = o
    funcs = sorted((S[n][0], S[n][1], n) for n in names)

    def where(i):
        a = 0x03000000 + ((i - 0x400000) << 1) if i >= 0x400000 else 0x08000000 + (i << 1)
        for lo, sz, n in funcs:
            if lo <= a < lo + max(sz, 2):
                return n
        return None
    mpos = S['s2f'][0]
    kc = S['key_calls'][0]
    for scene, keys, pre, beacon in (('foot idle', [], None, False), ('foot walk', ['A'], None, False), ('arwing street', [], (40, ['SELECT']), False),
                                     ('foot in a beacon', [], None, True)):
        tot = {'on': [], 'off': []}
        cpu = {'on': [], 'off': []}
        share = {}
        armed_frames, all_frames = [0], [0]
        for off in offs:
            run = Run(rom, elf, off)
            e = run.e
            if pre:
                e.run(*pre)
                e.run(60)
            if beacon:
                bx, by = run.first_beacon()
                run.tele(bx - 3, by)                     # (3 cells off the first challenge's beacon on map 0: the roam scan arms it, the line and the beacon are up)
                e.run(60)
                armed = run.r32(S['ms_run'][0] + 4)
                assert armed == 1, 'the beacon did not arm (state %d)' % armed
            st = e.save_state()
            for arm in ('on', 'off'):
                e.load_state(st)
                if arm == 'off':
                    run.content_off()
                e.prof_on(bps=[S['sf_keys'][0]])             # (a stamp of the cycle counter at each tick's key read: the ticks' lengths exactly)
                k0 = run.r32(kc)
                n = 0
                while run.r32(kc) - k0 < ticks + 2 and n < 600:
                    e.run(1, list(keys))
                    n += 1
                    armed_frames[0] += run.r32(S['ms_run'][0] + 4) == 1
                    all_frames[0] += 1
                hist, bplog, busy = e.prof_off()
                nt = max(1, run.r32(kc) - k0)
                stamps = [c for _, c in bplog]
                span = (stamps[-1] - stamps[1]) / (len(stamps) - 2) if len(stamps) > 2 else float('nan')     # (whole ticks between the first stamps after the start and the last)
                tot[arm].append(span)
                cpu[arm].append(span)
                if arm == 'on':
                    for i in np.nonzero(hist)[0]:
                        if i < 0x404000:
                            w = where(i)
                            if w:
                                share[w] = share.get(w, 0) + int(hist[i]) / nt / len(offs)
        print('%-16s a beacon armed in %d of %d frames' % (scene, armed_frames[0], all_frames[0]))
        a = sum(tot['off']) / len(tot['off'])
        b = sum(tot['on']) / len(tot['on'])
        d = [y - x for x, y in zip(tot['off'], tot['on'])]
        m, sd, se = stats(d)
        ca, cb = sum(cpu['off']) / len(cpu['off']), sum(cpu['on']) / len(cpu['on'])
        cm, csd, cse = stats([y - x for x, y in zip(cpu['off'], cpu['on'])])
        print('%-16s cycles a tick, first %d ticks of %d start states: content off %.0f  on %.0f  diff %+.0f (%+.3f%%)  se %.0f'
              % (scene, ticks, len(d), ca, cb, cb - ca, 100.0 * (cb - ca) / ca, cse), flush=True)
        top = sorted(share.items(), key=lambda kv: -kv[1])[:8]
        print('     of which in the stage-2 files (exact, content on), a tick: ' + ', '.join('%s %.0f' % kv for kv in top) + '; all %.0f = %.2f%% of a tick' % (sum(share.values()), 100.0 * sum(share.values()) / cb), flush=True)
else:
    sys.exit(__doc__)
