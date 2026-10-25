"""The settings pages and a new game, the same inputs on any build: title menu > Game options (change lines, leave), play
game (a new game starts), the hangar's OPTIONS > GAME SETTINGS (change lines, leave), a level end and start. Prints what
persisted (the progress copy and the extras word, and each setting's place on its slider) and saves screenshots under
$OUT; run on the old and the new ROM and diff the two outputs: they must be equal.

    SP=.. OUT=dir TAG=name ROM=x.gba ELF=x.elf python3 tests/s2/menus.py      (from stuntfox/)
"""
import h
from h import *

OUT, TAG = os.environ['OUT'], os.environ['TAG']
ck = Check()


def shot(name):
    e.frame.save('%s/menus_%s_%s.png' % (OUT, TAG, name))


def pos():
    return list(e.read(S['pos'], 26))


def snapshot(what):
    w = words()
    print('%-22s mirror %s extras %s slider %s' % (what, ' '.join('%08x' % x for x in w['mirror']), ' '.join('%08x' % x for x in w['extras']), pos()))
    return w


# ---- the title menu ----
def title_options():
    title_state()
    tap('UP', after=30)                  # (from the first line, up wraps to the last: Game options)
    tap('A', after=40)
    shot('title_page')
    for k in ('RIGHT', 'RIGHT', 'DOWN', 'RIGHT', 'DOWN', 'DOWN', 'LEFT', 'DOWN', 'RIGHT', 'RIGHT'):
        tap(k)
    shot('title_changed')
    w0 = snapshot('title: before leaving')
    tap('B', after=60)
    shot('title_back')
    return w0, snapshot('title: left')


w0, w1 = title_options()
ck(w1['mirror'][4] != w0['mirror'][4] and any(w1['mirror'][:4]) and any(w1['extras']), 'the title page saved what was changed (progress copy and extras word)')
slid = pos()
ck(slid[:6] == [2, 1, 0, 5, 2, 4], 'the sliders moved: target, time, wanted stars ...', str(slid[:6]))
tap('DOWN', after=30)                    # back to play game
tap('A', after=80)
for _ in range(11):
    tap('A', after=60)                   # slot, name, game menu: a new single player game
run(300)
shot('new_game')
w2 = snapshot('new game running')
ck(grid() == 0 and u32(0x02001e00) > 0 and modename() == 'FOOT', 'a new game starts on map 0, on foot', 'lives %d' % r16(0x02001e4e))
print('lives, new game        %d' % r16(0x02001e4e))
ck(w2['extras'] == w1['extras'] and w2['mirror'] == w1['mirror'] and pos() == slid, 'the settings are as they were when the game runs')

# ---- a rampage from the title, a level end and the start of the next map: the settings come through ----
title_options()
tap('DOWN', after=30)
tap('A', after=80)
for _ in range(2):
    tap('A', after=60)                   # slot, name
tap('DOWN')
tap('DOWN')
tap('A', after=60)                       # Single player rampage
shot('rampage_setup')
tap('A', after=600)                      # Play game
for _ in range(3):
    tap('A', after=60)
run(200)
w3 = snapshot('rampage running')
ck(grid() == 0 and u32(0x02001e00) > 0, 'the rampage starts on map 0', 'lives %d (as in the old build: it is compared)' % r16(0x02001e4e))
print('lives, rampage start   %d' % r16(0x02001e4e))
run(60)
e.write32(PL + 0x90, 9999999)
for _ in range(10):
    run(30)
    if r16(0x02001e08) == 3:
        break
run(30)
run(6, ['SELECT'])
for _ in range(25):
    run(45)
    if grid() == 1 and u32(0x02001e00) > 0:
        break
run(120)
w4 = snapshot('map 1 running')
ck(grid() == 1 and pos() == slid and w4['mirror'] == w3['mirror'] and w4['extras'] == w3['extras'], 'the level ended, map 1 began: sliders, progress copy and extras all as they were')
print('lives, map 1           %d' % r16(0x02001e4e))
shot('map1')

# ---- the hangar ----
merged_state(e)
run(5)
run(90, ['SELECT'])
run(30)
B = S['ship']


def setv(a, v):
    for i in range(3):
        e.write32(a + 4 * i, int(v[i]) & 0xffffffff)


sx, sy, sz = [r32(S['station_pos'] + 4 * i) for i in range(3)]
setv(B, ((sx + 3000) << 8, (sy - 140) << 8, (sz + 9000) << 8))
setv(B + 12, (0, 0, -(90 << 8)))
setv(B + 24, (-16384, 0, 0))
setv(B + 36, (0, 16384, 0))
setv(B + 48, (0, 0, -16384))
run(20, ['A'])
run(40, ['SELECT'])
for k in range(30):
    run(30)
    if r32(S['sg_state']) == 2:
        break
ck(r32(S['sg_state']) == 2, 'the Arwing docks', 'state %d' % r32(S['sg_state']))
run(60)
shot('hangar')
def htap(k, after=24):                   # (the hangar polls the pad about every 5 frames: a tap must outlast one)
    tap(k, hold=8, after=after)


for _ in range(3):
    htap('DOWN')
htap('A', after=40)                      # OPTIONS
shot('hangar_options')
htap('UP')
htap('A', after=40)                      # GAME SETTINGS
shot('hangar_page')
h0 = snapshot('hangar: page open')
for k in ('RIGHT', 'DOWN', 'RIGHT', 'DOWN', 'DOWN', 'RIGHT'):
    htap(k)
shot('hangar_changed')
htap('B', after=30)
h1 = snapshot('hangar: left')
ck(pos() != [0] * 26 and (h1['mirror'] != h0['mirror'] or h1['extras'] != h0['extras']), 'the hangar page saved what was changed')
run(60)
h2 = snapshot('hangar: a second on')
ck(h2['mirror'] == h1['mirror'] and h2['extras'] == h1['extras'], 'and it stays saved (the progress check puts nothing back)')

ck.done()
