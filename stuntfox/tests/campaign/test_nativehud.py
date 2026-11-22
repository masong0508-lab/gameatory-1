"""Exercise native overlay suppression without changing ordinary game calls."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NativeHudTests(unittest.TestCase):
    def test_overlay_ownership_and_forwarding(self):
        compiler = os.environ.get("HOSTCC", "cc")
        if not shutil.which(compiler):
            self.skipTest("requires a host C compiler")
        with tempfile.TemporaryDirectory(prefix="stuntfox-nativehud-") as directory:
            exe = Path(directory) / "nativehud"
            build = subprocess.run([
                compiler, "-std=gnu11", "-O2", "-Wall", "-Wextra",
                "-Wno-pointer-to-int-cast", "-I", str(ROOT / "src"),
                str(ROOT / "tests/campaign/nativehud_host.c"), "-o", str(exe),
            ], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("native HUD checks passed", run.stdout)


if __name__ == "__main__":
    unittest.main()
