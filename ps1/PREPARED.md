# Prepared Payback PS1 sources

This is the source assembly of the stage16 runtime with the stage17 model/tree
changes, stage18 model refinements and the stage19 fixes for accurate
emulators (GPU handshake, MIPS-I code, pad, CD driver, safe area, page cache).
`SOURCE_MANIFEST.json` records its exact
file hashes and the manifest used to prepare it. No game ROM, extracted assets,
translation, executable, or disc image is included.

The supported build driver is `ps1rt/build.sh`. Run its preflight first:

```sh
ROM=/absolute/path/to/Payback-Europe.gba sh ps1rt/build.sh --check
```

Preflight lists absent tools and generated inputs. A complete build needs
Clang/LLD/LLVM objcopy with MIPS-I support, Python 3, `genisoimage`, `isoinfo`,
an 8 MiB Payback Europe ROM, and private generated files:

- `out/boot.bin` and `out/SF3M.BIN`;
- `out/pr/{payback_P.map,payback_P.bin,meta_P.pkl,coldtab_P.bin,rompages_P.pkl}`;
- `out/s2/prog_pr.pkl`, or an explicit `PROGPKL` path;
- `out/pr/cold_P.bin` when the selected translation uses cold overlays;
- `t/swi5.bin`, the 56-byte ARM stub that packaging reads; it is not stored in
  the repository. Assemble it once, with a Clang that has the ARM target:
  `clang --target=armv4t-none-eabi -c t/swi5.s -o out/swi5.o && llvm-objcopy -O binary --only-section=.text out/swi5.o t/swi5.bin`;
- snapshot files only for snapshot build modes.

`PRD`, `BOOT`, `NAME`, `BLD`, `CFL`, `SFOPT`, and other documented build environment
variables select the private translation and build profile. `tools12/build.sh NAME`
builds the release profile: title boot (`pr_lb`, world layout `pr_l`), the 62
resident ROM pages of `t/resident62.txt`, no menu assist and no pad/entity debug
log; it therefore needs those matching generated inputs. `tools12/build_test_assist.sh NAME`
builds the same sources with the KPLAN menu assist (`out/kp/kplan.h`), which presses
menu keys by itself, and the `PADDBG` log (PADRAW/GS/GN lines on the TTY): a TEST
variant for timed emulator sessions, never a release. These
profiles are not interchangeable. Every build checks the linked `payback.elf`
with `tools/mips1_lint.py` and fails on an instruction the R3000A lacks.

```sh
ROM=/absolute/path/to/Payback-Europe.gba NAME=payback sh ps1rt/build.sh
```

Successful builds publish `out/payback.exe` and `out/payback.iso` after both disc
passes agree on file sectors. A failed build keeps the earlier outputs and
reports its complete diagnostic log directory. Outputs contain private game
data and belong outside source control.

The renderer uses `-Os` by default so the combined models and trees fit the
existing RAM region. Other optimization settings still have to pass the linker
assertions. Performance and final generated-table sizes require a real build
and emulator measurement.

Historical scripts are retained as source references; `build_ps1.sh` is an old
snapshot-oriented orchestration script, not a verified one-command release
pipeline. Source assembly does not run those scripts. See the repository's
`ps1/STATUS.md` for the current handoff, missing runtime acceptance tests, and
remaining merged Stunt Fox port work. The current runtime supports an 8 MiB
ROM window; passing the larger merged ROM is rejected.
