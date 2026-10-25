"""The Speed line of GAME SETTINGS: from the title menu's Game options, to Fastest and out; the sliders and the extras word keep it,
a new game starts with the governor on (sp_cap 10, Fast 7, Normal 0), and the page shows it again.

    SP=.. OUT=dir TAG=name ROM=x.gba ELF=x.elf python3 tests/s2/speedmenu.py      (from stuntfox/)
"""
import h
from h import *

OUT, TAG = os.environ['OUT'], os.environ['TAG']
ck = Check()
O_SPEED, O_N = 22, 28                    # settings.c's enum


def shot(name):
    e.frame.save('%s/speed_%s_%s.png' % (OUT, TAG, name))


def pos():
    return list(e.read(S['pos'], O_N))


def page(downs, rights, lefts=0):
    title_state()
    tap('UP', after=30)
    tap('A', after=40)
    global p_open
    p_open = pos()
    for _ in range(downs):
        tap('DOWN')
    for _ in range(rights):
        tap('RIGHT')
    for _ in range(lefts):
        tap('LEFT')


def cap():
    return e.read(S['sp_cap'], 1)[0]


for name, rights, want_pos, want_cap in (('fastest', 2, 2, 10), ('fast', 1, 1, 7), ('normal', 0, 0, 0)):
    page(O_SPEED, rights)
    shot('%s_page' % name)
    w0 = words()
    p0 = pos()
    tap('B', after=60)
    w1 = words()
    p1 = pos()
    ck(p1[O_SPEED] == want_pos and p0[O_SPEED] == want_pos, '%s: the Speed line is at %d on the page and after leaving' % (name, want_pos), str(p1))
    ck(all(p1[i] == p_open[i] for i in range(O_N) if i != O_SPEED), '%s: no other line moved' % name, str(p1))
    ck(cap() == want_cap, '%s: sp_cap is %d at once' % (name, want_cap), str(cap()))
    if want_pos:
        ck(any(w1['extras']) and w1['extras'] != [0] * len(w1['extras']), '%s: the extras word holds it' % name, str(w1['extras']))
    # a new game: the setting comes through, the governor runs
    tap('DOWN', after=30)
    tap('A', after=80)
    for _ in range(11):
        tap('A', after=60)
    run(300)
    ck(grid() == 0 and modename() == 'FOOT', '%s: a new game starts on map 0, on foot' % name)
    ck(cap() == want_cap and pos()[O_SPEED] == want_pos, '%s: sp_cap %d and the line %d in the running game' % (name, want_cap, want_pos), '%d %s' % (cap(), pos()[O_SPEED]))
    lv = e.read(S['sp_lv'], 1)[0]
    ck(lv <= want_cap, '%s: the row in use (%d) is within the setting' % (name, lv))
    shot('%s_game' % name)
    print('%-8s row in use %d' % (name, lv))
ck.done()
