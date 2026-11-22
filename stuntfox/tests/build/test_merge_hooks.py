"""Keep ROM-only entry points alive when linking with section garbage collection.

The original cartridge calls these wrappers only after build.py patches its BLs.
There is no reference from the linked Stunt Fox code, so the production linker
script must retain them explicitly. This test uses that script and the actual
ARM wrappers, without a cartridge image or generated world assets.
"""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MergeHookBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [tool for tool in ('clang', 'ld.lld', 'llvm-nm') if not shutil.which(tool)]
        if missing:
            raise RuntimeError('merged ARM hook gate needs: ' + ', '.join(missing))
        spec = importlib.util.spec_from_file_location('merge_hook_build', ROOT / 'build.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def test_native_overlay_entries_survive_unreferenced(self):
        with tempfile.TemporaryDirectory(prefix='stuntfox-merge-hooks-') as temp:
            folder = Path(temp)
            stub = folder / 'runtime.c'
            stub.write_text('#include "stage2.h"\n'
                            'S2Frame s2f;\n'
                            'int s2_ready(void) { return s2f.mode; }\n'
                            'int st_active(void) { return s2f.walk; }\n'
                            'int cp_ending(void) { return s2f.menu; }\n'
                            'void sf_frame(void) {}\n')
            objects = []
            for source in (ROOT / 'src' / 'nativehud.c', stub):
                obj = folder / (source.stem + '.o')
                result = subprocess.run([
                    'clang', *self.builder.CFLAGS, '-mthumb', '-DMERGE',
                    '-I', str(ROOT / 'src'), '-c', str(source), '-o', str(obj),
                ], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                objects.append(str(obj))
            elf = folder / 'hooks.elf'
            result = subprocess.run([
                'ld.lld', '-T', str(ROOT / 'src' / 'merge.ld'), '--gc-sections',
                '-e', 'sf_frame', '-o', str(elf), *objects,
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(['llvm-nm', str(elf)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            symbols = {parts[2]: int(parts[0], 16)
                       for parts in (line.split() for line in result.stdout.splitlines())
                       if len(parts) == 3}
            for name in ('sf_native_banner', 'sf_native_model'):
                self.assertIn(name, symbols, name + ' was discarded before ROM patching')
                self.assertGreaterEqual(symbols[name], self.builder.MERGE_BASE)
                self.assertLess(symbols[name], 0x08300000)


if __name__ == '__main__':
    unittest.main()
