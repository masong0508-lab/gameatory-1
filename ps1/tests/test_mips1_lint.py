"""ps1/tools/mips1_lint.py: R3000A instruction check of linked executables (ROM-free, no toolchain)."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import elf_fixture  # noqa: E402

PS1 = Path(__file__).resolve().parents[1]
LINT = PS1 / 'tools/mips1_lint.py'
spec = importlib.util.spec_from_file_location('ps1_mips1_lint', LINT)
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)


class InstructionTests(unittest.TestCase):
    def test_r3000a_instructions_pass(self):
        for word, what in ((0x00000000, 'nop'), (0x27bdfff0, 'addiu sp,sp,-16'), (0x03e00008, 'jr ra'),
                           (0x0c004000, 'jal'), (0x8fbf0010, 'lw ra,16(sp)'), (0x0085001a, 'div a0,a1'),
                           (0x0085001b, 'divu a0,a1'), (0x00001010, 'mfhi v0'), (0x88a40003, 'lwl'),
                           (0x04110002, 'bgezal'), (0x40026000, 'mfc0 v0,SR'), (0x40826000, 'mtc0 v0,SR'),
                           (0x42000010, 'rfe'), (0x48020000, 'mfc2'), (0x48c20000, 'ctc2'), (0x4a180001, 'GTE RTPS'),
                           (0xc8a00000, 'lwc2'), (0xe8a00000, 'swc2'), (0x0000000c, 'syscall'), (0x0000000d, 'break')):
            self.assertIsNone(lint.bad(word), what)

    def test_instructions_the_r3000a_lacks_are_named(self):
        for word, expected in ((0x00a001f4, 'teq'), (0x0000000a, 'movz'), (0x0000000f, 'sync'),
                               (0x50000000, 'beql'), (0x70000002, 'special2'), (0xc0000000, 'll'),
                               (0x44000000, 'cop1'), (0x04020000, 'REGIMM'), (0xbc000000, 'cache'),
                               (0x42000002, 'COP0')):
            reason = lint.bad(word)
            self.assertIsNotNone(reason, hex(word))
            self.assertIn(expected, reason, hex(word))


class ElfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ps1-lint-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, content):
        path = self.root / name
        path.write_bytes(content)
        return str(path)

    def main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = lint.main(list(argv))
        return status, out.getvalue()

    def test_clean_program_passes(self):
        status, text = self.main(self.write('clean.elf', elf_fixture.clean_program()))
        self.assertEqual(status, 0, text)
        self.assertIn('6 instruction words inside function symbols checked, 0 not valid', text)

    def test_zero_divisor_trap_fails_and_names_the_function(self):
        status, text = self.main(self.write('teq.elf', elf_fixture.trapping_program()))
        self.assertEqual(status, 1, text)
        self.assertIn('80010008: 00a001f4', text)
        self.assertIn('teq', text)
        self.assertIn('divide+0x8', text)

    def test_data_is_not_code_unless_asked(self):
        program = elf_fixture.mips_elf([elf_fixture.JR_RA, elf_fixture.NOP], [('leaf', 0, 8)],
                                       data_words=[elf_fixture.TEQ_A1_ZERO_7])
        path = self.write('data.elf', program)
        self.assertEqual(self.main(path)[0], 0)
        status, text = self.main(path, '--section', '.data')
        self.assertEqual(status, 1, text)
        self.assertIn('(whole section)', text)

    def test_words_outside_functions_are_not_checked(self):
        program = elf_fixture.mips_elf([elf_fixture.JR_RA, elf_fixture.NOP, elf_fixture.TEQ_A1_ZERO_7], [('leaf', 0, 8)])
        self.assertEqual(self.main(self.write('pad.elf', program))[0], 0)

    def test_unreadable_input_is_an_error_not_a_pass(self):
        self.assertEqual(self.main(self.write('notelf.bin', b'not an executable at all'))[0], 2)
        self.assertEqual(self.main(str(self.root / 'missing.elf'))[0], 2)

    def test_raw_image_scan(self):
        raw = self.write('raw.bin', bytes.fromhex('0800e003' '00000000' 'f401a000'))
        status, text = self.main('--raw', raw, '--base', '0x80010000')
        self.assertEqual(status, 1, text)
        self.assertIn('80010008', text)

    def test_command_line_exit_status(self):
        clean = self.write('clean.elf', elf_fixture.clean_program())
        bad = self.write('teq.elf', elf_fixture.trapping_program())
        self.assertEqual(subprocess.run([sys.executable, str(LINT), clean], capture_output=True).returncode, 0)
        result = subprocess.run([sys.executable, str(LINT), bad], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('not valid on the R3000A', result.stdout)


if __name__ == '__main__':
    unittest.main()
