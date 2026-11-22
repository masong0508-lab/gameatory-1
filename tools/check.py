#!/usr/bin/env python3
"""Run the repository's regression gates from any working directory.

The default run needs no game ROM. --rom opts into the existing private
content/arena integration cases; it never copies a ROM into the repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def gates():
    """Separate processes keep the suites' different common.py modules isolated."""
    return [
        ("mod", "Payback mod regression tests", ROOT,
         [PYTHON, "-m", "unittest", "discover", "-s", "payback-mod/tests", "-v"]),
        ("stuntfox", "Stunt Fox build entry point", ROOT,
         [PYTHON, "stuntfox/build.py", "--help"]),
        ("stuntfox", "Campaign content validators", ROOT / "stuntfox",
         [PYTHON, "-m", "unittest", "discover", "-s", "tests/content", "-v"]),
        ("stuntfox", "Stunt arena generation", ROOT / "stuntfox",
         [PYTHON, "-m", "unittest", "discover", "-s", "tests/arena", "-v"]),
        ("stuntfox", "Campaign save codec and interrupted writes", ROOT / "stuntfox",
         [PYTHON, "tests/save/run.py"]),
        ("stuntfox", "Campaign equipment and settings persistence", ROOT / "stuntfox",
         [PYTHON, "tests/save/progress.py"]),
        ("stuntfox", "Campaign ending and postgame continuation", ROOT / "stuntfox",
         [PYTHON, "-m", "unittest", "discover", "-s", "tests/campaign", "-v"]),
        ("stuntfox", "Space-walk assignment rewards and receipts", ROOT / "stuntfox",
         [PYTHON, "-m", "unittest", "discover", "-s", "tests/spacewalk", "-v"]),
        ("stuntfox", "Mission VM, fuzz and golden traces", ROOT / "stuntfox",
         [PYTHON, "tests/vm/run.py"]),
        ("stuntfox", "Mission test runner failure handling", ROOT / "stuntfox",
         [PYTHON, "-m", "unittest", "discover", "-s", "tests/vm", "-p", "test_runner.py", "-v"]),
        ("stuntfox", "Radio selection and playback transitions", ROOT / "stuntfox",
         [PYTHON, "tests/radio/run.py"]),
        ("stuntfox", "Physics simulator world loading and bounds", ROOT / "stuntfox",
         [PYTHON, "-m", "unittest", "discover", "-s", "tests/physics", "-v"]),
        ("stuntfox", "GBA ARM linkage, native hooks and stack reserve", ROOT / "stuntfox",
         [PYTHON, "-m", "unittest", "discover", "-s", "tests/build", "-v"]),
        ("ps1", "PlayStation build integrity", ROOT,
         [PYTHON, "-m", "unittest", "discover", "-s", "ps1/tests", "-v"]),
        ("ps1", "PlayStation rebuild scripts", ROOT,
         [PYTHON, "-m", "unittest", "discover", "-s", "ps1/rebuild/tests", "-v"]),
        ("ps1", "PlayStation source assembly", ROOT,
         [PYTHON, "ps1/tools/prepare.py", "--check"]),
        ("ps1", "PlayStation native compilation and RAM budgets", ROOT,
         [PYTHON, "ps1/tools/check_native.py"]),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append", choices=("mod", "stuntfox", "ps1"),
                        help="run only this group; may be repeated (default: all)")
    parser.add_argument("--rom", type=Path,
                        help="opt into private content/arena tests with the original Payback ROM")
    parser.add_argument("--report", type=Path, help="write the gate results as JSON")
    parser.add_argument("--timeout", type=int, default=600, help="seconds allowed per gate")
    parser.add_argument("--list", action="store_true", help="show gates without running them")
    args = parser.parse_args()
    selected = [g for g in gates() if not args.suite or g[0] in args.suite]
    if args.list:
        for group, label, _, _ in selected:
            print(f"{group}: {label}")
        return 0
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    # Some older suites skip compiler-dependent cases. A missing compiler must
    # not make the combined gate look green with those cases silently omitted.
    required = {"cc"}
    if any(group == "stuntfox" for group, *_ in selected):
        required.update(("gcc", "clang", "ld.lld", "llvm-nm", "llvm-objcopy"))
    if any(group == "ps1" for group, *_ in selected):
        required.update(("sh", "patch", "clang", "ld.lld", "llvm-nm", "llvm-objcopy"))
    missing = sorted(tool for tool in required if shutil.which(tool) is None)
    if missing:
        parser.error("missing required tools: " + ", ".join(missing))
    if any(group == "stuntfox" for group, *_ in selected):
        missing_modules = [name for name in ("numpy", "PIL")
                           if importlib.util.find_spec(name) is None]
        if missing_modules:
            parser.error("missing Python modules: " + ", ".join(missing_modules)
                         + "; install with python3 -m pip install -r stuntfox/requirements.txt")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("PAYBACK_ROM", None)
    rom_hash = None
    if args.rom:
        rom = args.rom.resolve()
        if not rom.is_file():
            parser.error("--rom does not name a file")
        rom_hash = hashlib.sha1(rom.read_bytes()).hexdigest()
        if rom_hash != "08df2c6f1b932b8c6e5e1bc9c6ccbe738832d2b7":
            parser.error("--rom must be the untouched European Payback ROM")
        env["PAYBACK_ROM"] = str(rom)
    results = []
    # A local atlas cache must not accidentally change what the ROM-free run
    # executes. Atlas integration is covered by the explicit content tools.
    with tempfile.TemporaryDirectory(prefix="stuntfox-check-atlas-") as atlas:
        env["SF_ATLAS_CACHE"] = atlas
        if args.rom and any(group == "stuntfox" for group, *_ in selected):
            # The shipped-content cases skip without an atlas cache, and the cache
            # above starts empty. Compile the content against the supplied ROM first:
            # that validates it and fills the temporary cache, so --rom runs them.
            at = next(i for i, gate in enumerate(selected)
                      if gate[1] == "Campaign content validators")
            selected.insert(at, ("stuntfox", "Campaign content compiled against the original ROM",
                                 ROOT / "stuntfox",
                                 [PYTHON, "tools/content/sfc.py", "check",
                                  "--rom", str(rom), "--cache", atlas]))
        for group, label, cwd, command in selected:
            print(f"\n=== {label} ===", flush=True)
            started = time.monotonic()
            error = None
            try:
                code = subprocess.run(command, cwd=cwd, env=env,
                                      timeout=args.timeout, check=False).returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                code, error = 1, str(exc)
                print(error, file=sys.stderr)
            results.append({"suite": group, "gate": label, "returncode": code,
                            "passed": code == 0,
                            "seconds": round(time.monotonic() - started, 3),
                            **({"error": error} if error else {})})
    report = {"schema_version": 1,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "rom_free": args.rom is None, "source_rom_sha1": rom_hash,
              "passed": all(r["passed"] for r in results), "gates": results}
    if args.report:
        path = args.report.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", delete=False) as f:
            temporary = Path(f.name)
            json.dump(report, f, indent=2)
            f.write("\n")
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    print("\nGate results:")
    for result in results:
        print(f"{'PASS' if result['passed'] else 'FAIL'}  {result['gate']} ({result['seconds']:.1f}s)")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
