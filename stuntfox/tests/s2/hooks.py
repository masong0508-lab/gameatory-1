"""Stage 2's hooks fire, with no other package built in: every hook is counted, every event can be raised, the player
can be put down, and the natural events (mode, death, a level end and start) arrive, all read back through the debug
mailbox (stage2.h) and no ticker line is written.

    ROM=out.gba ELF=build/merge/stuntfox-merge.elf python3 tests/s2/hooks.py      (from stuntfox/)
"""
import h
from h import *

ck = Check()
merged_state(e)
run(30)


def ticker_n():
    return r16(0x02019424)               # (Payback's ticker: the count of lines it was given)


# ---- the per-frame hooks ----
h0, f0, t0 = hooks(), s2f(), ticker_n()
run(120)
h1, f1 = hooks(), s2f()
d = {k: (h1[k] - h0[k]) & 0xffff for k in HK}
ck(d['TICK'] > 10 and all(abs(d[k] - d['TICK']) <= 1 for k in ('DRAW3D', 'HUD', 'KEYS')),
   'tick, draw3d, hud and keys hooks fire together, once a frame of ours', str(d))
# (ticks is read once a frame of ours, 3 vblanks apart at 20 a second, so a 120 frame window reads 118 to 123: the bound is two of our frames)
ck(abs(f1['ticks'] - f0['ticks'] - 122) <= 6 and f1['clock'] > f0['clock'], 's2f.ticks runs at 60 a second, s2f.clock follows Payback',
   '%d ticks in 122 frames, clock %d -> %d' % (f1['ticks'] - f0['ticks'], f0['clock'], f1['clock']))
pl = epos(PL)
ck(f1['mode'] == 0 and f1['map'] == grid(), 's2f: mode FOOT, map is the grid loaded',
   'mode %d map %d' % (f1['mode'], f1['map']))
pbm = r16(pba('PBA_MAP'))
for _i, _b in enumerate(((pbm + 5) % 11).to_bytes(2, 'little')):
    e.write8(pba('PBA_MAP') + _i, _b)                 # (the rampage's map is not the map loaded: a story level has the one and plays another)
run(3)
ck(s2f()['map'] == grid(), 's2f.map is the map whose world is loaded, whatever PB_MAP says', 'PB_MAP %d, grid %d, s2f.map %d' % ((pbm + 5) % 11, grid(), s2f()['map']))
for _i, _b in enumerate(pbm.to_bytes(2, 'little')):
    e.write8(pba('PBA_MAP') + _i, _b)
ck(abs(f1['pos'][0] - pl[0] * 1024) < 256 and abs(f1['pos'][2] - pl[1] * 1024) < 256, 's2f.pos is the man',
   'pos %s man %.2f,%.2f cells' % (f1['pos'], pl[0], pl[1]))
ck(d['LEVEL'] == 0 and d['MENU'] == 0 and d['ROOM'] == 0, 'level, menu and room hooks quiet on a plain stretch')

# ---- events: every one can be raised and is counted ----
ev_state = e.save_state()
mb(D_RESET)
ck(all(v == 0 for v in events().values()) and hooks()['TICK'] <= 1, 'reset zeroes the counters')
ok, frames, t0 = True, 0, ticker_n()
for ev in range(1, len(EV)):
    n0 = events()[EV[ev]]
    mb(D_RAISE, ev)
    n1 = events()[EV[ev]]
    ok &= n1 == n0 + 1 and mb(D_EVENTS, ev) == n1
ck(ok, 'EV_STUNT .. EV_MIS_FAIL raised through the mailbox: each counted once, read back by DBG_F_EVENTS', str(events()))
ck(mb(D_HOOK, 0) == hooks()['TICK'] and mb(D_EVENTS, 99) == -1 and mb(D_HOOK, 99) == -1 and mb(63) == -1,
   'mailbox answers: hook counts, out-of-range -1, a package with no code -1')
t1 = ticker_n()
e.load_state(ev_state)                                   # (the same frames again, nothing raised: the game's own lines)
run(1)
t2 = ticker_n()
for _ in range(len(EV) - 1):
    run(12)
ck(t1 - t0 == ticker_n() - t2, 'no ticker line was written by raising the events (the same frames without give the same count)',
   'with %d, without %d' % (t1 - t0, ticker_n() - t2))

# ---- put the player down: near works, far is refused ----
base = e.save_state()
me = s2f()['pos']
cx, cz = me[0] >> 10, me[2] >> 10
r_near = mb(D_PUT, (cx + 3) << 7 | cz)
run(4)
p = s2f()['pos']
ck(r_near == 1 and abs(p[0] - ((cx + 3) * 1024 + 512)) < 200, 's2_put_player: 3 cells away is taken', 'ret %s pos %s' % (r_near, p))
e.load_state(base)
run(2)
r_far = mb(D_PUT, (cx + 20) << 7 | cz)
run(4)
p2 = s2f()['pos']
ck(r_far == 0 and abs(p2[0] - me[0]) < 400, 's2_put_player: 20 cells away is refused (Payback would)', 'ret %s pos %s' % (r_far, p2))
e.load_state(base)
run(2)

# ---- the natural events ----
mb(D_RESET)
e.run(45, ['SELECT'])
for _ in range(40):
    if modename() == 'FLY':
        break
    run(10)
run(10)
ev = events()
ck(modename() == 'FLY' and ev['MODE'] == 1 and s2f()['mode'] == 2, 'EV_MODE: the Arwing boarded (SELECT held), s2f.mode FLY',
   'mode %s, EV_MODE %d' % (modename(), ev['MODE']))
e.load_state(base)
run(2)
mb(D_RESET)
c = ctl() or PL
e.write8(c + 0x68, 0), e.write8(c + 0x69, 0)             # the man's health
for _ in range(60):
    run(10)
    if r16(pba('PBA_RESPAWN')) > 0:
        break
run(10)                                                  # (our tick, once a frame of ours, sees the countdown a frame later)
ev, rs = events(), r16(pba('PBA_RESPAWN'))
ck(ev['DEATH'] == 1 and rs > 0, 'EV_DEATH: raised once as the respawn countdown starts (health 0)', 'EV_DEATH %d, countdown %d' % (ev['DEATH'], rs))
for _ in range(60):
    run(10)
    if r16(pba('PBA_RESPAWN')) == 0:
        break
run(60)
ck(events()['DEATH'] == 1 and r16(pba('PBA_RESPAWN')) == 0 and modename() == 'FOOT', 'no second death event, and the man is up again',
   'EV_DEATH %d, %s' % (events()['DEATH'], status()[:60]))

# ---- a level ends and the next starts ----
gstate(0)
run(30)
mb(D_RESET)
l0, m0 = hooks()['LEVEL'], hooks()['MENU']
e.write32(PL + 0x90, 9999999)                            # (a score far past the target: Payback ends the level, "press select")
for _ in range(10):
    run(30)
    if r16(0x02001e08) == 3:
        break
ck(r16(0x02001e08) == 3 and hooks()['MENU'] == m0, 'the rampage reached its target (level end 3); the menu has not been asked yet')
run(30)
run(6, ['SELECT'])
for _ in range(20):
    run(45)
    if grid() == 1 and u32(0x02001e00) > 0:
        break
run(120)
hk = hooks()
ck(grid() == 1 and hk['MENU'] - m0 == 1, 'HK_MENU: Payback asked for the next level once, the campaign went on to map 1',
   'grid %d, menu calls %d' % (grid(), hk['MENU'] - m0))
ck(hk['LEVEL'] - l0 == 1 and s2f()['map'] == 1, 'HK_LEVEL: once, for the new map, and s2f.map follows',
   'level calls %d, s2f.map %d' % (hk['LEVEL'] - l0, s2f()['map']))
ck(hk['BANNER'] >= 1, 'HK_BANNER: Payback\'s own banner (the level start) went through the veneer', 'banners %d' % hk['BANNER'])
t = hooks()['TICK']
run(120)                                                 # (the man starts where the clock puts him: at some starts of map 1 the base itself runs 9 frames a second, 19 ticks here)
ck(hooks()['TICK'] - t > 10 and modename() == 'FOOT' and s2f()['ticks'] > 0, 'the new level runs: hooks keep firing, on foot', status()[:80])

ck.done()
