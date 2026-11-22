"""ROM-free checks for exact staged-source assembly and the renderer ABI."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PS1_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ps1_prepare", PS1_ROOT / "tools/prepare.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


@unittest.skipUnless(shutil.which("patch"), "requires the standard patch utility")
class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ps1-prepare-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def altered_manifest(self, change):
        manifest = json.loads(prepare.MANIFEST.read_text())
        change(manifest)
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest))
        return path

    def test_complete_source_assembly_is_deterministic_and_preserves_stage16(self):
        one, two = self.root / "one", self.root / "two"
        first = prepare.assemble(output=one)
        second = prepare.assemble(output=two)
        self.assertEqual(first, second)
        self.assertEqual((one / "SOURCE_MANIFEST.json").read_bytes(), (two / "SOURCE_MANIFEST.json").read_bytes())
        rt = (one / "ps1rt/rt.c").read_text()
        renderer = (one / "sf/sf3.c").read_text()
        for text in ('#include "ppu12.h"', 'PPU_SF3HUD', 'static s32 g3_map', 'sf3_plook=', 'MODELTOUR'):
            self.assertIn(text, rt)
        self.assertIn('#include "../include/sf_entity.h"', rt)
        self.assertIn('#include "../include/sf_entity.h"', renderer)
        self.assertIn('#include "models.h"', renderer)
        self.assertIn('HASH_HOST', (one / "mkps1.py").read_text())
        self.assertIn('s.mr', (one / "t/sim4.py").read_text())
        self.assertFalse(any(p.suffix.lower() in ('.gba', '.iso', '.bin', '.exe', '.pkl') for p in one.rglob('*')))

    def test_modified_source_is_rejected_without_publishing(self):
        manifest = self.altered_manifest(lambda m: m['files'][0].update(sha256='0' * 64))
        output = self.root / "result"
        with self.assertRaisesRegex(prepare.PreparationError, 'source hash mismatch'):
            prepare.assemble(manifest_path=manifest, output=output)
        self.assertFalse(output.exists())

    def test_wrong_patch_base_is_rejected_without_publishing(self):
        manifest = self.altered_manifest(lambda m: m['patches'][0].update(input_sha256='0' * 64))
        output = self.root / "result"
        with self.assertRaisesRegex(prepare.PreparationError, 'patch input hash mismatch'):
            prepare.assemble(manifest_path=manifest, output=output)
        self.assertFalse(output.exists())

    def test_wrong_patch_result_is_rejected_without_publishing(self):
        manifest = self.altered_manifest(lambda m: m['patches'][0].update(result_sha256='0' * 64))
        output = self.root / "result"
        with self.assertRaisesRegex(prepare.PreparationError, 'patch result hash mismatch'):
            prepare.assemble(manifest_path=manifest, output=output)
        self.assertFalse(output.exists())

    def test_output_collision_preserves_existing_files(self):
        output = self.root / "result"
        output.mkdir()
        (output / "keep.txt").write_text('previous work')
        with self.assertRaisesRegex(prepare.PreparationError, 'output already exists'):
            prepare.assemble(output=output)
        self.assertEqual((output / "keep.txt").read_text(), 'previous work')

    def test_manifest_cannot_write_outside_destination(self):
        manifest = self.altered_manifest(lambda m: m['files'][0].update(target='../escape.txt'))
        with self.assertRaisesRegex(prepare.PreparationError, 'unsafe manifest path'):
            prepare.assemble(manifest_path=manifest, output=self.root / 'result')
        self.assertFalse((self.root / 'escape.txt').exists())

    @unittest.skipUnless(shutil.which('cc'), 'requires a host C compiler')
    def test_shared_entity_abi_has_expected_offsets(self):
        source = self.root / 'layout.c'
        source.write_text('typedef int s32; typedef unsigned short u16; typedef unsigned char u8;\n'
                          '#include "sf_entity.h"\n'
                          'int main(void) { SfEnt e = {0}; e.look=7; e.pol=1; '
                          'return ((unsigned char *)&e)[16] != 7 || ((unsigned char *)&e)[17] != 1; }\n')
        exe = self.root / 'layout'
        result = subprocess.run(['cc', '-std=c11', '-Wall', '-Werror', '-I', str(PS1_ROOT / 'include'),
                                 str(source), '-o', str(exe)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(subprocess.run([str(exe)]).returncode, 0)


if __name__ == '__main__':
    unittest.main()
