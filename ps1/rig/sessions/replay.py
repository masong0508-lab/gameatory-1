#!/usr/bin/env python3
"""Replay a recorded button script blind: the buttons are held from the frames the script names, nothing is read back to
decide anything.  Shows that a script.txt of another session reproduces (same core, same disc), and what the same presses do
on the disc as built when the menu assist of the build is left alone.

  python3 sessions/replay.py --disc DISC.cue --out runs/replay --script runs/b/script.txt [--syms payback.elf]
                             [--assist keep|off] [--assist-off-frame 610] [--tail 3000]

--assist off blanks the build's menu assist plan in RAM at --assist-off-frame (the frame at which the session that recorded
the script did it; needs --syms); --assist keep leaves the disc as built.
The result lines say where the replay ended (screen text, level clock) and at which frame the level clock first counted."""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *


def extra(ap):
    ap.add_argument('--script', required=True, help='script.txt of a session: lines "f<frame>: BTN+BTN" / "f<frame>: (release)"')
    ap.add_argument('--assist', default='off', choices=('keep', 'off'))
    ap.add_argument('--assist-off-frame', type=int, default=610)
    ap.add_argument('--tail', type=int, default=3000, help='frames to run after the last line of the script')
    ap.add_argument('--expect-level', type=int, default=None, help='frame at which the recording session first saw the level clock')


def load_script(path):
    out = []
    for line in open(path):
        m = re.match(r'\s*f(\d+):\s*(.*)$', line)
        if not m:
            continue
        b = m.group(2).strip()
        out.append((int(m.group(1)), [] if b.startswith('(') else [x for x in b.split('+') if x]))
    return out


def main():
    a = std_args(__doc__, extra)
    sc = load_script(a.script)
    rec = {}
    rj = os.path.join(os.path.dirname(os.path.abspath(a.script)), 'result.json')
    if os.path.exists(rj):                       # the recording session's own figures, when it left them
        try:
            rec = json.load(open(rj)).get('extra') or {}
        except ValueError:
            rec = {}
    if a.expect_level is None:
        a.expect_level = (rec.get('steps') or {}).get('level')
    g = open_game(a, 'replay')
    g.check(bool(sc), 'script loaded', '%d lines from %s, last at frame %s' % (len(sc), a.script, sc[-1][0] if sc else None))
    if not sc:
        return g.finish('replay')
    end = sc[-1][0] + a.tail
    held, i, level_at, off_done = [], 0, None, False
    assist_log, last_ap = [], []
    while g.nrun < end:
        while i < len(sc) and sc[i][0] <= g.nrun:
            held = sc[i][1]
            i += 1
        if a.assist == 'off' and not off_done and g.nrun >= a.assist_off_frame:
            off = g.assist_off()
            off_done = True
            g.note('menu assist plan blanked in RAM at frame %d: %s' % (g.nrun, off or 'no plan named by the symbols (nothing changed)'))
        nxt = min([s[0] for s in sc[i:]] + [end] + ([a.assist_off_frame] if (a.assist == 'off' and not off_done) else []))
        n = max(1, min(nxt - g.nrun, 20))
        g.run(n, held)
        if level_at is None and g.level_clock() > 0:
            level_at = g.nrun
        if a.assist == 'keep':
            ap = g.assist_pressed() or []
            if ap != last_ap:
                if ap:
                    assist_log.append('f%d (GBA frame %s, screen %s): %s' % (g.nrun, g.gba_frame(), g.where(), '+'.join(ap)))
                last_ap = ap
    g.release()
    if a.assist == 'off' and rec.get('end_frame') and rec.get('end_ram_sha1') and g.nrun <= rec['end_frame']:
        g.run(rec['end_frame'] - g.nrun)
        g.check(g.ram_sha1() == rec['end_ram_sha1'], 'RAM at the recording\'s last frame is byte-identical to the recording',
                'frame %d, sha1 of the 2 MiB of RAM %s (recording %s)' % (g.nrun, g.ram_sha1()[:16], rec['end_ram_sha1'][:16]))
    if a.assist == 'keep':
        g.note('menu assist left as built; keys it pressed during the replay (seen in the guest key word, not held on the pad): %s' % (assist_log or 'none'))
    ok, det = level_view(g) if g.level_clock() > 0 else (False, 'no level: screen %s, text %s' % (g.where(), g.text()[:100] or '(none)'))
    g.snap('end of the replay')
    g.check(level_at is not None, 'the replayed script reaches a running level', 'level clock first seen at or before frame %s; now clock %d' % (level_at, g.level_clock()))
    if level_at is not None:
        g.check(ok, 'the 3D city is on screen', det)
        if a.expect_level is not None:
            g.check(abs(level_at - a.expect_level) <= 20, 'the level clock starts at the same frame as in the recording', 'replay: first seen at frame %d (looked at every 20 frames or less), recording: %d' % (level_at, a.expect_level))
    faults = g.tty_faults()
    g.check(not faults, 'no fault text on the TTY', faults[:3])
    return g.finish('replay', extra={'level_at': level_at, 'script': a.script, 'assist': a.assist})


if __name__ == '__main__':
    sys.exit(main())
