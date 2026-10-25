"""A build with strong entry points (tests/s2/override/s2dummy.c) runs them in place of the weak stubs: every hook
reaches them, every event, every mailbox range, the keys they hold reach Payback's pad, and the next level is the one
cp_menu names.

    S2_EXTRA_SRC=tests/s2/override/s2dummy.c python3 build.py "$PAYBACK_ROM" --merge -o override.gba
    ROM=override.gba ELF=build/merge/stuntfox-merge.elf python3 tests/s2/override.py      (from stuntfox/)
"""
import h
from h import *

ck = Check()
merged_state(e)
run(30)


def dv(name, n=1):
    return [u32(S[name] + 4 * i) for i in range(n)]


ck(all(k in S for k in ('dummy_ms_tick', 'dummy_cp_ev', 'ms_tick', 'cp_keys')), 'the build has the dummy file in it')
d0, h0 = dv('dummy_ms_tick', 1)[0], hooks()
c0 = {k: dv(k)[0] for k in ('dummy_draw3d', 'dummy_hl', 'dummy_cp_tick', 'dummy_keys')}
run(120)
h1 = hooks()
n = (h1['TICK'] - h0['TICK']) & 0xffff
ck(n > 10 and dv('dummy_ms_tick')[0] - d0 == n, 'ms_tick runs once per tick', '%d ticks, %d calls' % (n, dv('dummy_ms_tick')[0] - d0))
ck(abs(dv('dummy_draw3d')[0] - c0['dummy_draw3d'] - n) <= 1 and abs(dv('dummy_hl')[0] - c0['dummy_hl'] - n) <= 1,
   'ms_draw3d and hl_draw run once a frame (hl_draw: no room view)', 'draw3d %d, hud %d' % (dv('dummy_draw3d')[0] - c0['dummy_draw3d'], dv('dummy_hl')[0] - c0['dummy_hl']))
ck(dv('dummy_cp_tick')[0] - c0['dummy_cp_tick'] == n and abs(dv('dummy_keys')[0] - c0['dummy_keys'] - n) <= 1, 'cp_tick and cp_keys run',
   'cp_tick %d, cp_keys %d' % (dv('dummy_cp_tick')[0] - c0['dummy_cp_tick'], dv('dummy_keys')[0] - c0['dummy_keys']))

b = [dv(k, 16) for k in ('dummy_ms_ev', 'dummy_cp_ev', 'dummy_st_ev')]
for ev in range(1, len(EV)):
    mb(D_RAISE, ev)
a = [dv(k, 16) for k in ('dummy_ms_ev', 'dummy_cp_ev', 'dummy_st_ev')]
ck(all(a[j][ev] - b[j][ev] == 1 for j in range(3) for ev in range(1, len(EV))), 'every event reaches ms_ev, cp_ev and st_ev, once each')
ck([mb(1, 5), mb(16, 2), mb(32, 1), mb(48, 3), mb(64 + 1, 0) == hooks()['TICK']] == [1000 + 16 + 5, 2000 + 256 + 2, 3000 + 512 + 1, 4000 + 768 + 3, True],
   'the mailbox ranges go to ms_dbg, cp_dbg, st_dbg, sg_dbg and F', str([mb(1, 5), mb(16, 2), mb(32, 1), mb(48, 3)]))

base = e.save_state()


def walked(mask):
    e.load_state(base)
    run(2)
    e.write32(S['dummy_keys_mask'], mask)
    p0 = epos(PL)
    run(90)
    p1 = epos(PL)
    e.write32(S['dummy_keys_mask'], 0)
    return math.hypot(p1[0] - p0[0], p1[1] - p0[1])


d_off, d_on = walked(0), walked(1 << 6)           # (B_A, accelerate: on foot, walk; no key is pressed by the harness)
ck(d_off < 0.05 and d_on > 0.5, 'cp_keys: a button it holds walks the man, no key pressed', 'idle %.2f cells, held %.2f cells in 90 frames' % (d_off, d_on))


def beyond(mask):
    """The bytes after PB_BTN (it is B_N long) after 30 frames of cp_keys answering mask: bits from B_N up must write nothing there."""
    e.load_state(base)
    run(2)
    e.write32(S['dummy_keys_mask'], mask)
    run(30)
    x = bytes(e.read(pba('PBA_BTN') + 14, 18))
    e.write32(S['dummy_keys_mask'], 0)
    return x


ck(beyond(0xffffc000) == beyond(0), 'cp_keys: bits from B_N up (14..31) are ignored, nothing past PB_BTN is written')
e.load_state(base)
run(2)

# ---- the station's room view (st_view answers 1 or 2): the world and the 3D hook stop, the room's own draw and HUD run ----
import numpy as np                                    # noqa: E402


def pic():
    return np.asarray(e.frame.convert('RGB'), dtype=int)


def room(v):
    e.write32(S['dummy_room_mode'], v)


h0, d0 = hooks(), {k: dv(k)[0] for k in ('dummy_draw3d', 'dummy_hl', 'dummy_room_draws', 'dummy_room_huds')}
room(1)
run(30)
h1, d1 = hooks(), {k: dv(k)[0] for k in d0}
f_room = pic()
n = (h1['TICK'] - h0['TICK']) & 0xffff                 # (frames of ours: about a third of the emulator's)
got = [(h1['ROOM'] - h0['ROOM']) & 0xffff, d1['dummy_room_draws'] - d0['dummy_room_draws'], d1['dummy_room_huds'] - d0['dummy_room_huds']]
ck(n >= 8 and all(abs(g - n) <= 1 for g in got), 'room view 1: HK_ROOM, st_draw and st_hud run once a frame of ours',
   '%d frames, room %d, draws %d, huds %d' % ((n,) + tuple(got)))
ck(d1['dummy_draw3d'] == d0['dummy_draw3d'] and d1['dummy_hl'] == d0['dummy_hl'], 'room view 1: the 3D scene and the usual HUD hooks stop',
   'draw3d +%d, hl +%d' % (d1['dummy_draw3d'] - d0['dummy_draw3d'], d1['dummy_hl'] - d0['dummy_hl']))
ck(f_room.std() > 5 and f_room.mean() > 5, 'room view 1: the picture is the room, not black', 'mean %.1f std %.1f' % (f_room.mean(), f_room.std()))
room(2)
run(30)
h2, d2 = hooks(), {k: dv(k)[0] for k in d0}
ck(d2['dummy_room_draws'] == d1['dummy_room_draws'] and np.abs(pic() - f_room).mean() < 1, 'room view 2: the last picture again, no redraw',
   'draws +%d, picture change %.2f' % (d2['dummy_room_draws'] - d1['dummy_room_draws'], np.abs(pic() - f_room).mean()))
ck(hooks()['TICK'] - h1['TICK'] >= 8 and hooks()['ROOM'] - h1['ROOM'] >= 8, 'room view 2: the hooks\' ticks go on, and it counts as the room',
   'ticks +%d, room +%d' % (hooks()['TICK'] - h1['TICK'], hooks()['ROOM'] - h1['ROOM']))
import random                                         # noqa: E402
random.seed(5)
for _ in range(200):
    room(random.choice([0, 1, 2]))
    run(random.randint(1, 5), random.choice([[], ['UP'], ['A'], ['SELECT']]))
room(0)
run(90)
d3 = dv('dummy_draw3d')[0]
run(30)
ck(dv('dummy_draw3d')[0] - d3 >= 8 and pic().std() > 5, 'after 200 random toggles with keys: the world draws again, the picture is not black',
   'draw3d +%d, std %.1f' % (dv('dummy_draw3d')[0] - d3, pic().std()))
e.load_state(base)
run(2)

gstate(0)
run(30)
n0 = dv('dummy_level_n')[0]
e.write32(S['dummy_menu_set'], 1), e.write32(S['dummy_menu_val'], 3 * 2)    # the next level: map 3, sub 0
e.write32(PL + 0x90, 9999999)
for _ in range(10):
    run(30)
    if r16(0x02001e08) == 3:
        break
run(30)
run(6, ['SELECT'])
for _ in range(25):
    run(45)
    if grid() == 3 and u32(0x02001e00) > 0:
        break
run(120)
ck(dv('dummy_menu')[0] >= 1 and grid() == 3, 'cp_menu: the level it names (map 3) is the one that is played', 'cp_menu calls %d, grid %d' % (dv('dummy_menu')[0], grid()))
ck(dv('dummy_level_n')[0] - n0 == 1 and dv('dummy_level_map')[0] == 3 and dv('dummy_cp_level_n')[0] >= 1, 'ms_level_enter / cp_level_enter ran for the new map',
   'ms_level_enter %d times, map %d' % (dv('dummy_level_n')[0] - n0, dv('dummy_level_map')[0]))
ck(modename() == 'FOOT' and hooks()['TICK'] > 100, 'the game runs on', status()[:80])

ck.done()
