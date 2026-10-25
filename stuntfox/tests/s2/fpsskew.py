"""The speed gate of a stage-2 package: fps3's scenes (foot idle, foot walk, the Arwing over the street, and the Arwing ten seconds
on) measured over many boots. One 300-frame window is good to about 1.5 fps (traffic and the pedestrians differ between two
builds' start states and drift with the boot's length), so the gate is the mean over N boot skews, each skew a boot a few frames
longer, not a single window: a package may cost at most 0.2 fps per scene on that mean.

    SP=<harness folder> python3 tests/s2/fpsskew.py run ROM ELF [N]            one ROM: the means, per-skew values
    SP=<harness folder> python3 tests/s2/fpsskew.py gate BASE.gba BASE.elf NEW.gba NEW.elf [N]     both, the deltas, exit 1 on a scene
                                                                              that lost more than 0.2 fps (N skews, default 16)
"""
import os
import struct
import subprocess
import sys

SCENES = ('idle', 'walk', 'arwing', 'arwing2')
LIMIT = 0.2


def skews(n):
    return [i * 6 + (i % 3) for i in range(n)]       # (0, 7, 14, 18, ... : not a multiple of any frame cycle of the game)


def run(rom, elf, n):
    sp = os.environ['SP']
    sys.path.insert(0, sp + '/work')
    os.chdir(sp + '/work')
    from retro import Emu
    S = {l.split()[2]: int(l.split()[0], 16) for l in subprocess.run(['llvm-nm', elf], capture_output=True, text=True).stdout.splitlines() if len(l.split()) == 3}
    e = Emu('gba', rom)
    rs = open('st/rsetup.st', 'rb').read()
    K = S['key_calls']

    def r32(a):
        return struct.unpack('<i', e.read(a, 4))[0]

    def fps(frames=300, keys=()):
        a = r32(K)
        e.run(frames, list(keys))
        return (r32(K) - a) * 60 / frames

    def boot(off):
        s = bytearray(rs)
        s[16:28] = e.romdata[0xa0:0xac]
        e.load_state(bytes(s))
        e.run(4 + off, ['A'])
        e.run(600)
        for _ in range(3):
            e.run(4, ['A'])
            e.run(60)
        return e.save_state()

    res = {k: [] for k in SCENES}
    for off in skews(n):
        st = boot(off)
        res['idle'].append(fps())
        res['walk'].append(fps(300, ['A']))
        e.load_state(st)
        e.run(40, ['SELECT'])
        e.run(30)
        res['arwing'].append(fps())
        res['arwing2'].append(fps())
    return res


def mean(v):
    return sum(v) / len(v)


def show(name, res):
    for k in SCENES:
        v = res[k]
        print('%-6s %-8s mean %.2f  min %.1f max %.1f  n %d' % (name, k, mean(v), min(v), max(v), len(v)), flush=True)


if __name__ == '__main__':
    mode = sys.argv[1]
    here = os.getcwd()
    if mode == 'child':
        import json
        rom, elf, n = sys.argv[2], sys.argv[3], int(sys.argv[4])
        print('RES ' + json.dumps(run(rom, elf, n)))
    elif mode == 'run':
        rom, elf = (os.path.join(here, a) for a in sys.argv[2:4])
        show('rom', run(rom, elf, int(sys.argv[4]) if len(sys.argv) > 4 else 16))
    else:
        import json
        n = int(sys.argv[6]) if len(sys.argv) > 6 else 16
        out = []
        for rom, elf in ((sys.argv[2], sys.argv[3]), (sys.argv[4], sys.argv[5])):
            r = subprocess.run([sys.executable, os.path.abspath(__file__), 'child', os.path.join(here, rom), os.path.join(here, elf), str(n)],
                               capture_output=True, text=True)
            line = [l for l in r.stdout.splitlines() if l.startswith('RES ')]
            if not line:
                sys.exit(r.stdout[-1500:] + r.stderr[-1500:])
            out.append(json.loads(line[0][4:]))
        show('base', out[0])
        show('new', out[1])
        bad = 0
        for k in SCENES:
            d = mean(out[1][k]) - mean(out[0][k])
            ok = d >= -LIMIT
            bad += not ok
            print('%s  %-8s new - base = %+.2f fps  (the limit is -%.1f)' % ('PASS' if ok else 'FAIL', k, d, LIMIT), flush=True)
        print('ALL PASS' if not bad else '%d FAILED' % bad)
        sys.exit(1 if bad else 0)
