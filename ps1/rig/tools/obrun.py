#!/usr/bin/env python3
"""obrun.py: one scripted, sampled session of a disc on one libretro core (one emulator process).

    obrun.py --core swanstation|beetle|pcsx_rearmed --disc X.cue --out DIR [--sys DIR] [--sym payback.elf|map|nm]
             [--ew 0x801b0000] [--iw 0x801f0000] [--script idle|probe1|FILE.py] [--frames N] [--opt key=value ...]
             [--sample 30] [--interp]

Nothing is specific to one build: the disc, the symbol file and the guest RAM windows are parameters.  Without --sym
only the fixed guest addresses (level clock, map id, title cursor ...) and the openboot trace table are sampled.
Outputs in DIR: samples.csv (every --sample frames), renders.csv (one line per 3D render: frame, hblank lines),
tty.log (openboot putchar ring), trace.txt (openboot trace table at the end), shots/*.png + sheet.png, summary.json,
core.log (the core's own log).  A session script is Python run with `S` (see class Session).
For SwanStation and Beetle --sys defaults to $RIG_SYSTEM (else ps1/rig/system): openboot as scph5500.bin, scph5501.bin
and scph5502.bin, see README.md.  The cores come from $RIG_CORES (default ps1/rig/cores).
"""
import argparse
import json
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obrig import Emu2, format_trace, load_syms, swan_regs, beetle_regs   # noqa: E402
from retro_ps1 import RigSetupError, system_dir   # noqa: E402

DEFAULT_OPTS = {
    'pcsx_rearmed': {'pcsx_rearmed_bios': 'HLE'},
    'swanstation': {'swanstation_GPU_Renderer': 'Software', 'swanstation_BIOS_PatchFastBoot': 'false', 'swanstation_GPU_UseThread': 'false',
                    'swanstation_Logging_LogLevel': 'Dev', 'swanstation_Console_Region': 'Auto', 'swanstation_CDROM_RegionCheck': 'false',
                    'swanstation_CDROM_ReadSpeedup': '1', 'swanstation_CDROM_SeekSpeedup': '1', 'swanstation_MemoryCards_Card1Type': 'Libretro',
                    # RetroArch hands a core the first value of an option the user never touched; this frontend must say so explicitly.
                    # Without a path the core only accepts images whose hash it knows and otherwise runs its built-in OpenBIOS.
                    'swanstation_BIOS_PathNTSCU': 'scph5501.bin', 'swanstation_BIOS_PathNTSCJ': 'scph5500.bin', 'swanstation_BIOS_PathPAL': 'scph5502.bin'},
    'beetle': {'beetle_psx_cpu_dynarec': 'disabled', 'beetle_psx_skip_bios': 'disabled', 'beetle_psx_cd_access_method': 'sync',
               'beetle_psx_cd_fastload': '2x(native)', 'beetle_psx_use_mednafen_memcard0_method': 'libretro'},
}
GUEST = ['g_gframes', 'g_pres', 'io_cyc', 'g_nvbl', 'cd_sectors', 'rom_miss_count', 'cold_loads', 'cold_calls', 'st3_render', 'st3_lines_sum',
         'st3_lines_max', 'sf3_frames', 'sf3_ok', 'sf3_stat_eng', 'sf3_stat_prim', 'sf3_stat_ovf', 'sf3_stat_lod', 'logic_lines', 'max_lines',
         'tot_lines', 'nfr_meas', 'pad_polls', 'pad_fails', 'pad_raw', 'mc_reads', 'mc_writes', 'mc_err', 'cdda_last', 'sf3_map_cur']


class Session:
    def __init__(self, a):
        self.a = a
        opts = dict(DEFAULT_OPTS.get(a.core, {}))
        if a.interp and a.core == 'swanstation':
            opts['swanstation_CPU_ExecutionMode'] = 'Interpreter'
        for kv in a.opt:
            k, v = kv.split('=', 1); opts[k] = v
        self.opts = opts
        os.makedirs(a.out + '/shots', exist_ok=True)
        self.e = Emu2(a.core, a.disc, a.out, opts, sysdir=a.sys)
        self.syms = load_syms(a.sym)
        self.ew, self.iw = a.ew, a.iw
        self.cols = ['frame', 'lvl_clock', 'map', 'grid', 'ctrl', 'cursor'] + [g for g in GUEST if g in self.syms] + ['ob_exc', 'ob_irq', 'ob_tty', 'ob_calls']
        self.csv = open(a.out + '/samples.csv', 'w'); self.csv.write(','.join(self.cols) + '\n')
        self.rcsv = open(a.out + '/renders.csv', 'w'); self.rcsv.write('frame,st3_render,lines\n')
        self.mcsv = open(a.out + '/misses.csv', 'w'); self.mcsv.write('frame,gframes,rom_miss_count,rom_offset_of_cluster,lvl_clock\n')
        self._m = None
        self._pgprev = None
        self.tty = open(a.out + '/tty.log', 'wb')
        self.shots = []
        self.marks = []
        self.rows = []
        self._r = None
        self.t0 = time.time()

    # ---- guest access
    def g(self, name, default=0):
        a = self.syms.get(name)
        return self.e.r32(a) if a else default

    def gba(self, addr):
        """host address of a GBA EWRAM/IWRAM address"""
        return self.ew + (addr & 0x3ffff) if (addr >> 24) == 2 else self.iw + (addr & 0x7fff)

    def lvl_clock(self): return self.e.r32(self.ew + 0x1e00)
    def map_id(self): return self.e.r16(self.ew + 0x1d40)
    def cursor(self): return self.e.r8(self.iw + 0x7e68)

    def player(self):
        """(x, y, z, heading) of the controlled entity, or None"""
        idx = self.e.r16(self.ew + 0x1db8)
        if idx > 100:
            return None
        p = self.e.r32(self.iw + 0xc60 + 4 * idx)
        if (p >> 24) == 2:
            h = self.gba(p)
        elif self.ew <= p < self.ew + 0x40000:      # the translated code stores host pointers into the EWRAM window
            h = p
        else:
            return None
        hd = self.e.r16(h + 0x12)
        return (self.e.r32(h + 4), self.e.r32(h + 8), self.e.r16(h + 0xc), hd - 65536 if hd & 0x8000 else hd)

    def row(self):
        e = self.e
        t = e.trace() if self.a.core != 'pcsx_rearmed' or self.a.sys else {'present': False}
        r = {'frame': e.frames, 'lvl_clock': self.lvl_clock(), 'map': self.map_id(), 'grid': e.r16(self.ew + 0x1e66),
             'ctrl': e.r16(self.ew + 0x1db8), 'cursor': self.cursor()}
        for gname in GUEST:
            if gname in self.syms:
                r[gname] = self.g(gname)
        if t.get('present'):
            r.update(ob_exc=t['exc_total'] - t['irq_total'], ob_irq=t['irq_total'], ob_tty=t['tty_chars'],
                     ob_calls=sum(t['A'].values()) + sum(t['B'].values()) + sum(t['C'].values()))
            b = e.tty_poll()
            if b:
                self.tty.write(b); self.tty.flush()
        else:
            r.update(ob_exc=0, ob_irq=0, ob_tty=0, ob_calls=0)
        return r

    # ---- running
    def run(self, frames, buttons=(), label=None):
        e = self.e
        ra, sa = self.syms.get('st3_render'), self.syms.get('st3_lines_sum')
        ma, la, sn = self.syms.get('rom_miss_count'), self.syms.get('slot_owner'), self.syms.get('slot_next')
        for _ in range(frames):
            e.run(1, buttons)
            if ra:
                n, s = e.r32(ra), e.r32(sa)
                if self._r and n != self._r[0]:
                    self.rcsv.write('%d,%d,%.1f\n' % (e.frames, n, ((s - self._r[1]) & 0xffffffff) / max(1, n - self._r[0])))
                self._r = (n, s)
            if ma:
                n = e.r32(ma)
                if n != self._m:
                    self._m = n
                    # The cluster just fetched = the page table entries (rom_pg[], 0 = not in RAM) that are set now and were not
                    # at the previous fetch.  (The first version of this tool looked at slot_owner[] behind slot_next; when
                    # the NEXT fetch had already begun inside the same emulated frame those owners were cleared again and
                    # ROM offset 0 was recorded: wrong.)  0xffffff000 (page 0xfffff) = could not tell.
                    pg = 0xfffff
                    rp = self.syms.get('rom_pg')
                    if rp:
                        cur = struct.unpack('<2048I', e.read(rp, 8192))
                        if self._pgprev is not None:
                            new = [q for q in range(2048) if cur[q] and not self._pgprev[q]]
                            if new:
                                pg = new[0] & ~3
                        self._pgprev = cur
                    self.mcsv.write('%d,%d,%d,%#x,%d\n' % (e.frames, self.g('g_gframes'), n, pg << 12, self.lvl_clock()))
            if e.frames % self.a.sample == 0:
                r = self.row(); self.rows.append(r)
                self.csv.write(','.join(str(r.get(c, '')) for c in self.cols) + '\n'); self.csv.flush()
            if e.frames % 1800 == 0:
                print('  frame %d (%.0f s emulated, %.0f s wall) gframes %d pres %d clock %d' % (e.frames, e.frames / e.fps, time.time() - self.t0,
                      self.g('g_gframes'), self.g('g_pres'), self.lvl_clock()), flush=True)
        if label:
            self.shot(label)

    def press(self, *buttons, hold=6, after=30, label=None):
        self.run(hold, buttons); self.run(after, (), label)

    def until(self, cond, maxframes, buttons=(), step=10):
        """run until cond(S) is true; returns True when it became true"""
        n = 0
        while n < maxframes:
            if cond(self):
                return True
            self.run(step, buttons); n += step
        return bool(cond(self))

    def save(self, name):
        """save state of the core to OUT/name.state (reload with --load; same core and options only)"""
        open('%s/%s.state' % (self.a.out, name), 'wb').write(self.e.save_state())

    def cpu_regs(self):
        """36 words r0..r31, hi, lo, pc, npc from a save state (SwanStation: block found by pattern; Beetle: named fields), else None"""
        s = bytes(self.e.save_state())
        if self.a.core.startswith('beetle'):
            return beetle_regs(s)
        if self.a.core == 'swanstation':
            self._regoff, w = swan_regs(s, getattr(self, '_regoff', None))
            return w
        return None

    def cpu_pc(self):
        w = self.cpu_regs()
        return w[34] if w else None

    def shot(self, label):
        im = self.e.image()
        name = '%s/shots/%02d_%s.png' % (self.a.out, len(self.shots), label)
        if im:
            im.convert('RGB').save(name)
        self.shots.append((label, self.e.frames, name if im else None))
        self.mark(label)

    def mark(self, label, **extra):
        m = {'label': label, 'frame': self.e.frames, 'emu_s': round(self.e.frames / self.e.fps, 2), 'gframes': self.g('g_gframes'), 'pres': self.g('g_pres'),
             'io_cyc': self.g('io_cyc'), 'lvl_clock': self.lvl_clock(), 'cursor': self.cursor(), 'size': list(self.e.size)}
        m.update(extra); self.marks.append(m)
        print('MARK', json.dumps(m), flush=True)

    def finish(self):
        from PIL import Image
        e = self.e
        r = self.row()
        t = e.trace()
        txt = format_trace(t)
        open(self.a.out + '/trace.txt', 'w').write(txt + '\n')
        ims = [(l, f, Image.open(p).convert('RGB').resize((320, 240))) for l, f, p in self.shots if p]
        if ims:
            W = 4; H = (len(ims) + W - 1) // W
            sheet = Image.new('RGB', (320 * W, 240 * H))
            for i, (l, f, im) in enumerate(ims):
                sheet.paste(im, ((i % W) * 320, (i // W) * 240))
            sheet.save(self.a.out + '/sheet.png')
        summ = {'core': self.a.core, 'disc': self.a.disc, 'sys': self.a.sys, 'sym': self.a.sym, 'opts': self.opts, 'frames': e.frames, 'core_fps': e.fps,
                'wall_s': round(time.time() - self.t0, 1), 'size': list(e.size), 'last': r, 'marks': self.marks,
                'asked': {k: (v.decode() if isinstance(v, bytes) else v) for k, v in e.asked.items()}, 'unknown_env': sorted(e.unknown_env),
                'messages': e.messages[:40], 'trace': {k: v for k, v in t.items() if k not in ('A', 'B', 'C')} if t.get('present') else None,
                'calls': {tab + '%02X' % k: v for tab in 'ABC' for k, v in (t.get(tab) or {}).items()} if t.get('present') else None}
        json.dump(summ, open(self.a.out + '/summary.json', 'w'), indent=1, default=str)
        print(txt)
        print('done: %d frames, %.0f s wall, last %s' % (e.frames, time.time() - self.t0, {k: r[k] for k in list(r)[:12]}))


def script_idle(S):
    S.run(S.a.frames or 3600, (), 'end')


def script_probe1(S):
    """a fixed pad script: 1200 frames, then 15 x (CROSS 6 frames, 240 frames)"""
    S.run(1200, (), 'boot')
    for i in range(15):
        S.run(6, ['CROSS']); S.run(240, (), 'cross%02d' % (i + 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--core', required=True); ap.add_argument('--disc', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--sys', default=None); ap.add_argument('--sym', default=None)
    ap.add_argument('--ew', type=lambda x: int(x, 0), default=0x801b0000); ap.add_argument('--iw', type=lambda x: int(x, 0), default=0x801f0000)
    ap.add_argument('--script', default='idle'); ap.add_argument('--frames', type=int, default=0)
    ap.add_argument('--opt', action='append', default=[]); ap.add_argument('--sample', type=int, default=30)
    ap.add_argument('--interp', action='store_true', help='swanstation: interpreter instead of the recompiler')
    ap.add_argument('--nslot', type=int, default=8, help='page-cache slots of the build (NSLOT), for misses.csv')
    ap.add_argument('--load', default=None, help='start from a save state written by S.save() (same core, disc and options)')
    ap.add_argument('--pad-name', default=None, help='controller of port 1 by (part of) the name the core announces, e.g. DualShock')
    ap.add_argument('--pad-device', type=lambda x: int(x, 0), default=None, help='libretro device id of port 1 (default 1 = digital pad; SwanStation 5 = DualShock; Beetle 0x105 = DualShock)')
    a = ap.parse_args()
    if a.sys is None and a.core in ('swanstation', 'beetle', 'beetle_apt'):
        # default: the openboot system directory (an empty directory would make SwanStation run its built-in OpenBIOS and
        # Beetle run without firmware)
        try:
            a.sys = system_dir()
        except RigSetupError as ex:
            sys.exit('obrun: %s' % ex)
    try:
        S = Session(a)
    except RigSetupError as ex:
        sys.exit('obrun: %s' % ex)
    print('system directory: %s' % a.sys, flush=True)
    if S.e.controllers:
        print('controllers the core offers for port 1: %s' % ', '.join('%s=%#x' % (d, i) for d, i in S.e.controllers), flush=True)
    if a.pad_name:
        hit = [i for d, i in S.e.controllers if a.pad_name.lower() in d.lower()]
        if not hit:
            sys.exit('no controller named like %r' % a.pad_name)
        a.pad_device = hit[0]
    if a.pad_device is not None:
        S.e.lib.retro_set_controller_port_device(0, a.pad_device); print('pad device of port 1: %#x' % a.pad_device, flush=True)
    if a.load:
        S.e.run(2); S.e.load_state(open(a.load, 'rb').read()); print('state loaded:', a.load)
    print('core %s fps %.3f opts %s' % (a.core, S.e.fps, S.opts), flush=True)
    try:
        if a.script == 'idle':
            script_idle(S)
        elif a.script == 'probe1':
            script_probe1(S)
            if a.frames > S.e.frames:
                S.run(a.frames - S.e.frames, (), 'end')
        else:
            exec(compile(open(a.script).read(), a.script, 'exec'), {'S': S, '__name__': 'session'})
    finally:
        S.finish()


if __name__ == '__main__':
    main()
