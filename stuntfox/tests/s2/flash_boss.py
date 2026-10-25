"""Flash check (WCAG 2 general and red flash, every frame of the screen) over a boss fight with explosions in the city: the
mothership and four foes, fired at (A held), its turrets, bays and core shot off one after the other and the pod taken, a
carrier and a frigate blown up with dbg 49, then the Arwing shot down (the shield at its last sliver, three pirates on it);
stage2.md 9.2. Uses the playtest monitor (pp.fm_*), the measure flashcheck.py uses.

    SP=<harness folder> ROM=x.gba ELF=x.elf [OUT=<shots folder>] python3 tests/s2/flash_boss.py        (from stuntfox/)

Prints one line per session and ALL OK or FAIL (exit status 1)."""
import h
from h import *

OUT = os.environ.get('OUT', START)
os.makedirs(OUT + '/flash', exist_ok=True)
pp.D = OUT                                           # (the monitor saves the big changes under D/flash)
merged_state(e)
run(30)
assert board_now() == 'FLY', 'could not board the Arwing'
base = e.save_state()
res = []


def mb(cmd, arg=0):                                  # (h.mb, stepping the monitor on every frame)
    a = S['s2_dbg']
    seq = u32(a + 12)
    e.write8(a + 4, cmd & 255), e.write8(a + 5, cmd >> 8), e.write8(a + 6, arg & 255), e.write8(a + 7, arg >> 8)
    e.write32(a, MAGIC)
    for _ in range(40):
        run(1)
        if u32(a + 12) != seq:
            return r32(a + 8)


def here():
    me = epos(PL)
    tele_ship([int(me[0] * 1024), 2400, int(me[1] * 1024) - 2000], f=(0, -3000, 15900))
    run(2)


# the fight: guns firing, the boss's parts and body shot off, explosions at each
e.load_state(base)
e.write8(S['sg_shield_k'], 255)
here()
fm_start('boss_fight')
mb(48, 8)
for k in (1, 4, 1, 4):
    mb(51, k)
run(120, ['A'])
for t in range(4):
    mb(56, 1 << 8 | 255)
    run(40, ['A'])
mb(56, 2 << 8 | 255)
run(20, ['A'])
mb(56, 2 << 8 | 255)
run(40, ['A'])
mb(56, 255)                                          # (the core: the whole of it goes)
run(90, ['A'])
mb(49)
run(90)
res.append(fm_report())

# two more bosses blown up at once
e.load_state(base)
e.write8(S['sg_shield_k'], 255)
here()
fm_start('boss_kills')
for b in (3, 4, 0, 6):
    mb(49)
    run(30)
    mb(48, b)
    run(60, ['A'])
    mb(49)
    run(120, ['A', 'LEFT'])
res.append(fm_report())

# the Arwing shot down
e.load_state(base)
e.write8(S['sg_shield_k'], 4)
here()
fm_start('arwing_down')
for k in (1, 4, 1):
    mb(51, k)
for t in range(60):
    e.write8(S['shield'], 1), e.write8(S['shield'] + 1, 0)
    run(15)
    if r32(S['sg_state']) == 4:
        break
run(300)
res.append(fm_report())
snap('boss_flash_end')
bad = [r for r in res if r[0] > 3 or r[1] > 3]
print('ALL OK' if not bad else 'FAIL')
sys.exit(1 if bad else 0)
