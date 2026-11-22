"""The real host physics runner on synthetic SFW4 worlds; no Payback ROM needed.

    python3 -m unittest discover -s tests/physics -v

The second deck sits beyond byte 262144, where the old runner truncated the
world and crashed. Exercise the production loader and actual car/ship updates,
then check that broken section tables are rejected before physics can read them.
"""
import importlib.util
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def world_fixture():
    cells = 128 * 128
    # No borrowed data: a flat street, and a distant two-deck structure. Its top
    # is 8192 units, so world_init must read the section past the old buffer end.
    deck = bytearray(cells * 4)
    deck2 = bytearray(cells * 4)
    remote_cell = (64 * 128) * 4
    struct.pack_into('<bbbB', deck, remote_cell, -8, 8, 8, 1)
    struct.pack_into('<bbbB', deck2, remote_cell, 48, 88, 88, 1)
    sections = [
        b'', b'', b'', b'', bytes(256 * 4), b'',
        struct.pack('<hhBB', 0, 0, 1, 1) * cells, bytes(256 * 4), b'', b'',
        b'\xff\xff' * cells, b'', bytes(deck), bytes(cells * 3), bytes(deck2),
        b'\xff\xff' * cells, bytes(cells) + struct.pack('<HH', 1, 0) + struct.pack('<BBBxhh', 1, 1, 0, 0, 256),
    ]
    data = bytearray(26 * 4)
    offsets = []
    for part in sections:
        data += bytes((-len(data)) & 3)
        offsets.append(len(data))
        data += part
    struct.pack_into('<4s7Ii17I', data, 0, b'SFW4', *([0] * 8), *offsets)
    return data


class SimulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = os.environ.get('HOSTCC') or shutil.which('clang') or shutil.which('gcc')
        if not cc:
            raise RuntimeError('physics tests need a host C compiler (HOSTCC, clang or gcc)')
        cls.tmp = tempfile.TemporaryDirectory(prefix='stuntfox-physics-')
        cls.folder = Path(cls.tmp.name)
        cls.addClassCleanup(cls.tmp.cleanup)
        spec = importlib.util.spec_from_file_location('physics_mkassets', ROOT / 'tools' / 'mkassets.py')
        assets = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(assets)
        table = cls.folder / 'tables.c'
        assets.main(str(table))
        cls.exe = cls.folder / 'sim'
        sources = ['fx.c', 'world.c', 'physics.c', 'car.c', 'ship.c', 'loops.c']
        subprocess.run([cc, '-O1', '-g', '-fno-builtin', '-Wall', '-Wextra', '-Wno-unused-function',
                        '-Wno-unused-parameter', '-I' + str(ROOT / 'src'),
                        *[str(ROOT / 'src' / s) for s in sources], str(table),
                        str(ROOT / 'tools' / 'sim' / 'sim.c'), '-o', str(cls.exe)], check=True)

    def simulate(self, data, mode='loop'):
        path = self.folder / (self.id().split('.')[-1] + '.bin')
        path.write_bytes(data)
        return subprocess.run([str(self.exe), str(path), mode], capture_output=True, text=True, timeout=15)

    def reject(self, data, why):
        result = self.simulate(data)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(why, result.stderr)
        self.assertNotIn('pos ', result.stdout)

    def test_full_world_drives(self):
        data = world_fixture()
        self.assertGreater(len(data), 262144)
        result = self.simulate(data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('highest collision surface 8256', result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 90)
        self.assertIn('wheels 4', lines[-1])
        first_x = int(re.search(r'pos\s+(-?\d+)', lines[0])[1])
        last_x = int(re.search(r'pos\s+(-?\d+)', lines[-1])[1])
        self.assertGreater(last_x - first_x, 10000)

    def test_full_world_flies(self):
        result = self.simulate(world_fixture(), 'ship')
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 60)
        height = int(re.search(r'pos\s+-?\d+\s+(-?\d+)', lines[-1])[1])
        self.assertGreater(height, 1000)

    def test_truncated_header(self):
        self.reject(b'SFW4', 'header')

    def test_truncated_world(self):
        self.reject(world_fixture()[:-32], 'section')

    def test_truncated_ladders(self):
        self.reject(world_fixture()[:-4], 'ladder')

    def test_overlarge_world(self):
        self.reject(world_fixture() + bytes(1 << 20), '1 MiB')

    def test_count_cannot_wrap_size_check(self):
        data = world_fixture()
        struct.pack_into('<I', data, 4, 0xffffffff)
        self.reject(data, 'section')

    def test_invalid_sector(self):
        data = world_fixture()
        at = struct.unpack_from('<I', data, 13 * 4)[0]
        struct.pack_into('<HH', data, at, 0, 1)
        self.reject(data, 'sector')

    def test_misaligned_offset(self):
        data = world_fixture()
        at = struct.unpack_from('<I', data, 23 * 4)[0]
        struct.pack_into('<I', data, 23 * 4, at + 1)
        self.reject(data, 'section')


if __name__ == '__main__':
    unittest.main()
