"""Check independent allocation properties and real PPU backdrop-cache behavior."""
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

PS1 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ps1_prepare_memory', PS1 / 'tools/prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class MemoryLayoutTests(unittest.TestCase):
    def test_persistent_vram_allocations_are_bounded_and_disjoint(self):
        values = {name: int(value) for name, value in re.findall(
            r'^#define PS1_VRAM_(\w+) (\d+)$', (PS1 / 'include/ps1_vram.h').read_text(), re.M)}
        regions = [('display buffers', 0, 0, 320, 480),
                   ('font', 960, 0, 32, 48), ('font CLUT', 0, 488, 16, 1),
                   ('world CLUTs', 0, 480, 256, 8)]
        regions += [(f'world page {page}', 320 + 128 * (page % 5), 256 * (page // 5), 128, 256)
                    for page in range(7)]
        for prefix in ('MODEL', 'MODEL_CLUT', 'PPU_L1', 'PPU_CLUT'):
            regions.append((prefix, *(values[prefix + '_' + key] for key in ('X', 'Y', 'W', 'H'))))
        for page in range(values['PPU_ATLAS_PAGES']):
            regions.append((f'PPU cache {page}', values['PPU_ATLAS_X'] + page * values['PPU_ATLAS_PAGE_W'],
                            values['PPU_ATLAS_Y'], values['PPU_ATLAS_PAGE_W'], values['PPU_ATLAS_PAGE_H']))
        for bits in (4, 8):
            regions.append((f'PPU OBJ{bits}', values['PPU_OBJ_X'], values[f'PPU_OBJ{bits}_Y'],
                            values['PPU_OBJ_W'], values['PPU_OBJ_H']))
        for index, (name, x, y, width, height) in enumerate(regions):
            self.assertTrue(0 <= x < x + width <= 1024 and 0 <= y < y + height <= 512, name)
            for other, ox, oy, ow, oh in regions[index + 1:]:
                overlap = x < ox + ow and ox < x + width and y < oy + oh and oy < y + height
                self.assertFalse(overlap, f'{name} overlaps {other}')
        # PS1 texture-page addressing must represent every model texel.
        u = (values['MODEL_X'] - values['MODEL_TPAGE_X']) * 4
        v = values['MODEL_Y'] - values['MODEL_TPAGE_Y']
        self.assertTrue(0 <= u < u + values['MODEL_W'] * 4 <= 256)
        self.assertTrue(0 <= v < v + values['MODEL_H'] <= 256)
        self.assertEqual(values['MODEL_TPAGE_X'] % 64, 0)
        self.assertEqual(values['MODEL_CLUT_X'] % 16, 0)

    @unittest.skipUnless(shutil.which('cc') and shutil.which('patch'), 'requires host C compiler and patch')
    def test_backdrop_cache_eviction_keeps_drawn_guest_pages(self):
        with tempfile.TemporaryDirectory(prefix='ps1-ppu-cache-') as directory:
            root = Path(directory)
            tree = root / 'source'
            prepare.assemble(output=tree)
            exe = root / 'ppu-cache'
            result = subprocess.run(['cc', '-std=c11', '-O2', '-Wno-unused-function',
                                     '-I', str(tree / 'ps1rt'), str(PS1 / 'tests/ppu_cache_native.c'),
                                     '-o', str(exe)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(exe)], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
