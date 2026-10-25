"""fps3's three standard scenes on one build, from several start states (the same ROM started EXTRA frames later: traffic and
pedestrians differ from one to the next, which moves a scene by up to 1.5 fps; averaging over the offsets, the same for two builds,
brings two builds to a few tenths).

    SP=<harness folder> python3 tests/s2/fpsab_off.py ROM ELF [windows] [offsets...]
"""
import os
import struct
import subprocess
import sys

START = os.getcwd()
SP = os.environ['SP']
sys.path.insert(0, SP + '/work')
rom, elf = (os.path.join(START, a) for a in sys.argv[1:3])
n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
offs = [int(a) for a in sys.argv[4:]] or [0, 5, 17, 40]
os.chdir(SP + '/work')
from retro import Emu          # noqa: E402
from mstate import merged_state  # noqa: E402

S = {l.split()[2]: int(l.split()[0], 16) for l in subprocess.run(['llvm-nm', elf], capture_output=True, text=True).stdout.splitlines()
     if len(l.split()) == 3}
res = {'foot idle': [], 'foot walk': [], 'arwing street': []}
for off in offs:
    e = Emu('gba', rom)
    merged_state(e)
    e.run(off)

    def r32(a):
        return struct.unpack('<i', e.read(a, 4))[0]

    def fps(frames=300, keys=()):
        a = r32(S['key_calls'])
        e.run(frames, list(keys))
        return (r32(S['key_calls']) - a) * 60 / frames

    def scene(name, keys):
        v = [fps(300, keys) for _ in range(n)]
        res[name] += v
        print('offset %3d %-14s mean %.2f   %s' % (off, name, sum(v) / n, ' '.join('%.1f' % x for x in v)), flush=True)

    scene('foot idle', [])
    scene('foot walk', ['A'])
    e.run(40, ['SELECT'])
    e.run(30)
    scene('arwing street', [])
for k, v in res.items():
    print('%-14s mean %.2f over %d windows (min %.1f max %.1f)' % (k, sum(v) / len(v), len(v), min(v), max(v)))
