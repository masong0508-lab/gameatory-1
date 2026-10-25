"""What the stage-2 hooks cost, in cycles a call, from the emulator's PC histogram (design 9.3: s2_tick <= 8k, s2_draw3d
<= 10k, s2_hud <= 4k; with every package still a stub they are a few hundred).

    SP=<harness folder> python3 tests/s2/hookcost.py ROM ELF
"""
import collections
import os
import struct
import subprocess
import sys

START = os.getcwd()
SP = os.environ['SP']
sys.path.insert(0, SP + '/work')
rom, elf = (os.path.join(START, a) for a in sys.argv[1:3])
os.chdir(SP + '/work')
import numpy as np             # noqa: E402
from retro import Emu          # noqa: E402
from mstate import merged_state  # noqa: E402

syms = []
for line in subprocess.run(['llvm-nm', '-S', '--defined-only', elf], capture_output=True, text=True).stdout.splitlines():
    p = line.split()
    if len(p) == 4:
        syms.append((int(p[0], 16) & ~1, int(p[1], 16), p[3]))
S = {n: a for a, _, n in syms}
HK = ['HK_TICK', 'HK_DRAW3D', 'HK_HUD', 'HK_LEVEL', 'HK_MENU', 'HK_KEYS', 'HK_ROOM', 'HK_BANNER']
WATCH = ('s2_gather', 's2_tick', 's2_draw3d', 's2_hud', 's2_room_view', 's2_room_draw', 's2_keys', 's2_menu', 's2_ev',
         'sf_keys', 'keys_main', 's2_ready', 's2_level_enter', 's2_banner_veneer', 'core_dbg', 'stage2_stub')
e = Emu('gba', rom)
merged_state(e)


def hooks():
    return struct.unpack('<8H', e.read(S['hook_count'], 16))


def name(a):
    for lo, sz, n in syms:
        if lo <= a < lo + max(sz, 1):
            return n
    return None


for scene, keys, pre in (('foot idle', [], None), ('foot walk', ['A'], None), ('arwing', [], (40, ['SELECT']))):
    if pre:
        e.run(*pre)
        e.run(60)
    h0 = hooks()
    e.prof_on()
    e.run(300, keys)
    hist, _, busy = e.prof_off()
    h1 = hooks()
    calls = {k: (h1[i] - h0[i] + 65536) & 0xffff for i, k in enumerate(HK)}
    tot = collections.Counter()
    for i in np.nonzero(hist)[0]:
        if i >= 0x403fff:
            continue
        a = 0x03000000 + ((i - 0x400000) << 1) if i >= 0x400000 else 0x08000000 + (i << 1)
        n = name(a) or name(a | 1)
        if n:
            tot[n] += int(hist[i])
    frames = calls['HK_TICK'] or 1
    print('%s: %d frames of ours in 300 (%.1f a second), %d cycles a 60 Hz frame busy' % (scene, frames, frames / 5.0, busy // 300))
    for n in WATCH:
        if tot[n]:
            print('   %-18s %7d cycles a frame of ours' % (n, tot[n] // frames))
    hot = sum(tot[n] for n in ('s2_gather', 's2_tick', 's2_draw3d', 's2_hud', 's2_room_view', 's2_room_draw', 's2_keys', 's2_ready',
                               'keys_main', 's2_ev', 's2_menu', 's2_level_enter', 's2_banner_veneer', 'core_dbg'))
    per_frame = (busy // 300) * 300 // frames            # (cycles of a frame of ours: our frames are about every third 60 Hz frame)
    print('   total stage 2: %d cycles a frame of ours = %.3f%% of the %d the frame takes' % (hot // frames, 100.0 * (hot // frames) / per_frame, per_frame))
    print('   calls in the window:', {k: v for k, v in calls.items() if v})
