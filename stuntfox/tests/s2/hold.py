"""The level hold (stage2.md 4.6) in the emulator: with a campaign on, Payback's kind-0 goal (the score target) is raised
out of reach each frame while the level has acts left, so a score above the target does not end the level; with the acts
done it goes back at what the score is and Payback ends the level by its own road, within a few clock ticks; with the goal
gone the level is ended by e08 instead. A control run with no campaign shows the same score does end the level, and a
chapter's acts done are the chapter's unlock. Payback's own goals are the same before and after.

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/hold.py      (from stuntfox/)
"""
import h
from h import *

sys.path.insert(0, os.path.join(START, 'tools', 'content'))
import misfmt as F                                   # noqa: E402

ck = Check()
G, E08, HOLD = 0x0201a7e0, 0x02001e08, 0x7fffffff
CHAP, MAP = 1, 3                                     # (the second chapter: map 3, a rampage, six acts in its one level)


def blob():
    head = bytes(e.read(S['s2_blob'], 56))
    return bytes(e.read(S['s2_blob'], F.unpack_rec('S2Head', head)['size']))


d = F.parse(blob())
ch = d['chapters'][CHAP]
acts = {m['act']: i for i, m in enumerate(d['missions'][ch['mis0']:ch['mis0'] + ch['nmis']], ch['mis0']) if m['kind'] == F.MK_ACT}
ck(ch['map'] == MAP and not ch['flags'] & F.CH_STORY and ch['nact'] == 6 and sorted(acts) == [1, 2, 3, 4, 5, 6],
   'chapter %d is map %d, a rampage with acts 1..6' % (CHAP, MAP), str(ch))


def kind0():
    for i in range(min(r16(0x0201a7d8), 100)):
        if r32(G + 0x24 * i + 4) == 0:
            return i, r32(G + 0x24 * i + 8)
    return None, None


def e08():
    return r16(E08)


def own():
    return sorted((g[0], g[1]) for g in goals() if g[1])      # (the kind-0 goal is gone once it was reached)


gstate(MAP)
run(40)
base = e.save_state()
base_goals = own()
i0, orig = kind0()
ck(i0 is not None and orig > 0, 'the rampage has its kind-0 goal with a target', 'goal %s a %s' % (i0, orig))


def over_target():
    """the player's score put above the target (Payback's own check then reaches it)"""
    c = ctl()
    e.write32(c + 0x90, orig + 5000)


# ---- control: no campaign, the score above the target ends the level ----
over_target()
run(90)
ck(e08() == 3, 'control (no campaign): a score above the target ends the level', 'e08 %d' % e08())

# ---- the hold ----
e.load_state(base)
run(2)
ck(mb(16, 0) == 1 and mb(24, 1) == 1 and mb(16, 3) == 1, 'the campaign is started and the chapter is open')
run(3)
ck(mb(17, 1) == CHAP and mb(17, 4) & 1 and mb(17, 3) == 0, 'this level is chapter %d with acts left: the hold is on' % CHAP, 'state %x' % mb(17, 4))
i1, a = kind0()
ck(a == HOLD and mb(17, 5) == orig, "the goal's target is out of reach and Payback's own is kept", 'a %x saved %s' % (a, mb(17, 5)))
over_target()
run(150)
ck(e08() == 0 and kind0()[1] == HOLD, 'a score above the target does not end the level', 'e08 %d' % e08())
for k in range(1, 6):                               # acts 1..5
    mb(25, acts[k])
    run(8)
    ck(mb(17, 3) == (1 << k) - 1 and mb(17, 4) & 1 and kind0()[1] == HOLD and e08() == 0, 'act %d done: its bit is in, the hold stays' % k, 'acts %x' % mb(17, 3))
mb(25, acts[6])
run(2)
ck(mb(17, 3) == 0x3f and mb(17, 2) == CHAP + 1, 'act 6 done: the chapter is done and the next one is open', 'acts %x open %d' % (mb(17, 3), mb(17, 2)))
ck(not mb(17, 4) & 1 and mb(17, 4) & 2, 'the hold is off and the release is running', 'state %x' % mb(17, 4))
rel_at = end_at = None
for n in range(400):
    run(1)
    if rel_at is None and (mb(17, 4) >> 1 & 3) == 2:
        rel_at = u32(0x02001e00)
    if e08() == 3:
        end_at = u32(0x02001e00)
        break
ck(end_at is not None and rel_at is not None and end_at - rel_at <= 15, "Payback's own goal ends the level within a few ticks of the release", 'released %s ended %s' % (rel_at, end_at))
ck(kind0()[0] is None, 'the score target was reached (and so consumed) by Payback, not left held', 'goal %s' % (kind0(),))
ck(own() == base_goals and not [g for g in goals() if 0x5000 <= g[0] < 0x5100], "Payback's other goals are the same as before the campaign (none of ours left)", '%s vs %s' % (own(), base_goals))

# ---- the goal gone: the level is ended by e08 ----
e.load_state(base)
run(2)
mb(16, 0), mb(24, 1), mb(16, 3)
run(3)
i1, a = kind0()
e.write32(G + 0x24 * i1 + 4, 99)                     # (it is no longer a score target)
run(2)
for k in range(1, 7):
    mb(25, acts[k])
    run(2)
t0 = u32(0x02001e00)
for n in range(300):
    run(1)
    if e08() == 3:
        break
ck(e08() == 3 and u32(0x02001e00) - t0 <= 90, 'with the goal gone the level is ended by e08 after the pause', 'e08 %d ticks %d' % (e08(), u32(0x02001e00) - t0))

# ---- stopping the campaign gives the level back ----
e.load_state(base)
run(2)
mb(16, 0), mb(24, 1), mb(16, 3)
run(3)
ck(kind0()[1] == HOLD, 'held again')
ck(mb(16, 1) == 0, 'the campaign is stopped')
over_target()
run(150)
ck(e08() == 3 or mb(17, 4) & 1 == 0, 'stopped: the hold is off and the score ends the level (the target is not restored by us: the level ends)', 'e08 %d state %x' % (e08(), mb(17, 4)))
ck.done()
