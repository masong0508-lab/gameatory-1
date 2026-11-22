#!/usr/bin/env python3
"""Reload the reusable save states in a FRESH process and prove them: the state is loaded, run for the number of frames its
.json names, and RAM + picture are compared with the fingerprint taken when it was saved.

  python3 sessions/state_check.py --disc DISC.cue --out runs/states [--syms payback.elf] [--state states/title.state ...]"""
import os, sys, glob, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *


def extra(ap):
    ap.add_argument('--state', action='append', default=None, help='state file (default: every *.state in STATE_DIR)')


def main():
    a = std_args(__doc__, extra)
    found = a.state or sorted(glob.glob(os.path.join(a.state_dir, '*.state')))
    g = open_game(a, 'state_check')
    states = []
    for path in found:
        fits, why = g.state_fits(path)
        if fits:
            states.append(path)
        else:
            g.note('%s skipped: %s' % (os.path.basename(path), why))
    g.check(bool(states), 'states of this disc and core to check', states or 'none in %s (make them with --save-state)' % (a.state or a.state_dir))
    for path in states:
        name = os.path.basename(path)
        try:
            meta = g.load_state_file(path)
        except Exception as e:
            g.check(False, '%s loads' % name, e)
            continue
        want = meta.get('fingerprint')
        n = meta.get('verify_frames') or 0
        if n > 1:
            g.run(n - 1)                   # load_state_file ran one frame already
        got = g.fingerprint()
        what = 'RAM and frame buffer' if (want or {}).get('fb') and got.get('fb') else ('RAM and picture' if (want or {}).get('img') and got.get('img') else 'RAM')
        g.check(want is not None and g.same_fingerprint(got, want), '%s: reloaded in a fresh process, %d frames later %s are those of the saving process' % (name, n, what),
                'note: %s; saved at frame %s; ram sha1 %s, frame buffer sha1 %s%s' % (meta.get('note'), meta.get('frame'), got['ram'][:16], (got.get('fb') or '-')[:16],
                                                                                     '; core picture still the old one, frame buffer read from VRAM' if g.picture_stale() else ''))
        g.snap('%s +%d' % (name, n))
        g.run(600)
        im = g.snap('%s +600' % name)
        g.check(not is_black(im), '%s: picture after 600 more frames' % name, 'screen %s, text %s, clock %d' % (g.where(), g.text()[:70] or '(none)', g.level_clock()))
        st = g.stalled(1200)
        g.check(st is not True, '%s: the game runs on' % name, 'guest frame %s, presents %s' % (g.gframes(), g.v('g_pres')))
    return g.finish('state_check')


if __name__ == '__main__':
    sys.exit(main())
