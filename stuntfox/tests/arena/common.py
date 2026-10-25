"""Shared set-up of the arena tests: import paths and the player's Payback ROM ($PAYBACK_ROM; tests that need it skip without)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
for p in (os.path.join(ROOT, 'tools', 'content'), os.path.join(ROOT, 'tools'), os.path.join(ROOT, '..', 'payback-mod')):
    if p not in sys.path:
        sys.path.insert(0, p)

ROM_PATH = os.environ.get('PAYBACK_ROM', '')
have_rom = bool(ROM_PATH) and os.path.exists(ROM_PATH)
needs_rom = unittest.skipUnless(have_rom, 'set PAYBACK_ROM to the Payback (Europe) ROM')
_rom = {}


def rom_bytes():
    if 'b' not in _rom:
        _rom['b'] = open(ROM_PATH, 'rb').read()
    return _rom['b']


def fresh_rom():
    from paybackmod.rom import PaybackRom
    return PaybackRom(rom_bytes())
