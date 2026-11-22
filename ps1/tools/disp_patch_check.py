#!/usr/bin/env python3
"""Decode and check the dispatch boot patches (PLAN.md Stage 2: D3, D1, D4, D2; ps1rt/rt.c dsp_boot) in a linked payback.elf.

    disp_patch_check.py payback.elf

dsp_boot() copies the words of the function symbol `dsp_new` over fixed words of the translator's runtime blob (t2m.py runtime(),
cfg 'P').  This tool decodes those words where they will execute and the new code they jump to, and checks them against the blob
layout, with no toolchain and no game data (it reads only the ELF):
  - dsp_new holds exactly the words of the flag set the symbols show: `j rt_mcache` + `addu $24,$25,$0` for RT_MISS (0x80030008,
    D1/D2), `j rd_front` + `j wr_front` for RT_MEMRD/RT_MEMWR (0x80030044, 0x8003013c, D4), or one `nop` at 0x80030044 (D3 alone);
  - every J word, completed with the upper 4 bits of the address it executes at, reaches the symbol it names;
  - the absolute jumps of the new code reach the blob's own stubs: rt_mcache RT_CC (0x80030150) with $28 = rt_miss_ret (0x80030028)
    and h_miss = HELP+8 (0x80028008) on its slow path; rd_front the kind dispatch (0x8003009c), RT_MEMRD_SLOW (0x80030128) and, with
    D3, the ROM fast path, at its start (0x8003004c) or past its region test (0x80030060: then rd_front begins with that same test,
    which leaves the region byte in $25); wr_front RT_CC with h_memwr = HELP+4 (0x80028004); both serve EWRAM and IWRAM themselves
    (region bytes 2 and 3, host 0x801b0000 and 0x801f0000), everything else reaches those stubs;
  - the D1 table that rt_mcache reads lies in the reserved area below ROMPG (0x80028010..0x8002a000) and clear of the D2 queue;
  - no jump or branch sits in a delay slot, every branch stays inside its function, every word is an R3000A instruction.
Exit status 0 when the ELF has no dispatch code or every check passes, 1 when a check fails, 2 when the input cannot be read.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys

_spec = importlib.util.spec_from_file_location('ps1_mips1_lint', Path(__file__).resolve().parent / 'mips1_lint.py')
mips1_lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mips1_lint)

RT_MISS, RT_MISS_RET, RT_MEMRD, ROM_FAST, KIND, RT_MEMRD_SLOW, RT_MEMWR, RT_CC = (
    0x80030008, 0x80030028, 0x80030044, 0x8003004c, 0x8003009c, 0x80030128, 0x8003013c, 0x80030150)
ROM_PAST = 0x80030060                        # the ROM fast path past its region test (sltiu $1,$25,0xe: $25 = the region byte)
REGION_TEST = [0x0018ce02, 0x332100f9, 0x38210008]   # the fast path's region test: srl $25,$24,24; andi $1,$25,0xf9; xori $1,$1,8
WINDOWS = {0x2721fffe, 0x2721fffd, 0x3c01801b, 0x3c01801f}   # addiu $1,$25,-2 / -3 (region bytes 2, 3); lui $1,0x801b / 0x801f (g2h bases)
HELP_MEMRD, HELP_MEMWR, HELP_MISS = 0x80028000, 0x80028004, 0x80028008
RESERVED = (0x80028010, 0x8002a000)          # free part of the reserved area (ROMPG starts at its end)
D2_QUEUE = (0x80029400, 0x80029800)          # rt.c LQ: 64 x 16 B
ADDU_T8_T9 = 0x0320c021                      # addu $24,$25,$0: RT_MISS's original first word
NOP = 0


def sext16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def jump_target(word: int, address: int) -> int | None:
    """Target of a j/jal word executed at address (None for any other word)."""
    if word >> 26 not in (2, 3):
        return None
    return ((address + 4) & 0xf0000000) | ((word & 0x03ffffff) << 2)


def is_control(word: int) -> bool:
    """A jump or branch (it has a delay slot)."""
    op = word >> 26
    return op in (1, 2, 3, 4, 5, 6, 7) or (op == 0 and (word & 0x3f) in (8, 9))


def branch_target(word: int, address: int) -> int | None:
    op = word >> 26
    if op in (1, 4, 5, 6, 7):
        return address + 4 + 4 * sext16(word & 0xffff)
    return None


def elf_symbols(path: str):
    """(sections [(name, address, bytes)], {name: (address, size)}) of every named symbol of a 32-bit little-endian ELF."""
    data = Path(path).read_bytes()
    if data[:4] != b'\x7fELF' or data[4] != 1 or data[5] != 1:
        raise ValueError('not a 32-bit little-endian ELF file')
    shoff, = struct.unpack_from('<I', data, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', data, 0x2e)
    sections = [struct.unpack_from('<10I', data, shoff + i * shentsize) for i in range(shnum)]
    names = sections[shstrndx][4]
    out, symbols = [], {}
    for sec in sections:
        name = data[names + sec[0]:data.index(b'\0', names + sec[0])].decode('latin1')
        if sec[1] == 1 and sec[5]:
            out.append((name, sec[3], data[sec[4]:sec[4] + sec[5]]))
        if sec[1] == 2:
            strings = sections[sec[6]][4]
            for offset in range(sec[4], sec[4] + sec[5], 16):
                nm, value, size, _info, _other, shndx = struct.unpack_from('<IIIBBH', data, offset)
                if nm and shndx:
                    symbols[data[strings + nm:data.index(b'\0', strings + nm)].decode('latin1')] = (value, size)
    return out, symbols


class Image:
    def __init__(self, sections):
        self.sections = sections

    def words(self, address: int, count: int) -> list[int]:
        for _name, base, data in self.sections:
            if base <= address and address + 4 * count <= base + len(data):
                return list(struct.unpack_from('<%dI' % count, data, address - base))
        raise ValueError('0x%08x: %d words are not in a loaded section' % (address, count))


def check(path: str) -> tuple[list[str], list[str]]:
    """(report lines, failures) for a linked ELF."""
    sections, symbols = elf_symbols(path)
    image, report, fails = Image(sections), [], []
    if 'dsp_new' not in symbols:
        return ['%s: no dispatch boot patches (no dsp_new symbol)' % path], []
    has_mc = 'rt_mcache' in symbols
    has_d4 = 'rd_front' in symbols and 'wr_front' in symbols
    if ('rd_front' in symbols) != ('wr_front' in symbols):
        fails.append('rd_front and wr_front come together (D4)')
    new_address, new_size = symbols['dsp_new']
    new = image.words(new_address, new_size // 4)
    expected = []                     # (patched address, what it must be: ('j', symbol) or a fixed word)
    if has_mc:
        expected += [(RT_MISS, ('j', 'rt_mcache')), (RT_MISS + 4, ADDU_T8_T9)]
    if has_d4:
        expected += [(RT_MEMRD, ('j', 'rd_front')), (RT_MEMWR, ('j', 'wr_front'))]
    elif len(new) == len(expected) + 1:
        expected += [(RT_MEMRD, NOP)]    # D3 alone
    if len(new) != len(expected):
        fails.append('dsp_new has %d words, the symbols call for %d' % (len(new), len(expected)))
    for (address, want), word in zip(expected, new):
        if isinstance(want, tuple):
            target = jump_target(word, address)
            goal = symbols[want[1]][0]
            if word >> 26 != 2 or target != goal:
                fails.append('patch word at 0x%08x is %08x, not `j %s` (0x%08x)' % (address, word, want[1], goal))
            report.append('  0x%08x <- %08x  j %s (0x%08x)' % (address, word, want[1], goal))
        else:
            if word != want:
                fails.append('patch word at 0x%08x is %08x, not %08x' % (address, word, want))
            report.append('  0x%08x <- %08x  %s' % (address, word, 'addu $24,$25,$0' if want == ADDU_T8_T9 else 'nop'))
    # D3 is in when RT_MEMRD's `j RT_MEMRD_SLOW` goes (a nop, or D4's rd_front reaching the ROM fast path)
    d3 = (not has_d4 and len(new) == len(expected) and expected and expected[-1] == (RT_MEMRD, NOP))
    functions = {name: symbols[name] for name in ('rt_mcache', 'rd_front', 'wr_front') if name in symbols}
    targets, loads = {}, {}
    for name, (base, size) in functions.items():
        code = image.words(base, size // 4)
        targets[name], loads[name] = set(), []
        upper = {}          # register -> every value a lui (or an addu of one) gave it anywhere in the function: paths join at labels
        for i, word in enumerate(code):
            address = base + 4 * i
            reason = mips1_lint.bad(word)
            if reason:
                fails.append('%s+0x%x: %08x is not an R3000A instruction (%s)' % (name, 4 * i, word, reason))
            if is_control(word) and i + 1 < len(code) and is_control(code[i + 1]):
                fails.append('%s+0x%x: a jump or branch in a delay slot' % (name, 4 * i + 4))
            if is_control(word) and i + 1 >= len(code):
                fails.append('%s ends in a jump or branch without its delay slot' % name)
            target = jump_target(word, address)
            if target is not None and not base <= target < base + size:
                targets[name].add(target)
            target = branch_target(word, address)
            if target is not None and not base <= target < base + size:
                fails.append('%s+0x%x: a branch leaves the function (0x%08x)' % (name, 4 * i, target))
            op, rs, rt, imm = word >> 26, (word >> 21) & 31, (word >> 16) & 31, word & 0xffff
            if op == 0x0f:                                   # lui
                upper.setdefault(rt, set()).add(imm << 16)
            elif op == 0x0d:                                 # ori after lui: a full constant
                loads[name] += [(rt, value | imm) for value in upper.get(rs, ())]
            elif op == 0x09:                                 # addiu after lui
                loads[name] += [(rt, (value + sext16(imm)) & 0xffffffff) for value in upper.get(rs, ())]
            elif op == 0x23 and rs == 2:                     # lw rt,off($2) with $2 = base + slot offset (rt_mcache)
                loads[name] += [('table', (value + sext16(imm)) & 0xffffffff) for value in upper.get(2, ())]
            if op == 0 and (word & 0x3f) == 0x21 and ((word >> 11) & 31) == rs == 2:   # addu $2,$2,$x after lui $x
                upper.setdefault(2, set()).update(upper.get(rt, ()))
    if has_mc:
        want = {RT_CC}
        if targets['rt_mcache'] != want:
            fails.append('rt_mcache jumps to %s, expected RT_CC 0x%08x only' % (sorted(map(hex, targets['rt_mcache'])), RT_CC))
        constants = loads['rt_mcache']
        if (28, RT_MISS_RET) not in constants:
            fails.append('rt_mcache does not set $28 = rt_miss_ret (0x%08x) for RT_CC' % RT_MISS_RET)
        if (25, HELP_MISS) not in constants:
            fails.append('rt_mcache does not load h_miss from HELP+8 (0x%08x)' % HELP_MISS)
        tables = sorted({value for kind, value in constants if kind == 'table'})
        if tables:                                       # D1: key at base, host at base + 4, 512 slots of 8 bytes
            base = tables[0]
            if tables != [base, base + 4] or not (RESERVED[0] <= base and base + 4096 <= RESERVED[1]) \
                    or (base < D2_QUEUE[1] and D2_QUEUE[0] < base + 4096):
                fails.append('D1 table at %s is not 512 x 8 B inside the reserved area clear of the D2 queue' % [hex(t) for t in tables])
            report.append('  rt_mcache: D1 table 0x%08x..0x%08x' % (base, base + 4096))
    if has_d4:
        rom = targets['rd_front'] & {ROM_FAST, ROM_PAST}
        if len(rom) > 1 or targets['rd_front'] != {KIND, RT_MEMRD_SLOW} | rom:
            fails.append('rd_front jumps to %s, expected the kind dispatch, RT_MEMRD_SLOW (and the ROM fast path)' % sorted(map(hex, targets['rd_front'])))
        if ROM_PAST in rom and image.words(functions['rd_front'][0], 3) != REGION_TEST:
            fails.append('rd_front enters the ROM fast path past its region test (0x%08x) without beginning with that test' % ROM_PAST)
        d3 = bool(rom)
        if targets['wr_front'] != {RT_CC}:
            fails.append('wr_front jumps to %s, expected RT_CC 0x%08x only' % (sorted(map(hex, targets['wr_front'])), RT_CC))
        if (25, HELP_MEMWR) not in loads['wr_front']:
            fails.append('wr_front does not rebuild the HELP+4 load (0x%08x) of RT_MEMWR' % HELP_MEMWR)
        for name in ('rd_front', 'wr_front'):
            if not WINDOWS <= set(image.words(functions[name][0], functions[name][1] // 4)):
                fails.append('%s does not serve EWRAM and IWRAM by the region byte (addiu $1,$25,-2 / -3, lui $1,0x801b / 0x801f)' % name)
    items = [label for label, on in (('D3', d3), ('D1', any(k == 'table' for k, _ in loads.get('rt_mcache', []))),
                                     ('D4', has_d4), ('D2', 'd2_linked' in symbols), ('D1CHK (test only)', 'h_mchk' in symbols)) if on]
    report.insert(0, '%s: dispatch boot patches %s: %d words' % (path, ' '.join(items) or '(none)', len(new)))
    for name, (base, size) in functions.items():
        report.append('  %s 0x%08x, %d words, jumps to %s' % (name, base, size // 4, ', '.join('0x%08x' % t for t in sorted(targets[name]))))
    return report, fails


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0].startswith('-'):
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    try:
        report, fails = check(argv[0])
    except (OSError, ValueError, KeyError, struct.error, IndexError) as error:
        print('%s: cannot be checked: %s' % (argv[0], error), file=sys.stderr)
        return 2
    for line in report:
        print(line)
    for line in fails:
        print('  FAIL ' + line)
    if fails:
        print('%s: %d dispatch patch checks failed' % (argv[0], len(fails)))
        return 1
    print('%s: dispatch patch words decoded and checked' % argv[0])
    return 0


if __name__ == '__main__':
    sys.exit(main())
