#!/usr/bin/env python3
"""Verify private Payback build inputs without extracting or publishing them.

Usage:
    python3 ps1/rebuild/check_owner_inputs.py MANIFEST PACKAGE.zip [--rom ROM]
    python3 ps1/rebuild/check_owner_inputs.py MANIFEST SURV_DIR [--release] [--rom ROM]

The manifest is the public SHA256 SIZE PATH index; iso_* entries are excluded
because the owner's private ZIP deliberately contains no disc staging trees.
Output contains filenames, PASS/FAIL status and counts, never game data.
"""

from __future__ import annotations

import argparse
import hashlib
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

CHUNK = 1024 * 1024
ROM_SIZE = 8 * 1024 * 1024
# Files copied by track_a_reuse.sh. The complete ZIP also contains seven
# independent regeneration comparison inputs, which --release need not require.
RELEASE = frozenset({
    "boot.bin", "SF3M.BIN", "touched_f1_boot.pkl.rompages",
    "s2/prog_pr.pkl",
    *(f"{profile}/{name}" for profile in ("pr_l", "pr_lb")
      for name in ("payback_P.bin", "payback_P.map", "meta_P.pkl",
                   "cold_P.bin", "coldtab_P.bin")),
})


class InputError(Exception):
    """Expected user-visible validation failure."""


def valid_relpath(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name and name != "." and name == p.as_posix()
                and not p.is_absolute() and not any(x in ("", ".", "..")
                                                   for x in name.split("/"))
                and "\\" not in name and ":" not in name and "\0" not in name)


def read_manifest(path: Path) -> tuple[dict[str, tuple[str, int]], str]:
    expected: dict[str, tuple[str, int]] = {}
    rom_hashes: set[str] = set()
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 3:
            raise InputError(f"manifest line {n}: expected SHA256 SIZE PATH")
        digest, size, name = fields
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise InputError(f"manifest line {n}: invalid SHA-256")
        if not size.isdecimal() or int(size) < 1 or not valid_relpath(name):
            raise InputError(f"manifest line {n}: invalid size/path")
        if name.startswith("iso_"):
            if name.endswith("/ROM.BIN"):
                if int(size) != ROM_SIZE:
                    raise InputError(f"manifest line {n}: ROM size mismatch")
                rom_hashes.add(digest)
            continue
        if name in expected:
            raise InputError(f"manifest line {n}: duplicate path {name}")
        expected[name] = digest, int(size)
    if not expected:
        raise InputError("manifest contains no expected private input files")
    if len(rom_hashes) != 1:
        raise InputError("manifest must give one consistent SHA-256 for the 8 MiB ROM")
    if not RELEASE.issubset(expected):
        raise InputError("manifest lacks one or more Track A release inputs")
    return expected, next(iter(rom_hashes))


def file_sha(stream, expected_size: int) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    while block := stream.read(CHUNK):
        total += len(block)
        if total > expected_size:
            # Don't hash oversized archive entries or accidentally process
            # enormous files if an input is corrupted or malicious.
            return "oversized", total
        h.update(block)
    return h.hexdigest(), total


def verify_zip(archive: Path, expected: dict[str, tuple[str, int]]) -> list[str]:
    failures = []
    with zipfile.ZipFile(archive) as z:
        members: dict[str, zipfile.ZipInfo] = {}
        for info in z.infolist():
            name = info.filename[:-1] if info.is_dir() else info.filename
            if not valid_relpath(name):
                failures.append("UNSAFE ZIP PATH")
                continue
            if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                failures.append("SYMLINK IN ZIP")
                continue
            if info.is_dir():
                # Directory entries are harmless, but must have safe paths.
                continue
            if name in members:
                failures.append(f"DUPLICATE {name}")
            else:
                members[name] = info
        for name in sorted(set(members) - set(expected)):
            failures.append(f"UNEXPECTED {name}")
        for name, (want, size) in expected.items():
            info = members.get(name)
            if info is None:
                failures.append(f"MISSING {name}")
            elif info.file_size != size:
                failures.append(f"SIZE {name}")
            else:
                try:
                    with z.open(info) as stream:
                        got, actual_size = file_sha(stream, size)
                except (OSError, ValueError, RuntimeError, EOFError, zipfile.BadZipFile):
                    failures.append(f"READ/CRC {name}")
                    continue
                if (got, actual_size) != (want, size):
                    failures.append(f"HASH {name}")
    return failures


def verify_directory(root: Path, expected: dict[str, tuple[str, int]]) -> list[str]:
    failures = []
    base = root.resolve()
    for name, (want, size) in expected.items():
        path = root / name
        if not path.is_file():
            failures.append(f"MISSING {name}")
        elif path.is_symlink() or not path.resolve().is_relative_to(base):
            failures.append(f"UNSAFE LINK {name}")
        elif path.stat().st_size != size:
            failures.append(f"SIZE {name}")
        else:
            try:
                with path.open("rb") as stream:
                    got, actual_size = file_sha(stream, size)
            except OSError:
                failures.append(f"READ {name}")
                continue
            if (got, actual_size) != (want, size):
                failures.append(f"HASH {name}")
    return failures


def verify_rom(path: Path, expected_sha: str) -> str | None:
    if not path.is_file() or path.stat().st_size != ROM_SIZE:
        return "ROM MISSING/WRONG SIZE"
    with path.open("rb") as stream:
        digest, size = file_sha(stream, ROM_SIZE)
    return None if digest == expected_sha and size == ROM_SIZE else "ROM SHA256 MISMATCH"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("inputs", type=Path, help="Private owner ZIP or extracted SURV directory")
    p.add_argument("--release", action="store_true", help="Verify only the 14 inputs staged by Track A")
    p.add_argument("--rom", type=Path, help="Also check the original owner's 8 MiB ROM")
    args = p.parse_args(argv)
    try:
        exp, rom_sha = read_manifest(args.manifest)
        if args.release:
            exp = {k: v for k, v in exp.items() if k in RELEASE}
        if args.inputs.is_dir():
            failures = verify_directory(args.inputs, exp)
        elif args.inputs.is_file() and zipfile.is_zipfile(args.inputs):
            failures = verify_zip(args.inputs, exp)
        else:
            raise InputError("inputs must be an existing directory or ZIP archive")
        if args.rom:
            rom_fail = verify_rom(args.rom, rom_sha)
            if rom_fail:
                failures.append(rom_fail)
        for fail in failures:
            print(f"FAIL {fail}")
        print(f"Owner input verification: {len(exp)} expected files; {len(failures)} error(s)")
        if args.rom and not any(f.startswith("ROM ") for f in failures):
            print("Owner ROM: SHA256 and 8 MiB size MATCH")
        return 1 if failures else 0
    except (InputError, OSError, zipfile.BadZipFile, ValueError) as exc:
        print(f"Input verification unavailable: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
