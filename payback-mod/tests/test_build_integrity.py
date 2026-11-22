"""Runtime provenance and injection boundaries, tested without a game ROM."""
import copy
import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from paybackmod.rom import (PaybackRom, RUNTIME_BASE, RUNTIME_LIMIT,
                            RUNTIME_SOURCES, validate_runtime)
from paybackmod.stuntpark import build_mode_columns


def artifact(code=b'\x00\xb5\x00\xbd'):
    cols = (RUNTIME_BASE + len(code) + 3) & ~3
    metadata = dict(format_version=1, hook=RUNTIME_BASE, cols=cols, maps=cols + 85 * 4,
                    code_size=len(code), code_sha256=hashlib.sha256(code).hexdigest(),
                    source_sha256={name: hashlib.sha256(name.encode()).hexdigest()
                                   for name in RUNTIME_SOURCES})
    return code, metadata


def rom_fixture():
    rom = PaybackRom.__new__(PaybackRom)
    rom.d = bytearray(0x1000000)
    rom.ncols = 1
    rom.new_columns = {}
    rom.painted = {0: [0] * 16384}
    rom.free = 0x9e0000
    rom.runtime_metadata = None
    struct.pack_into('<HH', rom.d, rom.HOOK_CALL - 0x08000000, 0xf064, 0xfade)
    return rom


class RuntimeProvenanceTest(unittest.TestCase):
    def test_source_change_requires_recompile(self):
        code, metadata = artifact()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in RUNTIME_SOURCES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            validate_runtime(code, metadata, source_root=root)
            (root / 'asm/editor.c').write_text('new runtime logic')
            with self.assertRaisesRegex(ValueError, 'stale for asm/editor.c'):
                validate_runtime(code, metadata, source_root=root)

    def test_old_metadata_and_corrupt_code_are_rejected(self):
        code, metadata = artifact()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            validate_runtime(code, {name: metadata[name] for name in ('hook', 'cols', 'maps')})
        with self.assertRaisesRegex(ValueError, 'length'):
            validate_runtime(code[:-1], metadata)
        with self.assertRaisesRegex(ValueError, 'hash'):
            validate_runtime(bytes([code[0] ^ 1]) + code[1:], metadata)
        broken = copy.deepcopy(metadata)
        del broken['source_sha256']['asm/hook.s']
        with self.assertRaisesRegex(ValueError, 'provenance'):
            validate_runtime(code, broken)

    def test_invalid_symbols_cannot_move_code_or_tables(self):
        code, metadata = artifact()
        cases = [('hook', RUNTIME_BASE - 2), ('hook', RUNTIME_BASE + len(code)),
                 ('hook', '0x081b0000'), ('cols', RUNTIME_BASE),
                 ('cols', metadata['cols'] + 4), ('maps', metadata['maps'] - 4),
                 ('maps', RUNTIME_LIMIT)]
        for symbol, value in cases:
            with self.subTest(symbol=symbol, value=value):
                altered = dict(metadata, **{symbol: value})
                with self.assertRaises(ValueError):
                    validate_runtime(code, altered)

    def test_blob_and_tables_must_fit_reserved_region(self):
        code, metadata = artifact(bytes(RUNTIME_LIMIT - RUNTIME_BASE))
        with self.assertRaisesRegex(ValueError, 'reserved injection region'):
            validate_runtime(code, metadata)


class RuntimeInjectionTest(unittest.TestCase):
    def test_wrong_original_call_rejected_before_rom_is_modified(self):
        rom = rom_fixture()
        # Still a well-formed Thumb BL, but targets a different routine.
        struct.pack_into('<HH', rom.d, rom.HOOK_CALL - 0x08000000, 0xf064, 0xfadf)
        before = bytes(rom.d)
        with self.assertRaisesRegex(ValueError, 'original keypad reader'):
            rom.add_build_mode(*artifact(), *build_mode_columns())
        self.assertEqual(bytes(rom.d), before)
        self.assertEqual(rom.ncols, 1)

    def test_truncated_table_rejected_before_rom_is_modified(self):
        rom = rom_fixture()
        flats, ramps, plates = build_mode_columns()
        before = bytes(rom.d)
        for payload in ((flats[:-1], ramps, plates), (flats, ramps[:-1], plates),
                        (flats, [ramps[0][:-1]] + ramps[1:], plates),
                        (flats, ramps, plates[:-1])):
            with self.subTest(lengths=tuple(len(part) for part in payload)):
                with self.assertRaises(ValueError):
                    rom.add_build_mode(*artifact(), *payload)
                self.assertEqual(bytes(rom.d), before)

    def test_valid_injection_preserves_thumb_target_and_tables(self):
        rom = rom_fixture()
        code, metadata = artifact()
        # Both LLVM's even nm address and ELF's Thumb-bit address encode identically.
        metadata['hook'] |= 1
        rom.add_build_mode(code, metadata, *build_mode_columns())
        h1, h2 = struct.unpack_from('<HH', rom.d, rom.HOOK_CALL - 0x08000000)
        target = rom.HOOK_CALL + 4 + ((h1 & 0x7ff) << 12) + ((h2 & 0x7ff) << 1)
        self.assertEqual(target, RUNTIME_BASE)
        pointers = struct.unpack_from('<85I', rom.d, metadata['cols'] - 0x08000000)
        self.assertTrue(all(0x08800000 <= p < rom.col_ptr(rom.ncols) for p in pointers))
        self.assertEqual(rom.d[RUNTIME_BASE - 0x08000000:RUNTIME_BASE - 0x08000000 + len(code)], code)
        self.assertEqual(len(rom.d), 0x1000000)

    def test_space_grid_requires_matching_runtime_and_full_maps(self):
        rom = rom_fixture()
        code, metadata = artifact()
        records = [bytes(60)] * 16384
        with self.assertRaisesRegex(ValueError, 'same validated runtime'):
            rom.add_space(metadata, records, records)
        rom.add_build_mode(code, metadata, *build_mode_columns())
        before = bytes(rom.d)
        with self.assertRaisesRegex(ValueError, 'expected 16384'):
            rom.add_space(metadata, records[:-1], records)
        altered = dict(metadata, maps=metadata['maps'] + 4)
        with self.assertRaisesRegex(ValueError, 'same validated runtime'):
            rom.add_space(altered, records, records)
        self.assertEqual(bytes(rom.d), before)

    def test_space_allocation_failure_does_not_partially_append_columns(self):
        rom = rom_fixture()
        code, metadata = artifact()
        rom.add_build_mode(code, metadata, *build_mode_columns())
        rom.free = len(rom.d) - 16384 * 4
        before = bytes(rom.d)
        column_count = rom.ncols
        records = [bytes(60)] * 16384
        with self.assertRaisesRegex(ValueError, 'ROM capacity'):
            rom.add_space(metadata, records, records)
        self.assertEqual(bytes(rom.d), before)
        self.assertEqual(rom.ncols, column_count)

    def test_variant_markers_are_unique_but_boundary_bytes_are_unchanged(self):
        rom = rom_fixture()
        code, metadata = artifact()
        rom.add_build_mode(code, metadata, *build_mode_columns())
        corner = bytes(rom.column(0))
        records = [corner] * 16384
        rom.add_space(metadata, records, records)
        tables = struct.unpack_from('<3I', rom.d, metadata['maps'] - 0x08000000)
        space, city, neo = [struct.unpack_from('<16384I', rom.d, p - 0x08000000) for p in tables]
        self.assertEqual(len({space[0], city[0], neo[0]}), 3)
        self.assertEqual(city[0], rom.col_ptr(0))
        self.assertEqual(rom.painted[0][0], 0)
        for grid in (space, neo):
            self.assertEqual(grid.count(grid[0]), 1)
            self.assertEqual(bytes(rom.d[grid[0] - 0x08000000:grid[0] - 0x08000000 + 60]), corner)
            self.assertNotEqual(rom.col_ptr(rom.add_column(corner)), grid[0])
        self.assertEqual(rom.map_marker_pointers, {'space': space[0], 'neo': neo[0]})

    def test_marker_capacity_is_reserved_before_any_space_mutation(self):
        rom = rom_fixture()
        code, metadata = artifact()
        rom.add_build_mode(code, metadata, *build_mode_columns())
        corner = bytes(60)
        rom.add_column(corner)
        records = [corner] * 16384
        rom.ncols = 32767  # ordinary deduplicated columns fit; both markers do not
        before = bytes(rom.d)
        with self.assertRaisesRegex(ValueError, 'column index limit'):
            rom.add_space(metadata, records, records)
        self.assertEqual(bytes(rom.d), before)
        self.assertEqual(rom.ncols, 32767)


if __name__ == '__main__':
    unittest.main()
