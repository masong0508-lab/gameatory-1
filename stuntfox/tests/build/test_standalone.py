"""Link the production standalone ARM game without cartridge data.

    python3 -m unittest discover -s tests/build -v

Requires clang, ld.lld and llvm-nm. Uses the same compiler flags, source selection
and linker script as build.py, with generated tables and a synthetic SFW4 world.
"""
import importlib.util
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class StandaloneBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [tool for tool in ('clang', 'ld.lld', 'llvm-nm') if not shutil.which(tool)]
        if missing:
            raise RuntimeError('standalone ARM gate needs: ' + ', '.join(missing))
        spec = importlib.util.spec_from_file_location('standalone_build', ROOT / 'build.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def test_complete_game_links_with_stack_headroom(self):
        with tempfile.TemporaryDirectory(prefix='stuntfox-arm-') as temp:
            folder = Path(temp)
            gen = folder / 'gen'
            gen.mkdir()
            make_world = runpy.run_path(str(ROOT / 'tests' / 'physics' / 'test_sim.py'))['world_fixture']
            (gen / 'world.bin').write_bytes(make_world())
            self.builder.mkassets.main(str(gen / 'tables.c'))
            elf, symbols = self.builder.link_standalone(str(folder), str(gen))
            self.assertTrue(Path(elf).is_file())
            self.assertGreaterEqual(symbols['__stack_top'] - symbols['__bss_end'], 3072)
            self.assertLessEqual(symbols['__sbss_end'], 0x02040000)
            for name in ('world_draw', 'model_draw', 'r_poly', 'vnorm'):
                self.assertGreaterEqual(symbols[name], 0x03000000, name)
                self.assertLess(symbols[name], symbols['__bss_end'], name)
            for name in ('body_integrate', 'model_init', 'world_data'):
                self.assertGreaterEqual(symbols[name], 0x08000000, name)
                self.assertLess(symbols[name], 0x0a000000, name)

    def test_linker_rejects_using_the_stack_for_static_data(self):
        with tempfile.TemporaryDirectory(prefix='stuntfox-stack-') as temp:
            folder = Path(temp)
            source = folder / 'oversized.c'
            source.write_text('volatile unsigned char state[0x7304];\n'
                              'void _start(void) { state[0] = 1; }\n')
            obj = folder / 'oversized.o'
            subprocess.run(['clang', *self.builder.CFLAGS, '-mthumb', '-c', str(source), '-o', str(obj)], check=True)
            result = subprocess.run(['ld.lld', '-T', str(ROOT / 'src' / 'gba.ld'), '--gc-sections',
                                     '-e', '_start', '-o', str(folder / 'oversized.elf'), str(obj)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('system stack', result.stderr)


if __name__ == '__main__':
    unittest.main()
