"""ROM-free and network-free orchestration regressions. No game data."""
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from types import SimpleNamespace
from unittest.mock import patch
import unittest

SRC=Path(__file__).with_name('run_rc8_matrix.py')
spec=importlib.util.spec_from_file_location('rc8',SRC)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class RetestTests(unittest.TestCase):
    def setUp(self):
        self.disc=Path('/private/rc8 disc.cue')
        self.syms=Path('/private/rc8 symbols.elf')
        self.out=Path('/private/out')

    def test_default_all_emulator_sections(self):
        plan=m.jobs(self.disc,self.syms,self.out)
        names=[x['name'] for x in plan]
        self.assertEqual(len(names),6)
        self.assertIn('swan_recommended_runner',names)
        self.assertIn('swan_recommended_30min_console_soak',names)
        self.assertIn('swan_recommended_11map_flicker',names)
        self.assertIn('beetle_stock_runner',names)
        self.assertIn('swan_stock_11map_flicker',names)
        self.assertIn('e',plan[0]['env']['ONLY'])
        self.assertNotIn(' f ', ' '+plan[0]['env']['ONLY']+' ')

    def test_recommended_settings_reach_all_accurate_sessions(self):
        plan=m.jobs(self.disc,self.syms,self.out)
        self.assertEqual(plan[0]['env']['RIG_OPTS'],' '.join(m.RECOMMENDED))
        for j in plan[1:3]:
            opts=m.opts_argv('swanstation',True)
            self.assertTrue(all(s in j['command'] for s in m.RECOMMENDED))
            self.assertTrue(j['command'][1].endswith('tools/ob_session.py'))
            self.assertEqual([j['command'][i+1] for i,x in enumerate(j['command'][:-1]) if x=='--opt'],list(m.RECOMMENDED))
        self.assertFalse(m.opts_argv('beetle',False))

    def test_console_soak_frames_are_explicit(self):
        j=m.jobs(self.disc,self.syms,self.out,soak_frames=111111)[1]
        self.assertEqual(j['command'][j['command'].index('--console-frames')+1],'111111')

    def test_soak_slice_scales_game_clock_without_weakening_default(self):
        full=m.jobs(self.disc,self.syms,self.out)[1]['command']
        short=m.jobs(self.disc,self.syms,self.out,soak_frames=540)[1]['command']
        custom=m.jobs(self.disc,self.syms,self.out,soak_frames=540,
                      soak_game_seconds=1.25)[1]['command']
        def clock_arg(cmd):
            return float(cmd[cmd.index('--min-game-seconds')+1])
        self.assertEqual(clock_arg(full),600.0)
        self.assertEqual(clock_arg(short),3.0)
        self.assertEqual(clock_arg(custom),1.25)

    def test_map_flicker_runpy_from_ob_session_style_path(self):
        # ob_session runs a script via runpy, without adding script's dir to sys.path.
        # Isolated Python removes any accidental unittest/checkout path that masks it.
        source=m.HERE/'map_flicker.py'
        code=(
            "import runpy,sys,types\\n"
            "sys.modules['payback']=types.ModuleType('payback')\\n"
            "assert not any(p.endswith('/ps1/qa') for p in sys.path)\\n"
            "ns=runpy.run_path(sys.argv[1],run_name='ob_session_import_probe')\\n"
            "assert callable(ns['display_step'])\\n"
        )
        done=subprocess.run([sys.executable,'-I','-B','-c',code,str(source)],
                            cwd=m.REPO,text=True,capture_output=True,check=False)
        self.assertEqual(done.returncode,0,done.stderr)

    def test_mgba_addition_is_optional_but_not_a_fake_pass(self):
        plan=m.jobs(self.disc,self.syms,self.out,gba_rom=Path('/private/original.gba'))
        self.assertEqual(plan[-1]['profile'],'mGBA_original')
        self.assertIn('--require-all',plan[-1]['command'])
        self.assertEqual(len(plan),7)

    def test_stock_can_be_skipped_explicitly(self):
        plan=m.jobs(self.disc,self.syms,self.out,stock=False)
        self.assertEqual(len(plan),3)
        self.assertTrue(all(x['profile']=='recommended' for x in plan))

    def test_rc8_preflight_rejects_packed_elf_and_missing_flip_counter(self):
        names = set(m.SYMBOLS_REQUIRED)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            m.symbol_preflight(False, names)
        with self.assertRaisesRegex(ValueError, 'g_flips'):
            m.symbol_preflight(None, names - {'g_flips'})
        m.symbol_preflight(None, names)  # matching .nm text; cannot prove EXE digest
        m.symbol_preflight(True, names)  # unpacked and byte-matching ELF

    def test_private_relative_paths_are_canonical_before_subprocesses(self):
        args = SimpleNamespace(disc=Path('private-input.cue'),
                               syms=Path('private-symbols.nm.txt'),
                               out=Path('ps1/qa/unsafe-results'),
                               cores=None,system=None,gba_rom=None)
        m.normalize_private_paths(args)
        self.assertTrue(all(p.is_absolute() for p in (args.disc,args.syms,args.out)))
        self.assertEqual(args.out, (m.REPO/'ps1/qa/unsafe-results').resolve())
        self.assertFalse(m.private_target(args.out))

    def test_flicker_slice_length_reaches_recommended_and_stock(self):
        plan = m.jobs(self.disc,self.syms,self.out,frames_per_map=423)
        for j in plan:
            if '11map_flicker' in j['name']:
                argv=j['command']
                self.assertEqual(argv[argv.index('--frames-per-map')+1], '423')
        self.assertEqual(len([j for j in plan if '11map_flicker' in j['name']]),2)

    def test_only_slice_dry_run_lists_one_job_without_files(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'test-rc8-once'
            capture=io.StringIO()
            with redirect_stdout(capture):
                status=m.main(['--disc',str(self.disc),'--syms',str(self.syms),
                               '--out',str(out),'--only','swan_recommended_11map_flicker',
                               '--frames-per-map','423','--dry-run'])
            self.assertEqual(status,0)
            obj=json.loads(capture.getvalue())
            self.assertEqual(obj['job_names'],['swan_recommended_11map_flicker'])
            self.assertFalse(out.exists())
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    m.main(['--disc',str(self.disc),'--syms',str(self.syms),
                            '--out',str(out),'--only','not_a_real_session','--dry-run'])
            self.assertEqual(ctx.exception.code,2)

    def test_reject_repo_relative_result_path_without_creating_files(self):
        path=m.REPO/'ps1/qa/do_not_create_rc8_test_private'
        self.assertFalse(path.exists())
        with patch('os.getcwd', return_value=str(m.REPO)):
            # The caller's cwd is already the repository in GitHub CI.
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    m.main(['--disc',str(self.disc),'--syms',str(self.syms),
                            '--out',str(path),'--dry-run'])
        self.assertEqual(ctx.exception.code,2)
        self.assertFalse(path.exists())

    def test_private_guard_and_dry_run_no_files(self):
        self.assertFalse(m.private_target(m.REPO/'ps1'/'qa'/'results'))
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'future_rc8'
            b=io.StringIO()
            with redirect_stdout(b):
                status=m.main(['--disc',str(self.disc),'--syms',str(self.syms),
                               '--out',str(out),'--dry-run'])
            self.assertEqual(status,0)
            self.assertIn('DRY_RUN_NO_EMULATION',b.getvalue())
            self.assertFalse(out.exists())
            self.assertIn('DuckStation_Android_owner_acceptance',b.getvalue())

if __name__=='__main__': unittest.main()