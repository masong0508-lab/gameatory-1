# Session for obrun.py (object S): no pad input until the level runs (the disc's own timed menu assist presses the keys),
# screenshots at fixed GUEST moments (GBA frames since power-on = io_cyc / 280896) so that cores can be compared at the same
# guest state, then in the level: idle, walk (Cross = GBA A), turn, weapon change (Up), shoot (R1), idle.  Pad holds are
# measured in GUEST frames, because the guest speed differs between cores.  Build independent: only S.* is used.
import os
MILE = [60, 120, 200, 300, 380, 450, 520, 600, 660, 700, 780, 860, 930, 990, 1020, 1060, 1090]
MAXF = int(os.environ.get('OB_MAXF', '110000'))       # give up waiting for the level after this many emulated frames
LVLF = int(os.environ.get('OB_LVLF', '30000'))        # emulated frame budget of each level step
def gf(): return S.g('io_cyc') // 280896
i = 0
S.run(int(os.environ.get('OB_BOOTF', '600')))         # firmware + loader: RAM may hold anything until the program has started
while S.e.frames < MAXF and not S.lvl_clock():
    S.run(10)
    while i < len(MILE) and gf() >= MILE[i]:
        S.shot('gf%04d' % MILE[i]); i += 1
if not S.lvl_clock():
    S.mark('NO_LEVEL', gf=gf())
else:
    S.mark('level_clock_runs', gf=gf(), player=S.player())
    S.save('level_start')
    def hold(n, buttons, name):
        g1 = gf()
        S.until(lambda S: gf() - g1 >= n, LVLF, buttons)
        S.shot(name); S.mark(name + '_state', gf=gf(), player=S.player(), pad_raw=S.g('pad_raw'), pad_polls=S.g('pad_polls'), pad_fails=S.g('pad_fails'),
               pad_id='%02x' % (S.g('pad_id') & 0xff), pad_analog=S.g('pad_analog'), pad_cfg_tries=S.g('pad_cfg_tries'))
    hold(30, (), 'lvl_gf+030')
    hold(60, (), 'lvl_gf+090')
    hold(40, ['CROSS'], 'walk_cross_40gf')
    hold(20, ['CROSS', 'LEFT'], 'walk_left_20gf')
    hold(20, ['CROSS', 'RIGHT'], 'walk_right_20gf')
    hold(3, ['UP'], 'weapon_up_3gf')
    hold(20, (), 'after_weapon_20gf')
    hold(3, ['R1'], 'shoot_r1_3gf')
    hold(30, (), 'level_end')
    S.save('level_end')
