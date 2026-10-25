"""Shared set-up of the content tests: import paths, a host compiler, the player's ROM ($PAYBACK_ROM) and the atlas cache
(tests that need them skip without; the fixtures use synthetic maps and need neither)."""
import os
import shutil
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
CACHE = os.environ.get('SF_ATLAS_CACHE', os.path.join(ROOT, 'build', 'atlas'))
HOSTCC = os.environ.get('HOSTCC') or shutil.which('clang') or shutil.which('gcc')
needs_cc = unittest.skipUnless(HOSTCC, 'no host C compiler')


def cached(levels=range(11)):
    """{level: Atlas} from the cache folder (no ROM needed): the levels it holds."""
    import atlas
    out = {}
    for m in levels:
        a = atlas.Atlas.cached(CACHE, m)
        if a is not None:
            out[m] = a
    return out


have_atlas = os.path.isdir(CACHE) and any(f.endswith('.pkl') for f in os.listdir(CACHE))
needs_atlas = unittest.skipUnless(have_atlas, 'no atlas cache (run tools/content/sfc.py check --rom ROM once, or set SF_ATLAS_CACHE)')
