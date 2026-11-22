#!/usr/bin/env python3
"""ob_openbios_halt.py: run a disc on the open-source BIOS that SwanStation carries inside (used when the system directory
holds no image it accepts), and if that kernel has stopped in its "=== halting ===" loop, print why: the registers it saved
(its Thread record), the exception program counter and cause, and the arguments of the stopped call from its stack frame.

  ob_openbios_halt.py --disc X.cue --out DIR [--frames 1500] [--sys EMPTYDIR] [--opt k=v ...]

--sys defaults to DIR/empty_system, an empty directory made for the run."""
import argparse, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obrig import Emu2, swan_regs  # noqa: E402
from obrun import DEFAULT_OPTS  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--disc', required=True); ap.add_argument('--out', required=True); ap.add_argument('--frames', type=int, default=1500)
ap.add_argument('--sys', default=None, help='a system directory without any firmware image (default: OUT/empty_system)')
ap.add_argument('--opt', action='append', default=[])
a = ap.parse_args()
opts = dict(DEFAULT_OPTS['swanstation'])
for kv in a.opt:
    k, v = kv.split('=', 1); opts[k] = v
os.makedirs(a.out, exist_ok=True)
if a.sys is None:
    a.sys = os.path.join(a.out, 'empty_system')
    os.makedirs(a.sys, exist_ok=True)
e = Emu2('swanstation', a.disc, a.out, opts, sysdir=a.sys)
loaded = None                     # first frame at which RAM at 0x80010000 holds something: the boot executable has been loaded
shots = {120: 'f00120', 300: 'f00300'}
for f in range(a.frames):
    e.run(1)
    if loaded is None and e.r32(0x80010000) != 0:
        o, w = swan_regs(bytes(e.save_state()))
        loaded = (e.frames, w[34] if w else 0)
    if e.frames in shots:
        im = e.image()
        if im:
            im.convert('RGB').save('%s/%s.png' % (a.out, shots[e.frames]))
im = e.image()
if im:
    im.convert('RGB').save(a.out + '/end.png'); print('picture at the end: %s, luminance range %s -> %s/end.png' % (im.size, im.convert('L').getextrema(), a.out))
print('boot executable in RAM (word at 0x80010000 not 0) from: %s' % ('frame %d (CPU then at %08x)' % loaded if loaded else 'never'))
o, w = swan_regs(bytes(e.save_state()))
N = 'r0 at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra hi lo pc npc'.split()
print('CPU now (frame %d): %s' % (e.frames, ' '.join('%s=%08x' % (N[i], w[i]) for i in range(36)) if w else 'not found'))
if w:
    sp, s0 = w[29], w[16]
    print('stack at sp: ' + ' '.join('%08x' % e.r32(sp + 4 * i) for i in range(12)))
    for base in sorted({s0, w[17], w[18]}):
        if 0 < (base & 0x1fffff) < 0x1fff00:
            ws = [e.r32(base + 4 * i) for i in range(0x28)]
            print('record at %08x: ' % base + ' '.join('%08x' % x for x in ws))
            # OpenBIOS Thread: flags, flags2, r0..r31, returnPC, hi, lo, SR, Cause (its halt routine prints gp from +0x78, sp +0x7c)
            if ws[2] == 0:
                r = ws[2:34]
                print('  saved registers: ' + ' '.join('%s=%08x' % (N[i], r[i]) for i in range(32)))
                print('  saved returnPC=%08x hi=%08x lo=%08x SR=%08x Cause=%08x (exception code %d)' % (ws[34], ws[35], ws[36], ws[37], ws[38], (ws[38] >> 2) & 31))
