#!/usr/bin/env python3
"""ob_speed.py RUNDIR [RUNDIR ...]: speed figures of obrun.py sessions from samples.csv / renders.csv / summary.json.
Guest frames per second of EMULATED time (frames / core fps), per phase: menus = before the level clock runs,
level = after.  CD: cluster fetches (rom_miss_count) and sectors per emulated second.  3D: hblank lines per render."""
import csv, json, sys, os

def phase(rows, fps, name):
    if len(rows) < 2: return None
    a, b = rows[0], rows[-1]
    dt = (int(b['frame']) - int(a['frame'])) / fps
    d = lambda k: (int(b.get(k) or 0) - int(a.get(k) or 0))
    cyc = sum(((int(y['io_cyc']) - int(x['io_cyc'])) & 0xffffffff) for x, y in zip(rows, rows[1:]))
    return {'phase': name, 'emu_s': round(dt, 1), 'guest_frames': d('g_gframes'), 'guest_fps': round(d('g_gframes') / dt, 3), 'gba_time_ratio': round(cyc / 16777216 / dt, 4),
            'presents': d('g_pres'), 'presents_per_s': round(d('g_pres') / dt, 3), 'cd_fetches': d('rom_miss_count'), 'cd_fetch_per_s': round(d('rom_miss_count') / dt, 2),
            'cd_sectors': d('cd_sectors'), 'cd_sectors_per_s': round(d('cd_sectors') / dt, 1), 'renders3d': d('st3_render'), 'lvl_clock': d('lvl_clock'), 'ri_exc_per_s': round(d('ob_exc') / dt, 1)}

for run in sys.argv[1:]:
    rows = list(csv.DictReader(open(run + '/samples.csv')))
    summ = json.load(open(run + '/summary.json')) if os.path.exists(run + '/summary.json') else {}
    fps = summ.get('core_fps') or 59.82
    start = next((i for i, r in enumerate(rows) if int(r['g_gframes'] or 0) > 0), 0)
    lvl = next((i for i, r in enumerate(rows) if int(r['lvl_clock']) > 0), None)
    out = {'run': run, 'core': summ.get('core'), 'game_first_frame_at_emu_s': round(int(rows[start]['frame']) / fps, 1)}
    out['menus'] = phase(rows[start:lvl] if lvl else rows[start:], fps, 'menus (boot to level clock)')
    # menu split at guest frame 660 (title menu reached by the assist)
    def idx(gf): return next((i for i, r in enumerate(rows) if int(r['g_gframes'] or 0) >= gf), None)
    cuts = [0, 380, 660, 1090]
    out['menu_segments'] = []
    for a, b in zip(cuts, cuts[1:]):
        ia, ib = idx(max(a, 1)), idx(b)
        if ia is not None and ib is not None and ib > ia:
            p = phase(rows[ia:ib + 1], fps, 'guest frames %d-%d' % (a, b)); out['menu_segments'].append(p)
    if lvl:
        out['level'] = phase(rows[lvl:], fps, 'level')
        ren = [float(l.split(',')[2]) for l in list(open(run + '/renders.csv'))[1:]] if os.path.exists(run + '/renders.csv') else []
        fr = [int(l.split(',')[0]) for l in list(open(run + '/renders.csv'))[1:]] if ren else []
        lf = int(rows[lvl]['frame'])
        ren = [x for x, f in zip(ren, fr) if f >= lf]
        if ren:
            out['renders3d'] = {'n': len(ren), 'lines_mean': round(sum(ren) / len(ren), 1), 'lines_max': max(ren), 'over_263': sum(1 for x in ren if x > 263), 'over_526': sum(1 for x in ren if x > 526),
                                'over_719': sum(1 for x in ren if x > 719), 'note': 'hblank lines per sf3_frame measured by the game with root counter 1 (263 lines = one NTSC field)'}
    print(json.dumps(out, indent=1))
