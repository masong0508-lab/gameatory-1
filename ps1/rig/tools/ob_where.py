#!/usr/bin/env python3
"""ob_where.py: where is the CPU?  Runs a core for some frames (no input), then reads the CPU registers out of save states.

  ob_where.py --core swanstation|beetle --disc X.cue --out DIR [--sys SYSTEMDIR] [--frames N] [--shots f1,f2,..]
              [--exe PSX.EXE] [--sym payback.elf] [--samples 8] [--opt k=v ...]

Prints: screenshots taken, K program-counter samples (10 frames apart) with ra/sp/v0/v1/a0, whether the boot executable is in
RAM (compared with --exe), and a few guest counters (--sym).  Works with any firmware (openboot, the core's built-in one)."""
import argparse, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obrig import Emu2, load_syms, format_trace, swan_regs, beetle_regs  # noqa: E402
from obrun import DEFAULT_OPTS  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--core', required=True); ap.add_argument('--disc', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--sys', default=None); ap.add_argument('--frames', type=int, default=1800); ap.add_argument('--shots', default='')
    ap.add_argument('--exe', default=None); ap.add_argument('--sym', default=None); ap.add_argument('--samples', type=int, default=8)
    ap.add_argument('--opt', action='append', default=[])
    a = ap.parse_args()
    opts = dict(DEFAULT_OPTS.get(a.core, {}))
    for kv in a.opt:
        k, v = kv.split('=', 1); opts[k] = v
    os.makedirs(a.out, exist_ok=True)
    e = Emu2(a.core, a.disc, a.out, opts, sysdir=a.sys)
    syms = load_syms(a.sym) if a.sym else {}
    shots = sorted(int(x) for x in a.shots.split(',') if x)

    def shot(tag):
        im = e.image()
        if im:
            p = '%s/%s.png' % (a.out, tag); im.convert('RGB').save(p)
            ex = im.convert('L').getextrema()
            print('shot %s frame %d size %s luminance %s -> %s' % (tag, e.frames, im.size, ex, p))
    while e.frames < a.frames:
        nxt = min([f for f in shots if f > e.frames] + [a.frames])
        e.run(nxt - e.frames)
        if e.frames in shots:
            shot('f%05d' % e.frames)
    shot('end')
    hint = None
    for k in range(a.samples):
        s = bytes(e.save_state())
        if a.core == 'swanstation':
            hint, w = swan_regs(s, hint)
        else:
            w = beetle_regs(s)
        if w:
            print('frame %d pc %08x npc %08x ra %08x sp %08x v0 %08x v1 %08x a0 %08x a1 %08x t0 %08x%s' % (
                e.frames, w[34], w[35], w[31], w[29], w[2], w[3], w[4], w[5], w[8], '' if hint is None else '  (block at state offset %#x)' % hint))
        else:
            print('frame %d: no register block found in the save state' % e.frames)
        e.run(10)
    if a.exe:
        x = open(a.exe, 'rb').read()
        taddr, tsize, pc0 = struct.unpack_from('<I', x, 0x18)[0], struct.unpack_from('<I', x, 0x1c)[0], struct.unpack_from('<I', x, 0x10)[0]
        body = x[0x800:0x800 + tsize]
        ram = bytes(e.read(taddr, len(body)))
        n = min(len(ram), len(body))
        same = sum(1 for i in range(0, n, 4) if ram[i:i + 4] == body[i:i + 4])
        print('boot executable: t_addr %08x t_size %#x pc0 %08x; RAM words equal to the file in the compared %d KiB: %d of %d (first RAM words %s)' % (
            taddr, tsize, pc0, n // 1024, same, n // 4, ram[:16].hex()))
    for name in ('g_gframes', 'g_pres', 'g_nvbl', 'io_cyc', 'cd_sectors', 'rom_miss_count', 'pad_polls', 'sf3_ok'):
        if name in syms:
            print('  %s = %d' % (name, e.r32(syms[name])))
    print('RAM vectors: [80]=%08x %08x  [a0]=%08x %08x  [b0]=%08x  [c0]=%08x' % (e.r32(0x80000080), e.r32(0x80000084), e.r32(0x800000a0), e.r32(0x800000a4), e.r32(0x800000b0), e.r32(0x800000c0)))
    t = e.trace()
    print(format_trace(t) if t.get('present') else 'no openboot trace table (other firmware)')
    tty = e.tty_poll() if t.get('present') else b''
    if tty:
        print('openboot TTY ring, last 300 bytes: %r' % bytes(tty)[-300:])


if __name__ == '__main__':
    main()
