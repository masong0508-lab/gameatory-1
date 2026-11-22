#!/bin/sh
# Rebuilds paybackmod/editor.bin and editor.json from hook.s and editor.c (needs clang and ld.lld).
set -eu
cd "$(dirname "$0")"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
# Compile a snapshot, then check that those same sources are still current before
# replacing the checked-in artifact. An edit during compilation must not produce
# metadata claiming that older machine code was built from the newer source.
cp editor.c hook.s link.ld build.sh "$T/"
clang --target=armv4t-none-eabi -mthumb -mcpu=arm7tdmi -Os -ffreestanding -fno-builtin -fno-stack-protector -nostdlib -c "$T/editor.c" -o "$T/editor.o"
clang --target=armv4t-none-eabi -c "$T/hook.s" -o "$T/hook.o"
ld.lld -T "$T/link.ld" "$T/hook.o" "$T/editor.o" -o "$T/editor.elf"
llvm-objcopy -O binary "$T/editor.elf" "$T/editor.bin"
if command -v llvm-nm >/dev/null; then
    llvm-nm "$T/editor.elf" > "$T/symbols"
else
    nm "$T/editor.elf" > "$T/symbols"
fi
python3 - "$T" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

temporary = Path(sys.argv[1])
root = Path.cwd().parent
sys.path.insert(0, str(root))
from paybackmod.rom import RUNTIME_SOURCES, validate_runtime

code = (temporary / 'editor.bin').read_bytes()
symbols = {}
for line in (temporary / 'symbols').read_text().splitlines():
    parts = line.split()
    if len(parts) == 3 and parts[2] in ('hook', 'cols', 'maps'):
        symbols[parts[2]] = int(parts[0], 16)
metadata = dict(symbols, format_version=1, code_size=len(code),
                code_sha256=hashlib.sha256(code).hexdigest(),
                source_sha256={name: hashlib.sha256((temporary / Path(name).name).read_bytes()).hexdigest()
                               for name in RUNTIME_SOURCES})
validate_runtime(code, metadata, source_root=root)
encoded = (json.dumps(metadata, indent=2, sort_keys=True) + '\n').encode()
for name, data in (('editor.bin', code), ('editor.json', encoded)):
    destination = root / 'paybackmod' / name
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.editor-', delete=False) as output:
        output.write(data)
        pending = Path(output.name)
    try:
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)
print(f'Compiled {len(code)} runtime bytes; source hashes and injection layout verified')
PY

