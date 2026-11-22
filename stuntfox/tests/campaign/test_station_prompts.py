"""Station help prompts: production logic, text width and cross-compiler integration."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class StationPromptTests(unittest.TestCase):
    def test_prompt_combinations_and_gba_width(self):
        cc = os.environ.get("HOSTCC", "cc")
        if not shutil.which(cc):
            self.fail("host C compiler missing; prompt gate cannot run")
        with tempfile.TemporaryDirectory(prefix="stuntfox-station-help-") as temp:
            exe = Path(temp) / "station-help"
            result = subprocess.run([
                cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-I", str(ROOT / "src"),
                str(ROOT / "tests/campaign/station_prompts_host.c"), "-o", str(exe),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            test = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(test.returncode, 0, test.stdout + test.stderr)
            self.assertIn("146 station prompt checks passed", test.stdout)

    def test_production_station_compiles_for_arm7tdmi(self):
        clang = shutil.which("clang")
        if not clang:
            self.fail("clang is required to verify the production ARM code")
        with tempfile.TemporaryDirectory(prefix="stuntfox-station-arm-") as temp:
            result = subprocess.run([
                clang, "--target=armv4t-none-eabi", "-mcpu=arm7tdmi",
                "-O2", "-ffreestanding", "-fno-builtin", "-nostdlib",
                "-mthumb", "-DMERGE", "-I", str(ROOT / "src"),
                "-c", str(ROOT / "src/station.c"), "-o", str(Path(temp) / "station.o"),
            ], capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
