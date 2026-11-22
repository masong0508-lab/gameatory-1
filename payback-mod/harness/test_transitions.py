#!/usr/bin/env python3
"""Exercise Arwing transitions and level reloads with real game button input.

The only setup edit moves the on-foot player next to an existing parked Arwing.
Vehicle entry, flight, landing, exit, pause, and menu navigation use normal keys.
An emulator checkpoint separates the flight and level-reload scenarios; this is
not a test of the game's own save format. No ROM is bundled with this harness.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

from retro import Emu
from drive_lanes import BOOT

ARWING = 0x08354EF0
ENTITY_TABLE = 0x03000C60
LAST_ENTITY = 0x0300000C
CONTROLLED = 0x02001DB8
GRID = 0x03000D60
SPACE = 0x0203FFFA
NEO = 0x0203FFFB
CURSOR_INDEX = 0x0203FFDC
FREE_ROAM = 0x02001D39
PLAYER_COPIES = (0x02008DF8, 0x02009398, 0x02009478, 0x02009484)


def actor(game):
    last = game.s16(LAST_ENTITY)
    index = game.s16(CONTROLLED)
    if not 0 <= index <= last <= 31:
        raise RuntimeError(f'invalid controlled entity: index={index}, last={last}')
    address = game.u32(ENTITY_TABLE + 4 * index)
    if address & 3 or not 0x02000000 <= address <= 0x0203FE98:
        raise RuntimeError(f'invalid entity pointer: 0x{address:08x}')
    return {
        'index': index,
        'last_index': last,
        'address': address,
        'descriptor': game.u32(address + 0x1C),
        'x': game.r32(address + 4) / 2048,
        'y': game.r32(address + 8) / 2048,
        'z': game.s16(address + 0xC),
        'heading': game.s16(address + 0x12),
    }


def wait_for(game, predicate, frames=900):
    for _ in range((frames + 7) // 8):
        if predicate():
            return True
        game.run(8)
    return bool(predicate())


def quit_to_menu(game):
    game.press('START', hold=16, after=120)
    game.press('DOWN', hold=16, after=30)
    game.press('A', hold=16, after=150)
    # Confirmation defaults to No. LEFT chooses Yes.
    game.press('LEFT', hold=16, after=30)
    game.press('A', hold=16, after=300)


def start_level(game, *, free_roam):
    if free_roam:
        game.press('DOWN', hold=16, after=30)
        game.press('DOWN', hold=16, after=30)
    game.press('A', hold=16, after=200)  # Game menu -> choose level.
    game.press('A', hold=16, after=600)
    for _ in range(3):
        game.press('A', hold=16, after=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--symbols', type=Path,
                        help='editor.json from the SAME ROM build; enables full map checks')
    parser.add_argument('--source', type=Path,
                        help='optional original user ROM, recorded by checksum only')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rom_bytes = args.rom.read_bytes()
    report = {
        'rom_sha256': hashlib.sha256(rom_bytes).hexdigest(),
        'output_sha1': hashlib.sha1(rom_bytes).hexdigest(),
        'setup': 'Player relocated beside an existing parked stadium Arwing; all actions use game buttons.',
        'native_game_save_load': 'Not tested. Rampage pause offers Return/Quit; checkpoint checks use emulator serialization.',
        'checks': [],
        'events': [],
    }
    if args.source:
        report['source_sha1'] = hashlib.sha1(args.source.read_bytes()).hexdigest()
    symbols = json.loads(args.symbols.read_text()) if args.symbols else None

    def check(name, passed, **details):
        report['checks'].append({'name': name, 'passed': bool(passed), **details})
        print(f'{"PASS" if passed else "FAIL"}: {name}', flush=True)

    with Emu('gba', args.rom) as game:
        def event(name):
            state = {
                'name': name,
                'frame': game.frames,
                **actor(game),
                'space': game.read(SPACE, 1)[0],
                'neo': game.read(NEO, 1)[0],
                'free_roam': game.read(FREE_ROAM, 1)[0],
                'grid': game.u32(GRID),
                'cursor_index': game.u32(CURSOR_INDEX),
            }
            report['events'].append(state)
            game.shot(args.out / f'{name}.png')
            return state

        def map_check(name, slot):
            if not symbols:
                return
            table = symbols['maps']
            expected_address = game.u32(table + slot * 4)
            if not 0x08000000 <= expected_address <= 0x09FF0000:
                raise RuntimeError('editor.json does not match this ROM: invalid map table')
            expected = struct.unpack('<16384I', game.read(expected_address, 65536))
            actual = struct.unpack('<16384I', game.read(game.u32(GRID), 65536))
            mismatches = [i for i, (a, b) in enumerate(zip(actual, expected))
                          if a >> 24 != 2 and a != b]
            check(name, not mismatches, mismatch_count=len(mismatches),
                  first_mismatches=mismatches[:12])

        try:
            for frames, button in BOOT:
                game.run(frames, [button] if button else [])
            initial = event('01-free-roam')
            check('Free roam starts in Neo', initial['free_roam'] == 1
                  and initial['neo'] == 1 and initial['space'] == 0)
            map_check('Neo grid matches its ROM map', 2)

            arwings = []
            for index in range(game.s16(LAST_ENTITY) + 1):
                address = game.u32(ENTITY_TABLE + 4 * index)
                if game.u32(address + 0x1C) == ARWING:
                    x, y = game.r32(address + 4), game.r32(address + 8)
                    arwings.append((address, x, y))
            if not arwings:
                raise RuntimeError('no parked Arwing found')
            vehicle, x, y = min(arwings, key=lambda h: (h[1] / 2048 - 57) ** 2
                               + (h[2] / 2048 - 34) ** 2)
            for address in PLAYER_COPIES:
                game.write32(address, x + 1200)
                game.write32(address + 4, y)
            game.write16(actor(game)['address'] + 0xC, game.u16(vehicle + 0xC))
            game.run(3)
            event('02-beside-arwing')

            # The walking-to-door animation keeps progressing while SELECT is
            # held, exercising cursor cleanup across the actual map switch.
            game.run(16, ['L'])
            game.run(160, ['SELECT'])
            entered = wait_for(game, lambda: actor(game)['descriptor'] == ARWING, 600)
            game.run(32)
            entry = event('03-entered-space')
            check('L enters the Arwing and switches to space', entered
                  and entry['space'] == 1 and entry['neo'] == 1)
            check('Cursor clears after entering space', entry['cursor_index'] == 0)
            map_check('Space grid has no stale city cursor cells', 0)
            if not entered:
                raise RuntimeError('could not enter the parked Arwing')

            game.press('L', hold=16, after=300)
            airborne = event('04-airborne')
            check('L takes off', airborne['descriptor'] == ARWING
                  and abs(airborne['z'] - entry['z']) > 1000)
            game.run(60, ['A'])
            flying = event('05-flying')
            distance = math.hypot(flying['x'] - airborne['x'], flying['y'] - airborne['y'])
            check('A flies the Arwing', distance > 0.2, distance_cells=distance)

            game.press('START', hold=16, after=120)
            paused = event('06-paused')
            pose = (paused['x'], paused['y'], paused['z'])
            game.run(120)
            still = actor(game)
            check('Pause holds vehicle position', pose == (still['x'], still['y'], still['z']))
            game.press('A', hold=16, after=120)
            resumed = event('07-resumed')
            check('Return to game resumes flight', pose != (resumed['x'], resumed['y'], resumed['z'])
                  and resumed['space'] == 1)

            checkpoint = game.save_state()
            game.run(40)
            game.load_state(checkpoint)
            restored = actor(game)
            check('Emulator checkpoint restores flight state',
                  (resumed['x'], resumed['y'], resumed['z'])
                  == (restored['x'], restored['y'], restored['z']))

            game.run(180, ['B'])
            game.press('L', hold=16, after=900)
            landed = event('08-landed')
            game.run(120)
            settled = actor(game)
            check('L lands and settles the Arwing', landed['descriptor'] == ARWING
                  and abs(settled['z'] - landed['z']) <= 32)
            space_checkpoint = game.save_state()
            game.press('L', hold=16, after=300)
            exited = event('09-exited-to-city')
            check('L exits to a player entity', exited['descriptor'] != ARWING)
            check('Exiting returns to Neo', exited['space'] == 0 and exited['neo'] == 1)
            check('Player remains within level bounds', 0 < exited['x'] < 128
                  and 0 < exited['y'] < 128)
            map_check('Returned Neo grid matches its ROM map', 2)
            position = (exited['x'], exited['y'])
            game.run(120, ['A'])
            walked = event('10-walking-after-exit')
            movement = math.hypot(walked['x'] - position[0], walked['y'] - position[1])
            if movement < 0.2:
                game.run(120, ['B'])
                walked = actor(game)
                movement = math.hypot(walked['x'] - position[0], walked['y'] - position[1])
            check('Player can walk after exit', movement > 0.2, distance_cells=movement)

            # Independent reload case: quit while still in space. The original
            # game reuses both the grid pointer and the mod's top-of-RAM bytes.
            game.load_state(space_checkpoint)
            game.run(1)
            quit_to_menu(game)
            report['scratch_at_menu'] = game.read(0x0203FFC0, 64).hex()
            game.shot(args.out / '11-quit-to-game-menu.png')
            start_level(game, free_roam=False)
            story = event('12-reloaded-story')
            check('Story reload clears space/Neo state', story['free_roam'] == 0
                  and story['space'] == 0 and story['neo'] == 0)
            map_check('Story reload preserves the story city', 1)
            check('Story reload clears build cursor', story['cursor_index'] == 0)

            quit_to_menu(game)
            start_level(game, free_roam=True)
            free = event('13-reloaded-free-roam')
            check('Free-roam reload enters Neo again', free['free_roam'] == 1
                  and free['space'] == 0 and free['neo'] == 1)
            map_check('Free-roam reload matches Neo', 2)
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
