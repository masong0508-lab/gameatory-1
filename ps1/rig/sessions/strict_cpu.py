#!/usr/bin/env python3
"""Strict-CPU check: boot under the core's CPU interpreter (pcsx_rearmed_drc=disabled).  The dynarec of the fast core lets
instructions pass that the R3000A does not have; the interpreter stops the program at the first one ("reserved instruction"
in OUT/core.log), which is what an accurate emulator and the console do.

  python3 sessions/strict_cpu.py --disc DISC.cue --out runs/strict [--syms payback.elf] [--patch-invalid] [--frames 3000]

With --syms pointing at the ELF, the instruction words inside its function symbols are also checked statically
(tools/mips1_lint.py).  --patch-invalid is an EXPERIMENT: the words found that way are overwritten with NOP in RAM before
the first frame, to see whether anything else stops the interpreter (the game itself is not changed)."""
import os, sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
from payback import *
import mips1_lint


def extra(ap):
    ap.add_argument('--frames', type=int, default=3000)
    ap.add_argument('--patch-invalid', action='store_true')


def static_hits(elf):
    try:
        secs, funcs = mips1_lint.elf_parse(elf)
    except Exception:
        return None
    hits = []
    for name, base, data, ex in secs:
        if not ex:
            continue
        for fa, fs, fn in funcs:
            if base <= fa < base + len(data):
                for adr, w, r, _ in mips1_lint.scan(data[fa - base:fa - base + fs], fa):
                    hits.append((adr, w, r, '%s+0x%x' % (fn, adr - fa)))
    return hits


def main():
    a = std_args(__doc__, extra)
    hits = static_hits(a.syms) if a.syms else None
    opts = dict({'pcsx_rearmed_drc': 'disabled'}, **a.core_opts)
    g = Payback(a.disc, a.out, core=a.core, card=a.card, syms=a.syms, opts=opts)
    print('== strict_cpu  disc %s  core %s  options %s  syms %s' % (a.disc, a.core, opts, a.syms), flush=True)
    if hits is None:
        g.note('no ELF given: static check skipped')
    else:
        for adr, w, r, fn in hits:
            g.log('  not an R3000A instruction: %08x: %08x  %s  in %s' % (adr, w, r, fn))
        g.check(not hits, 'static: every instruction word inside the function symbols is valid MIPS I', '%d invalid word(s)' % len(hits))
    if a.patch_invalid and hits:
        for adr, w, r, fn in hits:
            if g.r32(adr) == w:
                g.write(adr, struct.pack('<I', 0))
        g.note('EXPERIMENT: %d invalid word(s) overwritten with NOP in RAM before the first frame (a division by zero is then no longer trapped; the R3000A never trapped it either)' % len(hits))
    w = g.wait_until(lambda: g.at_language() and g.on('Italiano'), a.frames, step=10)
    g.run(60)
    im = g.snap('after %d frames' % g.nrun)
    try:
        g._rs.rs_flush()
        log = open(os.path.join(g.out, 'core.log'), errors='replace').read()
    except OSError:
        log = ''
    res = [l for l in log.splitlines() if 'reserved instruction' in l.lower() or 'unhandled' in l.lower()]
    g.check(not res, 'interpreter: no reserved instruction reported by the core', res[:3] if res else 'none in core.log')
    g.check(w is not None, 'interpreter: the language screen comes up', 'frame %d, guest frames %s, text %r' % (g.nrun, g.gframes(), g.text()[:60]))
    if w is not None:
        gf0 = g.gframes()
        g.run(600)
        g.check(g.gframes() is None or g.gframes() > gf0, 'interpreter: guest frames keep counting', 'from %s to %s in 600 frames' % (gf0, g.gframes()))
    return g.finish('strict_cpu')


if __name__ == '__main__':
    sys.exit(main())
