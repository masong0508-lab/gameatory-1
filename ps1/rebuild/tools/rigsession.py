#!/usr/bin/env python3
"""rigsession.py ISO NM OUTDIR [--state-out FILE] [--maxboot N]
Second-opinion session in the headless libretro rig (PCSX-ReARMed core r26, HLE BIOS, software GPU; EMULATOR-ONLY): exact video frames,
pad input per frame, state read straight from PS1 RAM (symbol addresses from the build's nm listing, guest windows EWRAM 0x801b0000 / IWRAM 0x801f0000).
boot via the disc's own menu assist (no pad input) -> level -> idle -> walk (Cross) -> pause/resume -> weapon switch -> R2 / L2 map change.
Screenshots (320x240, the core's frame buffer) go to OUTDIR; results to OUTDIR/result.json; a save state at level start to --state-out."""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'rig'))   # ps1/rig (cores: $RIG_CORES, see its README.md)
from retro_ps1 import Emu
A = [a for a in sys.argv[1:] if not a.startswith('--')]; F = [a for a in sys.argv[1:] if a.startswith('--')]
iso, nmf, out = A[:3]
def opt(name, d):
    for f in F:
        if f.startswith('--' + name + '='): return f.split('=', 1)[1]
    return d
MAXBOOT = int(opt('maxboot', '90000')); STATE_OUT = opt('state-out', ''); STATE_IN = opt('state-in', '')
NM = {}
for l in open(nmf):
    p = l.split()
    if len(p) == 3: NM[p[2]] = int(p[0], 16)
os.makedirs(out, exist_ok=True)
e = Emu('pcsx_rearmed', iso, out, {'pcsx_rearmed_bios': 'HLE'})
EW, IW = 0x801b0000, 0x801f0000
def s16(a): v = e.r16(a); return v - 65536 if v & 0x8000 else v
def s32(a): v = e.r32(a); return v - (1 << 32) if v & 0x80000000 else v
def sym(n): return e.r32(NM[n]) if n in NM else None
def ent():
    nl, ci = s16(IW + 0xc), s16(EW + 0x1db8)
    if nl < 0 or nl > 100 or ci < 0 or ci > nl: return None
    p = e.r32(IW + 0xc60 + 4 * ci)
    if (p >> 24) == 2: p = EW + (p & 0x3ffff)
    elif not (EW <= p < EW + 0x40000): return None
    return dict(ci=ci, nl=nl, x=s32(p + 4), z=s32(p + 8), y=e.r16(p + 0xc), hd=e.r16(p + 0x12), hp=s16(p + 0x68), sc=s32(p + 0x90))
def st():
    d = dict(vf=e.frames, gf=sym('g_gframes'), f=sym('io_cyc') // 280896, clk=e.r32(EW + 0x1e00), pres=sym('g_pres'), sf3_ok=sym('sf3_ok'), render=sym('st3_render'), map_cur=sym('sf3_map_cur'), map_loads=sym('sf3_map_loads'),
             gmap=s16(EW + 0x1e66), keys=sym('io_keys'), pad=e.r16(NM['pad_raw']), cold_loads=sym('cold_loads'), cold_conf=sym('cold_conflicts'), cd_sectors=sym('cd_sectors'), rom_miss=sym('rom_miss_count'),
             ip_enters=sym('ip_enters'), ip_steps=sym('ip_stat_steps'), ip_calls=sym('ip_stat_calls'), ip_undef=sym('ip_stat_undef'), ip_depth_max=sym('ip_depth_max'), cursor=e.r8(IW + 0x7e68))
    en = ent()
    if en: d.update(en)
    return d
res = {'iso': iso, 'core': 'pcsx_rearmed (libretro, HLE BIOS)', 'events': []}; t0 = time.time()
def save(): json.dump(res, open(out + '/result.json', 'w'), indent=1)
def shot(name): e.shot('%s/%s.png' % (out, name)); return name
def log(tag, **kw):
    s = st(); s.update(kw); s['tag'] = tag; s['wall'] = round(time.time() - t0, 1); res['events'].append(s)
    print(tag, ' '.join('%s %s' % (k, v) for k, v in s.items() if k not in ('tag',)), flush=True); save(); return s
def run(n, buttons=()): e.run(n, buttons)
if STATE_IN:
    e.run(2); e.load_state(open(STATE_IN, 'rb').read()); log('state loaded')
else:
    # ---------------- boot: no pad input at all; the menu assist presses the keys.  A shot each time the guest frame counter passes a multiple of 6 (340..1150), and every 900 video frames
    lastf = -1; lastshot = 0; prev = None
    while e.frames < MAXBOOT:
        run(20); s = st()
        if s['clk']: break
        f = s['f']
        if (340 <= f <= 1150 and f // 6 != lastf // 6) or e.frames - lastshot >= 900:
            shot('boot_vf%06d_f%04d' % (e.frames, f)); lastshot = e.frames
        if prev is None or f // 50 != prev // 50 or s['keys'] != 1023: print('boot vf %d f %d gf %d keys %03x cursor %d cold %d cds %d miss %d ipe %d' % (e.frames, f, s['gf'], s['keys'], s['cursor'], s['cold_loads'], s['cd_sectors'], s['rom_miss'], s['ip_enters']), flush=True)
        lastf = f; prev = f
    s = log('level clock first seen running' if st()['clk'] else 'LEVEL NOT REACHED')
    res['level_reached'] = bool(s['clk']); res['level_vf'] = e.frames; res['level_f'] = s['f']; res['level_gf'] = s['gf']; save()
    if not s['clk']: shot('boot_end_no_level'); raise SystemExit(1)
    shot('level_00_clock_first_seen')
    if STATE_OUT: open(STATE_OUT, 'wb').write(e.save_state())
# ---------------- level start: the renderer is initialised now (world read from the CD)
for i in range(40):
    run(60)
    if st()['render'] and st()['render'] >= 2: break
log('first renders'); shot('level_01_first_renders')
run(600); log('level start + 600 vf'); shot('level_02_start')
a = log('idle begin'); run(900); b = log('idle end (900 vf, no key)'); shot('level_03_idle')
res['idle'] = dict(vf=900, gf=b['gf'] - a['gf'], clk=(a['clk'], b['clk']), moved=(b.get('x', 0) - a.get('x', 0), b.get('z', 0) - a.get('z', 0)), renders=b['render'] - a['render'])
a = log('walk begin'); run(450, ['CROSS']); shot('level_04_walk_cross_held'); run(450, ['CROSS']); b = log('walk end (900 vf Cross)'); run(120); shot('level_05_after_walk')
res['walk'] = dict(vf=900, gf=b['gf'] - a['gf'], clk=(a['clk'], b['clk']), moved=(b.get('x', 0) - a.get('x', 0), b.get('z', 0) - a.get('z', 0)), hd=(a.get('hd'), b.get('hd')), renders=b['render'] - a['render'])
a = log('turn begin'); run(300, ['LEFT']); b = log('turn end (300 vf Left)'); res['turn_left'] = dict(hd=(a.get('hd'), b.get('hd')))
# ---------------- pause / resume
a = log('before pause'); run(120, ['START']); run(600); p1 = log('paused a'); shot('level_06_paused_a'); run(900); p2 = log('paused b'); shot('level_07_paused_b')
res['pause'] = dict(clk_before=a['clk'], clk_paused=(p1['clk'], p2['clk']), frozen=p2['clk'] == p1['clk'], sf3_ok=(p1['sf3_ok'], p2['sf3_ok']))
run(120, ['CROSS']); run(600); r1 = log('after resume a'); shot('level_08_after_resume_a'); run(1200); r2 = log('after resume b'); shot('level_09_after_resume_b')
res['resume'] = dict(clk=(r1['clk'], r2['clk']), running=r2['clk'] > p2['clk'], sf3_ok=(r1['sf3_ok'], r2['sf3_ok']), renders=r2['render'] - p2['render'])
# ---------------- weapon switch
a = log('before weapon'); run(120, ['UP']); shot('level_10_weapon_up_held'); run(600); w1 = log('after weapon a'); shot('level_11_after_weapon_a'); run(1200); w2 = log('after weapon b'); shot('level_12_after_weapon_b')
res['weapon'] = dict(sf3_ok=(a['sf3_ok'], w1['sf3_ok'], w2['sf3_ok']), renders=w2['render'] - a['render'], cold_conf=(a['cold_conf'], w2['cold_conf']), ip_enters=(a['ip_enters'], w2['ip_enters']))
# ---------------- map change: R2 next map, L2 back
for key, tag in (('R2', 'level_13_map_r2'), ('L2', 'level_15_map_l2_back')):
    a = log('before ' + key); run(300, [key]); run(900); m1 = log('after ' + key + ' a'); shot(tag + '_a'); run(1200); m2 = log('after ' + key + ' b'); shot(tag + '_b')
    res['map_' + key] = dict(map_cur=(a['map_cur'], m1['map_cur'], m2['map_cur']), map_loads=(a['map_loads'], m2['map_loads']), cd_sectors=m2['cd_sectors'] - a['cd_sectors'], sf3_ok=m2['sf3_ok'], renders=m2['render'] - a['render'])
a = log('walk2 begin'); run(900, ['CROSS']); b = log('walk2 end'); shot('level_17_end')
res['walk_after_maps'] = dict(moved=(b.get('x', 0) - a.get('x', 0), b.get('z', 0) - a.get('z', 0)))
res['final'] = st(); res['wall_s'] = round(time.time() - t0, 1); save(); print('DONE wall %.1f' % (time.time() - t0))
