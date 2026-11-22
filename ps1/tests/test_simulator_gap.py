"""The full-cold simulator must not place code in the PPU scratch reservation."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'tools/source_manifest.json').read_text())


def installed(target):
    """Text of the repository file prepare.py installs as `target` (none of these is patched)."""
    assert not any(patch['target'] == target for patch in MANIFEST['patches']), target
    sources = [entry['source'] for entry in MANIFEST['files'] if entry['target'] == target]
    assert len(sources) == 1, target
    return (ROOT / sources[0]).read_text()


class SimulatorGapTests(unittest.TestCase):
    def test_translation_gap_starts_at_linker_scratch(self):
        linker = installed('ps1rt/ps1_f.ld')
        match = re.search(r'\.\s*=\s*(0x[0-9a-fA-F]+);\s*\.ppuscratch', linker)
        self.assertIsNotNone(match)
        first_reserved = int(match[1], 16)
        self.assertEqual(first_reserved, 0x8017a000)
        # Every script that translates for the extended-memory simulator must use
        # this gap; rebuild_f1.sh makes the translation the function ranking reads.
        scripts = {Path(entry['target']).name: installed(entry['target']) for entry in MANIFEST['files']
                   if entry['target'].startswith('t/') and entry['target'].endswith('.sh')}
        with_gap = {name for name, script in scripts.items() if 'COLD_GAP=' in script}
        self.assertLessEqual({'rebuild_f1.sh', 'final.sh', 'boot_chain.sh'}, with_gap)
        for name in sorted(with_gap):
            gaps = re.findall(r'COLD_GAP=(0x[0-9a-fA-F]+),(0x[0-9a-fA-F]+)', scripts[name])
            self.assertTrue(gaps, name)
            for low, high in gaps:
                self.assertEqual((int(low, 16), int(high, 16)),
                                 (first_reserved, 0x80200000), name)

    @unittest.skipUnless(shutil.which('cc'), 'requires a host C compiler')
    def test_real_copy_predicate_protects_new_scratch_and_both_edges(self):
        runtime = installed('ps1rt/rt.c')
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
