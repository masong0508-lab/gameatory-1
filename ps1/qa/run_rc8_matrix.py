#!/usr/bin/env python3
"""ONE COMMAND for PS1 release-candidate QA with private disc+matching nm symbols.

Use a fresh PRIVATE out directory. No private outputs, core, ROM, disc, card,
movie, screenshot or game dialogue are ever committed or uploaded to GitHub.

  python3 ps1/qa/run_rc8_matrix.py --disc /private/rc8.cue \
      --syms /private/payback_rc8.nm.txt --out /private/rc8-matrix \
      --cores /private/kit/cores --system /private/kit/system \
      [--gba-rom '/private/Payback (Europe) (En,Fr,De,Es,It).gba']

The run is deliberately fail-closed, and records uncovered natural missions,
audio listening, unobserved vehicle descriptors and Android DuckStation as
NOT CERTIFIED. The 11-map R2 viewer is NOT natural map progression.
Requires the accepted run_all.sh enhancements from PRs #8 and #11.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
RIG=REPO/'ps1'/'rig'
RECOMMENDED=(
    'swanstation_CPU_Overclock=400',
    'swanstation_CDROM_ReadSpeedup=10',
    'swanstation_CDROM_SeekSpeedup=0',
)
GAPS=(
    'naturally_playable_guest_maps_all_11',
    'every_gba_vehicle_descriptor_on_every_map',
    'phone_pickups_and_completed_missions',
    'audible_cd_radio',
    'DuckStation_Android_owner_acceptance',
)


def opts_argv(core, recommended):
    if core == 'swanstation' and recommended:
        return [word for setting in RECOMMENDED for word in ('--opt', setting)]
    return []


def session_command(script, disc, syms, result, *, core='swanstation', recommended=False, extra=()):
    launch=[sys.executable]
    if core in ('swanstation','beetle'):
        launch.append(str(RIG/'tools'/'ob_session.py'))
    launch.append(str(script))
    return (launch + ['--disc',str(disc),'--syms',str(syms),'--core',core,
                      '--out',str(result), '--state-dir',str(result.parent/'states')]
            + opts_argv(core,recommended) + list(extra))


def jobs(disc,syms,out,*,stock=True,gba_rom=None,soak_frames=108000,soak_game_seconds=None,frames_per_map=1200):
    """Pure job construction, safe to inspect/test without a disc or core."""
    # Full acceptance: 108,000 console frames AND 600 guest seconds. Slices
    # scale the clock target proportionally instead of inheriting ten minutes.
    min_game_seconds = (600.0 * soak_frames / 108000.0
                        if soak_game_seconds is None else soak_game_seconds)
    planned=[]
    def add(name,cmd,profile,variables=None):
        planned.append(dict(name=name,command=cmd,profile=profile,env=variables or {}))
    add('swan_recommended_runner',
        ['sh',str(RIG/'run_all.sh'),str(disc),str(out/'recommended'/'rig'),str(syms),'swanstation'],
        'recommended', {'RIG_OPTS':' '.join(RECOMMENDED), 'ONLY':'a b c d e g h j'})
    add('swan_recommended_30min_console_soak',
        session_command(HERE/'console_soak.py',disc,syms,out/'recommended'/'console_soak',
                        core='swanstation',recommended=True,
                        extra=('--console-frames',str(soak_frames),
                               '--min-game-seconds',str(min_game_seconds))),
        'recommended')
    add('swan_recommended_11map_flicker',
        session_command(HERE/'map_flicker.py',disc,syms,out/'recommended'/'map_flicker',
                        core='swanstation',recommended=True,
                        extra=('--frames-per-map',str(frames_per_map))), 'recommended')
    if stock:
        add('swan_stock_runner',
            ['sh',str(RIG/'run_all.sh'),str(disc),str(out/'stock'/'swan_runner'),str(syms),'swanstation'],
            'stock', {'RIG_OPTS':'','ONLY':'a b c d e h'})
        add('swan_stock_11map_flicker',
            session_command(HERE/'map_flicker.py',disc,syms,out/'stock'/'map_flicker',
                            core='swanstation',
                            extra=('--frames-per-map',str(frames_per_map))), 'stock')
        add('beetle_stock_runner',
            ['sh',str(RIG/'run_all.sh'),str(disc),str(out/'stock'/'beetle_runner'),str(syms),'beetle'],
            'stock', {'RIG_OPTS':'','ONLY':'b c e'})
    if gba_rom is not None:
        add('original_gba_mgba_vehicle_census',
            [sys.executable,str(REPO/'payback-mod'/'harness'/'vehicle_matrix.py'),
             str(gba_rom),'--out',str(out/'gba_vehicles.json'),
             '--survey-frames','6000','--require-all'],'mGBA_original')
    return planned


def private_target(path):
    target=path.expanduser().resolve()
    return not target.is_relative_to(REPO)


def normalize_private_paths(args):
    """Make paths absolute *before* planning subprocesses with cwd=REPO.

    A relative OUT that was safe against the user's current directory could
    otherwise be reinterpreted under the public Git checkout by child jobs.
    """
    for key in ('disc', 'syms', 'out', 'cores', 'system', 'gba_rom'):
        value = getattr(args, key, None)
        if value is not None:
            setattr(args, key, Path(value).expanduser().resolve())
    return args


SYMBOLS_REQUIRED = ('g_flips', 'g_pres', 'sf3_map_cur', 'st3_render')


def symbol_preflight(exe_match, names):
    """Reject a provably wrong ELF and missing named rc8 runtime counters.

    A text .nm listing cannot prove the image hash matches the packed EXE;
    retain that explicit caveat instead of silently claiming verification.
    """
    if exe_match is False:
        raise ValueError('ELF symbol file does not match the packed disc PSX.EXE; '
                         'use the matching rc8 nm.txt listing instead')
    missing = sorted(set(SYMBOLS_REQUIRED) - set(names))
    if missing:
        raise ValueError('required rc8 symbols missing: ' + ', '.join(missing))


def inspect_disc_symbols(disc, syms):
    """Read the disc's PSX.EXE and test symbol provenance BEFORE any emulator job."""
    if str(RIG) not in sys.path:
        sys.path.insert(0, str(RIG))
    from ps1game import Disc, Game, load_symbols
    iso = Disc(str(disc))
    try:
        if 'PSX.EXE' not in iso.files:
            raise ValueError('disc has no PSX.EXE')
        symbols = load_symbols(str(syms))
        match = Game._syms_match(SimpleNamespace(disc=iso, syms_path=str(syms)))
        symbol_preflight(match, symbols)
        return dict(exe_sha1=iso.sha1('PSX.EXE'),
                    elf_matches_disc=match,
                    symbol_list_fingerprint_verified=match is True,
                    symbol_format='ELF' if syms.read_bytes()[:4] == b'\x7fELF' else 'text')
    finally:
        iso.f.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--syms',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--cores',type=Path,help='private directory with libretro cores; defaults to RIG_CORES')
    p.add_argument('--system',type=Path,help='private openboot scph55xx; defaults to RIG_SYSTEM')
    p.add_argument('--gba-rom',type=Path,help='private untouched European original; optional mGBA vehicle survey')
    p.add_argument('--soak-frames',type=int,default=108000,help='minimum emulated frames, default ~30m')
    p.add_argument('--soak-game-seconds',type=float,default=None,
                   help='override guest-clock target; default scales 600s at 108000 frames')
    p.add_argument('--frames-per-map',type=int,default=1200,help='per-map flicker scan length')
    p.add_argument('--only',action='append',default=[],help='run only this exact job name; may repeat')
    p.add_argument('--skip-stock',action='store_true',help='skip stock/Beetle comparisons (not release acceptance)')
    p.add_argument('--dry-run',action='store_true',help='print planned job NAMES only; no emulator or file writes')
    args=normalize_private_paths(p.parse_args(argv))
    if args.soak_frames < 1 or args.frames_per_map < 1:
        p.error('--soak-frames and --frames-per-map must be positive')
    if args.soak_game_seconds is not None and not (0 < args.soak_game_seconds < float('inf')):
        p.error('--soak-game-seconds must be finite and positive')
    if not private_target(args.out):
        p.error('results MUST be outside the public repository')
    todo=jobs(args.disc,args.syms,args.out,stock=not args.skip_stock,
              gba_rom=args.gba_rom,soak_frames=args.soak_frames,
              soak_game_seconds=args.soak_game_seconds,
              frames_per_map=args.frames_per_map)
    if args.only:
        valid={job['name'] for job in todo}
        unknown=sorted(set(args.only)-valid)
        if unknown:
            p.error('unknown or disabled --only jobs: '+', '.join(unknown))
        todo=[job for job in todo if job['name'] in set(args.only)]
    if args.dry_run:
        print(json.dumps({'status':'DRY_RUN_NO_EMULATION','job_names':[j['name'] for j in todo],
                          'recommended_options':RECOMMENDED,'not_certified':GAPS},indent=2))
        return 0
    if not args.disc.is_file() or not args.syms.is_file():
        p.error('private disc CUE/ISO or matching symbol listing is missing')
    if args.out.exists():
        p.error('output directory must be fresh; refuse stale passing result.json or save states')
    run_all=RIG/'run_all.sh'
    if not run_all.is_file() or 'RIG_OPTS' not in run_all.read_text() or 'SKIP b_assist_path' not in run_all.read_text():
        p.error('first merge tested PRs #8 and #11; the installed run_all.sh lacks required gates')
    env=dict(os.environ)
    if args.cores is not None:
        env['RIG_CORES']=str(args.cores.resolve())
    if args.system is not None:
        env['RIG_SYSTEM']=str(args.system.resolve())
    for key in ('RIG_CORES','RIG_SYSTEM'):
        if not env.get(key) or not Path(env[key]).is_dir():
            p.error(f'{key} must name a private installed directory')
    if args.gba_rom is not None and (not env.get('MGBA_CORE') or not Path(env['MGBA_CORE']).is_file()):
        p.error('mGBA vehicle survey selected but MGBA_CORE is absent; cannot fake GBA play results')
    try:
        preflight = inspect_disc_symbols(args.disc, args.syms)
    except (OSError, ValueError, RuntimeError) as exc:
        p.error('disc/symbol preflight failed BEFORE emulator launch: '+str(exc))
    args.out.mkdir(parents=True,exist_ok=False)
    outcomes=[]
    # Keep test runs from leaving ignored Python bytecode in the checkout.
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    for job in todo:
        local=dict(env,**job['env'])
        logpath=args.out/(job['name']+'.log')
        ts=time.monotonic()
        print('RUN',job['name'],flush=True)
        with logpath.open('w',encoding='utf-8') as log:
            proc=subprocess.run(job['command'],env=local,stdout=log,stderr=subprocess.STDOUT,cwd=REPO,check=False)
        outcome=dict(name=job['name'],profile=job['profile'],exit_code=proc.returncode,
                     wall_seconds=round(time.monotonic()-ts,2),
                     status='PASS_TOOL' if proc.returncode==0 else 'FAIL_TOOL')
        outcomes.append(outcome)
        print('RESULT',outcome['name'],outcome['status'],f"exit {outcome['exit_code']}",flush=True)
    missing=list(GAPS)
    if args.gba_rom is None:
        missing.append('original_GBA_mGBA_vehicle_reference_not_run')
    summary=dict(schema=1,disc_version='supplied_ps1_candidate_preflighted',
                 private_executable_preflight=preflight,
                 options={'recommended':list(RECOMMENDED),'stock':not args.skip_stock},
                 jobs=outcomes,has_failures=any(j['exit_code']!=0 for j in outcomes),
                 coverage_qualifiers=missing,
                 full_release_certified=False)
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('QA jobs:',len(outcomes),'failures:',sum(j['exit_code']!=0 for j in outcomes),
          'full_release_certified=FALSE; see private summary.json')
    return 1 if summary['has_failures'] else 0

if __name__=='__main__':
    raise SystemExit(main())