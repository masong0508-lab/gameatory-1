"""fps3's three standard scenes, each in several windows (traffic differs between two builds' start states, so one
window of 300 frames is good to a fraction of an fps at best): the mean and the spread of N windows each.

    SP=<harness folder> python3 tests/s2/fpsab.py ROM ELF [windows]
"""
import os
import struct
import subprocess
import sys

START = os.getcwd()
SP = os.environ['SP']
sys.path.insert(0, SP + '/work')
rom, elf = (os.path.join(START, a) for a in sys.argv[1:3])
n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
os.chdir(SP + '/work')
from retro import Emu          # noqa: E402
from mstate import merged_state  # noqa: E402

S = {l.split()[2]: int(l.split()[0], 16) for l in subprocess.run(['llvm-nm', elf], capture_output=True, text=True).stdout.splitlines()
     if len(l.split()) == 3}
e = Emu('gba', rom)
merged_state(e)


def r32(a):
    return struct.unpack('<i', e.read(a, 4))[0]


def fps(frames=300, keys=()):
    a = r32(S['key_calls'])
    e.run(frames, list(keys))
    return (r32(S['key_calls']) - a) * 60 / frames


def scene(name, keys):
    v = [fps(300, keys) for _ in range(n)]
    print('%-14s mean %.2f  min %.1f  max %.1f   %s' % (name, sum(v) / n, min(v), max(v), ' '.join('%.1f' % x for x in v)))
    return sum(v) / n


scene('foot idle', [])
scene('foot walk', ['A'])
e.run(40, ['SELECT'])
e.run(30)
scene('arwing street', [])
