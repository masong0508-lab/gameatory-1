#!/usr/bin/env python3
"""rigspeed.py ISO NM OUTDIR [--tag=NAME]
Speed measurement in EMULATED time (headless libretro rig, PCSX-ReARMed r26, HLE BIOS; EMULATOR-ONLY).  60 video frames = 1 emulated second.
The disc's own menu assist boots to the level (no pad input); then a fixed script of actions, each defined in GUEST frames (the pad is polled once
per guest frame), so discs of different speed run the same guest-side scenario.  For each segment: guest frames, video frames, ROM page cache
fetches (rom_miss_count), CD sectors, level clock, player position.  Writes OUTDIR/speed.json and a few 320x240 screenshots."""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'rig'))   # ps1/rig (cores: $RIG_CORES, see its README.md)
from retro_ps1 import Emu
A = [a for a in sys.argv[1:] if not a.startswith('--')]; F = dict(a[2:].split('=', 1) for a in sys.argv[1:] if a.startswith('--') and '=' in a)
iso, nmf, out = A[:3]; tag = F.get('tag', os.path.basename(iso))
NM = {}
for l in open(nmf):
    p = l.split()
    if len(p) == 3: NM[p[2]] = int(p[0], 16)
os.makedirs(out, exist_ok=True)
e = Emu('pcsx_rearmed', iso, out, {'pcsx_rearmed_bios': 'HLE'})
EW, IW = 0x801b0000, 0x801f0000
r = lambda n: e.r32(NM[n])
def s16(a): v = e.r16(a); return v - 65536 if v & 0x8000 else v
def s32(a): v = e.r32(a); return v - (1 << 32) if v & 0x80000000 else v
def gf(): return r('io_cyc') // 280896
def pos():
    nl, ci = s16(IW + 0xc), s16(EW + 0x1db8)
    if nl < 0 or nl > 100 or ci < 0 or ci > nl: return (None, None, None)
    p = e.r32(IW + 0xc60 + 4 * ci)
    if (p >> 24) == 2: p = EW + (p & 0x3ffff)
    elif not (EW <= p < EW + 0x40000): return (None, None, None)
    return (s32(p + 4), s32(p + 8), e.r16(p + 0x12))
def st(): return dict(vf=e.frames, gf=gf(), clk=e.r32(EW + 0x1e00), miss=r('rom_miss_count'), cds=r('cd_sectors'), render=r('st3_render'), pres=r('g_pres'), cold_loads=r('cold_loads'), conf=r('cold_conflicts'),
                      ipe=r('ip_enters'), ips=r('ip_stat_steps'), map_cur=r('sf3_map_cur'), sf3_ok=r('sf3_ok'), pos=pos())
res = {'iso': iso, 'tag': tag, 'core': 'pcsx_rearmed libretro r26, HLE BIOS', 'boot': [], 'segments': []}; t0 = time.time()
def save(): json.dump(res, open(out + '/speed.json', 'w'), indent=1)
# ---------------- boot: no input; note the video frame at which the guest frame counter passes the assist's key frames
marks = [100, 360, 660, 750, 836, 1028, 1094]; mi = 0; lastm = st()
while e.frames < 90000:
    e.run(10); g = gf()
    while mi < len(marks) and g >= marks[mi]:
        s = st(); res['boot'].append(dict(mark=marks[mi], vf=s['vf'], miss=s['miss'], cds=s['cds'])); print('boot  guest frame %4d at video frame %6d (%.1f emulated s)  fetches %d  cd sectors %d' % (marks[mi], s['vf'], s['vf'] / 60, s['miss'], s['cds']), flush=True); mi += 1
    if e.r32(EW + 0x1e00): break
s = st(); res['level'] = s; res['level_reached'] = bool(s['clk']); save()
print('LEVEL %s: guest frame %d at video frame %d = %.1f emulated s (%d min %02d s); fetches %d, cd sectors %d, cold loads %d, wall %.0f s' % ('clock runs' if s['clk'] else 'NOT REACHED', s['gf'], s['vf'], s['vf'] / 60, s['vf'] // 3600, s['vf'] // 60 % 60, s['miss'], s['cds'], s['cold_loads'], time.time() - t0), flush=True)
if not s['clk']: e.shot(out + '/no_level.png'); raise SystemExit(1)
def seg(name, buttons, nguest, cap=40000, shot=None):
    a = st(); g0 = a['gf']
    while gf() - g0 < nguest and e.frames - a['vf'] < cap: e.run(2, buttons)
    b = st(); n = b['gf'] - a['gf']; v = b['vf'] - a['vf']
    d = dict(name=name, buttons=list(buttons), guest_frames=n, video_frames=v, vf_per_guest_frame=round(v / max(n, 1), 1), guest_fps_emulated=round(60 * n / max(v, 1), 2), fetches=b['miss'] - a['miss'], cd_sectors=b['cds'] - a['cds'],
             renders=b['render'] - a['render'], presents=b['pres'] - a['pres'], clk=(a['clk'], b['clk']), pos=(a['pos'], b['pos']), conf=b['conf'] - a['conf'], ip_enters=b['ipe'] - a['ipe'], ip_steps=b['ips'] - a['ips'], capped=n < nguest)
    res['segments'].append(d); save()
    print('%-28s %3d guest frames in %6d video frames = %6.1f vf/frame = %5.2f guest fps | fetches %4d (%.2f/frame) cds %5d | renders %3d | clk %d->%d | pos %s -> %s%s' % (name, n, v, v / max(n, 1), 60 * n / max(v, 1), d['fetches'], d['fetches'] / max(n, 1), d['cd_sectors'], d['renders'], a['clk'], b['clk'], a['pos'], b['pos'], '  CAPPED' if d['capped'] else ''), flush=True)
    if shot: e.shot('%s/%s.png' % (out, shot))
    return d
seg('level start (first frames)', [], 16, shot='s00_level_start')
seg('idle', [], 32, shot='s01_idle')
seg('walk (Cross)', ['CROSS'], 64, shot='s02_walk')
seg('turn (Left)', ['LEFT'], 16)
seg('walk 2 (Cross)', ['CROSS'], 48, shot='s03_walk2')
seg('Start (pause) press', ['START'], 4); seg('paused', [], 24, shot='s04_paused')
seg('Cross (resume) press', ['CROSS'], 4); seg('after resume', [], 32, shot='s05_resumed')
seg('Up (next weapon) press', ['UP'], 4); seg('after weapon', [], 32, shot='s06_after_weapon')
seg('R1 press', ['R1'], 4); seg('after R1', [], 16)
seg('walk + Right', ['CROSS', 'RIGHT'], 24)
seg('walk 3 (Cross)', ['CROSS'], 48, shot='s07_end')
L = [d for d in res['segments']]; n = sum(d['guest_frames'] for d in L); v = sum(d['video_frames'] for d in L); f = sum(d['fetches'] for d in L)
res['level_total'] = dict(guest_frames=n, video_frames=v, guest_fps_emulated=round(60 * n / v, 2), fetches=f, fetches_per_guest_frame=round(f / n, 2)); res['final'] = st(); res['wall_s'] = round(time.time() - t0, 1); save()
print('LEVEL TOTAL %d guest frames in %d video frames (%.1f emulated s) = %.2f guest frames per emulated second; fetches %d = %.2f per guest frame; final %s; wall %.0f s' % (n, v, v / 60, 60 * n / v, f, f / n, res['final'], time.time() - t0), flush=True)
