"""Travel and the next level (stage2.md 5.1, 5.2; probes P3 and P5) in the emulator, with the flash monitor on every frame:
  - no campaign: sf_menu is Payback's (the rampage chain runs on as it always did), and a travel is refused;
  - a rampage level left for another rampage chapter, and for a story chapter, by the injected SELECT alone: a chapter that is not open
    is refused; the level changes within a few seconds; the trophies are the ones from before the travel; the new level is of the right chapter
    (map, rampage flag, hold on, an orbital drop starts docked);
  - a story level left by its own end (the human's SELECT and A): the first level to the second, the second to the next chapter;
  - a travel booked in a story level, taken when its level ends;
  - a story level with no score target (chapter 5): its early end moves the acts left to the second part;
  - a game over starts the same level again.

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/travel.py      (from stuntfox/)
"""
import h
from h import *

sys.path.insert(0, os.path.join(START, 'tools', 'content'))
import misfmt as F                                   # noqa: E402

ck = Check()
E08, CLK = 0x02001e08, 0x02001e00


def blob():
    head = bytes(e.read(S['s2_blob'], 56))
    return bytes(e.read(S['s2_blob'], F.unpack_rec('S2Head', head)['size']))


d = F.parse(blob())


def act(c, k):
    ch = d['chapters'][c]
    for i, m in enumerate(d['missions'][ch['mis0']:ch['mis0'] + ch['nmis']], ch['mis0']):
        if m['kind'] == F.MK_ACT and m['act'] == k:
            return i


def where():
    return dict(map=r16(0x02001d40), city=r16(0x02003ef2), sub=r16(0x02003ef4), ramp=r8(0x02001d39), e08=r16(E08), clk=u32(CLK))


def trophies():
    return [r16(0x020026d2 + 2 * i) for i in range(6)]


def level_key():
    w = where()
    return (w['ramp'], w['map'] if w['ramp'] else w['city'], 0 if w['ramp'] else w['sub'])


def wait_new_level(was, frames, keys=(), step=20):
    """frames of play, a key tapped each second (SELECT once, then A: a second SELECT undoes the first: a human at the end screens); the frames
    gone when the level key or the clock says a new level began, else None"""
    n, tapped, prev = 0, 0, u32(CLK)
    while n < frames:
        if keys and n >= tapped * 60:
            run(4, [keys[min(tapped, len(keys) - 1)]])
            tapped += 1
            n += 4
        else:
            run(step)
            n += step
        w = where()
        if w['e08'] == 0 and (level_key() != was or w['clk'] < prev - 20) and w['clk'] < 400:
            return n
        prev = w['clk']
    return None


title_state()                                        # (made from a cold boot here: the cached title is taken from a running game otherwise)
fm_start('travel')
gstate(0)
fm_break()
run(40)
rbase = e.save_state()

# ---- no campaign: Payback's own ----
ck(mb(19, 1) == 0, 'no campaign: a travel is refused')
e.write32(0x0201a7e0 + 8, 0)                         # (the score target reached: the rampage's own chain, as p1c)
n = wait_new_level(level_key(), 900, keys=('SELECT',))
w = where()
ck(n is not None and w['ramp'] == 1 and w['map'] == 1, 'no campaign: the rampage chain goes on to map 1 as it always did', 'frames %s %s' % (n, w))
ck(mb(21, 1) == -1, 'no campaign: cp_menu answered -1', 'answer %s' % mb(21, 1))

# ---- a rampage level, travel to another rampage chapter (chapter 3, map 4) ----
gstate(3)
fm_break()
run(40)
tbase = e.save_state()
ck(mb(16, 0) == 1 and mb(24, 3) == 3 and mb(16, 3) == 1 and mb(17, 1) == 1, 'campaign on in map 3 (chapter 1), chapters up to 3 open')
ck(mb(19, 4) == 0, 'a chapter that is not open is refused')
tr0 = trophies()
was = level_key()
ck(mb(19, 3) == 1, 'travel to chapter 3 (map 4, rampage) is taken')
n = wait_new_level(was, 900)
w = where()
ck(n is not None and w['ramp'] == 1 and w['map'] == 4 and w['e08'] == 0, 'the level changes to map 4, a rampage, by the injected SELECT alone', 'frames %s %s' % (n, w))
ck(trophies() == tr0, 'the trophies are the ones from before the travel', '%s vs %s' % (trophies(), tr0))
run(30)
ck(mb(17, 1) == 3 and mb(17, 12) == 3 and mb(17, 4) & 1, 'it is chapter 3 and the hold is on', 'chapter %s state %s' % (mb(17, 1), mb(17, 4)))
ck(mb(17, 4) & 0x20 and s2f()['docked'] == 1 and s2f()['mode'] == 2, 'a chapter after the first opens docked at the station: the orbital drop begins', 'state %x docked %s' % (mb(17, 4), s2f()['docked']))
e.frame.save(os.path.join(os.environ.get('OUT', '/tmp'), 'travel_drop_dock.png'))
ck(mb(21, 1) == 8, 'sf_menu was answered with map 4 (4 * 2)', 'asked %s answered %s' % (hex(mb(21, 0) & 0xffffffff), mb(21, 1)))

# ---- from there to a story chapter (chapter 2, map 1) ----
mb(24, 5)
was = level_key()
ck(mb(19, 2) == 1, 'travel to chapter 2 (map 1, story) is taken')
n = wait_new_level(was, 900)
w = where()
ck(n is not None and w['ramp'] == 0 and w['city'] == 1 and w['sub'] == 0 and w['e08'] == 0, 'the level changes to map 1, a story level, first part', 'frames %s %s' % (n, w))
ck(trophies() == tr0, 'trophies again as before', str(trophies()))
run(30)
ck(mb(17, 1) == 2 and mb(17, 14) == 0 and mb(17, 4) & 1 and s2f()['docked'] == 1, 'chapter 2, its first level, hold on, docked for the drop', 'chapter %s sub %s' % (mb(17, 1), mb(17, 14)))
ck(mb(21, 1) == 2, 'sf_menu was answered with 1 * 2 + 0', 'answer %s' % mb(21, 1))

# ---- the story: its own end, through the human's taps ----
title_state()
fm_break()
tap('A', after=80)
for _ in range(11):
    tap('A', after=60)
run(300)
sbase = e.save_state()
w = where()
ck(w['ramp'] == 0 and w['city'] == 0 and w['sub'] == 0 and w['clk'] > 0, 'a new story game is on map 0, first part', str(w))
ck(mb(16, 0) == 1 and mb(17, 1) == 0 and mb(17, 4) & 1 and mb(17, 4) & 0x20 == 0, 'the campaign is on, chapter 0 (no drop), hold on')
for k in (1, 2):
    mb(25, act(0, k))
run(10)
ck(mb(17, 4) & 1 and where()['e08'] == 0, 'two of the first part\'s three acts done: still held')
mb(25, act(0, 3))
run(150)
ck(where()['e08'] == 3 and mb(17, 3) == 7, "the third act done: Payback's level complete, by its own road", str(where()))
was = level_key()
n = wait_new_level(was, 2400, keys=('SELECT', 'A'))
w = where()
ck(n is not None and w['ramp'] == 0 and w['city'] == 0 and w['sub'] == 1, 'the human\'s SELECT and A go through the end screens to the second part of the same city', 'frames %s %s' % (n, w))
ck(mb(21, 1) == 1, "sf_menu was answered with 0 * 2 + 1 (the second part)", 'answer %s' % mb(21, 1))
run(30)
ck(mb(17, 14) == 1 and mb(17, 4) & 1, 'second part: the hold is on for acts 4..6', 'state %s' % mb(17, 4))
for k in (4, 5, 6):
    mb(25, act(0, k))
run(150)
ck(mb(17, 3) == 0x3f and mb(17, 2) == 1 and where()['e08'] == 3, "all six acts: chapter 1 is open and Payback's level is complete", 'acts %x open %s %s' % (mb(17, 3), mb(17, 2), where()))
was = level_key()
n = wait_new_level(was, 2400, keys=('SELECT', 'A'))
w = where()
ck(n is not None and w['ramp'] == 1 and w['map'] == 3, 'the end of the chapter leads to the next one: map 3, a rampage', 'frames %s %s' % (n, w))
ck(mb(21, 1) == 6, 'sf_menu was answered with 3 * 2', 'answer %s' % mb(21, 1))

# ---- a travel booked in a story level, taken when it ends ----
e.load_state(sbase)
fm_break()
run(2)
mb(16, 0), mb(24, 3)
ck(mb(19, 2) == 2 and mb(17, 10) == 2, 'story level, acts left: the travel to chapter 2 is booked, not taken', 'tgt %s' % mb(17, 10))
run(60)
ck(where()['e08'] == 0, 'the level goes on')
for k in (1, 2, 3):
    mb(25, act(0, k))
run(150)
was = level_key()
n = wait_new_level(was, 2400, keys=('SELECT', 'A'))
w = where()
ck(n is not None and w['ramp'] == 0 and w['city'] == 1 and w['sub'] == 0, 'the level\'s end takes the booked road: map 1, first part (not the second part of map 0)', 'frames %s %s' % (n, w))

# ---- a story level with no score target (Corona, chapter 5, first part): the hold never engages, Payback's own end can come early ----
gstate(0)
fm_break()
run(40)
mb(16, 0), mb(24, 10), mb(16, 3)
was = level_key()
ck(mb(19, 5) == 1, 'travel to chapter 5 (map 2, story) is taken')
n = wait_new_level(was, 1500)
w = where()
ck(n is not None and w['ramp'] == 0 and w['city'] == 2 and w['sub'] == 0 and w['e08'] == 0, 'chapter 5 begins on map 2, first part', 'frames %s %s' % (n, w))
run(120)
ck(mb(17, 1) == 5 and mb(17, 4) & 1 and not mb(17, 4) >> 6 & 1, 'the hold is on but it saw no kind-0 goal in this level (nothing to hold)', 'state %x' % mb(17, 4))
c5 = d['chapters'][5]
ck(c5['flags'] & F.CH_STORY and 0 < c5['split'] < c5['nact'], 'the chapter is a story one split in two levels (%d of %d acts in the first)' % (c5['split'], c5['nact']))
first = c5['split']
for k in range(1, first):                            # (all but the last act of the first part)
    mb(25, act(5, k))
run(10)
ck(mb(17, 3) == (1 << (first - 1)) - 1 and where()['e08'] == 0, 'all but one of the first part\'s acts done, the level goes on', 'acts %x' % mb(17, 3))
e.write8(E08, 3)                                      # (Payback's own story end, reached before the acts were)
was = level_key()
n = wait_new_level(was, 2400, keys=('SELECT', 'A'))
w = where()
ck(n is not None and w['city'] == 2 and w['sub'] == 1, 'the early end takes the second part of the same city', 'frames %s %s' % (n, w))
run(60)
left = (1 << c5['nact']) - 1 & ~mb(17, 3)
ck(mb(17, 14) == 1 and mb(17, 4) & 1 and left >> (first - 1) & 1, 'the second part carries the act that was left, with the others: hold on', 'state %x acts %x' % (mb(17, 4), mb(17, 3)))
for k in range(first, c5['nact'] + 1):
    mb(25, act(5, k))
run(200)
ck(mb(17, 3) == (1 << c5['nact']) - 1 and mb(17, 2) >= 6, 'all of them done: the chapter is done and the next is open', 'acts %x open %s' % (mb(17, 3), mb(17, 2)))
ck(where()['e08'] == 3, 'and the level ends (the goal gone: after the pause)', str(where()))

# ---- a game over: the same level again ----
e.load_state(tbase)
fm_break()
run(2)
mb(16, 0), mb(24, 3), mb(16, 3)
run(40)
e.write8(0x02001e4e, 0)                              # (no lives left, and the man at no health: his death is the game over)
e.write8(ctl() + 0x68, 0), e.write8(ctl() + 0x69, 0)
n = wait_new_level(level_key(), 2400, keys=('SELECT', 'A'))
w = where()
ck(n is not None and w['ramp'] == 1 and w['map'] == 3 and mb(21, 1) == 6, 'a game over starts the same level again', 'frames %s %s answer %s' % (n, w, mb(21, 1)))
ck(mb(17, 1) == 1 and mb(17, 4) & 1, 'and its chapter and hold are as they were')

worst, worst_red = fm_report()
ck(worst <= 3 and worst_red <= 3, 'flashcheck over every frame of the travels and level ends: most flashes in a second %d, red %d' % (worst, worst_red))
ck.done()
