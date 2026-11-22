#!/usr/bin/env python3
"""List instruction words that the PlayStation's R3000A cannot execute (it has MIPS I, COP0 and the GTE as COP2, nothing else).

    mips1_lint.py payback.elf                  every function symbol in the executable sections of a linked ELF
    mips1_lint.py --raw FILE --base 0x80010000 [--start OFF --size N]    a raw code image (data in it gives false hits)

Exit status 0 when every checked word is valid, 1 when one is not, 2 when the input cannot be read.  ps1rt/build.sh runs it on
every linked payback.elf, so a build with such an instruction fails.  Typical cause: clang emits `teq divisor,$zero,7` (MIPS II)
after every div/divu unless -mno-check-zero-division is given; a real R3000A, and an emulator that models it, raises a Reserved
Instruction exception for it, while lenient dynarecs run past it.  ROM-free: it reads only the file it is given.
"""
from __future__ import annotations

import argparse
import struct
import sys

SPECIAL_OK = {0x00, 0x02, 0x03, 0x04, 0x06, 0x07, 0x08, 0x09, 0x0c, 0x0d, 0x10, 0x11, 0x12, 0x13, 0x18, 0x19, 0x1a, 0x1b,
              0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x2a, 0x2b}
REGIMM_OK = {0x00, 0x01, 0x10, 0x11}            # bltz bgez bltzal bgezal
OP_OK = {0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
         0x28, 0x29, 0x2a, 0x2b, 0x2e, 0x32, 0x3a}   # ... loads/stores incl. lwl/lwr/swl/swr, lwc2/swc2 (GTE)
SPECIAL_NAMES = {0x0a: 'movz', 0x0b: 'movn', 0x0f: 'sync', 0x30: 'tge', 0x31: 'tgeu', 0x32: 'tlt', 0x33: 'tltu', 0x34: 'teq', 0x36: 'tne',
                 0x01: 'movf/movt', 0x14: 'dsllv', 0x1c: 'dmult'}
OP_NAMES = {0x14: 'beql', 0x15: 'bnel', 0x16: 'blezl', 0x17: 'bgtzl', 0x1c: 'special2 (mul/clz/madd)', 0x1f: 'special3', 0x2f: 'cache',
            0x30: 'll', 0x38: 'sc', 0x11: 'cop1 (no FPU)', 0x13: 'cop3', 0x31: 'lwc1', 0x39: 'swc1', 0x33: 'pref/lwc3', 0x1a: 'ldl', 0x1b: 'ldr'}


def bad(word: int) -> str | None:
    """None when the word is a valid R3000A instruction, else a short reason."""
    op = word >> 26
    if op == 0:
        funct = word & 0x3f
        return None if funct in SPECIAL_OK else 'SPECIAL funct 0x%02x %s' % (funct, SPECIAL_NAMES.get(funct, ''))
    if op == 1:
        rt = (word >> 16) & 0x1f
        return None if rt in REGIMM_OK else 'REGIMM rt 0x%02x (branch-likely / trap-immediate)' % rt
    if op == 0x10:                                   # COP0: mfc0, mtc0, rfe
        rs = (word >> 21) & 0x1f
        if rs in (0, 4) or (rs == 0x10 and (word & 0x3f) == 0x10):
            return None
        return 'COP0 rs 0x%02x funct 0x%02x' % (rs, word & 0x3f)
    if op == 0x12:                                   # COP2 = GTE: mfc2 cfc2 mtc2 ctc2 and the commands
        rs = (word >> 21) & 0x1f
        return None if rs in (0, 2, 4, 6) or (rs & 0x10) else 'COP2 rs 0x%02x' % rs
    if op in OP_OK:
        return None
    return 'opcode 0x%02x %s' % (op, OP_NAMES.get(op, ''))


def scan(data: bytes, base: int) -> list[tuple[int, int, str]]:
    """(address, word, reason) of every invalid word of a code block that starts at address base."""
    out = []
    for offset in range(0, len(data) - 3, 4):
        word, = struct.unpack_from('<I', data, offset)
        reason = bad(word)
        if reason:
            out.append((base + offset, word, reason))
    return out


def elf_parse(path: str):
    """(sections [(name, address, bytes, executable)], functions [(address, size, name)]) of a 32-bit little-endian ELF."""
    with open(path, 'rb') as handle:
        data = handle.read()
    if data[:4] != b'\x7fELF' or data[4] != 1 or data[5] != 1:
        raise ValueError('not a 32-bit little-endian ELF file')
    shoff, = struct.unpack_from('<I', data, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', data, 0x2e)
    sections = [struct.unpack_from('<10I', data, shoff + i * shentsize) for i in range(shnum)]
    names = sections[shstrndx][4]
    out, functions = [], []
    for sec in sections:
        name = data[names + sec[0]:data.index(b'\0', names + sec[0])].decode('latin1')
        if sec[1] == 1 and sec[5]:                       # SHT_PROGBITS with content
            out.append((name, sec[3], data[sec[4]:sec[4] + sec[5]], bool(sec[2] & 4)))
        if sec[1] == 2:                                  # SHT_SYMTAB
            strings = sections[sec[6]][4]
            for offset in range(sec[4], sec[4] + sec[5], 16):
                nm, value, size, info, _other, _shndx = struct.unpack_from('<IIIBBH', data, offset)
                if (info & 15) == 2 and size:            # STT_FUNC with a size
                    functions.append((value, size, data[strings + nm:data.index(b'\0', strings + nm)].decode('latin1')))
    return out, sorted(functions)


def lint_elf(path: str, whole_sections: tuple[str, ...] = ()) -> tuple[int, list[str]]:
    """(instruction words checked, report lines of invalid words) for a linked ELF."""
    sections, functions = elf_parse(path)
    checked, lines = 0, []
    for name, base, data, executable in sections:
        if name in whole_sections:
            checked += len(data) // 4
            lines += ['   %08x: %08x  %-34s %s (whole section)' % (a, w, r, name) for a, w, r in scan(data, base)]
            continue
        if not executable:
            continue
        for address, size, function in functions:
            if base <= address < base + len(data):
                code = data[address - base:address - base + size]
                checked += len(code) // 4
                lines += ['   %08x: %08x  %-34s %s+0x%x' % (a, w, r, function, a - address) for a, w, r in scan(code, address)]
    return checked, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('file')
    parser.add_argument('--raw', action='store_true', help='FILE is a raw code image')
    parser.add_argument('--base', default='0x80010000')
    parser.add_argument('--start', default='0')
    parser.add_argument('--size', default=None)
    parser.add_argument('--section', action='append', default=[], help='ELF: also scan this whole section as code (for example .blob)')
    parser.add_argument('--max', type=int, default=40, help='list at most this many invalid words')
    args = parser.parse_args(argv)
    try:
        if args.raw:
            with open(args.file, 'rb') as handle:
                data = handle.read()
            start = int(args.start, 0)
            data = data[start:start + int(args.size, 0)] if args.size else data[start:]
            hits = scan(data, int(args.base, 0))
            print('%s: %d words, %d not valid on the R3000A (raw scan: data in the image gives false hits)' % (args.file, len(data) // 4, len(hits)))
            for address, word, reason in hits[:args.max]:
                print('   %08x: %08x  %s' % (address, word, reason))
            return 1 if hits else 0
        checked, lines = lint_elf(args.file, tuple(args.section))
    except (OSError, ValueError, struct.error, IndexError) as error:
        print('%s: cannot be checked: %s' % (args.file, error), file=sys.stderr)
        return 2
    for line in lines[:args.max]:
        print(line)
    print('%s: %d instruction words inside function symbols checked, %d not valid on the R3000A' % (args.file, checked, len(lines)))
    return 1 if lines else 0


if __name__ == '__main__':
    sys.exit(main())
