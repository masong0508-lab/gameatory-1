"""Exercise failure/publication behavior with synthetic inputs and fake tools.

No game ROM, assets, SDK or emulator is needed. These tests validate the build
driver; they do not claim that mock binaries execute on a PlayStation.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import elf_fixture  # noqa: E402

PS1 = Path(__file__).resolve().parents[1]


def manifest_source(target):
    """The repository file that prepare.py installs as `target` of the assembled tree."""
    manifest = json.loads((PS1 / 'tools/source_manifest.json').read_text())
    sources = [entry['source'] for entry in manifest['files'] if entry['target'] == target]
    assert len(sources) == 1, target
    assert not any(patch['target'] == target for patch in manifest['patches']), target
    return PS1 / sources[0]


BUILD_SCRIPT = manifest_source('ps1rt/build.sh')
LINT = manifest_source('tools/mips1_lint.py')
PATCH_CHECK = manifest_source('tools/disp_patch_check.py')
MOCK_TOOL = r'''#!/usr/bin/env python3
import json, os
from pathlib import Path
import sys
tool, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ['MOCK_TRACE'], 'a') as out:
    out.write(json.dumps({'tool': tool, 'args': args, 'lbas': os.environ.get('LBAS')}) + '\n')
if os.environ.get('MOCK_FAIL_TOOL') == tool:
    print('deliberate tool failure: ' + tool, file=sys.stderr)
    raise SystemExit(19)
if tool == 'clang':
    source = args[args.index('-c') + 1]
    target = Path(args[args.index('-o') + 1])
    if Path(source).name == os.environ.get('MOCK_FAIL_SOURCE'):
        target.write_bytes(b'partial object')
        print('deliberate compile failure: ' + source, file=sys.stderr)
        raise SystemExit(23)
    target.write_bytes(b'fresh object ' + source.encode())
elif tool == 'ld.lld':
    Path(args[args.index('-o') + 1]).write_bytes(Path(os.environ['MOCK_ELF']).read_bytes())
elif tool == 'llvm-objcopy' and '-O' in args:
    Path(args[-1]).write_bytes(b'fixture binary')
elif tool == 'genisoimage':
    Path(args[args.index('-o') + 1]).write_bytes(b'fixture ISO ' + os.environ.get('LBAS', '').encode())
elif tool == 'isoinfo':
    base = 40 + (1 if os.environ.get('MOCK_MOVE_LBA') and os.environ.get('LBAS') else 0)
    for i, name in enumerate(('ROM.BIN', 'SF3M.BIN', 'PSX.EXE', 'SYSTEM.CNF')):
        print('fixture [ %d 00] %s;1' % (base + i, name))
'''


@unittest.skipUnless(shutil.which('sh'), 'requires a POSIX shell')
class BuildDriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ps1-build-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tree = self.root / 'assembled'
        required = [
            'ps1rt/rt.c', 'ps1rt/crt0.s', 'ps1rt/font.h', 'ps1rt/hw_pad.h',
            'ps1rt/hw_card.h', 'ps1rt/hw_cdda.h', 'ps1rt/hw_radio.h', 'ps1rt/hw_stub.h',
            'ps1rt/ppu12.h', 'ps1rt/ps1.ld', 'sf/sf3.c', 'sf/ps1.h', 'sf/sfmem.h',
            'sf/sfdata.s', 'rd/doll.c', 'rd/ragdoll_ps1.c', 'rd/ragdoll_ps1.h',
            'rd/gte_rp.h', 'rd/ps1.h', 'out/boot.bin', 'out/SF3M.BIN',
            'out/pr/payback_P.map', 'out/pr/payback_P.bin', 'out/pr/meta_P.pkl',
            'out/pr/coldtab_P.bin', 'out/pr/rompages_P.pkl', 'out/s2/prog_pr.pkl',
            't/swi5.bin',
        ]
        for name in required:
            path = self.tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic fixture')
        shutil.copyfile(BUILD_SCRIPT, self.tree / 'ps1rt/build.sh')
        (self.tree / 'tools').mkdir()
        shutil.copyfile(LINT, self.tree / 'tools/mips1_lint.py')
        shutil.copyfile(PATCH_CHECK, self.tree / 'tools/disp_patch_check.py')
        self.good_elf = self.root / 'linked-fixture.elf'
        self.good_elf.write_bytes(elf_fixture.clean_program())
        self.bad_elf = self.root / 'linked-fixture-teq.elf'
        self.bad_elf.write_bytes(elf_fixture.trapping_program())
        (self.tree / 'mkps1.py').write_text(
            'from pathlib import Path\nimport sys\n'
            'out=Path(sys.argv[6])\n'
            '(out/"syms.c").write_text("fixture symbols")\n'
            '(out/"blobs.s").write_text("fixture blobs")\n')
        self.rom = self.root / 'synthetic-input.bin'
        with self.rom.open('wb') as output:
            output.write(b'not a game ROM')
            output.truncate(8 * 1024 * 1024)  # synthetic sparse size fixture
        self.trace = self.root / 'trace.jsonl'
        tools = self.root / 'tools'
        tools.mkdir()
        for name in ('clang', 'ld.lld', 'llvm-objcopy', 'genisoimage', 'isoinfo'):
            path = tools / name
            path.write_text(MOCK_TOOL)
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                        ROM=str(self.rom), NAME='test', BLD='bld_test', PRD='pr',
                        NO_INTERP='1', MOCK_TRACE=str(self.trace), MOCK_ELF=str(self.good_elf))
        for key in ('CFL', 'SF3SRC', 'LD', 'SNAP', 'SNAPFILE', 'DEMO', 'AUTO', 'LBAS',
                    'PS1_CC', 'PS1_LD', 'PS1_OBJCOPY', 'PS1_GENISOIMAGE', 'PS1_ISOINFO',
                    'MOCK_FAIL_TOOL', 'MOCK_FAIL_SOURCE', 'MOCK_MOVE_LBA', 'PROGPKL'):
            self.env.pop(key, None)
        self.old_exe = self.tree / 'out/test.exe'
        self.old_iso = self.tree / 'out/test.iso'
        self.old_exe.write_bytes(b'previous successful EXE')
        self.old_iso.write_bytes(b'previous successful ISO')
        self.stale = self.tree / 'out/bld_test/rt.o'
        self.stale.parent.mkdir()
        self.stale.write_bytes(b'old object must not be reused')

    def run_build(self, *args, **settings):
        return subprocess.run(['sh', 'ps1rt/build.sh', *args], cwd=self.tree,
                              env=dict(self.env, **settings), text=True,
                              capture_output=True, timeout=30)

    def events(self):
        return [json.loads(line) for line in self.trace.read_text().splitlines()] if self.trace.exists() else []

    def assert_old_outputs(self):
        self.assertEqual(self.old_exe.read_bytes(), b'previous successful EXE')
        self.assertEqual(self.old_iso.read_bytes(), b'previous successful ISO')
        self.assertEqual(self.stale.read_bytes(), b'old object must not be reused')

    def test_preflight_reports_missing_source_before_compiling(self):
        (self.tree / 'sf/sfmem.h').unlink()
        result = self.run_build('--check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing input: ../sf/sfmem.h', result.stderr)
        self.assertEqual(self.events(), [])
        self.assert_old_outputs()

    def test_preflight_names_the_missing_arm_swi_stub(self):
        (self.tree / 't/swi5.bin').unlink()
        result = self.run_build('--check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing input: ../t/swi5.bin', result.stderr)
        self.assertEqual(self.events(), [])
        self.assert_old_outputs()

    def test_preflight_names_the_instruction_check(self):
        (self.tree / 'tools/mips1_lint.py').unlink()
        result = self.run_build('--check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing input: ../tools/mips1_lint.py', result.stderr)
        self.assertEqual(self.events(), [])
        self.assert_old_outputs()

    def test_preflight_names_the_dispatch_patch_check(self):
        (self.tree / 'tools/disp_patch_check.py').unlink()
        result = self.run_build('--check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing input: ../tools/disp_patch_check.py', result.stderr)
        self.assertEqual(self.events(), [])
        self.assert_old_outputs()

    def test_wrong_dispatch_patch_word_fails_the_build_before_a_disc(self):
        import test_disp_patch
        elf = self.root / 'linked-fixture-dispatch.elf'
        elf.write_bytes(test_disp_patch.program(patch=lambda new: [new[2]] + new[1:]))
        result = self.run_build(MOCK_ELF=str(elf))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not `j rt_mcache`', result.stdout + result.stderr)
        self.assertIn('PS1 build step failed: disp-patch-check-1', result.stderr)
        self.assertFalse(any(e['tool'] in ('genisoimage', 'isoinfo') for e in self.events()))
        self.assert_old_outputs()

    def test_non_r3000a_instruction_fails_the_build_before_a_disc(self):
        result = self.run_build(MOCK_ELF=str(self.bad_elf))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not valid on the R3000A', result.stderr)
        self.assertIn('divide+0x8', result.stderr)
        self.assertIn('PS1 build step failed: mips1-lint-1', result.stderr)
        self.assertFalse(any(e['tool'] in ('genisoimage', 'isoinfo') for e in self.events()))
        self.assertFalse(any(e['tool'] == 'llvm-objcopy' and '-O' in e['args'] for e in self.events()))
        self.assert_old_outputs()

    def test_compiler_flags_exclude_the_zero_divisor_trap(self):
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        compiles = [e['args'] for e in self.events() if e['tool'] == 'clang']
        self.assertTrue(compiles)
        for args in compiles:
            self.assertIn('-mno-check-zero-division', args)
            self.assertIn('-march=mips1', args)

    def test_compile_failure_cannot_link_stale_objects_or_publish(self):
        result = self.run_build(MOCK_FAIL_SOURCE='rt.c')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('deliberate compile failure: rt.c', result.stderr)
        self.assertFalse(any(e['tool'] in ('ld.lld', 'genisoimage') for e in self.events()))
        self.assert_old_outputs()
        logs = list((self.tree / 'out').glob('.test.build.*/logs/runtime-1.log'))
        self.assertEqual(len(logs), 1)
        self.assertIn('deliberate compile failure', logs[0].read_text())

    def test_renderer_compile_failure_also_stops_before_link(self):
        result = self.run_build(MOCK_FAIL_SOURCE='sf3.c')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(e['tool'] == 'ld.lld' for e in self.events()))
        self.assert_old_outputs()

    def test_isoinfo_failure_cannot_publish_a_disc(self):
        result = self.run_build(MOCK_FAIL_TOOL='isoinfo')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('deliberate tool failure: isoinfo', result.stderr)
        self.assert_old_outputs()

    def test_changed_second_pass_sector_locations_preserve_last_good_outputs(self):
        result = self.run_build(MOCK_MOVE_LBA='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('sector locations moved', result.stderr)
        self.assert_old_outputs()

    def test_success_uses_fresh_objects_and_publishes_only_after_both_passes(self):
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.old_exe.read_bytes().startswith(b'PS-X EXE'))
        self.assertEqual(self.old_iso.read_bytes(), b'fixture ISO 40,0,0,41,41,0,0')
        events = self.events()
        self.assertEqual(sum(e['tool'] == 'ld.lld' for e in events), 2)
        self.assertEqual(sum(e['tool'] == 'isoinfo' for e in events), 2)
        for event in events:
            if event['tool'] == 'clang':
                target = event['args'][event['args'].index('-o') + 1]
                self.assertIn('/.test.build.', target)
                self.assertNotIn('/bld_test/', target)
        self.assertTrue(list((self.tree / 'out').glob('.bld_test.previous.*/rt.o')))
        self.assertIn(b'fresh object', self.stale.read_bytes())

    def test_unsafe_output_name_is_rejected(self):
        result = self.run_build(BLD='../arbitrary')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('simple output names', result.stderr)
        self.assertEqual(self.events(), [])
        self.assert_old_outputs()

    def test_build_directory_cannot_alias_generated_translation(self):
        result = self.run_build(BLD='pr')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('aliases a generated input', result.stderr)
        self.assertEqual(self.events(), [])
        self.assert_old_outputs()

    def test_missing_optional_disc_entry_is_not_treated_as_sector_zero(self):
        (self.tree / 'out/pr/cold_P.bin').write_bytes(b'synthetic cold data')
        result = self.run_build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing ISO directory entry: COLD.BIN', result.stderr)
        self.assert_old_outputs()

    def test_explicit_program_metadata_path_is_honored(self):
        (self.tree / 'out/s2/prog_pr.pkl').rename(self.tree / 'custom.pkl')
        result = self.run_build('--check', PROGPKL='../custom.pkl')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.events(), [])

    def test_rom_outside_current_page_window_fails_before_compiling(self):
        with self.rom.open('ab') as output:
            output.truncate(32 * 1024 * 1024)
        result = self.run_build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('8 MiB page window', result.stderr)
        self.assertEqual(self.events(), [])
        self.assert_old_outputs()


if __name__ == '__main__':
    unittest.main()
