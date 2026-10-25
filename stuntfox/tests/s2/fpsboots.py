"""fps3's three standard scenes over many boots: one boot per build is not a measure (the traffic that fills the city differs
between two builds' start states, which moves a scene by up to 0.7 fps with no code to blame), so each boot waits a different
time (600 + j frames) before the windows, and the mean over the boots of one build is set against the other's.

    SP=.. python3 tests/s2/fpsboots.py run ROM ELF OUT.json [window=600] [j ...]       (from stuntfox/; once per build)
    python3 tests/s2/fpsboots.py cmp base.json new.json                                  (mean, standard error, difference)
"""
import json
import math
import os
import struct
import subprocess
import sys

if sys.argv[1] == 'cmp':
    a, b = (json.load(open(p)) for p in sys.argv[2:4])
    bad = 0
    for sc in a:
        x, y = list(a[sc].values()), list(b[sc].values())

        def ms(v):
            m = sum(v) / len(v)
            return m, math.sqrt(sum((t - m) ** 2 for t in v) / max(len(v) - 1, 1) / len(v))
        (m1, s1), (m2, s2) = ms(x), ms(y)
        se = math.sqrt(s1 * s1 + s2 * s2)
        print('%-8s base %.2f (se %.2f)  new %.2f (se %.2f)  new - base %+.2f (se %.2f, %d boots)' % (sc, m1, s1, m2, s2, m2 - m1, se, len(x)))
        bad += m2 - m1 < -0.2 - 2 * se
    sys.exit(1 if bad else 0)

START = os.getcwd()
SP = os.environ['SP']
sys.path.insert(0, SP + '/work')
rom, elf, out = sys.argv[2], sys.argv[3], os.path.join(START, sys.argv[4])
rom, elf = os.path.join(START, rom), os.path.join(START, elf)
W = int(sys.argv[5]) if len(sys.argv) > 5 else 600
jit = [int(a) for a in sys.argv[6:]] or list(range(0, 211, 7))
os.chdir(SP + '/work')
from retro import Emu  # noqa: E402

S = {l.split()[2]: int(l.split()[0], 16) for l in subprocess.run(['llvm-nm', elf], capture_output=True, text=True).stdout.splitlines()
     if len(l.split()) == 3}
e = Emu('gba', rom)
setup = open('st/rsetup.st', 'rb').read()
res = {'idle': {}, 'walk': {}, 'street': {}}


def r32(a):
    return struct.unpack('<i', e.read(a, 4))[0]


def cnt(keys):
    a = r32(S['key_calls'])
    e.run(W, list(keys))
    return (r32(S['key_calls']) - a) * 60 / W


for j in jit:
    s = bytearray(setup)
    s[16:28] = e.romdata[0xa0:0xac]
    e.load_state(bytes(s))
    e.run(4, ['A'])
    e.run(600 + j)
    for k in range(3):
        e.run(4, ['A'])
        e.run(60)
    e.run(30)
    res['idle'][j] = cnt([])
    res['walk'][j] = cnt(['A'])
    e.run(40, ['SELECT'])
    e.run(30)
    res['street'][j] = cnt([])
    json.dump(res, open(out, 'w'))
    print(j, ' '.join('%s %.1f' % (k, v[j]) for k, v in res.items()), flush=True)
