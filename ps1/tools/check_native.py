#!/usr/bin/env python3
"""Compile and link the combined native PS1 modules without game assets.

Uses the real linker script and the interpreter-enabled title-boot flags of the
release profile (single-page CD fetches, no menu assist) and of the KPLAN test
profile. Generated guest tables are minimal placeholders: this checks native
module compatibility, fixed RAM regions and that every linked function is
R3000A code (ps1/tools/mips1_lint.py), not a runnable game or final disc layout.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from prepare import PS1_ROOT, PreparationError, assemble


SYMBOLS = """
/* Code-layout fixture: no guest program or game data. Never a runnable build. */
unsigned GUEST_MAIN_HOST = 0;
const unsigned COLD_HOST=0, HASH_HOST=0, HASH_NSLOTS=0, ARMTAB_N=0;
const unsigned ARMTAB[1]={0}, STUBTAB[1]={0}, STUBTAB_N=0;
const unsigned RT_BX_HOST=0, RT_STUB_HOST=0;
const unsigned CD_ROM_LBA=0, CD_COLD_LBA=0, CD_COLD_PAGES=0;
const unsigned CD_SNAPST_LBA=0, CD_SF3W_LBA=0, CD_SF3W_SECS=0;
const unsigned CD_SF3A_LBA=0, CD_SNAP_LBA=0, CD_SNAP_N=0;
const unsigned char bootimg[4] __attribute__((section(".bootimg")))={0};
const unsigned coldtab[1] __attribute__((section(".coldtab")))={0};
const unsigned rompack[1] __attribute__((section(".rompack")))={0};
"""


def main() -> int:
    names = {"cc": os.environ.get("PS1_CC", "clang"), "ld": os.environ.get("PS1_LD", "ld.lld"),
             "objcopy": os.environ.get("PS1_OBJCOPY", "llvm-objcopy"),
             "nm": os.environ.get("PS1_NM", "llvm-nm")}
    for name in names.values():
        if not shutil.which(name):
            raise PreparationError(f"missing tool: {name}")
    common = ("--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float "
              "-fno-pic -ffreestanding -G0 -mno-gpopt -mno-check-zero-division -Wno-unused-command-line-argument "
              "-mllvm -disable-mips-delay-filler").split()
    with tempfile.TemporaryDirectory(prefix="ps1-native-check-") as temp:
        tree = Path(temp) / "source"
        assemble(output=tree)
        objects = tree / "native-check"
        objects.mkdir()

        def run(label: str, *command: str) -> str:
            result = subprocess.run(command, cwd=tree, text=True, capture_output=True, timeout=180)
            if result.returncode:
                raise PreparationError(f"{label} failed:\n{result.stdout}{result.stderr}")
            return result.stdout

        def compile_source(source: str, name: str, flags: list[str], prefix: str = "") -> str:
            target = f"native-check/{name}.o"
            run(f"compile {source}", names["cc"], *common, *flags, "-c", source, "-o", target)
            if prefix:
                run(f"prefix {name}", names["objcopy"], f"--prefix-alloc-sections={prefix}", target)
            return target

        # release profile (tools12/build.sh): single-page CD fetches, no menu assist, no PADDBG log; the TEST profile adds KPLAN and PADDBG
        runtime = ["-Os", "-DSF3_DEFER", "-DPCACHE1", "-Iinterp"]
        test_runtime = [*runtime, "-DKPLAN", "-DPADDBG", "-Iout/kp"]
        cluster_runtime = ["-Os", "-DSF3_DEFER", "-DPADDBG", "-Iinterp"]
        renderer = ["-Os", "-DSF_NOLIBC", "-fomit-frame-pointer", "-mno-check-zero-division", "-Isf"]
        ragdoll = ("-O3 -mllvm -inline-threshold=500 -fomit-frame-pointer -mno-check-zero-division "
                   "-DRP_LEVEL=2 -DRP_NS_BASE=3 -DRP_NS_DIV=10 -DRP_NSMAX=6 -DRP_HINGE_LAST=1 "
                   "-DRP_FAST=1 -Ird").split()
        modules = [compile_source("ps1rt/rt.c", "runtime", runtime),
                   compile_source("ps1rt/crt0.s", "startup", []),
                   compile_source("interp/interp.c", "interpreter", ["-Os", "-Iinterp"]),
                   compile_source("interp/interp_asm.s", "interpreter_asm", []),
                   compile_source("sf/sf3.c", "renderer", renderer, ".sf"),
                   compile_source("rd/doll.c", "ragdoll", ragdoll, ".dl"),
                   compile_source("sf/sfdata.s", "renderer_data", [])]
        (objects / "symbols.c").write_text(SYMBOLS)
        modules.append(compile_source("native-check/symbols.c", "symbols", ["-Os"]))
        lint = PS1_ROOT / "tools" / "mips1_lint.py"

        def link_and_report(label: str, elf: str, objects_: list[str]) -> None:
            run(f"{label} layout link", names["ld"], "--defsym=ip_stacks=0x8002c000", "-T", "ps1rt/ps1.ld",
                *objects_, "-o", elf)
            symbol_text = run(f"read {label} layout symbols", names["nm"], "--defined-only", elf)
            symbols = {parts[2]: int(parts[0], 16) for line in symbol_text.splitlines()
                       if len(parts := line.split()) == 3}
            for name, start, end, limit in (("Runtime", 0x80010000, "__bss_end", 0x80028000),
                                            ("Ragdoll", 0x80163000, "__dlbss_end", 0x8017a000),
                                            ("Renderer", 0x80199000, "__sfbss_end", 0x801b0000)):
                used = symbols[end] - start
                print(f"{label} {name}: {used:,} / {limit - start:,} bytes; {limit - symbols[end]:,} bytes free")
            if symbols["__ppu_start"] != 0x8017a000 or symbols["__veneer_scratch"] != 0x8017b000:
                raise PreparationError("unexpected PPU/veneer scratch allocation")
            print(run(f"{label} R3000A instruction check", sys.executable, str(lint), elf).strip().splitlines()[-1])

        link_and_report("Release", "native-check/layout.elf", modules)
        test_modules = [compile_source("ps1rt/rt.c", "test_runtime", test_runtime), *modules[1:]]
        link_and_report("Test (KPLAN)", "native-check/test-layout.elf", test_modules)
        print("Native module compile/link passed with explicit PS1 RAM allocations.")

        def reject(label: str, expected: str, *command: str) -> None:
            result = subprocess.run(command, cwd=tree, text=True, capture_output=True, timeout=180)
            if result.returncode == 0 or expected not in result.stdout + result.stderr:
                raise PreparationError(f"{label} did not fail for the expected reason:\n{result.stdout}{result.stderr}")

        reject("partial CD-fetch group", "NSLOT must be", names["cc"], *common, *cluster_runtime,
               "-DNSLOT=3", "-c", "ps1rt/rt.c", "-o", "native-check/invalid-cache.o")
        reject("empty single-page cache", "NSLOT must be at least one", names["cc"], *common, *runtime,
               "-DNSLOT=0", "-c", "ps1rt/rt.c", "-o", "native-check/invalid-cache1.o")
        compile_source("ps1rt/rt.c", "cluster_runtime", cluster_runtime)
        cache64 = compile_source("ps1rt/rt.c", "cache64", [*runtime, "-DNSLOT=64"])
        reject("cache/ragdoll overlap", "ROM page cache overlaps ragdoll code", names["ld"],
               "--defsym=ip_stacks=0x8002c000", "-T", "ps1rt/ps1.ld", cache64, *modules[1:],
               "-o", "native-check/invalid-cache.elf")
        (objects / "oversized.c").write_text('unsigned char guard_probe[0x6000];\n')
        oversized = compile_source("native-check/oversized.c", "oversized", [], ".dl")
        reject("ragdoll/scratch overlap", "ragdoll code overlaps PPU scratch", names["ld"],
               "--defsym=ip_stacks=0x8002c000", "-T", "ps1rt/ps1.ld", *modules, oversized,
               "-o", "native-check/invalid-scratch.elf")
        print("Rejected partial CD-fetch groups, an empty single-page cache, cache/ragdoll overlap and ragdoll/scratch overlap.")
        # Discovery runs all translated cold code in a 16 MiB simulator. Its
        # deliberate virtual cache is legal only in the simulator linker, and
        # the full-cold profile does not need interpreter fallback.
        simulator = ["-Os", "-DNO_INTERP", "-DCDSIM", "-DNOSF3", "-DKPLAN", "-Iout/kp",
                     "-DTESTFAST", "-DPRESENT_EVERY=2", "-DCOLDGROUPS=512", "-DNSLOT=512"]
        sim_runtime = compile_source("ps1rt/rt.c", "simulator_runtime",
                                     [*simulator, "-DPCACHE_ADDR=0x80600000"])
        sim_modules = [sim_runtime, modules[1], *modules[4:]]
        run("full-cold simulator layout", names["ld"], "-T", "ps1rt/ps1_f.ld",
            *sim_modules, "-o", "native-check/simulator.elf")
        run("simulator R3000A instruction check", sys.executable, str(lint), "native-check/simulator.elf")
        for script in ("ps1rt/ps1.ld", "ps1rt/ps1_probe.ld"):
            reject("virtual cache in physical layout", "ROM page cache overlaps ragdoll code", names["ld"],
                   "-T", script, *sim_modules, "-o", "native-check/invalid-physical.elf")
        too_high = compile_source("ps1rt/rt.c", "invalid_simulator_runtime",
                                  [*simulator, "-DPCACHE_ADDR=0x807ff000"])
        reject("virtual cache beyond simulator window", "simulator page cache must", names["ld"],
               "-T", "ps1rt/ps1_f.ld", too_high, *sim_modules[1:],
               "-o", "native-check/invalid-simulator.elf")
        print("Full-cold simulator links; both physical linkers reject its virtual cache, and its upper bound is enforced.")
        print("Generated tables/assets are placeholders. This is not a game boot, speed or final disc test.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PreparationError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"PS1 native check: {error}")
