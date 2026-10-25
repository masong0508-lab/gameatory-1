"""The mission engine in the emulator, on the demo blob (tests/vm/mkdemo.py): nothing armed at the level's start, the act shown when walked up to and
started by a second in its beacon or by the mailbox, completed, failed and flown by the autopilot (cmds 1-5, 7-9), Payback's goal
list the same after every one, a phone mission in the middle (the act waits), a death, and no line on the ticker.

    S2_DEMO=1 python3 build.py ... --merge -o out.gba        (the demo chapters are in the blob only on request: the real campaign's
    ROM=out.gba ELF=build/merge/stuntfox-merge.elf python3 tests/s2/mission.py      301 missions are tests/s2/acts.py's)
"""
import h
from h import *

ck = Check()
merged_state(e)
run(30)
if mb(8, 0) != 6:                     # (not a demo build: the missions are the campaign's own, which acts.py runs)
    print('SKIP  this ROM has %d missions, not the demo blob\'s 6: build with S2_DEMO=1 for this suite' % mb(8, 0))
    sys.exit(0)

BAN = 0x020026e4                      # Payback's banner slot 0 (the literal in pb_banner_raw, 0x08039bc8)
D_MIS, D_ACT = 0, 1                   # (demo: mission 0 is the on-foot act at (14.5, 58.5))


def ban():
    return bytes(e.read(BAN, 20)).split(b'\0')[0].decode('latin1')


def ticker_n():
    return r16(0x02019424)            # (Payback's ticker: the count of lines it was given)


def st():
    v = mb(7)
    return v & 255, (v >> 8) & 255, (v >> 16) & 0xffff      # state, objective in the mission, mission


def gl():
    return [(g[0], g[1], g[4], g[5]) for g in goals()]


def ours():
    return [g for g in gl() if 0x5000 <= g[0] < 0x5100]


def own():
    return [g for g in gl() if not 0x5000 <= g[0] < 0x5100]


def seen_banners(frames, step=3):
    out = []
    for _ in range(frames // step):
        run(step)
        b = ban()
        if not out or out[-1] != b:
            out.append(b)
    return out


# ---- the level starts with the act armed ----
ck(mb(8, 0) == 6 and mb(8, 1) == 2, 'the demo blob is in: 6 missions, 2 chapters', 'missions %s chapters %s' % (mb(8, 0), mb(8, 1)))
ck(st()[0] == 0 and st()[2] == 0xffff, 'map 0: nothing is armed at the start (the campaign arms acts; a lone engine shows the first act when walked up to)', str(st()))
base_state = e.save_state()
base_goals, base_ticker = own(), ticker_n()
s_before = score()

# ---- standing in the beacon starts it, the title is the banner ----
tele_man(14.5, 58.5)
fm_break()
banners = seen_banners(240)
ck(st()[0] == 2 and 'FIRST STEPS' in banners, 'walking up to the beacon arms the act and a second in it starts it, its title is the banner', '%s %s' % (st(), banners))
ck(own() == base_goals and not ours(), "a phone is ringing: the arrow is Payback's, no goal of ours", str(gl()))
e.frame.save(os.path.join(START, '..', '..', 'E', 'shot_e1_started.png')) if False else None
run_state = e.save_state()

# ---- the mailbox: complete, fail, autopilot, dump ----
o0 = st()[1]
mb(2)
run(4)
ck(st()[1] > o0, 'cmd 2 (complete) moves the act to its next objective', '%d -> %d' % (o0, st()[1]))
mb(3)
run(4)
ck(st()[0] == 1 and mb(8, 3) == 1 and ban() == 'ACT FAILED' and mb(8, 5) == 1, 'cmd 3 (fail): ACT FAILED, the act stands armed again',
   '%s nfail %d retries %d banner %s' % (st(), mb(8, 3), mb(8, 5), ban()))
ck(own() == base_goals and not ours(), "Payback's goals are as they were after the fail", str(gl()))
s_h = e.save_state()
h1 = mb(5)
e.load_state(s_h)
ck(h1 == mb(5) and h1 != 0, 'cmd 5 (dump) is deterministic: the same state, the same hash (it moves with the dwell and the roam scan)', hex(h1 & 0xffffffff))
mb(1, 0)
run(6)
mb(4, 1)
banners, n = [], 0
while mb(8, 2) < 1 and n < 500:                # (the autopilot completes an objective a second after it began)
    run(3)
    n += 1
    b = ban()
    if not banners or banners[-1] != b:
        banners.append(b)
ck(mb(8, 2) == 1 and 'ACT COMPLETE' in banners, 'cmd 4 (autopilot) flies the act to its end: ACT COMPLETE, one finished', '%s done %d in %d frames' % (banners, mb(8, 2), 3 * n))
ck(score() > s_before, "and the score is paid", '%s -> %s' % (s_before, score()))
run(4)
ck(own() == base_goals and not ours(), "Payback's goals are as they were after the act", str(gl()))
ck(st()[0] in (1, 2), 'the act is repeatable: armed again (and, standing in its beacon, begun again)', str(st()))
mb(4, 0)
mb(10, 1)                                 # (roaming off: the act's beacon would be shown again at once)
ck(mb(9) == 0 and st()[0] == 0, 'cmd 9 (abort) drops everything', str(st()))
mb(10, 0)
t_end = ticker_n()
ev = events()
ck(ev['MIS_DONE'] == 1 and ev['MIS_FAIL'] == 1, 'EV_MIS_DONE and EV_MIS_FAIL were raised once each', str(ev))

# ---- no ticker line: the same frames without the missions give the same count ----
frames_run = None
e.load_state(base_state)
run(1)
t0 = ticker_n()
run(150)
ctl_extra = ticker_n() - t0
e.load_state(base_state)
run(1)
t1 = ticker_n()
tele_man(14.5, 58.5)
mb(1, 0)
mb(4, 1)
run(150)
ck(ticker_n() - t1 == ctl_extra, 'no ticker line from the engine (a run and a control give the same count)', '%d vs %d' % (ticker_n() - t1, ctl_extra))

# ---- our arrow: with no phone ringing the goal is ours, on the objective ----
e.load_state(run_state)
run(1)
e.write8(0x0201a7d8, 1)               # (only the level's own goal: no ringing phone)
e.write8(0x0201a7d9, 0)
run(10)
og = ours()
ck(len(og) == 1 and og[0][1] == 4 and og[0][2] == 0x7f and og[0][3] == 0, 'no phone ringing: one goal of ours, kind 4, floor 0x7f, marker 0', str(gl()))
g = [x for x in goals() if 0x5000 <= x[0] < 0x5100]
ck(g and abs(g[0][2] - 11.5) < 0.01 and abs(g[0][3] - 60.5) < 0.01, 'on the first marker (11.5, 60.5)', str(g))
run(60)
arrow = (r32(0x020025f0), r32(0x020025f4))
ck(abs(arrow[0] - 11.5 * 2048) < 64 and abs(arrow[1] - 60.5 * 2048) < 64, "Payback's arrow points at it", str(arrow))
mb(2)
run(10)
og2 = ours()
ck(len(og2) == 1 and og2[0] != og[0], 'the next objective: the goal moved (one goal, a new id)', '%s -> %s' % (og, og2))
mb(3)
run(10)
ck(not ours(), 'a fail takes the goal away', str(gl()))

# ---- a phone mission in the middle: the act waits ----
e.load_state(run_state)
run(1)
for (dx, dy), hd in zip(((0, 1.5), (1.5, 0), (-1.5, 0), (0, -1.5)), (2880, 4320, 1440, 0)):
    s0 = e.save_state()
    tele_man(12.5 + dx, 24.5 + dy)
    e.write8(PL + 0x12, hd & 255)
    e.write8(PL + 0x13, hd >> 8)
    run(5)
    ok = False
    for _ in range(10):
        run(15, ['A'])
        if r16(0x02007134) != 0:
            ok = True
            break
    if ok:
        break
    e.load_state(s0)
run(20)
ck(ok and st()[0] == 5, "a phone mission began (Payback's current mission %d): the act is paused" % r16(0x02007134), str(st()))
ck(not ours(), 'and its goal is gone', str(gl()))
pk = mb(8, 6)
run(60)
e.write8(0x0201a7d8, 1)               # (the phone mission is over: only the level's own goal)
e.write8(0x0201a7d9, 0)
e.write8(0x02007134, 0)
run(20)
ck(st()[0] == 2, 'the phone mission over: the act is running again', str(st()))

# ---- a death in the middle fails it ----
e.load_state(run_state)
run(1)
mb(D_RAISE, EV.index('DEATH'))
run(6)
ck(st()[0] == 1 and mb(8, 3) == 1, 'a death during the act fails it (FF_DEATH): armed again, one fail', '%s nfail %d' % (st(), mb(8, 3)))
ck(len(own()) == len(base_goals), "Payback's goals are as they were", str(gl()))

ck(hooks()['TICK'] > 0, 'the hooks ran throughout')
ck.done()
