#!/usr/bin/env python3
"""Assemble the PS1 source layers without a ROM or extracted game assets.

The manifest pins every copied file, patch input and patch result. --check
performs the complete assembly in a temporary directory. --output publishes
only after validation succeeds, and refuses to replace an existing directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile


PS1_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PS1_ROOT / "tools/source_manifest.json"


class PreparationError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative(value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PreparationError(f"invalid manifest path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value or value == ".":
        raise PreparationError(f"unsafe manifest path: {value!r}")
    return Path(*path.parts)


def verified_source(root: Path, entry: dict) -> bytes:
    path = root / relative(entry["source"])
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise PreparationError(f"missing or unsafe source: {entry['source']}")
    expected = entry["sha256"]
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise PreparationError(f"invalid SHA-256 for {entry['source']}")
    data = path.read_bytes()
    if digest(data) != expected:
        raise PreparationError(f"source hash mismatch: {entry['source']}; review and update the manifest deliberately")
    return data


def assemble(root: Path = PS1_ROOT, manifest_path: Path = MANIFEST,
             output: Path | None = None) -> dict:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != 1 or not manifest.get("files"):
        raise PreparationError("unsupported or empty source manifest")
    patch_tool = shutil.which("patch")
    if manifest.get("patches") and not patch_tool:
        raise PreparationError("missing tool: patch (the standard unified-diff utility)")
    if output is not None:
        output = output.absolute()
        if output.exists() or output.is_symlink():
            raise PreparationError(f"output already exists: {output}; choose a new directory")
        output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ps1-prepare-",
                                     dir=output.parent if output is not None else None) as temp:
        temporary = Path(temp)
        tree = temporary / "source"
        tree.mkdir()
        copied = set()
        for entry in manifest["files"]:
            target = relative(entry["target"])
            if target.as_posix() in copied or target == Path("SOURCE_MANIFEST.json"):
                raise PreparationError(f"duplicate or reserved output: {target}")
            data = verified_source(root, entry)
            destination = tree / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            copied.add(target.as_posix())
        for index, entry in enumerate(manifest.get("patches", [])):
            target = relative(entry["target"])
            if target.as_posix() not in copied:
                raise PreparationError(f"patch target is not a source file: {target}")
            destination = tree / target
            if digest(destination.read_bytes()) != entry["input_sha256"]:
                raise PreparationError(f"patch input hash mismatch: {target}")
            patch = temporary / f"{index}.patch"
            patch.write_bytes(verified_source(root, entry))
            result = subprocess.run(
                [patch_tool, "--batch", "--fuzz=0", "--no-backup-if-mismatch",
                 str(destination), str(patch)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode:
                raise PreparationError(f"patch failed: {entry['source']}\n{result.stdout}{result.stderr}")
            if digest(destination.read_bytes()) != entry["result_sha256"]:
                raise PreparationError(f"patch result hash mismatch: {target}")
        record = {
            "schema": 1,
            "profile": manifest["profile"],
            "base_commit": manifest["base_commit"],
            "manifest_sha256": digest(manifest_bytes),
            "files": {name: digest((tree / name).read_bytes()) for name in sorted(copied)},
        }
        (tree / "SOURCE_MANIFEST.json").write_text(json.dumps(record, indent=2) + "\n")
        if output is not None:
            # Temporary assembly is a sibling on the same filesystem. A source
            # or patch failure never leaves a partially prepared destination.
            if output.exists() or output.is_symlink():
                raise PreparationError(f"output appeared during preparation: {output}")
            tree.rename(output)
        return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="verify and assemble in a temporary directory")
    action.add_argument("--output", type=Path, help="new directory for the assembled source tree")
    args = parser.parse_args()
    try:
        record = assemble(output=args.output)
    except (PreparationError, OSError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as error:
        parser.exit(1, f"PS1 preparation: {error}\n")
    print(f"Verified {len(record['files'])} source files: {record['profile']}")
    if args.output:
        print(f"Prepared {args.output.resolve()}")
    print("Source only. Run the assembled ps1rt/build.sh --check with ROM set to inspect private build prerequisites.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
