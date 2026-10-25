"""Stage 2's part of the merge build: build.py calls the three hooks below and nothing else of stage 2.

    pre_world(rom, orig)            after the phones are added, before the worlds are built: a stage-2 arena
                                    (tools/content/mkarena.py) regrids its map; returns {level: loops} for mkworld
    pre_link(rom, orig, gen)        after the worlds and tables, before the compile: the content blobs go above
                                    8 MiB (rom.alloc) and into the link as symbols; returns (sources, ld flags)
    post_link(rom, sym, elf, ...)   after the link and the code is placed: the redirects that only apply when
                                    a package has defined its symbol, then memguard, pbapi_check and lint_text

A package adds its source by creating the file named in S2_SOURCES (or its blob builder in tools/content/);
nobody edits build.py for it. Sources named here are built in the merge build only.
"""
import importlib.util
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
GBA = 0x08000000

# E: mission.c hudline.c msn_draw.c; P: campaign.c save.c; S: station.c stationdraw.c; K: sgx.c (F: s2core.c)
S2_SOURCES = ['s2core.c', 'mission.c', 'hudline.c', 'msn_draw.c', 'campaign.c', 'save.c', 'station.c',
              'stationdraw.c', 'sgx.c']

# (symbol the link defines, builders in the order tried: a path under stuntfox/, and the function in it)
BLOBS = (('s2_blob', ('tools/content/sfc.py', 'tests/vm/mkdemo.py')),
         ('st_blob', ('tools/content/station.py',)))
ARENA = 'tools/content/mkarena.py'

BANNER_BY_NUMBER = 0x0807a684     # Payback's banner by number (pbapi.h PBA_BANNER_IDX_FN); the veneer calls it
BANNER_SITES = 72                 # its calls in Payback's code (probe P2: counted from the ROM image, asserted here)
EEP_IDENT = 0x0807c3ac            # Payback's EEPROM identify (pbapi.h PBA_EEP_IDENT), called from one place
EEP_IDENT_SITE = 0x08027c76       # (that bl; P's sf_eep_identify takes it over when P defines it)


def present(paths):
    return [p for p in (os.path.join(ROOT, q) for q in paths) if os.path.exists(p)]


def load(path):
    """Import a builder by its file: one that exists but does not import or run fails the build."""
    spec = importlib.util.spec_from_file_location('s2_' + re.sub(r'\W', '_', os.path.relpath(path, ROOT)), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sources():
    """The stage-2 .c files that exist (build.py leaves them out of the plain build and the src/ glob)."""
    out = [os.path.join(SRC, f) for f in S2_SOURCES if os.path.exists(os.path.join(SRC, f))]
    out += [p for p in os.environ.get('S2_EXTRA_SRC', '').split(os.pathsep) if p]     # (tests: dummy strong symbols)
    return out


def pre_world(rom, orig):
    arena = present([ARENA])
    if not arena:
        return {}
    return load(arena[0]).build(rom, orig) or {}


def pre_link(rom, orig, gen):
    flags = []
    for sym, builders in BLOBS:
        found = present(b for b in builders if not b.startswith('tests/') or os.environ.get('S2_DEMO'))     # (the demo chapters only on request)
        data = load(found[0]).build(rom, orig, gen) if found else bytes(8)     # (8 zero bytes: no content)
        assert isinstance(data, (bytes, bytearray)) and len(data) >= 8, '%s: a builder gave no blob' % sym
        at = GBA + rom.alloc(bytes(data))
        flags.append('--defsym=%s=0x%08x' % (sym, at))
        print('s2build: %s %d bytes at 0x%08x%s' % (sym, len(data), at, '' if found else ' (no builder: empty)'))
    return sources(), flags


def post_link(rom, sym, elf, redirect, calls_to, orig, files):
    """redirect(site, old, new) and calls_to(target) are build.py's; orig the Payback ROM; files the
    stage-2 sources that were built."""
    import memguard
    import pbapi_check
    import lint_text
    if 's2_banner_veneer' in sym:
        sites = calls_to(BANNER_BY_NUMBER)
        assert len(sites) == BANNER_SITES, 'expected %d calls to the banner by number, found %d' % (BANNER_SITES, len(sites))
        for site in sites:
            redirect(site, BANNER_BY_NUMBER, sym['s2_banner_veneer'])
        print('s2build: %d banner sites -> s2_banner_veneer' % len(sites))
    if 'sf_eep_identify' in sym:
        redirect(EEP_IDENT_SITE, EEP_IDENT, sym['sf_eep_identify'])
        print('s2build: eeprom identify -> sf_eep_identify')
    print(memguard.check(elf, os.path.join(SRC, 'merge.ld'), os.path.join(ROOT, 'memmap.txt')))
    print(pbapi_check.check(orig, SRC, files))
    print(lint_text.check(ROOT, files))
