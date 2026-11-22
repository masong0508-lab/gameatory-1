"""ROM-free regression for the PS1 rig's orchestration and error status."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1] / "run_all.sh"


class RunAllTests(unittest.TestCase):
    def run_mock(self, case, core="pcsx_rearmed", only="a"):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            mockbin = temp / "bin"
            mockbin.mkdir()
            argv_file = temp / "argv.txt"
            fake_python = mockbin / "python3"
            fake_python.write_text('''#!/bin/sh
printf '%s\\n' "$@" > "$ARGV_FILE"
case "$CASE" in
  pass) echo 'PASS synthetic gameplay' ; exit 0 ;;
  fail) echo 'PASS synthetic start'; echo 'FAIL synthetic physics'; exit 0 ;;
  exit) echo 'PASS synthetic start'; exit 17 ;;
  empty) echo 'diagnostic only'; exit 0 ;;
esac
exit 99
''')
            fake_python.chmod(0o755)
            # These paths deliberately contain spaces and must survive as
            # single argv entries through the runner and the accurate-core shim.
            disc = temp / "disc with spaces.cue"
            symbols = temp / "game symbols.elf"
            out = temp / "run output"
            result = subprocess.run(
                ["sh", str(RUNNER), str(disc), str(out), str(symbols), core],
                env={**os.environ, "PATH": str(mockbin) + os.pathsep + os.environ["PATH"],
                     "ARGV_FILE": str(argv_file), "CASE": case, "ONLY": only},
                text=True, capture_output=True, timeout=10,
            )
            args = argv_file.read_text().splitlines() if argv_file.exists() else []
            logs = (out / "session_failures.txt").read_text() if (out / "session_failures.txt").exists() else ""
            return result, args, logs, disc, symbols

    def test_all_pass(self):
        r, args, fail_log, disc, symbols = self.run_mock("pass")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(str(disc), args)
        self.assertIn(str(symbols), args)
        self.assertEqual(args[args.index("--disc") + 1], str(disc))
        self.assertEqual(args[args.index("--syms") + 1], str(symbols))
        self.assertFalse(fail_log)

    def test_reported_fail_must_fail_runner(self):
        r, args, fail_log, _, _ = self.run_mock("fail")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("FAIL synthetic physics", fail_log)

    def test_child_failure_must_fail_runner(self):
        r, args, fail_log, _, _ = self.run_mock("exit")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("child exited with 17", fail_log)

    def test_zero_assertions_must_fail_runner(self):
        r, args, fail_log, _, _ = self.run_mock("empty")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no PASS assertions", fail_log)

    def test_accurate_core_preserves_arguments(self):
        r, args, _, disc, symbols = self.run_mock("pass", core="swanstation")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(args[0].endswith("tools/ob_session.py"), args)
        self.assertEqual(args[args.index("--disc") + 1], str(disc))
        self.assertEqual(args[args.index("--syms") + 1], str(symbols))

    def test_invalid_core_stops_without_running(self):
        r, args, logs, _, _ = self.run_mock("pass", core="duckstation")
        self.assertEqual(r.returncode, 2)
        self.assertFalse(args)

    def test_empty_session_selection_is_error(self):
        r, args, logs, _, _ = self.run_mock("pass", only="z")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("0 sessions", r.stdout)


if __name__ == "__main__":
    unittest.main()
