#!/usr/bin/env python3
"""ROM data read sampling for the *private* Stage-7 / Track-B Unicorn MIPS sim.

Requires the prepared tree and its private f1 EXE/ISO/ELF. Never records ROM
contents, translated instructions, game text, screenshots, or controller data.
Records only ROM page IDs, read counts, map index, and controlled-entity class.

This hooks h_memrd (CPU data reads) and cannot see all ROM-origin DMA or
inlined/native page reads: counts are lower bounds. Use mGBA or another
instrumented path for complete data+DMA read coverage. Scene attribution is
sampled once per present(), so transitions can have one-frame lag.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from collections import deque
import os
import sys
from pathlib import Path
from working_set import capture, page_indices, trace_fingerprint

EW, IW = 0x801b0000, 0x801f0000
DESC0 = 0x08354af4
DESCSIZE = 0x3c


def controlled_mode(rd16, rd32, read_rom_byte):
    """Classify Payback's selected entity without exposing any descriptor data.

    Returns foot, vehicle_XXX, or unclassified, never guesses car type names.
    Reads the same offsets as ps1/rig/ps1game.py's player()/entity().
    """
    n = rd16(IW + 0x0c)
    ci = rd16(EW + 0x1db8)
    if n >= 101 or ci > n:
        return 'unclassified'
    pointer = rd32(IW + 0x0c60 + ci * 4)
    if (pointer >> 24) == 2:
        rec = EW + (pointer & 0x3ffff)
    elif EW <= pointer < EW + 0x40000:
        rec = pointer
    else:
        return 'unclassified'
    desc = rd32(rec + 0x1c)
    if desc < DESC0 or desc >= DESC0 + 128 * DESCSIZE or (desc - DESC0) % DESCSIZE:
        return 'unclassified'
    kind = (desc - DESC0) // DESCSIZE
    cls = read_rom_byte(desc + 0x26)
    return 'foot' if cls == 1 else f'vehicle_{kind:03d}' if cls == 0 else 'unclassified'


class PageRecorder:
    """Pure read/present classifier; never records address values or ROM bytes.

    The last N pre-level *present calls* are assigned to the map that begins
    after them. This is a load-transition approximation, not an exact marker:
    the window may contain the menu immediately before launching the level.
    """
    def __init__(self, prelevel_present_frames=30):
        if prelevel_present_frames < 1:
            raise ValueError('invalid_prelevel_window')
        self.data = collections.defaultdict(collections.Counter)
        self.samples = collections.Counter()
        self.active = None
        self.pending = collections.Counter()
        self.recent = deque(maxlen=prelevel_present_frames)

    def read(self, ea, size):
        try:
            pages = page_indices(ea, size)
        except ValueError:
            return
        target = self.data[self.active] if self.active is not None else self.pending
        for page in pages:
            target[page] += 1

    def presented(self, map_id=None, mode=None, phase=None):
        good = map_id is not None and 0 <= map_id < 11 and mode is not None and phase in ('early_play', 'play')
        if good:
            if self.active is None:
                pre = collections.Counter()
                for item in self.recent:
                    pre.update(item)
                pre.update(self.pending)
                if pre:
                    k = (map_id, 'unclassified', 'pre_level')
                    self.data[k].update(pre)
                    self.samples[k] += len(self.recent) + 1
                self.recent.clear()
                self.pending.clear()
            self.active = (map_id, mode, phase)
            self.samples[self.active] += 1
        else:
            if self.active is not None:
                self.recent.clear()
                self.pending.clear()
            self.active = None
            self.recent.append(self.pending)
            self.pending = collections.Counter()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tree', type=Path, required=True, help='private prepared tree containing t/sim4.py')
    ap.add_argument('--variant', default='f1', help='prepared-tree sim build name (default f1)')
    ap.add_argument('--max-gba-frame', type=int, default=1600, help='stop at this guest frame; 1500 was the Track B discovery baseline')
    ap.add_argument('--early-ticks', type=int, default=300, help='first N positive level-clock ticks are early play')
    ap.add_argument('--prelevel-present-frames', type=int, default=30, help='rolling pre-level presentation window (can include menus)')
    ap.add_argument('--rom', type=Path, required=True, help='private untouched owner ROM (used only to classify controlled entity)')
    ap.add_argument('--output-dir', type=Path, required=True, help='private output directory OUTSIDE Git checkout')
    a = ap.parse_args(argv)
    tree = a.tree.expanduser().resolve()
    out = a.output_dir.expanduser().resolve()
    if tree == out or tree in out.parents or out in tree.parents:
        ap.error('output must not be inside prepared tree (or vice versa)')
    if a.max_gba_frame < 1 or a.early_ticks < 0 or a.prelevel_present_frames < 1:
        ap.error('frame and tick limits invalid')
    simfile = tree / 't' / 'sim4.py'
    exe = tree / 'out' / f'{a.variant}.exe'
    iso = tree / 'out' / f'{a.variant}.iso'
    elf = tree / 'out' / f'bld_{a.variant}' / 'payback.elf'
    if not all(x.is_file() for x in (simfile, exe, iso, elf, a.rom)):
        ap.error('missing private sim4.py, EXE, ISO, ELF or owner ROM')
    # The size guard alone used to admit an arbitrary zero-filled 8 MiB file,
    # which can misidentify the controlled entity as a vehicle. Verify the
    # untouched European dump against the same constant used by the mod.
    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root / 'payback-mod'))
    from paybackmod.rom import PAYBACK_EU_SHA1
    rom = a.rom.read_bytes()
    if len(rom) != 0x800000 or hashlib.sha1(rom).hexdigest() != PAYBACK_EU_SHA1:
        ap.error('requires the exact original European 8 MiB Payback ROM (SHA-1 mismatch)')
    try:
        from unicorn import UC_HOOK_CODE
        from unicorn.mips_const import UC_MIPS_REG_4, UC_MIPS_REG_5
    except ImportError:
        ap.error('Unicorn is required (use the PS1 Track B environment)')
    sys.path.insert(0, str(tree / 't'))
    from sim4 import Sim  # type: ignore
    s = Sim(str(exe), str(iso), str(elf))
    if 'h_memrd' not in s.sym or 'io_cyc' not in s.sym:
        ap.error('sim ELF does not expose h_memrd/io_cyc symbols')
    recorder = PageRecorder(a.prelevel_present_frames)
    reached_limit = False

    def rom_byte(addr):
        return rom[(addr & 0x1ffffff)]

    def on_frame(sim):
        nonlocal reached_limit
        frame = sim.r32(sim.sym['io_cyc']) // 280896
        reached_limit = frame >= a.max_gba_frame
        clock = sim.r32(EW + 0x1e00)
        if clock and sim.r16(IW + 0x0c) <= 100:
            mi = sim.r16(EW + 0x1d40)
            if 0 <= mi < 11:
                mode = controlled_mode(sim.r16, sim.r32, rom_byte)
                phase = 'early_play' if clock <= a.early_ticks else 'play'
                recorder.presented(mi, mode, phase)
            else:
                recorder.presented()
        else:
            recorder.presented()
        return reached_limit

    def on_rom_read(uc, address, size, userdata):
        ea = uc.reg_read(UC_MIPS_REG_4)
        kind = uc.reg_read(UC_MIPS_REG_5)
        if 0 <= kind < 5:
            recorder.read(ea, (1, 1, 2, 2, 4)[kind])

    s.u.hook_add(UC_HOOK_CODE, on_rom_read, None, s.sym['h_memrd'], s.sym['h_memrd'])
    s.cb = on_frame
    s.run(count=30000000000)
    if not reached_limit:
        print('Simulator did not reach the requested guest frame; possible crash, timeout or interpreter fault', file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    saved = 0
    for (mi, mode, phase), reads in sorted(recorder.data.items()):
        if not reads:
            continue
        obj = capture(mi, mode, phase, reads, source='unicorn_sim_h_memrd_cpu_data_only')
        obj['sampled_present_frames'] = recorder.samples[(mi, mode, phase)]
        obj['coverage_status'] = 'live_observed'
        obj['trace_sha256'] = trace_fingerprint(reads)
        obj['limitations'] = ['CPU helper reads only; DMA accesses not guaranteed', 'map/mode attribution at presentation boundaries', 'pre_level window may include the last menu pages']
        target = out / f'map{mi:02d}_{mode}_{phase}.json'
        target.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')
        saved += 1
        print(f'map {mi:02d} {mode} {phase}: {len(reads)} 4K pages, {sum(reads.values())} CPU data reads')
    if not saved:
        print('No level data reads captured; verify private sim reaches a running map', file=sys.stderr)
        return 2
    print('Wrote', saved, 'data-only page captures under private output directory')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())