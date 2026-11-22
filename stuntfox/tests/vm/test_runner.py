"""Failures must not become green gates merely because stdout looks correct."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location('stuntfox_vm_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def failed(stdout='', stderr='sanitizer failure after output\n'):
    return subprocess.CompletedProcess(['fake-vm'], 1, stdout, stderr)


class RunnerFailureTests(unittest.TestCase):
    def test_failed_demo_generation_never_uses_a_stale_demo(self):
        with tempfile.TemporaryDirectory() as folder:
            stale = Path(folder) / 'demo.bin'
            stale.write_bytes(b'stale demo from an earlier successful run')
            with mock.patch.object(runner, 'OUT', folder), \
                 mock.patch.object(runner, 'sh', return_value=failed(stderr='demo generation failed\n')), \
                 mock.patch.object(runner, 'host_cc') as compiler, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main([]), 1)
            compiler.assert_not_called()
            self.assertIn('demo generation', output.getvalue())
            self.assertEqual(stale.read_bytes(), b'stale demo from an earlier successful run')

    def test_matching_fuzz_hashes_do_not_hide_a_failed_process(self):
        good = subprocess.CompletedProcess(['fake-vm'], 0, 'hash 12345678\n', '')
        with mock.patch.object(runner, 'sh', side_effect=[failed(good.stdout), good]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.check_fuzz('vm', 'demo'), 1)
        self.assertIn('fuzz run 1 exited 1', output.getvalue())
        self.assertIn('sanitizer failure', output.getvalue())

    def test_matching_golden_output_does_not_hide_a_failed_process(self):
        with tempfile.TemporaryDirectory() as folder:
            expected = Path(folder) / 'act1.txt'
            expected.write_text('complete expected trace\n')
            with mock.patch.object(runner, 'TRACES', ('act1',)), \
                 mock.patch.object(runner, 'sh', return_value=failed(expected.read_text())), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.check_golden('vm', 'demo', folder, folder), 1)
            self.assertIn('golden trace act1 exited 1', output.getvalue())
            self.assertEqual(expected.read_text(), 'complete expected trace\n')

    def test_update_keeps_existing_golden_when_child_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            expected = Path(folder) / 'act1.txt'
            expected.write_text('reviewed golden trace\n')
            with mock.patch.object(runner, 'TRACES', ('act1',)), \
                 mock.patch.object(runner, 'sh', return_value=failed('partial failing trace\n')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.check_golden('vm', 'demo', folder, folder, update=True), 1)
            self.assertEqual(expected.read_text(), 'reviewed golden trace\n')


if __name__ == '__main__':
    unittest.main()
