"""ROM-free acceptance-audit regression tests with synthetic session artifacts."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

P = Path(__file__).resolve().parent / "audit.py"
sp = importlib.util.spec_from_file_location("qa_audit", P)
audit = importlib.util.module_from_spec(sp)
sp.loader.exec_module(audit)
SHA = "a" * 40
SHA2 = "b" * 40


def session(root, name, *, labels=("level is running",), sha=SHA, core="swanstation",
            statuses=None, frames=100, faults=None, extra=None):
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    statuses = [True] * len(labels) if statuses is None else statuses
    data = {"session": name, "frames": frames, "pass": sum(statuses), "fail": len(labels) - sum(statuses),
            "results": [{"ok": ok, "text": label, "detail": "SECRET GAME TEXT"} for ok, label in zip(statuses, labels)],
            "meta": {"core": core, "exe_sha1": sha, "disc": "SECRET-DISC-PATH", "syms_match_disc": True},
            "tty_faults": [] if faults is None else faults, "extra": extra or {}}
    (path / "result.json").write_text(json.dumps(data))
    return path


def full(root):
    for name in audit.PROFILES["gameplay"]:
        session(root, name)
    session(root, "c_in_level", labels=tuple(k + ": verified" for k in audit.LEVEL_CATEGORIES))
    session(root, "d_maps", labels=tuple(f"map {i}: valid" for i in range(11)))
    session(root, "e_save_load", labels=("save payload: magic and CRC are good",))
    session(root, "e_save_load/reboot", labels=("the save on the card is still valid",))
    session(root, "f_soak", labels=("soak covered 600 s of game time",), extra={"ticks": 18000})
    session(root, "h_speed", labels=("speed table written",))
    (root / "h_speed/speed.json").write_text(json.dumps([
        {"scene": s, "gframes_per_60": 25.0, "presents_per_60": 15.0}
        for s in audit.SPEED_SCENES]))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_full_synthetic_gameplay_passes_but_no_duckstation_claim(self):
        full(self.root)
        rep = audit.audit(self.root, "swanstation", "gameplay")
        self.assertEqual(rep["status"], "PASS")
        self.assertEqual(rep["passed_sessions"], 7)
        self.assertFalse(rep["duckstation_android_verified"])
        self.assertFalse(rep["performance_thresholds_configured"])
        self.assertEqual(rep["disc_sha1"], SHA)
        self.assertNotIn("SECRET", json.dumps(rep))

    def test_required_missing_session_fails(self):
        session(self.root, "a_boot_to_title")
        rep = audit.audit(self.root, "swanstation", "boot")
        self.assertEqual(rep["status"], "FAIL")
        self.assertIn("b_new_game_to_level", rep["failures"])

    def test_wrong_core_and_changed_build_detected(self):
        session(self.root, "a_boot_to_title", core="beetle")
        session(self.root, "b_new_game_to_level", sha=SHA2)
        rep = audit.audit(self.root, "swanstation", "boot", expected_sha=SHA)
        self.assertEqual(rep["status"], "FAIL")
        self.assertIn("mixed_builds", rep["failures"])
        self.assertIn("wrong_core", rep["sessions"][0]["errors"])
        self.assertIn("wrong_executable", rep["sessions"][1]["errors"])

    def test_zero_pass_and_false_success_counts(self):
        session(self.root, "a_boot_to_title", labels=("bare crash",), statuses=(False,))
        session(self.root, "b_new_game_to_level")
        rep = audit.audit(self.root, "swanstation", "boot")
        self.assertIn("no_pass_assertions", rep["sessions"][0]["errors"])
        self.assertIn("failed_assertions", rep["sessions"][0]["errors"])
        data = json.loads((self.root / "b_new_game_to_level/result.json").read_text())
        data["pass"] = 999
        (self.root / "b_new_game_to_level/result.json").write_text(json.dumps(data))
        rep = audit.audit(self.root, "swanstation", "boot")
        self.assertIn("mismatched_check_counts", rep["sessions"][1]["errors"])

    def test_save_must_cold_boot_from_same_executable(self):
        full(self.root)
        (self.root / "e_save_load/reboot/result.json").unlink()
        rep = audit.audit(self.root, "swanstation", "gameplay")
        self.assertIn("cold_boot_load_unverified", rep["sessions"][4]["errors"])
        session(self.root, "e_save_load/reboot", sha=SHA2)
        rep = audit.audit(self.root, "swanstation", "gameplay")
        self.assertIn("reboot_used_other_executable", rep["sessions"][4]["errors"])

    def test_partial_walk_and_map_tour_not_full_coverage(self):
        full(self.root)
        session(self.root, "c_in_level", labels=("level is running", "walk: moves"))
        session(self.root, "d_maps", labels=("map 0", "map 1"))
        rep = audit.audit(self.root, "swanstation", "gameplay")
        self.assertIn("missing_vehicle_check", rep["sessions"][2]["errors"])
        self.assertIn("incomplete_map_tour", rep["sessions"][3]["errors"])

    def test_soak_pass_label_without_enough_ticks_fails(self):
        full(self.root)
        session(self.root, "f_soak", labels=("soak covered 600 s of game time",), extra={"ticks": 100})
        rep = audit.audit(self.root, "swanstation", "gameplay")
        self.assertIn("insufficient_soak_ticks", rep["sessions"][5]["errors"])

    def test_short_soak_and_no_speed_scene_do_not_pass(self):
        full(self.root)
        session(self.root, "f_soak", labels=("clock advanced",))
        (self.root / "h_speed/speed.json").write_text(json.dumps([{"scene": "language screen"}]))
        rep = audit.audit(self.root, "swanstation", "gameplay")
        self.assertIn("soak_time_unverified", rep["sessions"][5]["errors"])
        self.assertIn("missing_speed_scene", rep["sessions"][6]["errors"])

    def test_optional_performance_thresholds_are_real_gates(self):
        full(self.root)
        rep = audit.audit(self.root, "swanstation", "gameplay", min_guest_fps=30., min_presented_fps=20.)
        self.assertEqual(rep["status"], "FAIL")
        self.assertIn("guest_fps_below_required", rep["sessions"][6]["errors"])
        self.assertIn("presented_fps_below_required", rep["sessions"][6]["errors"])
        rep = audit.audit(self.root, "swanstation", "gameplay", min_guest_fps=20., min_presented_fps=10.)
        self.assertEqual(rep["status"], "PASS")
        self.assertTrue(rep["performance_thresholds_configured"])

    def test_guest_faults_fail_even_if_checks_claim_pass(self):
        session(self.root, "a_boot_to_title", faults=["SECRET GAME TEXT"])
        session(self.root, "b_new_game_to_level")
        rep = audit.audit(self.root, "swanstation", "boot")
        self.assertIn("guest_faults_detected", rep["sessions"][0]["errors"])
        self.assertNotIn("SECRET", json.dumps(rep))

    def test_invalid_result_and_invalid_speed_metric_fails(self):
        full(self.root)
        (self.root / "a_boot_to_title/result.json").write_text("not JSON")
        (self.root / "h_speed/speed.json").write_text(json.dumps([{
            "scene": scene, "gframes_per_60": "fast", "presents_per_60": 10.0}
            for scene in audit.SPEED_SCENES]))
        rep = audit.audit(self.root, "swanstation", "gameplay")
        self.assertIn("invalid_json", rep["sessions"][0]["errors"])
        self.assertIn("invalid_speed_metric", rep["sessions"][6]["errors"])

    def test_failures_manifest_rejects_an_old_passing_json(self):
        full(self.root)
        # The most dangerous failure: a core aborts before replacing a prior
        # successful result. The runner's fresh FAIL manifest must veto it.
        (self.root / "session_failures.txt").write_text("FAIL b_new_game_to_level: no PASS assertions\n")
        rep = audit.audit(self.root, "swanstation", "gameplay")
        self.assertEqual(rep["status"], "FAIL")
        self.assertIn("runner_reported_failures", rep["failures"])

    def test_log_newer_than_json_rejects_stale_session(self):
        full(self.root)
        p = self.root / "b_new_game_to_level"
        log = self.root / "b_new_game_to_level.log"
        log.write_text("synthetic new failed run")
        os.utime(p / "result.json", (100, 100))
        os.utime(log, (110, 110))
        rep = audit.audit(self.root, "swanstation", "gameplay")
        self.assertIn("session_result_stale", rep["sessions"][1]["errors"])

    def test_reboot_older_than_parent_is_not_fresh_save_evidence(self):
        full(self.root)
        parent = self.root / "e_save_load/result.json"
        child = self.root / "e_save_load/reboot/result.json"
        os.utime(child, (100, 100))
        os.utime(parent, (110, 110))
        rep = audit.audit(self.root, "swanstation", "gameplay")
        self.assertIn("reboot_result_stale", rep["sessions"][4]["errors"])

    def test_symbol_mismatch_and_monitor_warnings(self):
        session(self.root, "a_boot_to_title")
        session(self.root, "b_new_game_to_level")
        p = self.root / "a_boot_to_title/result.json"
        data = json.loads(p.read_text())
        data["meta"]["syms_match_disc"] = False
        data["meta"]["tty"] = False
        p.write_text(json.dumps(data))
        rep = audit.audit(self.root, "swanstation", "boot")
        self.assertIn("symbols_for_another_disc", rep["sessions"][0]["errors"])
        self.assertIn("guest_fault_monitor_unavailable", rep["sessions"][0]["warnings"])
        self.assertIn("emulator_options_not_recorded", rep["sessions"][0]["warnings"])
        self.assertEqual(rep["exe_sha1"], SHA)
        self.assertNotIn("SECRET", json.dumps(rep))

    def test_missing_fingerprint_not_certified(self):
        session(self.root, "a_boot_to_title", sha=None)
        session(self.root, "b_new_game_to_level")
        rep = audit.audit(self.root, "swanstation", "boot")
        self.assertEqual(rep["status"], "FAIL")
        self.assertIn("missing_exe_fingerprint", rep["sessions"][0]["errors"])


if __name__ == "__main__":
    unittest.main()