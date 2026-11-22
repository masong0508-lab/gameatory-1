#!/usr/bin/env python3
"""Audit the private PS1 emulator rig's result.json files without exposing game data.

This is a coverage/provenance gate, NOT a game emulator or a DuckStation test.
The output contains only session identifiers, error codes, numeric metrics and
an executable fingerprint. No game dialogue, log text, screenshots or saves.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

PROFILES = {
    "boot": ("a_boot_to_title", "b_new_game_to_level"),
    "gameplay": ("a_boot_to_title", "b_new_game_to_level", "c_in_level",
                 "d_maps", "e_save_load", "f_soak", "h_speed"),
    "extended": ("a_boot_to_title", "b_new_game_to_level", "c_in_level",
                 "d_maps", "e_save_load", "f_soak", "g_state_check",
                 "h_speed", "j_replay_script"),
}

# Evidence is based on the rig's *own check labels*, not the copyrighted
# text drawn by the game. One passing generic 'level is running' test cannot
# stand in for all the behaviours a selected session was supposed to test.
LEVEL_CATEGORIES = {
    "walk": ("walk:",),
    "turn": ("turn:",),
    "weapons": ("weapons:",),
    "fire": ("fire:",),
    "pause": ("pause:",),
    "death": ("death:",),
    "vehicle": ("vehicle:",),
}
MIN_MAPS = set(range(11))
SPEED_SCENES = ("level, standing", "level, walking (Cross)", "level, walking and turning")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def read_json(path: Path):
    try:
        if not path.is_file() or path.stat().st_size > 15_000_000:
            raise ValueError("missing_or_oversized_json")
    except OSError:
        raise ValueError("inaccessible_json") from None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, UnicodeError):
        raise ValueError("invalid_json") from None


def one_result(path: Path, core: str):
    """Return a sanitized report and a set of the successfully exercised labels."""
    row = {"id": path.parent.name, "ok": False, "errors": [],
           "frames": None, "passed": None, "failed": None}
    try:
        o = read_json(path)
    except ValueError as e:
        row["errors"].append(str(e))
        return row, [], None
    if not isinstance(o, dict):
        row["errors"].append("invalid_schema")
        return row, [], None
    meta = o.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        row["errors"].append("missing_meta")
    if meta.get("core") != core:
        row["errors"].append("wrong_core")
    sha = meta.get("exe_sha1")
    if not isinstance(sha, str) or not HEX40.fullmatch(sha.lower()):
        row["errors"].append("missing_exe_fingerprint")
        sha = None
    else:
        sha = sha.lower()
    if meta.get("syms_match_disc") is False:
        row["errors"].append("symbols_for_another_disc")
    frames, passed, failed = o.get("frames"), o.get("pass"), o.get("fail")
    if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
        row["errors"].append("invalid_frame_count")
    else:
        row["frames"] = frames
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (passed, failed)):
        row["errors"].append("invalid_check_counts")
    else:
        row["passed"] = passed
        row["failed"] = failed
        if passed == 0:
            row["errors"].append("no_pass_assertions")
        if failed > 0:
            row["errors"].append("failed_assertions")
    checks = o.get("results")
    valid = isinstance(checks, list) and len(checks) > 0 and all(
        isinstance(c, dict) and type(c.get("ok")) is bool and isinstance(c.get("text"), str)
        for c in checks
    )
    if not valid:
        row["errors"].append("invalid_check_results")
        checks = []
    else:
        real_ok = sum(c["ok"] for c in checks)
        if real_ok != passed or len(checks) - real_ok != failed:
            row["errors"].append("mismatched_check_counts")
    faults = o.get("tty_faults", [])
    if not isinstance(faults, list):
        row["errors"].append("invalid_fault_record")
    elif faults:
        row["errors"].append("guest_faults_detected")
    row["ok"] = not row["errors"]
    return row, [c["text"].lower() for c in checks if c["ok"]], sha


def evidence_errors(session: str, good_labels: list[str], root: Path, core: str,
                    required_guest_fps: float | None, required_presented_fps: float | None,
                    required_soak_seconds: int):
    errs = []
    if session == "c_in_level":
        for name, prefixes in LEVEL_CATEGORIES.items():
            if not any(any(t.startswith(p) for p in prefixes) for t in good_labels):
                errs.append("missing_" + name + "_check")
    if session == "d_maps":
        numbers = set()
        for t in good_labels:
            for m in re.finditer(r"\bmap (\d+)\b", t):
                numbers.add(int(m.group(1)))
        if not MIN_MAPS.issubset(numbers):
            errs.append("incomplete_map_tour")
    if session == "e_save_load":
        if not any("save payload:" in t for t in good_labels):
            errs.append("missing_save_payload_check")
        child, labels, _sha = one_result(root / "e_save_load" / "reboot" / "result.json", core)
        if not child["ok"] or not any("save on the card is still valid" in t for t in labels):
            errs.append("cold_boot_load_unverified")
    if session == "f_soak":
        if not any(t.startswith("soak covered") for t in good_labels):
            errs.append("soak_time_unverified")
        try:
            entry = read_json(root / "f_soak" / "result.json")
            ticks = entry.get("extra", {}).get("ticks")
            if type(ticks) is not int or ticks < 30 * required_soak_seconds:
                errs.append("insufficient_soak_ticks")
        except (ValueError, AttributeError, TypeError):
            errs.append("insufficient_soak_ticks")
    if session == "h_speed":
        try:
            rows = read_json(root / "h_speed" / "speed.json")
        except ValueError:
            return ["missing_speed_measurements"], None
        if not isinstance(rows, list):
            return ["invalid_speed_measurements"], None
        by_scene = {r.get("scene"): r for r in rows if isinstance(r, dict) and isinstance(r.get("scene"), str)}
        observed = {}
        for scene in SPEED_SCENES:
            r = by_scene.get(scene)
            if r is None:
                errs.append("missing_speed_scene")
                continue
            nums = {}
            for k in ("gframes_per_60", "presents_per_60"):
                val = r.get(k)
                if type(val) not in (float, int) or not math.isfinite(val) or val < 0:
                    errs.append("invalid_speed_metric")
                    break
                nums[k] = round(float(val), 3)
            if len(nums) != 2:
                continue
            observed[scene] = nums
            if required_guest_fps is not None and nums["gframes_per_60"] < required_guest_fps:
                errs.append("guest_fps_below_required")
            if required_presented_fps is not None and nums["presents_per_60"] < required_presented_fps:
                errs.append("presented_fps_below_required")
        return sorted(set(errs)), observed
    return sorted(set(errs)), None


def audit(root: Path, core: str, profile: str, expected_sha: str | None = None,
          min_guest_fps: float | None = None, min_presented_fps: float | None = None,
          soak_seconds: int = 600):
    rows = []
    failures = []
    fingerprints = set()
    extras = {}
    for session in PROFILES[profile]:
        row, checks, sha = one_result(root / session / "result.json", core)
        row["id"] = session
        if sha is not None:
            fingerprints.add(sha)
            if expected_sha and sha != expected_sha:
                row["errors"].append("wrong_executable")
        if row["ok"]:
            more, metrics = evidence_errors(session, checks, root, core, min_guest_fps, min_presented_fps, soak_seconds)
            row["errors"].extend(more)
            if metrics is not None:
                extras["speed"] = metrics
            if session == "e_save_load":
                child, _ch, child_sha = one_result(root / session / "reboot" / "result.json", core)
                if child_sha and sha and child_sha != sha:
                    row["errors"].append("reboot_used_other_executable")
        row["errors"] = sorted(set(row["errors"]))
        row["ok"] = not row["errors"]
        if not row["ok"]:
            failures.append(session)
        rows.append(row)
    if len(fingerprints) > 1:
        failures.append("mixed_builds")
    return {
        "schema": 1, "profile": profile, "core": core,
        "status": "PASS" if not failures else "FAIL",
        "session_count": len(rows), "passed_sessions": sum(r["ok"] for r in rows),
        "failures": sorted(set(failures)), "disc_sha1": next(iter(fingerprints)) if len(fingerprints) == 1 else None,
        "performance_thresholds_configured": min_guest_fps is not None and min_presented_fps is not None,
        "duckstation_android_verified": False,
        "unsupported_gates": ["all_vehicle_types", "radio_audio_listening", "flicker_scan", "duckstation_android_device"],
        "sessions": rows, **extras,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, type=Path, help="private rig OUTROOT; never commit its contents")
    ap.add_argument("--core", required=True, choices=("pcsx_rearmed", "swanstation", "beetle"))
    ap.add_argument("--profile", choices=tuple(PROFILES), default="gameplay")
    ap.add_argument("--exe-sha1", default=None, help="optional expected disc PSX.EXE SHA-1")
    ap.add_argument("--min-guest-fps", type=float, default=None)
    ap.add_argument("--min-presented-fps", type=float, default=None)
    ap.add_argument("--soak-seconds", type=int, default=600, help="required observed game time for soak (default 600)")
    ap.add_argument("--output", type=Path, help="private sanitized summary JSON (not raw rig results)")
    a = ap.parse_args(argv)
    if a.exe_sha1 is not None and not HEX40.fullmatch(a.exe_sha1.lower()):
        ap.error("--exe-sha1 must be 40 hexadecimal digits")
    for value in (a.min_guest_fps, a.min_presented_fps):
        if value is not None and (not math.isfinite(value) or value < 0):
            ap.error("FPS thresholds must be finite and nonnegative")
    if a.soak_seconds < 1:
        ap.error("--soak-seconds must be positive")
    report = audit(a.root, a.core, a.profile,
                   a.exe_sha1.lower() if a.exe_sha1 else None,
                   a.min_guest_fps, a.min_presented_fps, a.soak_seconds)
    out = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(out, encoding="utf-8")
    print(out, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())