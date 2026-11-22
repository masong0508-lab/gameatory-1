#!/usr/bin/env python3
"""Exercise actual ROM gameplay with a stock mGBA core and private source ROM.

The boot and controls are real joypad input. RAM teleports and a descriptor
change prepare repeatable lane tests; this does not claim a manual playthrough.
Run each ROM in its own process; libretro cores contain global state.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import time
import zlib

from drive_lanes import boot_into_car, controlled_entity, position_car, GROUND_Z


class Geometry(C.Structure):
    _fields_ = [('base_width', C.c_uint), ('base_height', C.c_uint),
                ('max_width', C.c_uint), ('max_height', C.c_uint), ('aspect', C.c_float)]


class Timing(C.Structure):
    _fields_ = [('fps', C.c_double), ('sample_rate', C.c_double)]


class AVInfo(C.Structure):
    _fields_ = [('geometry', Geometry), ('timing', Timing)]


def state(e, car):
    return {'x': e.r32(car + 4) / 2048, 'y': e.r32(car + 8) / 2048,
            'height': (GROUND_Z - e.s16(car + 12)) / 16,
            'loop': e.read(0x0203fffc, 1)[0], 'phase': e.r32(0x0203ffec),
            'roll': e.r32(0x0203fff4),
            'velocity': list(struct.unpack('<hhh', e.read(car + 0x40, 6)))}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom')
    ap.add_argument('--symbols', required=True, help='editor.json belonging to this ROM')
    ap.add_argument('--out', required=True, help='private report/screenshot directory')
    ap.add_argument('--baseline', action='store_true', help='skip newly added retry control')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    syms = json.loads(Path(a.symbols).read_text())
    rom = Path(a.rom).read_bytes()
    report = {'rom_sha256': hashlib.sha256(rom).hexdigest(),
              'method': 'mGBA libretro; real boot/joypad input, RAM setup for reproducible scenarios',
              'checks': {}, 'performance': {}}
    start = time.monotonic()
    e = boot_into_car(a.rom)
    car = controlled_entity(e)
    base = e.save_state()
    base_ram_hash = hashlib.sha256(e.read(0x02000000, 0x40000)).hexdigest()
    grid = e.u32(0x03000d60)
    columns = [e.u32(syms['cols'] + 4*i) for i in range(85)]

    def check(name, passed, **details):
        report['checks'][name] = {'passed': bool(passed), **details}
        print(name, 'PASS' if passed else 'FAIL', json.dumps(details), flush=True)

    check('cold_boot_and_car_entry', e.read(0x0203fffb, 1)[0] == 1,
          controlled_entity=hex(car), grid=hex(grid), neo=e.read(0x0203fffb, 1)[0])

    for name, lane, frames, goal in (
            ('kicker_whoops_tabletop', (36.5, 28.5, 1440), 760, 79),
            ('deck_climb_drop', (86, 40.5, 4320), 720, 46),
            ('speed_loop', (42, 37.5, 1440), 650, 60)):
        e.load_state(base)
        car = position_car(e, lane)
        log, loop_frames, images, completed = [], 0, {}, False
        loop_state = None
        for i in range(frames):
            e.run(1, ['A'])
            s = state(e, car)
            log.append(s)
            if len(log) > 1 and log[-2]['loop'] == 1 and s['loop'] != 1 and s['phase'] >= 6144:
                completed = s['height'] == 0 and s['roll'] == 0
            if s['loop'] == 1:
                loop_frames += 1
                if loop_state is None and 800 <= s['phase'] <= 1800:
                    loop_state = e.save_state()
                if 'entry' not in images:
                    images['entry'] = e.frame.copy()
                if 2600 <= s['phase'] <= 3500 and 'top' not in images:
                    images['top'] = e.frame.copy()
            if i in (0, 180, 300, 420):
                e.shot(out / f'{name}-{i:03d}.png')
        reached = max(p['x'] for p in log) >= goal if lane[2] < 2880 else min(p['x'] for p in log) <= goal
        passed = reached and max(p['height'] for p in log) > 100
        if name == 'speed_loop':
            passed &= completed and loop_frames > 0 and log[-1]['loop'] != 1 and log[-1]['roll'] == 0
            for label, im in images.items():
                im.save(out / f'loop-{label}.png')
            e.shot(out / 'loop-exit.png')
        check(name, passed, start=lane, end=log[-1],
              peak_height=max(p['height'] for p in log), loop_video_frames=loop_frames,
              completed_turn=completed if name == 'speed_loop' else None,
              max_step_cells=max(abs(b['x']-a_['x']) + abs(b['y']-a_['y']) for a_,b in zip(log, log[1:])))
        if name == 'speed_loop' and not a.baseline:
            if loop_state is None:
                check('build_keys_isolated_from_loop', False, reason='no active loop checkpoint')
            else:
                e.load_state(loop_state)
                e.run(12, ['SELECT', 'A'])
                ramp_motion = state(e, car)
                e.load_state(loop_state)
                e.run(12, ['SELECT', 'B'])
                block_motion = state(e, car)
                check('build_keys_isolated_from_loop', ramp_motion == block_motion,
                      select_a=ramp_motion, select_b=block_motion)

    # Each build action is executed on the emulated CPU, then its live grid is
    # compared with the actual pointer table installed in this ROM.
    e.load_state(base)
    car = position_car(e, (60.5, 30.5, 1440))
    tx, ty = 62, 30
    target = grid + 4*(tx*128+ty)
    blink_seen = False
    for _ in range(24):
        e.run(1, ['SELECT'])
        blink_seen |= e.u32(target) in columns[83:85]
    check('build_cursor_visible', blink_seen and e.r32(0x0203ffdc) == tx*128+ty+1)

    def build_key(key):
        e.run(8, ['SELECT', key])
        e.run(8)
        return e.u32(target)

    actions = [('L', 0), ('B', 2), ('R', 3), ('L', 0), ('UP', 81), ('DOWN', 82), ('A', 33)]
    actual = []
    for key, index in actions:
        value = build_key(key)
        actual.append({'key': key, 'matches': value == columns[index]})
    check('all_builder_controls', all(item['matches'] for item in actual), actions=actual)
    check('cursor_restored_on_release', e.r32(0x0203ffdc) == 0 and e.u32(target) not in columns[83:85])
    e.shot(out / 'built-ramp.png')

    # Boundary targeting must not modify the map or leave a stale cursor.
    position_car(e, (126.5, 126.5, 0))
    before = e.read(grid, 65536)
    e.run(12, ['SELECT', 'A'])
    e.run(8)
    check('builder_map_edge', e.r32(0x0203ffdc) == 0 and e.read(grid, 65536) == before)

    # Retry is tested separately by test_retry.py in a naturally entered road
    # vehicle. Replacing a tank's model descriptor leaves tank-specific control
    # state and is an unsuitable fixture for stopped/turning-car assertions.

    # Compare engine video updates in an identical driving scene, rather than
    # mistaking the emulator's host speed or 59.7Hz output for game FPS.
    e.load_state(base)
    car = position_car(e, (36.5, 28.5, 1440))
    av = AVInfo()
    e.lib.retro_get_system_av_info.argtypes = [C.POINTER(AVInfo)]
    e.lib.retro_get_system_av_info(C.byref(av))
    hz = av.timing.fps
    frames, changed, flips = 600, 0, 0
    previous_hash = zlib.crc32(e.frame.tobytes())
    previous_page = e.u16(0x04000000) & 16
    for _ in range(frames):
        e.run(1, ['A'])
        current_hash = zlib.crc32(e.frame.tobytes())
        current_page = e.u16(0x04000000) & 16
        changed += current_hash != previous_hash
        flips += current_page != previous_page
        previous_hash, previous_page = current_hash, current_page
    report['performance'] = {
        'scene': '600 emulated video frames; lane A from x36.5,y28.5 with A held',
        'core_refresh_hz': hz, 'seconds_emulated': frames/hz,
        'changed_video_frames': changed, 'display_page_flips': flips,
        'changed_frames_per_second': changed*hz/frames,
        'page_flips_per_second': flips*hz/frames,
        'qualification': 'One scripted mGBA scene, not hardware timing or a whole-game FPS guarantee.'}
    e.load_state(base)
    check('state_restore', controlled_entity(e) == car and
          hashlib.sha256(e.read(0x02000000, 0x40000)).hexdigest() == base_ram_hash)
    e.close()
    report['elapsed_host_seconds'] = time.monotonic()-start
    report['passed'] = all(v['passed'] for v in report['checks'].values())
    (out / 'gameplay-report.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print('RESULT', 'PASS' if report['passed'] else 'FAIL', json.dumps(report['performance']), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
