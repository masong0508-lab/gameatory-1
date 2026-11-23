#!/usr/bin/env python3
"""Packed PS-X EXE (stage 19 speed item M11, -DEXEPACK): the boot ROM reads no zero sectors.

The linked image (llvm-objcopy -O binary of payback.elf, loaded at 0x80010000) is mostly zeros: the runtime BSS and reserved
tables, zero stretches of the boot image, the cold homes, the page-cache slots, the PPU scratch and the guest windows.  The packed
EXE holds

  [0x80010000, __bss_start)   the runtime (crt0, rt.c, ...) verbatim, at its home: crt0 runs from there
  [__bss_start, +12+8n)       the run table: 'PKX1', n, zero_end, then n x (dest, len), ascending dest, all word aligned
  then                        the bytes of the n runs, back to back, in table order

and crt0 (crt0.s assembled with EXEPACK) rebuilds the image before main():
  1. copies the runs highest destination first, each one backward.  Every source lies below its destination (checked here), and
     the sources of the runs still to be moved lie below the source of the current one, so no copy overwrites a source that is
     still needed; an overlap with its own source is a memmove;
  2. zeroes the gaps, highest first: [end of run n-1, zero_end), ..., [end of run 0, dest of run 1), and last [__bss_start,
     dest of run 0), which also wipes the table (nothing below __bss_start is ever written: crt0 itself stays intact);
  3. calls FlushCache (BIOS A(44h)) once, before anything jumps into the moved code.
Afterwards [0x80010000, zero_end) equals the unpacked EXE image byte for byte, whatever RAM held before.  pack() checks that
with unpack(), a model of steps 1-2 started from garbage RAM, and refuses to write an EXE otherwise.

  exepack.py RAW.bin ELF OUT.exe [--min-gap N]     (RAW.bin: objcopy -O binary of ELF; ELF must define __exepack_v1)
"""
import re
import struct
import sys
from pathlib import Path

BASE = 0x80010000
MAGIC = 0x31584b50          # 'PKX1'


def elf_symbols(elf):
    """name -> value of the ELF32 little-endian symbol table."""
    d = bytes(elf)
    if d[:4] != b'\x7fELF' or d[4] != 1 or d[5] != 1:
        raise ValueError('not a 32-bit little-endian ELF')
    shoff, = struct.unpack_from('<I', d, 0x20)
    shentsize, shnum = struct.unpack_from('<HH', d, 0x2e)
    secs = [struct.unpack_from('<IIIIIIIIII', d, shoff + i * shentsize) for i in range(shnum)]
    out = {}
    for s in secs:
        if s[1] != 2:                                   # SHT_SYMTAB
            continue
        stroff = secs[s[6]][4]
        for off in range(s[4], s[4] + s[5], 16):
            name, value = struct.unpack_from('<II', d, off)
            end = d.index(b'\0', stroff + name)
            out[d[stroff + name:end].decode()] = value
    return out


def runs_of(img, start, min_gap):
    """Word-aligned (offset, length) runs of img[start:] that hold every non-zero byte: img is split at every zero stretch of
    at least min_gap whole words' bytes."""
    n = len(img)
    if start % 4 or n % 4 or min_gap < 4:
        raise ValueError('runs_of needs word alignment')
    runs, prev = [], start
    for m in re.compile(b'\x00{%d,}' % min_gap).finditer(img, start):
        a, b = (m.start() + 3) & ~3, m.end() & ~3       # the whole words inside the zero stretch
        if b - a < min_gap:
            continue
        if a > prev:
            runs.append((prev, a - prev))
        prev = b
    if prev < n:
        runs.append((prev, n - prev))
    return runs


def pack(raw, bss_start, min_gap=64):
    """(packed image without the PS-X header, runs) of the raw image `raw` loaded at BASE.  Raises ValueError when the
    layout breaks an assumption of the crt0 unpacker or the model does not give the image back."""
    if bss_start % 4 or not BASE < bss_start < BASE + len(raw):
        raise ValueError('__bss_start 0x%08x is not a word address inside the image' % bss_start)
    img = bytes(raw) + b'\0' * (-len(raw) % 2048)       # the unpacked EXE as the BIOS loaded it before (whole sectors)
    bss_off = bss_start - BASE
    runs = runs_of(img, bss_off, min_gap)
    if not runs:
        raise ValueError('nothing above __bss_start to pack')
    table = struct.pack('<III', MAGIC, len(runs), BASE + len(img)) + b''.join(struct.pack('<II', BASE + a, ln) for a, ln in runs)
    src = bss_off + len(table)
    for a, ln in runs:
        if src > a:
            raise ValueError('run at 0x%08x would be copied from above its destination (0x%08x)' % (BASE + a, BASE + src))
        src += ln
    packed = img[:bss_off] + table + b''.join(img[a:a + ln] for a, ln in runs)
    packed += b'\0' * (-len(packed) % 2048)
    for garbage in (0x00, 0xa5, 0xff):
        back = unpack(packed, bss_start, garbage)
        if back != img:
            bad = next(i for i in range(len(img)) if back[i] != img[i])
            raise ValueError('unpack model differs from the image at 0x%08x' % (BASE + bad))
    return packed, runs


def table_of(mem, bss_off):
    """(n, zero_end, [(dest, len)]) of the run table at mem[bss_off], None when there is none."""
    if bss_off + 12 > len(mem):
        return None
    magic, n, zero_end = struct.unpack_from('<III', mem, bss_off)
    if magic != MAGIC or bss_off + 12 + 8 * n > len(mem):
        return None
    return n, zero_end, [struct.unpack_from('<II', mem, bss_off + 12 + 8 * i) for i in range(n)]


def unpack(packed, bss_start, garbage=0xa5):
    """Model of crt0 steps 1-2: RAM from BASE after the BIOS loaded `packed` there (the RAM above it holds `garbage`).
    Returns the bytes of [BASE, zero_end)."""
    bss_off = bss_start - BASE
    t = table_of(packed, bss_off)
    if t is None:
        raise ValueError('no run table at 0x%08x' % bss_start)
    n, zero_end, ents = t
    mem = bytearray([garbage]) * max(zero_end - BASE, len(packed))
    mem[:len(packed)] = packed
    src_end = bss_off + 12 + 8 * n + sum(ln for _, ln in ents)
    for dest, ln in reversed(ents):                     # step 1: highest destination first
        src_end -= ln
        d = dest - BASE
        mem[d:d + ln] = mem[src_end:src_end + ln]       # a slice copy reads its source first: a memmove
    cur = zero_end - BASE
    for dest, ln in reversed(ents):                     # step 2: the gaps, highest first, the table's gap last
        d = dest - BASE
        mem[d + ln:cur] = bytes(cur - d - ln)
        cur = d
    mem[bss_off:cur] = bytes(cur - bss_off)
    return bytes(mem[:zero_end - BASE])


def exe_header(t_size):
    header = bytearray(2048)
    header[:8] = b'PS-X EXE'
    struct.pack_into('<IIIIIIIIIIII', header, 0x10, BASE, 0, BASE, t_size, 0, 0, 0, 0, 0x801fd000, 0, 0, 0)
    return bytes(header)


def main(argv):
    args = list(argv)
    min_gap = 64
    if '--min-gap' in args:
        i = args.index('--min-gap')
        min_gap = int(args[i + 1])
        del args[i:i + 2]
    if len(args) != 3:
        raise SystemExit(__doc__)
    raw = Path(args[0]).read_bytes()
    syms = elf_symbols(Path(args[1]).read_bytes())
    if '__exepack_v1' not in syms:
        raise SystemExit('exepack: the linked crt0 has no unpacker (symbol __exepack_v1): assemble crt0.s with EXEPACK')
    try:
        packed, runs = pack(raw, syms['__bss_start'], min_gap)
    except ValueError as e:
        raise SystemExit('exepack: ' + str(e))
    Path(args[2]).write_bytes(exe_header(len(packed)) + packed)
    print('exepack: %d runs, image %d -> %d sectors (run table %d bytes at 0x%08x)'
          % (len(runs), (len(raw) + 2047) // 2048, len(packed) // 2048, 12 + 8 * len(runs), syms['__bss_start']))


if __name__ == '__main__':
    main(sys.argv[1:])
