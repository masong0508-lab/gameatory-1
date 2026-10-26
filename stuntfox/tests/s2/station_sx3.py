"""Fox Station expansion (SX3): the story talks that set campaign flags, the city board (Ops), Kestrel's board (Quarters), the heard talks
kept in Prog (and across a save and a power cycle), and SAVE... in one press.

    SP=.. ROM=x.gba ELF=x.elf [SHOTS=dir] python3 tests/s2/station_sx3.py        (from stuntfox/)
"""
import sys
import h
from h import *

SHOTS = os.environ.get('SHOTS', SP + '/v12/s2/SX3/shots')
os.makedirs(SHOTS, exist_ok=True)
ck = Check()


def shot(name):
    e.frame.save('%s/sx3_%s.png' % (SHOTS, name))


def setv(a, v):
    for i in range(3):
        e.write32(a + 4 * i, int(v[i]) & 0xffffffff)


def dock():
    merged_state(e)
    run(5)
    run(90, ['SELECT'])
    run(30)
    B = S['ship']
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
    return r32(S['sg_state']) == 2


def st(a):
    return mb(33, a)


def htap(k, after=16):
    tap(k, hold=8, after=after)


def hd():
    return (mb(33, 14) & 0xffffffff) | (mb(33, 15) & 0xffffffff) << 32


def credits():
    return mb(17, 6)


def talk_all(crew, limit=40):
    """Talk to `crew` until a talk ends, pressing A; the entry's id."""
    mb(37, crew)
    ent = st(5)
    n = 0
    while st(5) and n < limit:
        htap('A', after=10)
        n += 1
    return ent


ck(dock(), 'docked')
ck(mb(16, 0) == 1, 'the campaign is on')
ck(st(17) == 52, 'the walker state is 52 bytes (the heard talks moved into Prog)', str(st(17)))
mb(38)                                            # (nothing heard yet)
ck(mb(34, 1) == 1, 'in the hub')

# ---- the five story talks: each is told after its chapter, sets its flag, and not before ----
for (crew, chap, flag, who) in ((1, 2, 3, 'Rook'), (2, 4, 4, 'Pip'), (3, 6, 5, 'Nova'), (7, 7, 6, 'Kestrel'), (1, 8, 7, 'Rook')):
    ck(mb(43, 0x50 + flag) == 0, '%s: flag %d is off before chapter %d is done' % (who, flag, chap))
    for i in range(30):
        if mb(43, 0x50 + flag):
            break
        mb(45, chap - 1)                          # (the chapter before: not done yet)
        talk_all(crew)
    ck(not mb(43, 0x50 + flag), '%s: not told before chapter %d is done' % (who, chap))
    mb(45, chap)
    done = False
    for i in range(30):
        talk_all(crew)
        if mb(43, 0x50 + flag):
            done = True
            break
    ck(done, '%s: told after chapter %d: flag %d is set (%d talks)' % (who, chap, flag, i + 1))
ck(all(mb(43, 0x50 + f) for f in range(3, 8)), 'all five flags are set')

# ---- the heard talks live in Prog's spare bytes ----
heard = hd()
ck(bin(heard).count('1') >= 8, 'many talks are heard', 'bits %s' % bin(heard).count('1'))
ck('cp_prog' in S, 'cp_prog is in the ELF')
prog = e.read(S['cp_prog'], 260)
got = int.from_bytes(prog[241:249], 'little')                # (Prog is 260 bytes, spare[20] its last: spare[1..8])
ck(got == heard, 'the heard bits are Prog.spare[1..8]', '%x vs %x' % (got, heard))

# ---- the city board ----
mb(45, 3)
mb(47, 0 | 1 << 8)                                # one contract done in city 0
mb(34, 2), run(10)
mb(39, 2)                                         # the contracts screen
ck(st(4) & 255 == 2, 'contracts screen open')
shot('contracts')
htap('RIGHT')
ck(st(20) == 1, 'RIGHT turns to the city board')
shot('cityboard')
c0 = credits()
htap('A', after=20)
bonus = credits() - c0
ck(bonus == 100 + 50 + 50, 'A claims the bonus for city 0: 100 + Pip 50 + Nova 50', 'paid %d' % bonus)
ck(st(21) >> 8 & 1 == 1, 'the claim is in Prog (story[3] bit 0)', hex(st(21)))
c1 = credits()
htap('A', after=20)
ck(credits() == c1, 'a second A pays nothing again', 'paid %d' % (credits() - c1))
shot('cityboard_claimed')
htap('LEFT')
ck(st(20) == 0, 'LEFT is back to this city')
htap('B', after=20)
ck(st(4) & 255 == 0, 'B closes it')

# ---- Kestrel's board ----
mb(34, 8), run(10)
mb(39, 11)
shot('log')
htap('RIGHT')
ck(st(20) == 1, 'RIGHT in Kestrel\'s log turns to her board')
shot('acepage')
cr0 = credits()
mb(46, 0 | 2 << 8)
ck(credits() - cr0 == 150 and (st(21) & 7) == 1, 'challenge 1 (flag 6 is on): +150, bit 0', 'paid %d %x' % (credits() - cr0, st(21)))
mb(46, 0 | 2 << 8)
ck(credits() - cr0 == 150, 'done again: nothing more')
cr1 = credits()
mb(46, 6 | 2 << 8)
ck(credits() - cr1 == 150 and (st(21) & 7) == 5, 'challenge 3 (flag 7 is on): +150', 'paid %d %x' % (credits() - cr1, st(21)))
mb(46, 5 | 2 << 8)
ck((st(21) & 7) == 5, 'a challenge that is not on the board counts for nothing')
mb(44, 2)                                         # the finale: Ace mode
ck(mb(43, 0x60) == 1, 'Ace mode is on')
cr2 = credits()
mb(46, 0 | 2 << 8)
ck(credits() - cr2 == 300, 'done in Ace mode: +300', 'paid %d %x' % (credits() - cr2, st(21)))
ck((st(21) >> 3) & 1 == 1, 'the Ace bit is set')
shot('acepage_done')
htap('LEFT')
ck(st(20) == 0, 'back to the log')
htap('B', after=20)

# ---- SAVE... in one press ----
mb(34, 7), run(10)
mb(39, 8)
ck(st(4) & 255 == 8, 'the comms screen')
htap('A', after=6)
ck(mb(17, 7) >> 4 & 1 or mb(27) & 15 in (1, 2), 'one A on SAVE... saves (no second press)', 'busy %x save %x' % (mb(17, 7), mb(27)))
for _ in range(120):
    run(2)
    if not mb(27) & 16:
        break
ck(mb(27) & 15 == 2, 'and the save finished', 'state %d' % (mb(27) & 15))
h0 = hd()
# ---- the city board travels to a city with no contract done (last: the level changes) ----
ck(mb(17, 11) & 15 == 1, 'the campaign menu stayed up after SAVE... (it shows how the save went)')
htap('B', after=20)
ck(mb(17, 11) & 15 == 0, 'B closes it')
mb(34, 2), run(10)
mb(39, 2)
htap('RIGHT')
htap('DOWN')
c2 = credits()
shot('travel_before')
htap('A', after=10)
shot('travel_after')
for _ in range(60):
    run(10)
    if mb(17, 1) == 1 or mb(17, 10) == 1:
        break
ck((mb(17, 1) == 1 or mb(17, 10) == 1) and credits() == c2, 'A on another city travels there (chapter 2 is the current one), paying nothing', 'chap %s tgt %s cur %s credits %s' % (mb(17, 1), mb(17, 10), mb(17, 12), credits()))

ck(mb(23) & 1 == 1, 'power cycle: the campaign is back')
h1 = hd()
ck(h1 == h0 and h0 == heard, 'the heard talks came back from the save', '%x %x %x' % (h0, h1, heard))
ck(st(21) & 0xffffff, 'the boards\' bits came back too', hex(st(21)))

ck.done()
