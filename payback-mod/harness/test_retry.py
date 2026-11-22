#!/usr/bin/env python3
"""Test stadium retry in a real traffic vehicle, without changing its model.

Setup moves only the on-foot player beside existing traffic. Entry and every
subsequent action use normal buttons. The driving fixture deliberately avoids
the model-swapped tank used by the older synthetic lane benchmark.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from retro import Emu
from drive_lanes import BOOT, PLAYER_POS, controlled_entity

FIRST_CAR = 0x08354AF4
ARWING = 0x08354EF0
TANK_DESC = 0x08354D88


def vehicle_state(game):
    car = controlled_entity(game)
    return {
        'address': car,
        'descriptor': game.u32(car + 0x1C),
        'x': game.r32(car + 4),
        'y': game.r32(car + 8),
        'z': game.s16(car + 0xC),
        'heading': game.s16(car + 0x12),
        'velocity': [game.s16(car + offset) for offset in (0x40, 0x42, 0x44)],
        'angular_velocity': game.s16(car + 0x56),
        'throttle_acceleration': game.s16(car + 0x58),
        'propulsion_speed': game.s16(car + 0xBA),
        'loop': game.read(0x0203FFFC, 1)[0],
        'phase': game.r32(0x0203FFEC),
        'roll': game.r32(0x0203FFF4),
    }


def boot_real_car(game, attempts):
    for frames, button in BOOT:
        game.run(frames, [button] if button else [])
    for attempt in range(16):
        player = controlled_entity(game)
        px, py = game.r32(player + 4), game.r32(player + 8)
        cars = []
        for index in range(game.s16(0x0300000C) + 1):
            address = game.u32(0x03000C60 + 4 * index)
            descriptor = game.u32(address + 0x1C)
            x, y = game.r32(address + 4), game.r32(address + 8)
            if (FIRST_CAR <= descriptor < ARWING and descriptor != TANK_DESC
                    and 5 * 2048 < x < 123 * 2048 and 5 * 2048 < y < 123 * 2048):
                cars.append((abs(px - x) + abs(py - y), address, descriptor, x, y))
        if not cars:
            raise RuntimeError('no accessible non-tank road vehicle found')
        _, target, target_desc, x, y = sorted(cars)[attempt % min(len(cars), 3)]
        dx, dy = ((1200, 0), (-1200, 0), (0, 1200), (0, -1200))[attempt % 4]
        for address in PLAYER_POS:
            game.write32(address, x + dx)
            game.write32(address + 4, y + dy)
        game.write16(player + 0xC, 19904)
        game.run(3)
        game.press('L', hold=16, after=240)
        live = vehicle_state(game)
        attempts.append({'attempt': attempt + 1, 'target': target,
                         'target_descriptor': target_desc, 'controlled': live})
        if FIRST_CAR <= live['descriptor'] < ARWING and live['descriptor'] != TANK_DESC:
            return live
    raise RuntimeError('could not enter a real traffic vehicle with L')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--source', type=Path, help='optional original ROM checksum provenance')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    data = args.rom.read_bytes()
    report = {
        'output_sha1': hashlib.sha1(data).hexdigest(),
        'rom_sha256': hashlib.sha256(data).hexdigest(),
        'setup': 'Existing traffic vehicle entered with L; only player coordinates changed for setup; no model/descriptor edits.',
        'checks': [], 'entry_attempts': [], 'scenarios': [],
    }
    if args.source:
        report['source_sha1'] = hashlib.sha1(args.source.read_bytes()).hexdigest()

    def check(name, passed, **details):
        report['checks'].append({'name': name, 'passed': bool(passed), **details})
        print(f'{"PASS" if passed else "FAIL"}: {name}', flush=True)

    with Emu('gba', args.rom) as game:
        try:
            entered = boot_real_car(game, report['entry_attempts'])
            check('Enter a real existing traffic vehicle', True,
                  descriptor=entered['descriptor'], address=entered['address'])
            game.shot(args.out / '01-real-vehicle.png')
            initial = game.save_state()
            descriptor = entered['descriptor']
            scenarios = (
                ('stationary', (), 60),
                ('forward', ('A',), 180),
                ('turn-left', ('A', 'LEFT'), 60),
                ('turn-right', ('A', 'RIGHT'), 60),
                ('reverse', ('B',), 120),
                ('reverse-turn', ('B', 'LEFT'), 60),
            )
            for name, buttons, frames in scenarios:
                game.load_state(initial)
                game.run(frames, buttons)
                before = vehicle_state(game)
                if name != 'stationary':
                    check(f'{name}: scenario has real propulsion', abs(before['propulsion_speed']) > 20,
                          speed=before['propulsion_speed'])
                if name.startswith('reverse'):
                    check(f'{name}: propulsion is in reverse', before['propulsion_speed'] < 0)
                if 'turn' in name:
                    check(f'{name}: vehicle actually turned', before['heading'] != entered['heading'])
                game.run(16, ['SELECT', 'START'])
                after = vehicle_state(game)
                trace = []
                for frame in range(120):
                    game.run(1)
                    trace.append({'frame': frame + 1, **vehicle_state(game)})
                settled = trace[-1]
                reset_correctly = (
                    after['x'] == 42 * 2048 and after['y'] == 37 * 2048 + 1024
                    and after['z'] == 19904 and after['heading'] == 1440
                    and after['velocity'] == [0, 0, 0] and after['propulsion_speed'] == 0
                    and after['descriptor'] == descriptor
                )
                check(f'{name}: retry resets position and motion', reset_correctly,
                      after=after)
                motionless = all(
                    (row['x'], row['y'], row['z'], row['heading'])
                    == (42 * 2048, 37 * 2048 + 1024, 19904, 1440)
                    and row['velocity'] == [0, 0, 0] and row['propulsion_speed'] == 0
                    for row in trace
                )
                check(f'{name}: retry stays stopped for 120 frames', motionless,
                      settled=settled)
                report['scenarios'].append({'name': name, 'before': before,
                                            'after': after, 'idle_trace': trace})
                game.shot(args.out / f'retry-{name}.png')

            # A complete unassisted run from the retry location must still work.
            game.load_state(initial)
            game.run(16, ['SELECT', 'START'])
            game.run(32)
            active_frames, completed, previous = 0, False, vehicle_state(game)
            drive_log = []
            for frame in range(720):
                game.run(1, ['A'])
                current = vehicle_state(game)
                if current['loop'] == 1:
                    active_frames += 1
                    if active_frames == 1:
                        game.shot(args.out / '02-loop-entry.png')
                    if 2600 <= current['phase'] <= 3600:
                        game.shot(args.out / '03-loop-inverted.png')
                if previous['loop'] == 1 and current['loop'] != 1 and current['phase'] >= 6144:
                    completed = True
                    game.shot(args.out / '04-loop-complete.png')
                if frame % 4 == 0:
                    drive_log.append({'frame': frame, **current})
                previous = current
                if completed and current['x'] >= 62 * 2048 and current['roll'] == 0:
                    break
            report['drive_from_retry'] = drive_log
            final = vehicle_state(game)
            check('A drives from retry through a complete loop', completed and active_frames > 0,
                  active_video_frames=active_frames, final=final)
            check('Loop finish restores an upright view', completed and final['roll'] == 0)
            check('Real vehicle model stays unchanged', final['descriptor'] == descriptor)
            game.shot(args.out / '05-driving-after-loop.png')
        except Exception as error:
            report['error'] = f'{type(error).__name__}: {error}'
            check('Scenario completed', False, error=report['error'])
            if game.frame is not None:
                game.shot(args.out / 'error.png')
        finally:
            report['passed'] = bool(report['checks']) and all(c['passed'] for c in report['checks'])
            (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
