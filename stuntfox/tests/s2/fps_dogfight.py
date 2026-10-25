"""The city dogfight's frame rate (stage2.md 9.2): the Arwing over the city with a boss and the foes round it, drawn and
shooting (the Arwing cannot be hurt: the shield setting at 255), windows of 240 frames, the mean of each and the worst.
Floor: 17 fps for every scene. The scenes are one boss each with the foes that fit in the 8 slots up to four more; the
first scene is the hardest to draw (a boss with parts and four raiders and aces, the draw caps at their limit).

    SP=<harness folder> ROM=x.gba ELF=x.elf python3 tests/s2/fps_dogfight.py [windows]       (from stuntfox/)

Prints one line per scene and ALL PASS or the number failed (exit status 1)."""
import h
from h import *

FLOOR = 17.0
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
WINDOW = 240
SETTLE = 200                                         # (past the seconds the boss's name is up for)
ck = Check()
merged_state(e)
run(30 + int(os.environ.get('PRE', 0)))                 # (PRE: more frames before the start state, for another phase of Payback's traffic)
ck(board_now() == 'FLY', 'in the Arwing')
base = e.save_state()
none = [None]                                        # (the first scene's mean: what the street and the traffic leave, which moves by a fps or more with the traffic's phase)
KINDS = {'RAIDER': 1, 'CARRIER': 2, 'ACE': 4, 'COURIER': 5}


def scene(name, boss, foes):
    v = []
    for w in range(N):
        e.load_state(base)
        e.write8(S['sg_shield_k'], 255)              # (nothing hurts it)
        run(1 + 17 * w)                              # (a different start each window: the traffic differs)
        if boss is not None:
            mb(48, boss)
        for k in foes:
            mb(51, KINDS[k])
        alive = mb(50, 0)
        run(SETTLE)
        k0 = r32(S['key_calls'])
        run(WINDOW)
        v.append((r32(S['key_calls']) - k0) * 60.0 / WINDOW)
    mean = sum(v) / N
    if none[0] is None:
        none[0] = mean
    ck(min(v) >= FLOOR, '%-34s %d foes' % (name, alive), 'mean %.1f  min %.1f  (%+.1f on no foes)  %s' % (mean, min(v), mean - none[0], ' '.join('%.1f' % x for x in v)))
    return mean


scene('no foes (the Arwing over the street)', None, [])
scene('4 foes, no boss', None, ['RAIDER', 'ACE', 'RAIDER', 'COURIER'])
scene('CARRIER + 4 foes (7 slots)', 3, ['RAIDER', 'ACE', 'RAIDER', 'ACE'])
scene('FRIGATE + 3 foes (8 slots)', 4, ['RAIDER', 'ACE', 'ACE'])
scene('SIEGE BARGE + 3 foes (8 slots)', 2, ['RAIDER', 'ACE', 'RAIDER'])
scene('IRON COMET + 4 foes', 6, ['RAIDER', 'ACE', 'RAIDER', 'ACE'])
scene('GULLWING + 4 foes', 0, ['RAIDER', 'ACE', 'RAIDER', 'ACE'])
scene('DROPSHIP + 4 foes', 1, ['RAIDER', 'ACE', 'RAIDER', 'ACE'])
scene('MOTHERSHIP + 1 foe (7 + 1 slots)', 8, ['ACE'])
scene('KESTREL + 4 foes', 5, ['RAIDER', 'ACE', 'RAIDER', 'ACE'])
ck.done()
