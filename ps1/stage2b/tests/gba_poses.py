"""gba_poses.py: teleport Payback's man in the GBA build to chosen street spots, let the chase camera settle, record the
camera and a screenshot (240x160).  Output: shots/gba_<tag>.png and build/gba_poses.json.   python3 -I (needs numpy, libmgba shim)."""
import sys, struct, json, os
SP = '/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
sys.path.insert(0, SP + '/work')
from emu import Emu
import scenes
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.dirname(here)
e = Emu(SP + '/v12/s2/v1226/m.gba', elf='/home/user/gameatory-1/stuntfox/build/merge/stuntfox-merge.elf')
S = e.S
def s32s(a, n): return [struct.unpack('<i', struct.pack('<I', e.r32(a + 4 * i)))[0] for i in range(n)]
scenes.boot_to_level(e)
# tag, cell x, cell z (fractions allowed), heading in turns (0 = +z, 0.25 = +x)
TARGETS = [('street', 9.5, 2.07 + 0.55, 0.0), ('cross', 60.5, 10.2, 0.0), ('ramp', 9.3, 11.5, 0.25), ('bridge', 8.0, 9.5, 0.25),
           ('water', 11.0, 7.5, 0.25), ('kicker', 94.5, 85.5, 0.25)]
if len(sys.argv) > 1: TARGETS = [t for t in TARGETS if t[0] in sys.argv[1:]]
out = {}
for tag, cx, cz, hd in TARGETS:
    h = e.r32(S['hero'])
    x, z = int(cx * 1024), int(cz * 1024)
    for k in range(60):
        for off, v in ((4, x * 2), (8, z * 2), (0xe4, x * 2), (0xe8, z * 2), (0xf0, x * 2), (0xf4, z * 2)): e.w32(h + off, v & 0xffffffff)
        e.w16(h + 0x12, int(hd * 5760) & 0xffff)
        e.run(2, [])
    e.run(60, [])
    c = s32s(S['cam'], 12)
    d = dict(tag=tag, pos=c[0:3], r=c[3:6], u=c[6:9], f=c[9:12], focal=s32s(S['focal'], 1)[0], man=[e.r32(h + 4) // 2, e.r32(h + 8) // 2])
    e.screenshot(os.path.join(root, 'shots', 'gba_%s.png' % tag)); out[tag] = d; print(json.dumps(d))
json.dump(out, open(os.path.join(root, 'build', 'gba_poses_%s.json' % ('all' if len(sys.argv) < 2 else '_'.join(sys.argv[1:]))), 'w'), indent=1)
