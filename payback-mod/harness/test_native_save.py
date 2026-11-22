#!/usr/bin/env python3
"""Verify Payback native EEPROM saves across fresh emulator processes.

Creates a profile through game menus, performs a real carjacking with L, quits
through the game's confirmation dialog, and cold-boots the exported save. Both
original and mod ROMs write saves, then read each other's saves. Only libretro
memory kind 0 is persisted. Emulator savestates are deliberately prohibited.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from retro import Emu
from test_retry import boot_real_car

# Observed native profile fields: the menu name and the carjacking total. The
# profile total is committed on Quit after an actual L carjacking, and restores
# from EEPROM on boot. The current-run counter is separate from this total.
PROFILE_NAME = 0x02000014
CARJACKINGS = 0x02002698


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def profile(game):
    name = game.read(PROFILE_NAME, 24).split(b'\0', 1)[0].decode('ascii')
    return {'name': name, 'carjackings': game.u32(CARJACKINGS)}


def no_savestates(*_args, **_kwargs):
    raise RuntimeError('native-save verification must never use emulator savestates')


def boot_saved_profile(game, folder):
    game.run(300)
    game.shot(folder / '01-cold-boot.png')
    for button in ('START', 'START', 'A', 'A'):
        game.press(button, hold=16, after=200)
    game.shot(folder / '02-select-saved-profile.png')
    game.press('A', hold=16, after=200)
    game.shot(folder / '03-loaded-profile.png')


def quit_game(game):
    game.press('START', hold=16, after=120)
    game.press('DOWN', hold=16, after=30)
    game.press('A', hold=16, after=150)
    game.press('LEFT', hold=16, after=30)  # Yes; the dialog defaults to No.
    game.press('A', hold=16, after=300)


def worker(args):
    folder = args.result.parent
    folder.mkdir(parents=True, exist_ok=True)
    before_disk = args.save.read_bytes() if args.save.exists() else None
    result = {'pid': os.getpid(), 'action': args.worker,
              'rom_sha256': checksum(args.rom.read_bytes()), 'save_path': str(args.save)}
    with Emu('gba', args.rom, save_path=args.save) as game:
        game.save_state = no_savestates
        game.load_state = no_savestates
        result['loaded_bytes'] = game.loaded_save_bytes
        if args.worker == 'write':
            if before_disk is not None:
                raise RuntimeError('write worker requires a fresh save path')
            result['initial_blank'] = all(value == 0xFF for value in game.mem(0))
            attempts = []
            entered = boot_real_car(game, attempts)
            created = game.mem(0)
            result['profile_created'] = profile(game)
            result['entry_attempts'] = attempts
            result['real_vehicle_descriptor'] = entered['descriptor']
            result['created_save_bytes'] = len(created)
            result['created_save_sha256'] = checksum(created)
            created_path = folder / 'profile-before-quit.srm'
            created_path.write_bytes(created)
            result['created_save_path'] = str(created_path)
            game.shot(folder / '01-real-carjacking.png')
            quit_game(game)
            result['after_quit_profile'] = profile(game)
            result['quit_changed_native_save'] = game.mem(0) != created
            result['quit_save_sha256'] = checksum(game.mem(0))
            result['game_acknowledged_carjacking'] = b'You committed 1 carjacking' in game.mem(2)
            game.shot(folder / '02-after-quit.png')
            game.press('UP', hold=16, after=30)  # Game Menu wraps to End game.
            game.press('A', hold=16, after=240)
            game.shot(folder / '03-end-game.png')
            result['end_game_preserved_save'] = checksum(game.mem(0)) == result['quit_save_sha256']
            result['native_bytes_before_close'] = len(game.mem(0))
        elif args.worker == 'read':
            if before_disk is None:
                raise RuntimeError('read worker requires an existing native save')
            boot_saved_profile(game, folder)
            result['restored_profile'] = profile(game)
            result['native_bytes_after_boot'] = len(game.mem(0))
            result['memory_equals_disk'] = game.mem(0) == before_disk
        elif args.worker == 'close':
            pass
        elif args.worker == 'one-frame':
            game.run(1)
        else:
            raise RuntimeError(f'unknown worker {args.worker}')
    after_disk = args.save.read_bytes() if args.save.exists() else None
    result['disk_bytes_after_close'] = len(after_disk) if after_disk is not None else 0
    result['disk_sha256_after_close'] = checksum(after_disk) if after_disk is not None else None
    result['disk_unchanged'] = after_disk == before_disk
    args.result.write_text(json.dumps(result, indent=2) + '\n')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True, help='modified Payback ROM')
    parser.add_argument('--original', type=Path, help='original user ROM for compatibility checks')
    parser.add_argument('--out', type=Path, help='new or empty results directory')
    parser.add_argument('--worker', choices=('write', 'read', 'close', 'one-frame'),
                        help=argparse.SUPPRESS)
    parser.add_argument('--save', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--result', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    if args.original is None or args.out is None:
        parser.error('--original and --out are required')
    if args.out.exists() and any(args.out.iterdir()):
        parser.error('--out must be new or empty; existing native saves will not be overwritten')
    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        'method': 'Native EEPROM memory kind0; separate OS process for every writer, cold reader, and close guard; no emulator savestates.',
        'limitations': 'Checks native profiles and carjacking statistics saved on Quit. Does not claim mid-level world resume or live builder-edit persistence.',
        'rom_sha256': checksum(args.rom.read_bytes()),
        'rom_sha1': hashlib.sha1(args.rom.read_bytes()).hexdigest(),
        'source_sha1': hashlib.sha1(args.original.read_bytes()).hexdigest(),
        'checks': [], 'workers': {},
    }

    def check(name, passed, **details):
        report['checks'].append({'name': name, 'passed': bool(passed), **details})
        print(f'{"PASS" if passed else "FAIL"}: {name}', flush=True)

    def run(name, action, rom, save_source=None):
        folder = args.out / name
        folder.mkdir()
        save = folder / 'native.srm'
        if save_source is not None:
            shutil.copyfile(save_source, save)
        result = folder / 'worker.json'
        command = [sys.executable, str(Path(__file__).resolve()), '--worker', action,
                   '--rom', str(rom.resolve()), '--save', str(save.resolve()),
                   '--result', str(result.resolve())]
        process = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (folder / 'worker.log').write_text(process.stdout + process.stderr)
        if process.returncode:
            raise RuntimeError(f'{name} exited {process.returncode}: {process.stderr[-2000:]}')
        value = json.loads(result.read_text())
        report['workers'][name] = value
        return value, save

    try:
        writes = {}
        for label, rom in (('mod', args.rom), ('original', args.original)):
            value, path = run(f'{label}-write', 'write', rom)
            writes[label] = (value, path)
            check(f'{label}: native EEPROM starts blank', value['initial_blank'])
            check(f'{label}: game creates a native profile',
                  value['created_save_bytes'] == 512 and bool(value['profile_created']['name']))
            check(f'{label}: actual carjacking is recorded',
                  value['profile_created']['carjackings'] == 0
                  and value['after_quit_profile']['carjackings'] == 1
                  and value['game_acknowledged_carjacking'])
            check(f'{label}: Quit writes changed EEPROM', value['quit_changed_native_save'])
            check(f'{label}: End game preserves quit save', value['end_game_preserved_save'])
            check(f'{label}: close persists exactly512 native bytes', value['disk_bytes_after_close'] == 512
                  and value['disk_sha256_after_close'] == value['quit_save_sha256'])

            # The carjacking happened in the current run, but the freshly-created
            # profile does not receive the total until the game's Quit path.
            created, _ = run(f'{label}-created-profile-coldboot', 'read', rom,
                             Path(value['created_save_path']))
            check(f'{label}: newly created profile survives a fresh process',
                  created['restored_profile']['name'] == value['profile_created']['name']
                  and created['restored_profile']['carjackings'] == 0)
            check(f'{label}: profile-only coldboot preserves EEPROM bytes',
                  created['memory_equals_disk'] and created['disk_unchanged'])

        for writer, reader, rom in (('mod', 'mod', args.rom),
                                     ('mod', 'original', args.original),
                                     ('original', 'original', args.original),
                                     ('original', 'mod', args.rom)):
            written, save = writes[writer]
            loaded, _ = run(f'{writer}-save-in-{reader}', 'read', rom, save)
            check(f'{writer} save -> {reader}: profile and quit statistics survive coldboot',
                  loaded['loaded_bytes'] == 512
                  and loaded['native_bytes_after_boot'] == 512
                  and loaded['restored_profile'] == written['after_quit_profile'])
            check(f'{writer} save -> {reader}: EEPROM remains byte-identical',
                  loaded['memory_equals_disk'] and loaded['disk_unchanged'])

        for action in ('close', 'one-frame'):
            guarded, _ = run(f'existing-save-{action}', action, args.rom, writes['mod'][1])
            check(f'{action}: early exit preserves the512-byte existing save',
                  guarded['disk_unchanged'] and guarded['disk_bytes_after_close'] == 512)
        blank, blank_path = run('blank-immediate-close', 'close', args.rom)
        check('Immediate close does not create an oversized blank save',
              blank['disk_bytes_after_close'] == 0 and not blank_path.exists())
        pids = [item['pid'] for item in report['workers'].values()]
        check('All native-save stages used separate fresh processes', len(set(pids)) == len(pids))
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        check('Native save suite completed', False, error=report['error'])
    report['passed'] = bool(report['checks']) and all(item['passed'] for item in report['checks'])
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
