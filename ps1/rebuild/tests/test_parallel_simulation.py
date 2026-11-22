"""ROM-free b9 regression: a failed parallel guest probe must fail the build."""
from __future__ import annotations
import os
import pathlib
import re
import subprocess
import tempfile
import textwrap
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "track_b_regenerate.sh"


class ParallelSimulationTests(unittest.TestCase):
    def test_both_child_exit_codes_are_propagated(self):
        source = SCRIPT.read_text()
        part = re.search(
            r"    rm -f out/touched_f1\.pkl.*?\n(.*?)    # expect in both logs:",
            source, re.DOTALL,
        )
        self.assertIsNotNone(part, "could not locate the production b9 subprocess section")
        fragment = part.group(1)
        # This is the source's actual job start / wait logic, not a copy of it.
        self.assertIn('wait "$level_pid"', fragment)
        self.assertIn('wait "$boot_pid"', fragment)
        for level, boot in ((0, 0), (7, 0), (0, 8), (7, 8)):
            with self.subTest(level=level, boot=boot), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                (root / "t").mkdir()
                (root / "out").mkdir()
                (root / "t/snapdump.py").write_text(textwrap.dedent('''\
                    import os, pathlib, sys
                    kind = os.environ['TOUCH_FROM']
                    # Deliberately produce the expected output even for a failed child.
                    pathlib.Path('out/touched_f1%s.pkl' % ('_boot' if kind == 'boot' else '')).write_bytes(b'synthetic')
                    sys.exit(int(os.environ[kind.upper() + '_EXIT']))
                '''))
                script = "set -euo pipefail\nFRAMES=5\n" + fragment + "\n"
                result = subprocess.run(
                    ["bash", "-c", script], cwd=root,
                    env={**os.environ, "LEVEL_EXIT": str(level), "BOOT_EXIT": str(boot)},
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0 if level == boot == 0 else 4,
                                 result.stdout + result.stderr)
                if level or boot:
                    self.assertIn("simulator run failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
