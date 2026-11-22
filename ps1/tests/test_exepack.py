"""ps1rt/exepack.py and the crt0 unpacker (speed item M11, -DEXEPACK): synthetic images only, no game data.

The packer tests need nothing but Python.  The crt0 test assembles the manifest's crt0.s with EXEPACK, links it with a small
image of its own, packs that, and runs the machine code in unicorn (MIPS32 little endian) from garbage RAM; it is skipped when
clang, ld.lld, llvm-objcopy or the unicorn module is missing."""
import importlib.util
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

PS1 = Path(__file__).resolve().parents[1]


def manifest_source(target):
    manifest = json.loads((PS1 / 'tools/source_manifest.json').read_text())
    sources = [entry['source'] for entry in manifest['files'] if entry['target'] == target]
    assert len(sources) == 1, target
    return PS1 / sources[0]


spec = importlib.util.spec_from_file_location('ps1_exepack', manifest_source('ps1rt/exepack.py'))
xp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xp)
BASE = xp.BASE


def synthetic(seed, runtime=0x1800, bss=0x900, pieces=40):
    """A raw image: `runtime` non-zero bytes, a zero BSS of `bss` bytes, then non-zero runs and zero stretches of every size."""
    rnd = random.Random(seed)
    img = bytearray(rnd.randrange(1, 256) for _ in range(runtime)) + bytes(bss)
    for _ in range(pieces):
        img += bytes(rnd.randrange(1, 256) for _ in range(4 * rnd.randrange(1, 300)))
        img += bytes(4 * rnd.choice((1, 3, 15, 16, 17, 100, 2000, 9000)))
    img += bytes(rnd.randrange(1, 256) for _ in range(4 * rnd.randrange(1, 50)))
    return bytes(img), BASE + runtime


class PackTests(unittest.TestCase):
    def test_round_trip_from_any_ram(self):
        for seed in range(8):
            raw, bss = synthetic(seed)
            packed, runs = xp.pack(raw, bss)
            img = raw + bytes(-len(raw) % 2048)
            self.assertEqual(len(packed) % 2048, 0)
            self.assertLess(len(packed), len(img))
            self.assertEqual(packed[:bss - BASE], img[:bss - BASE], 'the runtime below __bss_start is stored verbatim')
            for garbage in (0x00, 0x5a, 0xff):
                self.assertEqual(xp.unpack(packed, bss, garbage), img, (seed, garbage))

    def test_table_layout(self):
        raw, bss = synthetic(3)
        packed, runs = xp.pack(raw, bss)
        n, zero_end, ents = xp.table_of(packed, bss - BASE)
        self.assertEqual(n, len(runs))
        self.assertEqual(zero_end, BASE + len(raw) + (-len(raw) % 2048))
        src = bss + 12 + 8 * n
        last = bss
        for dest, ln in ents:
            self.assertEqual(dest % 4, 0)
            self.assertEqual(ln % 4, 0)
            self.assertGreaterEqual(dest, last, 'ascending, not overlapping')
            self.assertLessEqual(src, dest, 'every source lies at or below its destination (backward copies are safe)')
            last, src = dest + ln, src + ln

    def test_short_zero_stretches_stay_inside_runs(self):
        body = b'\x11' * 64 + bytes(32) + b'\x22' * 64 + bytes(64) + b'\x33' * 64
        raw = b'\x01' * 0x100 + bytes(0x100) + body
        runs = xp.runs_of(raw, 0x100, 64)
        self.assertEqual(runs, [(0x200, 64 + 32 + 64), (0x200 + 64 + 32 + 64 + 64, 64)])

    def test_refuses_a_run_that_starts_at_bss_start(self):
        # no zero stretch right after __bss_start: the table would cover the first run's own bytes
        raw = b'\x01' * 0x100 + b'\x02' * 0x400 + bytes(0x1000) + b'\x03' * 0x100
        with self.assertRaises(ValueError):
            xp.pack(raw, BASE + 0x100)

    def test_refuses_a_bad_bss_start(self):
        raw, bss = synthetic(1)
        for bad in (bss + 2, BASE, BASE + len(raw) + 4):
            with self.assertRaises(ValueError):
                xp.pack(raw, bad)

    def test_header(self):
        h = xp.exe_header(0x8000)
        self.assertEqual(h[:8], b'PS-X EXE')
        self.assertEqual(struct.unpack_from('<IIII', h, 0x10), (BASE, 0, BASE, 0x8000))
        self.assertEqual(len(h), 2048)


LINKER = '''
ENTRY(_start)
SECTIONS {
  . = 0x80010000;
  .text : { *(.text.start) *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  . = ALIGN(4);
  __bss_start = .;
  .bss (NOLOAD) : { *(.bss*) *(COMMON) }
  . = ALIGN(4);
  __bss_end = .;
  . = 0x80030000;
  .high : { KEEP(*(.high*)) }
  /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.comment) }
}
'''
# main: an endless loop the test stops at.  .high: words with zero stretches of every size above the BSS, as the boot image,
# cold homes and renderer data are in the real image.
PROGRAM = '''
.set noreorder
.section .text,"ax"
.global main
main:
  b main
  nop
.section .bss,"aw",@nobits
.space 0x600
.section .high,"aw"
'''


def tools_missing():
    if not all(shutil.which(t) for t in ('clang', 'ld.lld', 'llvm-objcopy')):
        return 'clang, ld.lld or llvm-objcopy missing'
    if importlib.util.find_spec('unicorn') is None:
        return 'unicorn missing'
    return None


@unittest.skipIf(tools_missing(), tools_missing() or '')
class Crt0UnpackTests(unittest.TestCase):
    """The real crt0 machine code, linked with -Wa,-defsym,EXEPACK=1 as build.sh does."""
    F = ['--target=mipsel-none-elf', '-march=mips1', '-mno-abicalls', '-fno-pic', '-G0', '-mno-gpopt']

    def build(self, root, rnd):
        words = []
        for _ in range(30):
            words += [rnd.randrange(1, 1 << 32) for _ in range(rnd.randrange(1, 200))]
            words += [0] * rnd.choice((1, 16, 17, 300, 4000))
        (root / 'prog.s').write_text(PROGRAM + ''.join('.word 0x%08x\n' % w for w in words))
        (root / 'link.ld').write_text(LINKER)
        crt0 = manifest_source('ps1rt/crt0.s')
        subprocess.run(['clang', *self.F, '-Wa,-defsym,EXEPACK=1', '-c', str(crt0), '-o', str(root / 'crt0.o')], check=True,
                       capture_output=True)
        subprocess.run(['clang', *self.F, '-c', str(root / 'prog.s'), '-o', str(root / 'prog.o')], check=True, capture_output=True)
        subprocess.run(['ld.lld', '-T', str(root / 'link.ld'), str(root / 'crt0.o'), str(root / 'prog.o'), '-o', str(root / 'p.elf')],
                       check=True, capture_output=True)
        subprocess.run(['llvm-objcopy', '-O', 'binary', str(root / 'p.elf'), str(root / 'p.bin')], check=True, capture_output=True)
        return (root / 'p.elf').read_bytes(), (root / 'p.bin').read_bytes()

    def run_crt0(self, packed, syms, garbage):
        from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
        from unicorn import mips_const as M
        mu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_LITTLE_ENDIAN)
        mu.mem_map(0, 0x200000)
        mu.mem_write(0, bytes([garbage]) * 0x200000)
        mu.mem_write(BASE - 0x80000000, packed)
        regs = [getattr(M, 'UC_MIPS_REG_%d' % i) for i in range(32)]
        calls, low = [], []
        bss = syms['__bss_start']

        def on_code(uc, addr, size, _):
            w, = struct.unpack('<I', uc.mem_read(addr & 0x1fffffff, 4))
            op = w >> 26
            if op == 0 and (w & 63) == 9 and uc.reg_read(regs[(w >> 21) & 31]) & 0x1fffffff == 0xA0:
                calls.append(uc.reg_read(M.UC_MIPS_REG_T1))          # BIOS A-call: record the function number, return
                uc.reg_write(M.UC_MIPS_REG_PC, addr + 8)
                return
            if op in (0x28, 0x29, 0x2a, 0x2b, 0x2e):
                imm = w & 0xffff
                va = ((uc.reg_read(regs[(w >> 21) & 31]) + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xffffffff) | 0x80000000
                sp = uc.reg_read(M.UC_MIPS_REG_SP) | 0x80000000
                if va < bss and not sp - 64 <= va < sp + 64:
                    low.append(va)
        mu.hook_add(UC_HOOK_CODE, on_code)
        mu.emu_start(syms['_start'], syms['main'], count=5_000_000)
        return mu, calls, low

    def test_crt0_rebuilds_the_image(self):
        with tempfile.TemporaryDirectory(prefix='ps1-exepack-') as tmp:
            root = Path(tmp)
            elf, raw = self.build(root, random.Random(7))
            syms = xp.elf_symbols(elf)
            self.assertIn('__exepack_v1', syms)
            self.assertEqual(syms['_start'], BASE, 'crt0 first, at the load address, as in the real link')
            packed, runs = xp.pack(raw, syms['__bss_start'])
            self.assertGreater(len(runs), 10)
            img = raw + bytes(-len(raw) % 2048)
            for garbage in (0x00, 0xa5, 0xff):
                mu, calls, low = self.run_crt0(packed, syms, garbage)
                self.assertEqual(mu.reg_read(__import__('unicorn').mips_const.UC_MIPS_REG_PC), syms['main'])
                got = bytes(mu.mem_read(BASE - 0x80000000, len(img)))
                self.assertEqual(got, img, 'garbage 0x%02x' % garbage)
                self.assertEqual(calls, [0x44], 'one FlushCache (A(44h)) before main')
                self.assertEqual(low, [], 'nothing below __bss_start is written')

    def test_plain_image_is_left_alone(self):
        # an unpacked EXE (no run table at __bss_start) only gets its BSS cleared, no FlushCache
        with tempfile.TemporaryDirectory(prefix='ps1-exepack-') as tmp:
            root = Path(tmp)
            elf, raw = self.build(root, random.Random(9))
            syms = xp.elf_symbols(elf)
            img = raw + bytes(-len(raw) % 2048)
            mu, calls, low = self.run_crt0(img, syms, 0x5a)
            self.assertEqual(calls, [])
            self.assertEqual(bytes(mu.mem_read(BASE - 0x80000000, len(img))), img)


if __name__ == '__main__':
    unittest.main()
