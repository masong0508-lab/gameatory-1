#!/usr/bin/env python3
"""Build the mashup ROM from your own copy of Payback (Europe).

    python3 payback-mod/build.py "Payback (Europe) (En,Fr,De,Es,It).gba" -o payback-stunt.gba
    python3 payback-mod/build.py "Payback (Europe) (En,Fr,De,Es,It).gba" --bps patches/payback-stunt-park.bps
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paybackmod import bps, expansion, newcity, space, stuntpark  # noqa: E402
from paybackmod.rom import PaybackRom, OLD_TABLE_START, OLD_TABLE_END, NEW_BASE, validate_runtime  # noqa: E402


def load_runtime():
    root = Path(__file__).resolve().parent
    try:
        code = (root / 'paybackmod' / 'editor.bin').read_bytes()
        metadata = json.loads((root / 'paybackmod' / 'editor.json').read_text())
    except (OSError, ValueError) as exc:
        raise ValueError('compiled runtime is missing or unreadable; run sh payback-mod/asm/build.sh') from exc
    validate_runtime(code, metadata, source_root=root)
    return code, metadata


def build(orig, gravity='half', park=True, recolour=True, text=True, build_mode=True, physics=True):
    if build_mode:
        code, syms = load_runtime()
    rom = PaybackRom(orig)
    rom.build_settings = dict(gravity=gravity, park=park, recolour=recolour,
                              text=text, build_mode=build_mode, physics=physics)
    cells = {}
    park_cells = stuntpark.build() if park else {}
    cells.update(park_cells)
    if cells:
        rom.paint(0, cells)
    rom.set_gravity(gravity)
    if physics:
        rom.tune_vehicles()
    if recolour:
        rom.swap_bg_green_blue()
    if text:
        rom.retext(expansion.EXACT, expansion.REPLACE)
        for old, new in expansion.INPLACE.items():
            rom.retext_inplace(old, new)
    if build_mode:
        rom.add_build_mode(code, syms, *stuntpark.build_mode_columns())
        city = [rom.column(i) for i in (rom.painted.get(0) or rom.grid(0))]
        neo = list(city)
        for (x, y), col in newcity.build(city).items():
            neo[x * 128 + y] = col
        rom.add_space(syms, space.build(city), neo)
    return rom


def build_report(orig, rom, data, patch=None):
    """Content identities only: the same build has the same report on every machine."""
    def identity(blob):
        return dict(size_bytes=len(blob), sha1=hashlib.sha1(blob).hexdigest(),
                    sha256=hashlib.sha256(blob).hexdigest())
    root = Path(__file__).resolve().parent
    sources = [root / 'build.py'] + sorted((root / 'paybackmod').glob('*.py'))
    report = dict(format_version=1, settings=rom.build_settings,
                  source_rom=identity(orig), output_rom=identity(data),
                  runtime=rom.runtime_metadata,
                  tooling_sha256={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sources},
                  map_columns=rom.ncols,
                  new_columns=len(rom.new_columns) + len(rom.marker_columns),
                  allocation_end=rom.free, remaining_rom_bytes=len(data) - rom.free)
    if rom.runtime_metadata is not None:
        report['runtime_map_markers'] = rom.map_marker_pointers
    if patch is not None:
        report['bps_patch'] = identity(patch)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', help='Payback (Europe) (En,Fr,De,Es,It).gba')
    ap.add_argument('-o', '--out', help='write the modded ROM here')
    ap.add_argument('--bps', help='also write a BPS patch (original -> modded) here')
    ap.add_argument('--report', help='write a deterministic JSON build report with source and output hashes')
    ap.add_argument('--gravity', choices=sorted(PaybackRom.GRAVITY), default='half',
                    help='vehicle/character gravity (default: half, for longer jumps)')
    ap.add_argument('--no-park', action='store_true', help='leave Freedom City unchanged')
    a = ap.parse_args()
    if not (a.out or a.bps):
        ap.error('give -o and/or --bps')
    orig = open(a.rom, 'rb').read()
    try:
        rom = build(orig, a.gravity, not a.no_park)
    except ValueError as e:
        sys.exit(str(e))
    data = rom.data()
    patch = None
    if a.out:
        open(a.out, 'wb').write(data)
        print(f'wrote {a.out} ({len(data) >> 20} MiB, {len(rom.new_columns) + len(rom.marker_columns)} new map columns)')
    if a.bps:
        moves = [(NEW_BASE, OLD_TABLE_START, OLD_TABLE_END - OLD_TABLE_START)]
        patch = bps.encode(orig, data, moves)
        assert bps.apply(orig, patch) == data
        open(a.bps, 'wb').write(patch)
        print(f'wrote {a.bps} ({len(patch)} bytes)')
    if a.report:
        Path(a.report).write_text(json.dumps(build_report(orig, rom, data, patch), indent=2, sort_keys=True) + '\n')
        print(f'wrote {a.report}')


if __name__ == '__main__':
    main()
