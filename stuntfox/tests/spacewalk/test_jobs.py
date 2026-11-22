"""ROM-free policy/reward regressions using the production space-walk code."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SpaceWalkJobs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which("cc")
        if not cc:
            raise RuntimeError("a host C compiler is required")
        cls.temp = tempfile.TemporaryDirectory(prefix="stuntfox-spacewalk-")
        cls.binary = Path(cls.temp.name) / "jobs"
        subprocess.run([cc, "-std=c11", "-O2", "-ffunction-sections", "-fdata-sections",
                        "-Wno-int-to-pointer-cast", "-Wl,--gc-sections",
                        str(Path(__file__).with_name("jobs_host.c")),
                        str(ROOT / "src/save.c"), "-o", str(cls.binary)],
                       check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_acceptance_preserves_existing_jobs(self):
        self.run_case("policy")

    def test_rewards_and_saved_receipts(self):
        self.run_case("rewards")

    def test_relay_requires_both_beacons_and_safe_return(self):
        self.run_case("relay")

    def test_interruption_and_cancel_cannot_award_progress(self):
        self.run_case("interruption")


if __name__ == "__main__":
    unittest.main()
