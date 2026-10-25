"""Frames a second on map 3 (the arena) with the demo ring run's rings drawn, against the same flight with no mission.

The ship is put back 5 cells before ring 1 every 40 frames, flying along it. Four runs of WINDOWS windows each, interleaved (one window of each in turn) (at least 12: a
window is 4 s and traffic and the ship's path move one by up to 1.5 fps, so fewer windows let the choice of N decide the verdict):
  control    no mission
  armed      the ring run's start ring and its line, nothing running
  title      the first 4 s after the run starts: Payback's title banner is up (measured apart, it is not ours)
  far ring   the run on, its count left to count: after the first ring it is the second, 13 cells off, that is drawn
  near ring  the run on with its count put back to 0 at every teleport (debug command 11): ring 1, 5 cells ahead and then
             through it and past, is what is drawn for the first part of every 40 frames, with the bracket for ring 2
The gates: near ring mean at least 18 and no window below 16, far ring mean at least 18, and both under 1.5 fps below the control.

    ROM=out.gba ELF=build/merge/stuntfox-merge.elf python3 tests/s2/fps_rings.py [windows]      (from stuntfox/)
"""
import sys

import h
from h import *

ck = Check()
merged_state(e)
gstate(3)                                      # (map 3, the arena the demo's ring run is laid in)
run(30)
ck(s2f()['map'] == 3 and mb(8, 0) == 6, 'map 3, the demo blob in')
N = max(12, int(sys.argv[1])) if len(sys.argv) > 1 else 12
RING_MIS = 4                                   # (the demo's ring run)
CELL = 1024


def kc():
    return u32(S['key_calls'])


def window(placed, frames=240, hold=False):
    """fps over `frames`, the ship put back at `placed` every 40 frames (so a ring stays in view); hold: and the count put back to 0."""
    a = kc()
    for _ in range(frames // 40):
        tele_ship(*placed)
        if hold:
            mb(11, 0)
        run(40)
    return (kc() - a) * 60 / frames


def stats(v):
    return sum(v) / len(v), min(v)


board_now()
ck(modename() == 'FLY', 'in the Arwing', modename())
# 5 cells before the demo's ring 1 (64, 70, h 1700), flying along +x at the ring's height
at = ((59 * CELL, 1700, 70 * CELL), (16384, 0, 0), (0, 0, 0))
mb(10, 1)                                      # (no roaming: the start ring 5 cells off would be armed by walking up to it)
mb(9)
run(10)
ck(mb(7) & 255 == 0, 'nothing armed for the control', hex(mb(7)))
# The four runs are interleaved, one window of each in turn, so that drift in the traffic and in the ship's path (which moved a
# control by 1.5 fps between its first and its last windows) falls on all four alike.
off, armed, title, far, near = [], [], [], [], []
bad = []                                       # (any window whose mission was not in the state the run wants)
for i in range(N):
    mb(9)                                      # (cancel whatever ran)
    run(10)
    if mb(7) & 255 != 0:
        bad.append((i, 'control', hex(mb(7))))
    off.append(window(at))
    mb(6, RING_MIS)
    run(10)
    if not (mb(7) & 255 == 1 and mb(7) >> 16 == RING_MIS):
        bad.append((i, 'armed', hex(mb(7))))
    armed.append(window(at))
    assert mb(1, RING_MIS) == 1
    run(10)
    st = mb(7)
    if not ((st & 255) == 2 and (st >> 16) == RING_MIS):
        bad.append((i, 'on', hex(st)))
    tele_ship(*at)
    run(6)
    title.append(window(at))                   # (the title banner is up for the first 220 ticks; it is Payback's own drawing, measured apart)
    window(at)                                 # (and let it go: 480 frames are 240 ticks)
    far.append(window(at))
    tele_ship(*at)
    mb(11, 0)
    run(6)
    if mb(8, 7) != 0:
        bad.append((i, 'count', mb(8, 7)))
    near.append(window(at, hold=True))
    print('window %2d: no mission %.1f  armed %.1f  title banner %.1f  far ring %.1f  near ring %.1f' % (i, off[-1], armed[-1], title[-1], far[-1], near[-1]), flush=True)
e.frame.save(os.path.join(os.environ.get('SHOTS', '.'), 'shot_rings.png'))
ck(not bad, 'every window had its mission in the state the run wants (control idle, armed, on, count held at 0)', str(bad))
(m_off, lo_off), (m_arm, lo_arm), (m_tit, lo_tit), (m_far, lo_far), (m_near, lo_near) = (stats(v) for v in (off, armed, title, far, near))
print('mean/min: no mission %.2f/%.1f, armed %.2f/%.1f, title banner %.2f/%.1f, far ring %.2f/%.1f, near ring %.2f/%.1f   (%d windows each)' %
      (m_off, lo_off, m_arm, lo_arm, m_tit, lo_tit, m_far, lo_far, m_near, lo_near, N))
ck(m_near >= 18 and lo_near >= 16, 'near ring: mean at least 18 and no window under 16', 'mean %.2f, min %.1f against %.2f/%.1f with no mission' % (m_near, lo_near, m_off, lo_off))
ck(m_tit >= 16 and lo_tit >= 14, 'the title banner window (about 4 s once per act start): mean at least 16 and none under 14', 'mean %.2f, min %.1f' % (m_tit, lo_tit))
ck(m_far >= 18, 'far ring: mean at least 18', 'mean %.2f (min %.1f)' % (m_far, lo_far))
ck(m_off - m_near < 1.5 and m_off - m_far < 1.5, 'and the mission costs under 1.5 fps here', 'near %.2f, far %.2f against the control' % (m_off - m_near, m_off - m_far))
ck.done()
