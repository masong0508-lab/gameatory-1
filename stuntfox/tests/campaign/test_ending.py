"""Run the production campaign controller against a small playable-state fixture."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CampaignEndingTests(unittest.TestCase):
    def test_completion_input_and_postgame(self):
        compiler = os.environ.get("HOSTCC", "cc")
        if not shutil.which(compiler):
            self.skipTest("requires a host C compiler")
        with tempfile.TemporaryDirectory(prefix="stuntfox-ending-") as directory:
            exe = Path(directory) / "ending"
            build = subprocess.run([
                compiler, "-std=gnu11", "-O2", "-Wall", "-Wextra",
                "-Wno-pointer-to-int-cast", "-Wno-unused-parameter", "-DSV_HOST",
                "-I", str(ROOT / "src"), "-include", str(ROOT / "tests/campaign/cpmock.h"),
                str(ROOT / "tests/campaign/t_ending.c"), str(ROOT / "src/save.c"),
                "-o", str(exe),
            ], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("campaign ending checks passed", run.stdout)


if __name__ == "__main__":
    unittest.main()
