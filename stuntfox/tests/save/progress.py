#!/usr/bin/env python3
"""Compile and exercise the production campaign equipment/settings codec."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile


def main():
    root = Path(__file__).resolve().parents[2]
    cc = os.environ.get("HOSTCC") or shutil.which("gcc") or shutil.which("clang")
    if not cc:
        raise SystemExit("a host C compiler is required")
    with tempfile.TemporaryDirectory(prefix="stuntfox-progress-") as tmp:
        exe = Path(tmp) / "progress"
        command = [cc, "-std=gnu11", "-O1", "-g", "-DMERGE", "-DSETTINGS_HOST",
                   "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                   "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined",
                   str(root / "tests/save/t_progress.c"), str(root / "src/settings.c"),
                   "-o", str(exe)]
        subprocess.run(command, check=True)
        subprocess.run([str(exe)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
