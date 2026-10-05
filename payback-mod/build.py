#!/usr/bin/env python3
"""Build the mashup ROM from your own copy of Payback (Europe).

    python3 payback-mod/build.py "Payback (Europe) (En,Fr,De,Es,It).gba" -o payback-stunt.gba
    python3 payback-mod/build.py "Payback (Europe) (En,Fr,De,Es,It).gba" --bps patches/payback-stunt-park.bps
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paybackmod import bps, expansion, streets, stuntpark  # noqa: E402
from paybackmod.rom import PaybackRom, OLD_TABLE_START, OLD_TABLE_END, NEW_BASE  # noqa: E402


def build(orig, gravity='half', park=True, ramps=True, recolour=True, text=True, build_mode=True):
    rom = PaybackRom(orig)
    cells = {}
    park_cells = stuntpark.build() if park else {}
    if ramps:
        cells.update(streets.build(rom, 0, avoid=park_cells))
    cells.update(park_cells)
    if cells:
        rom.paint(0, cells)
    rom.set_gravity(gravity)
    if recolour:
        rom.swap_bg_green_blue()
    if text:
        rom.retext(expansion.EXACT, expansion.REPLACE)
        for old, new in expansion.INPLACE.items():
            rom.retext_inplace(old, new)
    if build_mode:
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'paybackmod')
        code = open(os.path.join(here, 'editor.bin'), 'rb').read()
        syms = json.load(open(os.path.join(here, 'editor.json')))
        rom.add_build_mode(code, syms, *stuntpark.build_mode_columns())
    return rom


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', help='Payback (Europe) (En,Fr,De,Es,It).gba')
    ap.add_argument('-o', '--out', help='write the modded ROM here')
    ap.add_argument('--bps', help='also write a BPS patch (original -> modded) here')
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
    if a.out:
        open(a.out, 'wb').write(data)
        print(f'wrote {a.out} ({len(data) >> 20} MiB, {len(rom.new_columns)} new map columns)')
    if a.bps:
        moves = [(NEW_BASE, OLD_TABLE_START, OLD_TABLE_END - OLD_TABLE_START)]
        patch = bps.encode(orig, data, moves)
        assert bps.apply(orig, patch) == data
        open(a.bps, 'wb').write(patch)
        print(f'wrote {a.bps} ({len(patch)} bytes)')


if __name__ == '__main__':
    main()
