#!/usr/bin/env python3
"""ob_session.py: run a session script of sessions/ (framework payback.py / ps1game.py of the rig) on an accurate core
with openboot as firmware.  Nothing of the framework is changed on disk: open_game() is wrapped so that the Game object gets
the openboot system directory and the core options of tools/obrun.py.

  ob_session.py [--sys DIR] SESSION.py --disc X.cue --out DIR --core swanstation|beetle [session arguments ...]

The system directory is --sys DIR as given, else $RIG_SYSTEM, else ps1/rig/system, which must then hold openboot as
scph5500.bin, scph5501.bin and scph5502.bin (README.md).  The cores are looked up in $RIG_CORES (default ps1/rig/cores)."""
import os, runpy, sys
HERE = os.path.dirname(os.path.abspath(__file__)); RIG = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, RIG)
from obrun import DEFAULT_OPTS  # noqa: E402
from retro_ps1 import RigSetupError, system_dir  # noqa: E402
argv = sys.argv[1:]
sysdir = None
if argv and argv[0] == '--sys':
    sysdir = os.path.abspath(argv[1]); argv = argv[2:]
if not argv:
    sys.exit(__doc__)
session = os.path.abspath(argv[0])
import payback  # noqa: E402
_open = payback.open_game


def open_game(args, name, **kw):
    core = args.core
    if core in ('swanstation', 'beetle'):
        try:
            kw.setdefault('sysdir', system_dir(sysdir))
        except RigSetupError as ex:
            sys.exit('ob_session: %s' % ex)
        o = dict(DEFAULT_OPTS.get(core, {})); o.update(kw.get('opts') or {}); kw['opts'] = o
        print('ob_session: core %s, system directory %s (openboot), options %s' % (core, kw['sysdir'], o), flush=True)
    return _open(args, name, **kw)


payback.open_game = open_game
sys.argv = [session] + argv[1:]
runpy.run_path(session, run_name='__main__')
