#!/usr/bin/env python3
"""objck_search.py (rc10.2): build and run the host search for misses of the OBJ tile change check (objck_search.c) on the C cut out of
ps1/stage19/ps1rt/ppu12.h.  ROM-free.  The long run: objck_search.py --tries 10000000 (per class, about 15 classes; minutes on one core).
test_objhash.py runs a short one.  Extra arguments: --seed N, --class N (one class only), --cc CC, -D NAME=VALUE (a different constant, to
compare designs; the PP_OBJCK constants sit behind #ifndef PP_OBJCK_KA)."""
import argparse, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PPU = HERE.parent / 'stage19' / 'ps1rt' / 'ppu12.h'


def cut():
    s = PPU.read_text()
    m = re.search(r'(/\* PP_OBJCK BEGIN.*?/\* PP_OBJCK END \*/)', s, re.S)
    if not m:
        raise SystemExit('PP_OBJCK block not found in ppu12.h')
    return m.group(1)


def build(cc=None, defs=(), opt='-O2'):
    d = Path(tempfile.mkdtemp(prefix='objck_search'))
    (d / 'objck_cut.h').write_text(cut() + '\n')
    cc = cc or shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    exe = d / 'objck_search'
    cmd = [cc, opt, '-std=gnu99', '-w', '-I', str(d)] + ['-D' + x for x in defs] + ['-o', str(exe), str(HERE / 'objck_search.c')]
    subprocess.run(cmd, check=True)
    return exe


def run(tries, seed=1, cls=None, cc=None, defs=(), out=sys.stdout):
    exe = build(cc, defs)
    args = [str(exe), str(tries), str(seed)] + ([str(cls)] if cls is not None else [])
    p = subprocess.run(args, capture_output=True, text=True)
    if out:
        out.write(p.stdout)
    return p.returncode, p.stdout


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tries', type=int, default=10000000)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--class', dest='cls', type=int)
    ap.add_argument('--cc')
    ap.add_argument('-D', dest='defs', action='append', default=[])
    a = ap.parse_args()
    rc, _ = run(a.tries, a.seed, a.cls, a.cc, a.defs)
    sys.exit(rc)
