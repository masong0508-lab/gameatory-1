"""ROM-free tests: the rig's symbol check (Game._syms_match) accepts a packed PSX.EXE (-DEXEPACK) built from the same ELF.

A synthetic ELF (three PT_LOAD segments: the runtime, a data segment and an overlay far beyond the packed file's end, plus a
symbol table with __exepack_v1 and __bss_start) is linked into a raw image, packed with the build's own packer
(ps1/stage19/ps1rt/exepack.py) and checked against the rig: the packed EXE matches, a changed run, a changed overlay byte and an
ELF of another build do not, and an unpacked EXE still matches as before."""
from __future__ import annotations
import importlib.util
import pathlib
import struct
import sys
import tempfile
import types
import unittest

RIG = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RIG))
import ps1game  # noqa: E402

PACKER = RIG.parent / 'stage19' / 'ps1rt' / 'exepack.py'
BASE = 0x80010000


def elf32(segments, symbols):
    """A minimal ELF32 LE MIPS executable: PT_LOAD per (vaddr, bytes), a .symtab/.strtab with name -> value (shndx 1)."""
    eh, ph = 52, 32
    data_off = eh + ph * len(segments)
    blobs, offs, o = [], [], data_off
    for _, b in segments:
        offs.append(o); blobs.append(b); o += len(b)
    strtab = b'\0'
    syms = [b'\0' * 16]
    for name, val in symbols.items():
        syms.append(struct.pack('<IIIBBH', len(strtab), val, 0, 0x10, 0, 1))
        strtab += name.encode() + b'\0'
    symtab = b''.join(syms)
    shstr = b'\0.symtab\0.strtab\0.shstrtab\0'
    sym_off = o; str_off = sym_off + len(symtab); shs_off = str_off + len(strtab); sh_off = (shs_off + len(shstr) + 3) & ~3
    out = bytearray(sh_off + 40 * 4)
    out[:16] = b'\x7fELF\x01\x01\x01' + b'\0' * 9
    struct.pack_into('<HHIIIIIHHHHHH', out, 16, 2, 8, 1, BASE, eh, sh_off, 0, eh, ph, len(segments), 40, 4, 3)
    for i, ((va, b), fo) in enumerate(zip(segments, offs)):
        struct.pack_into('<8I', out, eh + ph * i, 1, fo, va, va, len(b), len(b), 7, 0x10000)
        out[fo:fo + len(b)] = b
    out[sym_off:sym_off + len(symtab)] = symtab
    out[str_off:str_off + len(strtab)] = strtab
    out[shs_off:shs_off + len(shstr)] = shstr
    sh = [(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
          (1, 2, 0, 0, sym_off, len(symtab), 2, 1, 4, 16),
          (9, 3, 0, 0, str_off, len(strtab), 0, 0, 1, 0),
          (17, 3, 0, 0, shs_off, len(shstr), 0, 0, 1, 0)]
    for i, s in enumerate(sh):
        struct.pack_into('<10I', out, sh_off + 40 * i, *s)
    return bytes(out)


def raw_image(segments):
    end = max(va + len(b) for va, b in segments)
    img = bytearray(end - BASE)
    for va, b in segments:
        img[va - BASE:va - BASE + len(b)] = b
    return bytes(img)


def check(exe, elf_bytes):
    with tempfile.TemporaryDirectory(prefix='ps1rig-exepack-') as tmp:
        p = pathlib.Path(tmp) / 'payback.elf'
        p.write_bytes(elf_bytes)
        fake = types.SimpleNamespace(syms_path=str(p), disc=types.SimpleNamespace(read=lambda name: exe))
        return ps1game.Game._syms_match(fake)


@unittest.skipUnless(PACKER.exists(), 'the build packer ps1/stage19/ps1rt/exepack.py is not in this tree')
class PackedExeSymbolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('exepack_build', PACKER)
        cls.xp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.xp)

    def build(self, overlay=b'\x5a' * 3000):
        runtime = bytes(range(256)) * 16                       # 4 KiB of runtime code below __bss_start
        bss = BASE + len(runtime) + 0x400                      # BSS, then the packed part
        data = b'DATA' * 512
        segs = [(BASE, runtime), (bss + 0x2000, data), (0x80199000, overlay)]   # the overlay lies far beyond the packed file
        syms = {'__exepack_v1': BASE + 0x40, '__bss_start': bss}
        elf = elf32(segs, syms)
        packed, runs = self.xp.pack(raw_image(segs), bss)
        return elf, self.xp.exe_header(len(packed)) + packed, segs, syms, runs

    def test_packed_exe_matches_its_elf(self):
        elf, exe, segs, _, runs = self.build()
        self.assertGreater(len(runs), 1)
        self.assertLess(struct.unpack_from('<I', exe, 0x1c)[0], 0x80199000 - BASE)   # packed: shorter than the overlay's offset
        self.assertIs(check(exe, elf), True)

    def test_image_model_equals_build_unpacker(self):
        elf, exe, segs, syms, _ = self.build()
        t_addr, img = ps1game.exe_image(exe, syms)
        self.assertEqual(t_addr, BASE)
        self.assertEqual(img, raw_image(segs) + b'\0' * (len(img) - len(raw_image(segs))))
        self.assertEqual(img, self.xp.unpack(exe[0x800:], syms['__bss_start']))

    def test_changed_run_does_not_match(self):
        elf, exe, _, _, _ = self.build()
        bad = bytearray(exe)
        bad[-200] ^= 0xff                                      # a byte of the last run (the overlay)
        self.assertIs(check(bytes(bad), elf), False)

    def test_elf_of_another_build_does_not_match(self):
        elf, exe, _, _, _ = self.build()
        other, _, _, _, _ = self.build(overlay=b'\x5b' * 3000)
        self.assertIs(check(exe, other), False)

    def test_unpacked_exe_still_matches(self):
        _, _, segs, syms, _ = self.build()
        plain_syms = {'__bss_start': syms['__bss_start']}      # no __exepack_v1: a build without EXEPACK
        elf = elf32(segs, plain_syms)
        raw = raw_image(segs)
        raw += b'\0' * (-len(raw) % 2048)
        exe = self.xp.exe_header(len(raw)) + raw
        self.assertIs(check(exe, elf), True)

    def test_packed_exe_without_the_packer_symbol_is_a_mismatch(self):
        elf, exe, segs, syms, _ = self.build()
        no_sym = elf32(segs, {'__bss_start': syms['__bss_start']})
        self.assertIs(check(exe, no_sym), False)


if __name__ == '__main__':
    unittest.main()
