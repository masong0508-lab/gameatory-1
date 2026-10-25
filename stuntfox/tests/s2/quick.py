"""The campaign's quick menu through its keys (mailbox 26 sends the hangar's keys to it), and what a code and a stop do to the player's own state:
  - ENTER CODE asks A again before it replaces a campaign that is running; it keeps the player's stick, aim, missiles, paint and jobs (a code has
    none of them) and takes the chapters, the Arwing's upgrades and the credits from the code;
  - STOP CAMPAIGN switches the campaign off, nothing erased, and saves that: after a power cycle it stays off, the credits earned since are the
    player's, and START CAMPAIGN (CONTINUE CAMPAIGN) goes on where it was; a stop with no campaign running says so;
  - a chip proved only when a save is first wanted (mode 4 Kbit until then).

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/quick.py      (from stuntfox/)
"""
import h
from h import *

ck = Check()
A, B, RIGHT, UP, DN, L = 1, 2, 16, 64, 128, 512
ALPHA = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def key(k):
    mb(26, k)
    run(3)


def q():
    return mb(17, 11) & 15


def code():
    return ''.join(''.join(chr((mb(22, i) >> (8 * j)) & 255) for j in range(4)) for i in range(4))


gstate(3)
run(40)
ck(mb(17, 8) == 0, 'before a campaign the chip is in Payback\'s 4 Kbit mode: nothing was proved at the boot', 'mode %s' % mb(17, 8))
ck(mb(16, 0) == 1 and mb(17, 8) == 1, 'START CAMPAIGN proves the chip: 64 Kbit mode', 'mode %s' % mb(17, 8))
f0 = mb(17, 16)
ck(f0 & 3 and (f0 >> 8) & 255, 'the player has the stick/aim flags and missiles to keep (flags %x, missiles %d)' % (f0 & 255, (f0 >> 8) & 255), hex(f0))
mb(18, 0 << 8 | 0x3f)                                 # (chapter 1's acts done: the code carries it)
mb(28, 700)
c = code()
cr = mb(17, 6)
ck(len(c) == 16 and cr >= 700, 'a code of 16 letters for the progress now', '%s credits %d' % (c, cr))
mb(24, 0)
mb(28, 5000)
ck(mb(17, 6) > cr and mb(17, 2) == 0, 'then the progress moves on: more credits, no chapter open', 'credits %d open %d' % (mb(17, 6), mb(17, 2)))

# ---- the quick menu, ENTER CODE with a campaign running ----
key(L)
ck(q() == 1, 'L opens the quick menu')
for _ in range(4):
    key(DN)
key(A)
ck(q() == 1 and mb(17, 17) & 1, 'ENTER CODE on a running campaign asks A again (nothing opened)', 'q %d confirm %d' % (q(), mb(17, 17) & 1))
key(DN)
ck(not mb(17, 17) & 1, 'a move of the cursor takes the question back')
key(UP)
key(A)
key(B)
ck(q() == 0 and not mb(17, 17) & 1, 'B in the question closes the menu and takes the question with it (nothing opened)')
key(L)
for _ in range(4):
    key(DN)
key(A)
key(A)
ck(q() == 4, 'A again opens the code page', 'q %d' % q())
for ch in c:
    i = ALPHA.index(ch)
    for _ in range(i if i <= 16 else 32 - i):
        key(UP if i <= 16 else DN)
    key(RIGHT)
key(A)
ck(q() == 1, 'the code was accepted: back on the quick menu', 'q %d' % q())
ck(mb(17, 6) == cr - cr % 100 and mb(17, 2) == 1, 'its chapters and credits are the code\'s', 'credits %d (code %d) open %d' % (mb(17, 6), cr - cr % 100, mb(17, 2)))
ck(mb(17, 16) == f0, 'the stick, aim, missiles, paint and jobs are the player\'s own, not the code\'s zeros', '%x vs %x' % (mb(17, 16), f0))

# ---- STOP CAMPAIGN ----
mb(24, 3)
for _ in range(5):
    key(DN)
key(A)
ck(q() == 0 and mb(17, 0) & 1 == 0, 'STOP CAMPAIGN: the quick menu closes and the campaign is off', 'q %d flags %d' % (q(), mb(17, 0)))
for _ in range(80):
    run(2)
    if not mb(27) & 16:
        break
ck(mb(27) & 15 == 2, 'and the stop was saved (a campaign that stays on at the next boot is no stop)', 'save state %d' % (mb(27) & 15))
mb(28, 123)
earned = mb(17, 6)
ck(mb(23) & 1 == 0, 'power cycle: the campaign is still off')
ck(mb(17, 6) == earned and mb(17, 0) & 1 == 0, 'and what was earned since is the player\'s: the saved image did not take it back', 'credits %d vs %d' % (mb(17, 6), earned))
key(L)
for _ in range(5):
    key(DN)
key(A)
ck(q() == 0 and mb(17, 0) & 1 == 0, 'STOP CAMPAIGN with no campaign running: nothing happens')
key(L)
ck(q() == 1, 'the menu opens again')
key(A)
ck(mb(17, 0) & 1 == 1 and mb(17, 2) == 3 and mb(17, 6) == earned, 'CONTINUE CAMPAIGN goes on where it was (3 chapters open), and keeps what the player has', 'flags %d open %d credits %d' % (mb(17, 0), mb(17, 2), mb(17, 6)))
ck.done()
