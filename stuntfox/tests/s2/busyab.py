"""fpsab.py's three scenes and windows, but the work counted, not the frames: the busy cycles of a frame of ours (the emulator's
profiler: what the CPU did that was not waiting for the vertical blank), the mean and spread over N windows. The cycles do not
move with where in Payback's traffic a build's window happens to start, as the frame rate does.

    SP=<harness folder> python3 tests/s2/busyab.py ROM ELF [windows]
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


def window(frames, keys):
    k0 = r32(S['key_calls'])
    e.prof_on()
    e.run(frames, list(keys))
    _, _, busy = e.prof_off()
    return busy / frames, (r32(S['key_calls']) - k0) * 60 / frames


def scene(name, keys):
    v = [window(300, keys) for _ in range(n)]
    c = [x[0] for x in v]
    print('%-14s busy cycles/frame mean %d  min %d  max %d   fps mean %.2f   %s' % (
        name, sum(c) / n, min(c), max(c), sum(x[1] for x in v) / n, ' '.join('%d' % x for x in c)))


scene('foot idle', [])
scene('foot walk', ['A'])
e.run(40, ['SELECT'])
e.run(30)
scene('arwing street', [])
