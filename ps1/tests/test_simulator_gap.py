"""The full-cold simulator must not place code in the PPU scratch reservation."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SimulatorGapTests(unittest.TestCase):
    def test_translation_gap_starts_at_linker_scratch(self):
        linker = (ROOT / 'stage16/merge/ps1rt/ps1_f.ld').read_text()
        match = re.search(r'\.\s*=\s*(0x[0-9a-fA-F]+);\s*\.ppuscratch', linker)
        self.assertIsNotNone(match)
        first_reserved = int(match[1], 16)
        self.assertEqual(first_reserved, 0x8017a000)
        for name in ('final.sh', 'boot_chain.sh'):
            script = (ROOT / 'stage7/integration/t' / name).read_text()
            gaps = re.findall(r'COLD_GAP=(0x[0-9a-fA-F]+),(0x[0-9a-fA-F]+)', script)
            self.assertTrue(gaps, name)
            for low, high in gaps:
                self.assertEqual((int(low, 16), int(high, 16)),
                                 (first_reserved, 0x80200000), name)

    @unittest.skipUnless(shutil.which('cc'), 'requires a host C compiler')
    def test_real_copy_predicate_protects_new_scratch_and_both_edges(self):
        runtime = (ROOT / 'stage16/merge/ps1rt/rt.c').read_text()
        match = re.search(r'static int sim_cold_overlap\([^)]*\)\{[^}]*\}', runtime)
        self.assertIsNotNone(match)
        self.assertIn('if(sim_cold_overlap(dst,dst+16384))', runtime)
        self.assertIn('if(!sim_cold_overlap(a,a+1))', runtime)
        # Compile the production predicate, with the linker's fixed symbol
        # represented as a host-sized pointer; no game bytes or MIPS tools.
        source = '''#include <stdint.h>
typedef uintptr_t u32;
#define __ppu_start ((unsigned char *)(uintptr_t)0x8017a000)
''' + match[0] + '''
int main(void) {
    if (sim_cold_overlap(0x80178000, 0x8017a000)) return 1;
    if (!sim_cold_overlap(0x80179fff, 0x8017a001)) return 2;
    if (!sim_cold_overlap(0x8017a000, 0x8017a001)) return 3;
    if (!sim_cold_overlap(0x8017bfff, 0x8017c000)) return 4;
    if (!sim_cold_overlap(0x801fffff, 0x80200000)) return 5;
    if (sim_cold_overlap(0x80200000, 0x80204000)) return 6;
    /* Simulate the actual straddling CD group: only its first 8 KiB copy. */
    unsigned copied=0;
    for (u32 a=0x80178000; a<0x8017c000; ++a)
        if (!sim_cold_overlap(a,a+1)) ++copied;
    return copied != 0x2000;
}
'''
        with tempfile.TemporaryDirectory(prefix='ps1-gap-test-') as temp:
            code = Path(temp) / 'gap.c'
            exe = Path(temp) / 'gap'
            code.write_text(source)
            result = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                     str(code), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(subprocess.run([str(exe)]).returncode, 0)


if __name__ == '__main__':
    unittest.main()
