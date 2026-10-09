"""Builds Stunt Fox: python3 build.py "Payback (Europe) (En,Fr,De,Es,It).gba" -o stuntfox.gba

The Payback ROM provides the city layout (and the cartridge logo); it is read, never copied
into this repository. Needs clang and ld.lld.
"""
import argparse
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'src')
BUILD = os.path.join(HERE, 'build')
GEN = os.path.join(BUILD, 'gen')
sys.path.insert(0, os.path.join(HERE, 'tools'))
import mkworld   # noqa: E402
import mkassets  # noqa: E402

CFLAGS = ['--target=armv4t-none-eabi', '-mcpu=arm7tdmi', '-O2', '-ffreestanding', '-fno-builtin',
          '-nostdlib', '-ffunction-sections', '-Wall', '-Wno-unused-function']
ARM_FILES = {'render.c', 'citydraw.c', 'fx.c', 'physics.c', 'model.c'}  # hot code: ARM, IWRAM


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit('failed: ' + ' '.join(cmd))
    if r.stderr.strip():
        sys.stderr.write(r.stderr)


def build(payback, out):
    os.makedirs(GEN, exist_ok=True)
    rom = open(payback, 'rb').read()
    data, stats = mkworld.build(rom)
    open(os.path.join(GEN, 'world.bin'), 'wb').write(data)
    mkassets.main(os.path.join(GEN, 'tables.c'))
    objs = []
    sources = [os.path.join(SRC, f) for f in sorted(os.listdir(SRC)) if f.endswith(('.c', '.s'))]
    sources.append(os.path.join(GEN, 'tables.c'))
    for src in sources:
        name = os.path.basename(src)
        obj = os.path.join(BUILD, name + ('.iw.o' if name in ARM_FILES else '.o'))
        if src.endswith('.s'):
            run(['clang', '--target=armv4t-none-eabi', '-mcpu=arm7tdmi', '-c', src, '-o', obj,
                 '-Wa,-I' + GEN])
        else:
            mode = '-marm' if os.path.basename(src) in ARM_FILES else '-mthumb'
            run(['clang'] + CFLAGS + [mode, '-I' + SRC, '-c', src, '-o', obj])
        objs.append(obj)
    elf = os.path.join(BUILD, 'stuntfox.elf')
    run(['ld.lld', '-T', os.path.join(SRC, 'gba.ld'), '--gc-sections', '-e', '_start', '-o', elf] + objs)
    run(['llvm-objcopy', '-O', 'binary', elf, out])
    img = bytearray(open(out, 'rb').read())
    img[4:0xa0] = rom[4:0xa0]                     # logo from the player's own cartridge
    img[0xa0:0xac] = b'STUNT FOX\0\0\0'
    img[0xac:0xb0] = b'BSFE'
    img[0xb0:0xb2] = b'01'
    img[0xb2] = 0x96
    img[0xb3:0xbd] = bytes(10)
    img[0xbd] = (-sum(img[0xa0:0xbd]) - 0x19) & 0xff
    while len(img) % 4:
        img.append(0)
    open(out, 'wb').write(img)
    return stats, len(img)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('payback')
    ap.add_argument('-o', '--out', default='stuntfox.gba')
    a = ap.parse_args()
    stats, size = build(a.payback, a.out)
    print('wrote %s (%d KiB), world %s' % (a.out, size // 1024, stats))
