"""Execute the production runtime C against synthetic GBA RAM, without a ROM.

These tests cover behavior at memory/API boundaries; emulator tests remain the
authority for the original game's integration, video and controls.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform.startswith("linux"), "native GBA address fixture requires Linux mmap")
class RuntimeStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which(os.environ.get("CC", "cc"))
        if not compiler:
            raise unittest.SkipTest("a host C compiler is required for direct runtime tests")
        cls.tmp = tempfile.TemporaryDirectory(prefix="stuntfox-runtime-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.binary = Path(cls.tmp.name) / "runtime-tests"
        source = Path(__file__).with_name("runtime_native.c")
        result = subprocess.run(
            [compiler, "-std=c11", "-O1", "-fno-strict-aliasing", "-Wall", "-Wextra",
             "-Wno-attributes", str(source), "-o", str(cls.binary)],
            text=True, capture_output=True,
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def check(self, case):
        result = subprocess.run([str(self.binary), case], text=True, capture_output=True, timeout=10)
        if result.returncode == 77:
            self.skipTest(result.stderr.strip())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_entity_bounds(self):
        self.check("entity_bounds")

    def test_world_and_column_bounds(self):
        self.check("world_and_column_bounds")

    def test_cursor_and_map_swap(self):
        self.check("cursor_and_map_swap")

    def test_reload_state(self):
        self.check("reload_state")

    def test_landed_arwing_exit(self):
        self.check("landed_arwing_exit")

    def test_loop_entry_and_z(self):
        self.check("loop_entry_and_z")

    def test_build_controls_and_braking(self):
        self.check("build_controls_and_braking")

    def test_continuous_loop_exit(self):
        self.check("continuous_loop_exit")

    def test_entity_switch_and_invalid_world(self):
        self.check("entity_switch_and_invalid_world")

    def test_stadium_retry_controls(self):
        self.check("stadium_retry_controls")

    def test_signed_headings(self):
        self.check("signed_headings")


if __name__ == "__main__":
    unittest.main()
