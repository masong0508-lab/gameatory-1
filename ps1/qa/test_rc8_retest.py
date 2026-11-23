"""ROM-free and network-free orchestration regressions. No game data."""
import importlib.util
import io
from pathlib import Path
import tempfile
from contextlib import redirect_stdout
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

    def test_mgba_addition_is_optional_but_not_a_fake_pass(self):
        plan=m.jobs(self.disc,self.syms,self.out,gba_rom=Path('/private/original.gba'))
        self.assertEqual(plan[-1]['profile'],'mGBA_original')
        self.assertIn('--require-all',plan[-1]['command'])
        self.assertEqual(len(plan),7)

    def test_stock_can_be_skipped_explicitly(self):
        plan=m.jobs(self.disc,self.syms,self.out,stock=False)
        self.assertEqual(len(plan),3)
        self.assertTrue(all(x['profile']=='recommended' for x in plan))

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