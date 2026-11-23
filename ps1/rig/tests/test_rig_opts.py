"""ROM-free subprocess tests: RIG_OPTS reaches all emulator sessions exactly."""
from __future__ import annotations
import ast
import os
import pathlib
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'run_all.sh'
SAVE_LOAD = ROOT / 'sessions' / 'save_load.py'


class RigOptionsTests(unittest.TestCase):
    def mock_run(self, rig_opts=None, core='swanstation', only='b', case='pass', env_updates=None, assist=False):
        with tempfile.TemporaryDirectory(prefix='ps1 rig options ') as tmp:
            tmp = pathlib.Path(tmp)
            script = tmp / 'bin' / 'python3'
            script.parent.mkdir(parents=True)
            script.write_text('''#!/bin/sh
printf '%s\\n' ==== "$@" >> "$ARGUMENTS"
case "$CASE" in
 pass) echo 'PASS synthetic test' ; exit 0 ;;
 fail) echo 'PASS started'; echo 'FAIL synthetic defect' ; exit 0 ;;
esac
exit 22
''')
            script.chmod(0o755)
            disc = tmp / 'disc with spaces.cue'
            symbols = tmp / 'my game.elf'
            if assist:
                symbols.write_text('KPLB synthetic test assist\n')
            out = tmp / 'run results'
            cap = tmp / 'arguments.txt'
            env = dict(os.environ, PATH=str(script.parent) + os.pathsep + os.environ['PATH'],
                       ARGUMENTS=str(cap), CASE=case, ONLY=only)
            env.update(env_updates or {})
            if rig_opts is None:
                env.pop('RIG_OPTS', None)
            else:
                env['RIG_OPTS'] = rig_opts
            p = subprocess.run(['sh', str(RUNNER), str(disc), str(out), str(symbols), core],
                               env=env, text=True, capture_output=True, timeout=10)
            chunks = [piece.splitlines() for piece in cap.read_text().split('====\n') if piece.strip()] if cap.exists() else []
            return p, chunks, str(disc), str(symbols)

    @staticmethod
    def options(argv):
        return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == '--opt']

    def test_three_recommended_options_reach_all_selected_sessions(self):
        settings = ('swanstation_CPU_Overclock=400 swanstation_CDROM_ReadSpeedup=10 '
                    'swanstation_CDROM_SeekSpeedup=0')
        p, chunks, disc, symbols = self.mock_run(settings, only='b', assist=True)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(len(chunks), 2)  # TEST builds have KPL assist symbols
        for argv in chunks:
            self.assertEqual(self.options(argv), settings.split())
            self.assertEqual(argv[argv.index('--disc') + 1], disc)
            self.assertEqual(argv[argv.index('--syms') + 1], symbols)
            self.assertTrue(argv[0].endswith('tools/ob_session.py'))

    def test_release_disc_skips_assist_even_with_options(self):
        p, chunks, *_ = self.mock_run('swanstation_CPU_Overclock=400', only='b')
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(len(chunks), 1)
        self.assertIn('SKIP b_assist_path', p.stdout)
        self.assertEqual(chunks[0][chunks[0].index('--path') + 1], 'pad')

    def test_runner_parses_as_posix_sh_before_any_emulation(self):
        check = subprocess.run(['sh', '-n', str(RUNNER)], text=True,
                               capture_output=True, check=False)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_parenthesized_safe_core_value_survives_quoting(self):
        p, chunks, *_ = self.mock_run('swanstation_GPU_ResolutionScale=2x(native)',
                                      only='a')
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(self.options(chunks[0]),
                         ['swanstation_GPU_ResolutionScale=2x(native)'])

    def test_explicit_opt_tokens_are_accepted(self):
        p, chunks, *_ = self.mock_run('--opt swanstation_CPU_Overclock=400 --opt swanstation_CDROM_ReadSpeedup=10', only='a')
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(self.options(chunks[0]), ['swanstation_CPU_Overclock=400', 'swanstation_CDROM_ReadSpeedup=10'])

    def test_stock_unset_has_no_core_options(self):
        p, chunks, *_ = self.mock_run(None, only='a')
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(self.options(chunks[0]), [])

    def test_fallback_pcsx_receives_selected_options(self):
        p, chunks, *_ = self.mock_run('pcsx_rearmed_cd_turbo=enabled', core='pcsx_rearmed', only='a')
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(self.options(chunks[0]), ['pcsx_rearmed_cd_turbo=enabled'])
        self.assertTrue(chunks[0][0].endswith('sessions/boot_to_title.py'))

    def test_defects_still_fail_batch(self):
        p, chunks, *_ = self.mock_run('swanstation_CPU_Overclock=400', only='a', case='fail')
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.options(chunks[0]), ['swanstation_CPU_Overclock=400'])

    def test_soak_duration_passed_to_session(self):
        # A 30-minute emulator soak is approximately 108,000 frames at 60Hz.
        # Require at least 1,800s of guest clock too; a slow build fails that gate.
        p, chunks, *_ = self.mock_run('swanstation_CPU_Overclock=400', only='f')
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(len(chunks), 1)
        argv = chunks[0]
        self.assertEqual(argv[argv.index('--max-frames') + 1], '120000')
        self.assertEqual(argv[argv.index('--game-seconds') + 1], '600')
        self.assertEqual(self.options(argv), ['swanstation_CPU_Overclock=400'])

    def test_explicit_30_minute_soak_budget(self):
        p, chunks, *_ = self.mock_run(
            'swanstation_CPU_Overclock=400', only='f',
            env_updates={'SOAK_FRAMES': '108000', 'SOAK_GAME_SECONDS': '1800'})
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        argv = chunks[0]
        self.assertEqual(argv[argv.index('--max-frames') + 1], '108000')
        self.assertEqual(argv[argv.index('--game-seconds') + 1], '1800')

    def test_invalid_tokens_fail_before_any_session(self):
        for bad in ('swanstation_CPU_Overclock', '=400', 'swanstation_CPU_Overclock=',
                    '--opt', '--opt --opt foo=1', 'x-y=1', '--invalid foo=1'):
            with self.subTest(opts=bad):
                p, chunks, *_ = self.mock_run(bad, only='a')
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertFalse(chunks, bad)
                self.assertIn('RIG_OPTS:', p.stderr)

    def test_shell_metacharacters_are_rejected_before_any_session(self):
        for bad in ('swanstation_CDROM_ReadSpeedup=10;echo_BAD',
                    'swanstation_CPU_Overclock=$HOME',
                    'swanstation_CDROM_ReadSpeedup=10*',
                    'swanstation_CPU_Overclock=400|bad'):
            with self.subTest(value=bad):
                p, chunks, *_ = self.mock_run(bad, only='a')
                self.assertEqual(p.returncode, 2, p.stderr + p.stdout)
                self.assertFalse(chunks)
                self.assertIn('invalid option value', p.stderr)

    def test_zero_or_malformed_soak_is_rejected(self):
        for name, bad in (('SOAK_GAME_SECONDS', '0'), ('SOAK_GAME_SECONDS', '-2'),
                          ('SOAK_FRAMES', '0'), ('SOAK_FRAMES', '4.5')):
            with self.subTest(setting=name, value=bad):
                p, chunks, *_ = self.mock_run(None, only='f', env_updates={name: bad})
                self.assertEqual(p.returncode, 2, p.stderr + p.stdout)
                self.assertFalse(chunks)

    def test_result_schema_records_core_options(self):
        # Source-level check: every session goes through Game.finish's meta.
        core = ROOT / 'ps1game.py'
        tree = ast.parse(core.read_text())
        self.assertIn("'core_options':", core.read_text())

    def test_save_load_cold_boot_preserves_options(self):
        # Test the actual helper AST without importing the emulator dependencies.
        body = ast.parse(SAVE_LOAD.read_text()).body
        fn = next(x for x in body if isinstance(x, ast.FunctionDef) and x.name == 'cold_boot_command')
        ns = {'sys': sys, 'os': os, '__file__': str(SAVE_LOAD)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), str(SAVE_LOAD), 'exec'), ns)
        args = SimpleNamespace(disc='/path with spaces/rc7.cue', core='swanstation',
                               state_dir='/temporary/states', syms='/private/rc7.elf',
                               opt=['swanstation_CPU_Overclock=400', 'swanstation_CDROM_ReadSpeedup=10',
                                    'swanstation_CDROM_SeekSpeedup=0'])
        cmd = ns['cold_boot_command'](args, '/tmp/card with space.mcd', '/tmp/out with space')
        self.assertEqual(self.options(cmd), args.opt)
        self.assertEqual(cmd[cmd.index('--disc') + 1], args.disc)
        self.assertEqual(cmd[cmd.index('--card') + 1], '/tmp/card with space.mcd')
        self.assertTrue(cmd[1].endswith('ps1/rig/tools/ob_session.py'), cmd)
        self.assertEqual(cmd[2], str(SAVE_LOAD))
        # Every accurate core needs openboot in the second process too.
        args.core = 'beetle'
        self.assertTrue(ns['cold_boot_command'](args, 'card', 'out')[1].endswith('/tools/ob_session.py'))
        # PCSX-ReARMed does not need the accurate-core BIOS setup wrapper.
        args.core = 'pcsx_rearmed'
        args.opt = []
        direct = ns['cold_boot_command'](args, 'card', 'out')
        self.assertEqual(direct[1], str(SAVE_LOAD))
        self.assertEqual(self.options(direct), [])


if __name__ == '__main__':
    unittest.main()