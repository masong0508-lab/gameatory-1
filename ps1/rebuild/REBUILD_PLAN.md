# PS1 port at PR #1 head (d02652a): private inputs, reuse proof and rebuild plan

Written 2026-11-22 (PS1 part 1 of 2). Machine: clang/ld.lld 18.1.3 by default, LLVM 19.1.1 also installed
(`/usr/lib/llvm-19/bin`). Names used below: `TREE` is a prepared tree (`python3 ps1/tools/prepare.py --output TREE`),
`ROM` the untouched 8 MiB Payback (Europe) cartridge image, `SURV` the directory of surviving private inputs, listed
file by file in `private_inputs.sha256`. The run logs named below (`01_prepare_check.log` ...) stayed with the private
files outside the repository: they show the game's output. Everything in `TREE/out`, `SURV` and the logs derives from
the ROM and is never committed. The plan describes the PR head; section 9 says how the current release is built.

## 0. Bottom line

1. The four ROM-free checks pass with LLVM 18.1.3. The native sizes differ from STATUS.md only because of the
   compiler: with LLVM 19.1.1 they are exactly the PR's numbers.
2. **Every private input of the title-boot build survives and is valid UNCHANGED for the PR's RAM/VRAM layout.**
   Shown three ways: address ranges inside the files (`verify_inputs.py`: 0 failed checks), regeneration with the
   PR tree and the new gap (byte-identical files), and a real strict-linker build that boots.
3. **Track A (section 3) is the way to build: 11 seconds.** Track B (section 5) regenerates everything from the ROM
   and is a verification exercise only; all of it except two simulator runs has already been executed here.
4. Three things had to be worked around at the PR head (section 6): `t/swi5.bin` is missing and not checked,
   `t/rebuild_f1.sh` still translates with the old gap, and the disc packer in the PR (unchanged from the base)
   writes the licence text to the wrong sector. Commit d0d0010 of the main line fixes all three; `t/swi5.bin` still
   has to be assembled, which both track scripts do.

## 1. Check results

| Check | Result | Log |
| --- | --- | --- |
| `python3 ps1/tools/prepare.py --check` | exit 0, "Verified 149 source files"; the manifest's 6 patches apply with `--fuzz=0` and matching input/result hashes | `01_prepare_check.log` |
| `python3 -m unittest discover -s ps1/tests -v` | 22 tests, all ok, none skipped (3.9 s) | `02_unittest.log` |
| `python3 ps1/tools/check_native.py`, LLVM 18.1.3 | exit 0. Runtime 96,036 / 98,304; ragdoll 79,492 / 94,208; renderer 90,652 / 94,208. All rejection cases behave as STATUS.md says | `03_check_native.log` |
| same, LLVM 19.1.1 | exit 0. Runtime 96,180; ragdoll 78,564; renderer 92,316 = STATUS.md's table exactly | `25_check_native_llvm19.log` |
| `prepare.py --output TREE` | exit 0, 149 files + `SOURCE_MANIFEST.json` | `04_prepare_output.log` |
| `ROM=... sh ps1rt/build.sh --check` in `TREE` (nothing staged) | exit 1 as expected: 8 "Missing input" lines (`out/boot.bin`, `out/SF3M.BIN`, five `out/pr/*`, `out/s2/prog_pr.pkl`); no missing tool | `05_preflight_empty.log` |
| same preflight with `PRD=pr_lb` after staging (Track A) | exit 0, "PS1 build inputs and commands are present" | `27_trackA_validation.log` |

LLVM 18 against the PR's LLVM 19 numbers: runtime -144 bytes, ragdoll +928, renderer -1,664. Every linker assertion
passes with both compilers; the margins are small either way. In the real build (Track A) the figures are:

| | LLVM 18.1.3 (default here) | LLVM 19.1.1 | STATUS.md (19.1.7) |
| --- | --- | --- | --- |
| runtime, of 98,304 | 96,176 (2,128 free) | 96,320 (1,984 free) | 96,320 (1,984 free) |
| ragdoll (base 0x80160000) | 79,492 (27,004 below the scratch) | 78,564 | 78,564 (native table) |
| renderer, of 94,208 | 90,652 (3,556 free) | 92,316 (1,892 free) | 92,316 (native table) |
| EXE | 1,691,648 bytes, sha256 `55e534290e4356e6d95675fc56e8df140d5437489e37adb9c7a8ab32ff26b652` | 1,693,696 bytes, `3cc2f0858121da5d728affeca578b1dc23244bedec27f6d8255819ab597799ae` | `9bd2ac66...` (not reproduced) |
| disc LBAs (ROM, COLD, pages, SF3M) | 1209, 24, 180, 5305 | 1210, 24, 180, 5306 | not stated |

The EXE is deterministic (same hash from three builds and two output names). The ISO is not: `genisoimage` stores
the build time, so two builds of identical inputs gave different ISO hashes; STATUS.md's ISO hash cannot be
reproduced by anyone. The PR's EXE hash was not reproduced with either compiler although the runtime size matches
to the byte with LLVM 19; the cause (19.1.1 against 19.1.7, or different private inputs on the author's side) cannot
be decided without the author's files.

Not in the task but done as plan validation (bounded, `29_emu_smoke_trialA.log`, `30_disc_step_validation.log`):
the Track A image boots in PCSX-ReARMed (libretro, HLE BIOS): the language selection screen is shown from frame 600
to 3600; with Cross presses it goes on through the licence screen and the publisher's logo to the title menu.
That reproduces STATUS.md's boot checkpoint. Gameplay on the new layout was not tested.

## 2. Verdict for each private input

"Reuse" means: copy the surviving file, no regeneration needed. Surviving copies (private, outside the repository):
the stage 18 input directory that v3 used (`SURV`; every file is listed in `private_inputs.sha256`) and the complete
`out/` directory of the stage 7 pipeline with its logs (identical files).

| Input (in `TREE/out` unless noted) | Made by | What ties it to the layout | Verdict and proof | Regenerate: command, time |
| --- | --- | --- | --- | --- |
| `t/swi5.bin` (in the tree, 56 bytes) | clang ARM + objcopy from `t/swi5.s` | nothing | Not in the repository or the prepared tree: must be assembled. Result equals the v3 and stage 7 copies (sha256 `1ef66d21718d657c`) | step b0, under 1 s |
| `out/kp/kplan.h` (pad plan) | checked in (`stage16/merge/out_kp/kplan.h`) | nothing | Already in the prepared tree (`864279772c8ced4e`). Do not regenerate the stage 7 way: that drops `KPLB`/`KPLC`, which `rt.c` uses (`16_kplan.log`) | none |
| `s2/prog_pr.pkl` (guest discovery, 220,981 instructions, 27.4 MB) | `tools7/mkprog.py` | guest addresses only | Reuse. Regenerated byte-identical (`98e3fb9586bd5291`), `21_regen_checks.log` | b2, 35 s |
| `iw.bin`, `cov_L3.pkl`, `s2/resident.pkl`, `s2/cold.pkl`, `cold_all.pkl` (IWRAM image, coverage, hot set, cold sets) | `tools7/mkiw.py`, `tools7/explore.py`, `mkresident.py`, `mkcold.py`, `tools7/mkcoldall.py` | guest addresses only | Only translation needs them. All regenerated byte-identical (`9b294845`, `b422f240`, `4cf20559`, `572d2fb0`, `32c72d80`), `20_regen_sets.log`, `21_regen_checks.log` | b1, b3, b4: 1 s, 170 s, 3 s |
| `boot.bin` (boot state, 396,448 bytes) | `t2m.py` profile `pr_b`, then `lockstep2.py ... P 3` | guest registers and guest RAM; sp `0x801f7f00` is in the unchanged IWRAM window; lr `0x800325c0` is a hot-blob address that guest main never returns to; exactly one other host-like word, in the guest windows | Reuse. Regenerated byte-identical (`1b264ca5a9cee352`) with 3 matching ARM/MIPS snapshots, 3,196 I/O events each. `06_verify_inputs.log`, `21_regen_checks.log` | b5, 20 s |
| `SF3M.BIN` (11 worlds, 5,847,040 bytes, 2,855 sectors) | merged GBA cartridge (`stuntfox/build.py --merge --no-remixes --amiga DIR`), then `tools7/dumpworld.py` x 11, `tools7/mkmaps7.py` | texture rectangles in VRAM and the size of the world window | Reuse. Its atlas pages use only the 7 world slots at (320..832, 0) and (320..448, 256), the font (960,0,32x48) and CLUT rows the PR left alone; nothing touches the moved model atlas (960,64) or the PPU pages (576/704/832,256). Largest world (map 1) is 239,616 bytes = the window. The 11 world blobs in today's PR-head cartridge are byte-identical to the stage 7 ones, and `SF3M.BIN` rebuilt from the PR-head cartridge is byte-identical (`87e0ea7eae36caaa`). `18_worlds_compare.log`, `19_sf3m_regen.log` | b7, 20 s plus 90 s if the cartridge must be built. The cartridge MUST be built with `--amiga`: without it maps 0, 1 and 3 differ |
| `pr_lb/{payback_P.bin, payback_P.map, meta_P.pkl, cold_P.bin, coldtab_P.bin}` (title-boot translation: hot blob 85,128 bytes; cold overlay 734,828 bytes, 952 rows, 45 groups) | `t2m.py` twice (`pr_f2b`, then the prefix `pr_lb`) from the simulator's function lists | host addresses: blob `0x80030000`, helpers `0x80028000`, draw ring `0x8017c000`, guest windows, cold home `0x80044c88..0x800f82f4` | Reuse. All bases are unchanged in the PR's `rt.c`/`ps1.ld`; highest cold address is 531,736 bytes below the new scratch at `0x8017a000`; no constant in the code points into the scratch or the renderer. Re-translated with the PR tree and the NEW gap: all five files byte-identical. `06_verify_inputs.log`, `17_regen_compare.log` | b8 to b10, 85 s once the simulator lists exist |
| `pr_l/{meta_P.pkl, cold_P.bin}` (level tier: 558,588 bytes; fixes the world window at `0x800cd800`) | `t2m.py` twice (`pr_f2`, `pr_l`) | same as above | Reuse; byte-identical after re-translation. Headroom: the prefix may grow by 1,404 bytes before `t/worldaddr.py` refuses | b11, 85 s |
| `touched_f1_boot.pkl.rompages` (which guest ROM pages the boot path reads: 99 pages) | simulator run `TOUCH_FROM=boot t/snapdump.py f1 60 1500 ...` | guest page numbers only | Reuse (`23ca44c013506c60`). `t/mkrompages.py` turns it into the 56 preloaded pages at build time: cache at `0x80158000`, 8 slots, ragdoll at `0x80160000` | b9, the long part |
| `pr_lb/rompages_P.pkl` | `t/mkrompages.py`, run by `t/disc7.sh` in every build | - | Do not copy it (the copy in `SURV` is a different list); the build writes it | part of the build |
| simulator-only files: `pr_f1`, `pr_f2`, `pr_f2b` translations, `f1.exe`, `SNAPST*.BIN` | `t2m.py` with `COLD_GAP`, `ps1rt/build.sh` with `LD=ps1_f.ld` | **the excluded range** | Not needed for the build. The surviving ones are INVALID for the new layout: made with gap `0x8017c000`, they put 1, 10 and 8 code spans into the new scratch (`0x8017a000..0x8017c000`). Regenerated with gap `0x8017a000,0x80200000`: 0 of 3,299 spans in the range | b8, b10, b11 |
| simulator results: `touched_f1*.pkl`, `rank_*.pkl` | `t/snapdump.py`, `t/mkrank.py` | guest addresses only | Valid as they are (they reproduce `pr_lb`/`pr_l` exactly with the new gap). Kept with the private files | b9, b10 |

## 3. Track A: build from the surviving inputs (validated end to end, 11 s)

Inputs: the prepared tree, the ROM, fourteen files from `SURV`. Outputs: `TREE/out/NAME.exe`,
`TREE/out/NAME.iso` (data track only), `TREE/out/bld_NAME/payback.elf`, step logs in `TREE/out/bld_NAME/logs/`.

```sh
export ROM=/path/to/payback.gba SURV=/path/to/private/inputs     # both outside the repository
python3 ps1/tools/prepare.py --output "$TREE"                    # from the top of the repository; TREE must not exist yet
ps1/rebuild/track_a_reuse.sh "$TREE" payback_rc ""
```

What the script does, in order, with the checks it enforces:

1. A1 copies `boot.bin`, `SF3M.BIN`, `touched_f1_boot.pkl.rompages`, `s2/prog_pr.pkl`, five files each of `pr_lb`
   and `pr_l` into `TREE/out` and compares 13 sha256 prefixes (exit 3 on any mismatch).
2. A2 assembles `t/swi5.bin` (`clang --target=armv4t-none-eabi -c t/swi5.s -o out/swi5.o && llvm-objcopy -O binary
   --only-section=.text out/swi5.o t/swi5.bin`) and checks it and `out/kp/kplan.h`.
3. A3 runs `verify_inputs.py out .`: expected last line `RESULT: 0 failed checks`.
4. A4 writes `out/pr_lb/rompages_P.pkl` (`t/mkrompages.py ... 56 ...`: "pages touched 99, in rompack 56 (224 KiB),
   PCACHE_ADDR=0x80158000"), runs `PRD=pr_lb sh ps1rt/build.sh --check`, then `bash tools12/build.sh NAME ""`
   (= `NPAGES=56 PRD=pr_lb WORLDPRD=pr_l RPG=out/touched_f1_boot.pkl.rompages VOL=PAYBACK bash t/disc7.sh NAME
   "-DSF3_DEFER -DPADDBG" 0`). Expected last line: `Built ../out/NAME.exe and ../out/NAME.iso; disc LBAs:
   1209,24,180,5305,5305,0,0`.
5. A5 prints sizes and hashes. Expected with LLVM 18.1.3: EXE 1,691,648 bytes, sha256 `55e534290e4356e6...`;
   runtime ends `0x800277b0`; page cache `0x80158000..0x80160000`; ragdoll `0x80160000..0x80173684`; renderer ends
   `0x801af21c`; ISO files COLD.BIN (734,828 bytes, sector 24), PSX.EXE (383), ROM.BIN (1209), SF3M.BIN (5305),
   SYSTEM.CNF (8160).

To build with LLVM 19 instead: prefix the script call with `PATH=/usr/lib/llvm-19/bin:$PATH` (expected EXE
`3cc2f0858121da5d...`, runtime 96,320 bytes). v3 and the PR's own image were built with `-DPADDBG`; `PADDBG=` in
the environment removes it (runtime 93,712 bytes with LLVM 19).

## 4. Disc image and emulator check (validated with 2 s of audio per track)

At the PR head both copies of the packer (`ps1/stage5/discpack/mkdisc2.py` and the prepared tree's
`tools7/mkdisc2.py`, the same in the base and in the PR) wrote the licence string to sector 0. The validation used the
corrected packer, which puts it in sector 4 as the PlayStation disc format requires. Both copies have the fix since
commit d0d0010, so the `tools7/mkdisc2.py` of a tree prepared from the main line is the one to use.

```sh
OUT=/path/outside/the/repository/disc && mkdir -p "$OUT"
python3 "$TREE/tools7/mkdisc2.py" --iso "$TREE/out/payback_rc.iso" --out "$OUT/payback_rc_E" --region E --default-tracks
python3 ps1/stage5/discpack/verify_disc.py "$OUT/payback_rc_E.cue"     # expected: RESULT PASS, 15 tracks (1 data + 14 audio)
```

`--default-tracks` reads the 11 `(PS1 remix final).mp3` files in the directory `MUSIC_MODS` names and Songs 1, 2, 4
in `MUSIC_PB` (the owner's remixes, read only, not in the repository; set both variables to the owner's music folders)
through ffmpeg. The full disc is about 593 MiB, so check the free space first and delete it when a CHD has been made.
`--region U` gives the NTSC variant (the core then runs at 60 instead of 50 frames per second). `--seconds 2` makes a
28 MiB test disc in 10 s. Validated: `30_disc_step_validation.log`.

Emulator (the headless libretro rig in `ps1/rig/`, 3,600 frames in 7 s; setup in `ps1/rig/README.md`, a short
description in `00_READ_ME_FIRST_FAST_EMULATOR.md`):

```sh
cd ps1/rig && python3 -B retro_ps1.py pcsx_rearmed "$OUT/payback_rc_E.cue" runs/smoke 3600 \
    --shots 600,1200,2400,3600 --opt pcsx_rearmed_bios=HLE
```

Expected: `frames 3600 video (320, 240)`, `core.log` shows the 15 tracks and `manual booting 'PSX.EXE;1'`, and
`f003600.png` shows the language selection screen with its five languages (the reference pictures stayed with the
private files). A probe that pressed Cross 15 times reached the title menu (the rig's `sessions/boot_to_title.py`
does this now). In that probe four more Cross presses left the title menu on screen; whether starting a game needs a
longer press, another button or the menu assist was not looked into. Reaching a level, saving, audio and frame rate on
the new layout are all still open (part 2).

## 5. Track B: regenerate everything from the ROM (draft; only needed to re-verify)

Inputs: the prepared tree, the ROM, the owner's Amiga Payback folder with `maps/` (`AMIGA`) and a checkout of the
repository (`REPO`, for the GBA build). No surviving file is read except for comparisons (`SURV`; `SURV=` skips them).
Outputs: all of section 2 in `TREE/out`, then the same EXE/ISO as Track A. Use a fresh tree so Track A's tree stays as
a reference:

```sh
python3 ps1/tools/prepare.py --output "$TREE_B"
export ROM=/path/to/payback.gba AMIGA=/path/to/amiga/payback REPO="$PWD" SURV=/path/to/private/inputs
nohup ps1/rebuild/track_b_regenerate.sh "$TREE_B" > "$TREE_B.log" 2>&1 &
# or step by step:  ps1/rebuild/track_b_regenerate.sh "$TREE_B" b0 b1 b2 ...
```

| Step | Command (see the script for the exact line) | Output | Expected check | Time here |
| --- | --- | --- | --- | --- |
| b0 | tools, `t/swi5.bin`, `out/kp/kplan.h` | `t/swi5.bin` | sha256 `1ef66d21...`, `86427977...` | 1 s |
| b1 | `tools7/mkiw.py ROM out/iw.bin` | `iw.bin` | `9b294845...` | 1 s |
| b2 | `python3 -I tools7/mkprog.py` | `s2/prog_pr.pkl` | "prog ok 220981", `98e3fb95...` | 35 s |
| b3 | `python3 -I tools7/explore.py L3 3000 "[...]" ""` | `cov_L3.pkl` | "end tick 3000 swis 91 dl 6425 demand 0", `b422f240...` | 168 to 187 s |
| b4 | `mkresident.py`, `tools7/mkcoldall.py`, `mkcold.py ... 85000` | `s2/resident.pkl`, `cold_all.pkl`, `s2/cold.pkl` | "resident 85 insns 5980", "cold 2723", "cold 779 functions 84999 insns" | 3 s |
| b5 | `t2m.py ... out/pr_b --cache ... --cold out/s2/cold.pkl`; `BOOT=out/boot.bin lockstep2.py ROM out/pr_b P 3` | `boot.bin` | "io writes arm 3196 mips 3196 first mismatch None", 3 snapshots with 0 differences, `1b264ca5...` | 15 s |
| b6 | `t2m.py ... out/pr --cache ... --cold out/cold_all.pkl`; empty `out/pr/rompages_P.pkl` | `pr/` | hot blob 85,184 bytes, 3,299 cold rows | 10 s |
| b7 | GBA build in a private copy, 11 x `tools7/dumpworld.py`, `tools7/mkmaps7.py` | `SF3M.BIN` | world 0 has 1983 boxes, 436 ramps, 9 ladders; "SF3M.BIN sectors 2855"; `87e0ea7e...` | 118 s (about 95 s of it the GBA build) |
| b8 | `COLD_GAP=0x8017a000,0x80200000 t2m.py ... out/pr_f1`; simulator build `LD=ps1_f.ld NO_INTERP=1 ... -DNSLOT=512` | `pr_f1/`, `f1.exe`, `f1.iso` | 0 spans in the excluded range; hot blob `24034513...`; "disc LBAs: 5564,24,725,9660,9660,0,0" | 57 s |
| b9 | `TOUCH_FROM=level t/snapdump.py f1 60 1500 ...` and `TOUCH_FROM=boot ...` in parallel | `touched_f1.pkl`, `touched_f1_boot.pkl`, both `.rompages` | "LEVEL clock runs at gba frame 1103 map 0", "SNAPSHOT at gba frame 1165.7", "done frame 1501.70"; 4,949 and 9,006 labels; 58 and 99 pages | **not run**; stage 7 needed 4 min 12 s per run, the first 250 frames took 23 s here against 8 s then, so allow up to 12 min |
| b10 | `t/mkrank.py` twice, `t2m.py` twice | `rank_S0.pkl`, `rank_B.pkl`, `pr_f2b/`, `pr_lb/` | 172 and 289 functions; prefix identical to the full translation; five `pr_lb` files SAME | 90 s |
| b11 | `EXTRA_TOUCH=tools7/extra_touch.txt t/mkrank.py`, `t2m.py` twice, `t/worldaddr.py pr_l` | `rank_S.pkl`, `pr_f2/`, `pr_l/` | 216 functions; world window `0x800cd800`; `pr_l` files SAME | 90 s |
| b12 | `bash tools12/build.sh NAME ""` | `NAME.exe`, `NAME.iso` | EXE `55e53429...` with LLVM 18.1.3 | 11 s |
| hashes | every file of `private_inputs.sha256` found under `TREE/out`, by full sha256 | report only | SAME, except `kp/kplan.h` and `*/rompages_P.pkl`, which differ by design | 1 s |

Measured total without the simulator runs: 10 min 17 s. Status: the script was run from a fresh prepared tree
with every step executed for real except the two simulator runs of b9, whose four output files were taken from
stage 7 (`SEED_TOUCHED` set to the stage 7 output directory). Every regenerated input came out byte-identical to the
surviving file, including `pr_lb` and `pr_l`, and the final EXE is `55e534290e4356e6...`, the same as Track A
(`31_trackB_validation_seeded.log`). b9's own command line was exercised for 250 frames only
(`23_regen_f1link.log`: no exception, "frame 250 ... clk 0"). The `hashes` step was added afterwards.

That tree was kept with the private files, with b0 to b8 done (the bulky b7 intermediates were deleted,
`out/SF3M.BIN` is there). The shortest way to finish the proof is therefore to run only the open part in such a tree:

```sh
nohup ps1/rebuild/track_b_regenerate.sh "$TREE_B" b9 b10 b11 b12 hashes \
    > "$TREE_B.b9.log" 2>&1 &      # no SEED_TOUCHED: the simulator really runs
```

In a tree that was run with `SEED_TOUCHED`, `out/touched_f1*.pkl`, `pr_lb`, `pr_l` and `NAME.exe` come from the
seeded lists and are overwritten.

If b9 gives different label sets than stage 7 (the script prints SAME or DIFF): the runtime of the simulator
build changed since stage 7 (PPU layer, menu assist), so that is possible and not an error by itself. Then
(a) `pr_lb`/`pr_l` will differ from the surviving files; (b) `t/worldaddr.py` may fail, because the level tier may
grow by at most 1,404 bytes before the largest world no longer fits; (c) the new image needs its own emulator
pass. In that case the surviving translations remain the tested choice and Track A stays the release path.

Things the old scripts do that the script above deliberately does not:
- `t/rebuild_f1.sh` (old gap, see 6.1), `build_ps1.sh` (regenerates `kplan.h` without `KPLB`/`KPLC`, copies the
  whole repository, swallows a failed simulator build with `|| true`).
- `t/boot_chain.sh` and `t/final.sh` both write `out/rank_S.pkl`, with different contents (172 without and 216 with
  `tools7/extra_touch.txt`). Stage 7 ran `boot_chain.sh` first, which is why the shipped `pr_lb` has the
  172-function level tier and `pr_l` the 216-function one. The script keeps the two apart (`rank_S0.pkl`,
  `rank_S.pkl`) to reproduce exactly that.
- `t/f1_variants.sh` (six perturbed simulator runs, 11 minutes): with `extra_touch.txt` it adds no function.
- the f2 simulator run and `SNAPST.BIN`: only snapshot-resume discs need them.

## 6. Defects and pitfalls found

6.1 **Old gap left in three scripts (the PR's code).** `t/rebuild_f1.sh`, `t/mk_stage4.sh` and `t/step2to5.sh` still
set `COLD_GAP=0x8017c000,0x80200000`; only `t/final.sh` and `t/boot_chain.sh` were moved to `0x8017a000`, and
`ps1/tests/test_simulator_gap.py` looks at those two only. `rebuild_f1.sh` makes the translation every later step
reads. With the old gap one function (guest `0x0803b8a0`, host `0x801776d8..0x8017bdc4`) lies across the new PPU
and veneer scratch, and the simulator's copy routine leaves everything from `0x8017a000` on unloaded: the very
failure STATUS.md reports as fixed ("a cold function at 0x8017a25c"). Evidence: `17_regen_compare.log`,
`24_stale_gap.log`. Fixed in the main line by commit d0d0010 (three scripts, their manifest hashes, the test now
covers every script that sets the gap; the new test fails on the PR head and passes with the fix). Track B does not
call these scripts.

6.2 **`t/swi5.bin` is neither shipped nor checked (the PR's code).** The repository holds only `t/swi5.s`.
`ps1rt/build.sh --check` reports all inputs present, then the build stops in step `package-1` with
`FileNotFoundError: .../t/swi5.bin` from `prune.py` (`09_trial_build_no_swi5.log`). Fixed by commit d0d0010
(the preflight lists it, `PREPARED.md` gives the command, the build-driver fixture and one new test). Both fixes were
tested together in a separate worktree detached at d02652a: `prepare.py --check` passes, 23 tests pass,
`check_native.py` passes, and Track A on the patched tree gives the identical EXE (`28_patches_validation.log`).

6.3 **Preflight and the release profile (documentation).** The preflight's default profile is `pr`; the release is
built from `pr_lb` with the world window of `pr_l`. `PRD=pr_lb sh ps1rt/build.sh --check` fails with "Missing
input: ../out/pr_lb/rompages_P.pkl" until `t/mkrompages.py` has run, which only `t/disc7.sh` does
(`08_trial_preflight.log`). Neither STATUS.md nor PREPARED.md gives a command that regenerates a private
input; the only end-to-end description is the historical `build_ps1.sh`, and the command that produces
`touched_f1_boot.pkl` is in no script at all (taken here from `t/snapdump.py` and the stage 7 logs).

6.4 **Disc packer (older than the PR).** See section 4. Fixed in the main line by commit d0d0010, for both copies
(`ps1/stage5/discpack/` and the manifest-pinned `stage7/integration/tools7/mkdisc2.py`). Checked here: the corrected
packer's disc passes `verify_disc.py` and boots in PCSX-ReARMed at 50 frames per second for region E. DuckStation
itself was not run.

6.5 **Hashes in STATUS.md.** The ISO hash depends on the build time. The EXE hash was not reproduced (section 1).

6.6 **Level functions outside the level tier of the shipped translation (older than the PR).** `pr_lb` was built
with the 172-function level set, `pr_l` with the 216-function one. Of the 44 functions in between (37 belong to the
handler family at guest `0x08072dec..0x08072f5e`), 12 sit in the menus/boot tier inside the renderer's world window
and 32 are not in COLD.BIN at all; in a level these run through the interpreter fallback
(`22_tier_consistency.log`). v3 shipped like this. Using `rank_S.pkl` (216) for b10 as well would change
COLD.BIN and needs its own emulator pass; it was not tried.

6.7 **`t2m.py --cache` changes the hot blob** (85,184 instead of 85,128 bytes). A full translation and its prefix
must be made the same way or the `cmp` checks fail. The scripts keep stage 7's usage: cache for `pr_b` and `pr` only.

6.8 **Environment.** `python3 -I` ignores `PYTHONDONTWRITEBYTECODE`, so the tree gets `__pycache__` directories
(harmless, never in the repository). `/usr/bin/time` and `xxd` are absent. `pcsxr` is `/usr/games/pcsxr` and the
old run scripts expect `/dev/shm` and private `bin/` copies: use the rig (`ps1/rig`) instead. A foreground shell call
is moved to the background after two minutes by default, so run Track B with `nohup` and poll its log.

## 7. Not verified

- The two 1500-frame simulator runs of b9 with the new layout (STATUS.md's "level starts at frame 1103 ... ten
  entities" was not re-run here).
- Anything past the title menu on the physical layout: starting a level, the city renderer with the moved model
  atlas, saving, pad variants, CD audio, speed.
- DuckStation, a real BIOS, hardware.
- The full-length audio disc (only a 2 s per track test disc was packed).

## 8. Files

In this directory:

| Path | What |
| --- | --- |
| `REBUILD_PLAN.md` | this plan |
| `README.md` | what to run, in which order |
| `track_a_reuse.sh`, `track_b_regenerate.sh` | the two procedures of sections 3 and 5 |
| `REBUILD.sh` | Track A for the PR head plus copies of the results and a layout report (release candidate 4) |
| `verify_inputs.py` | layout proof of a set of private inputs against a prepared tree |
| `cmp_worlds.py` | compares the 11 world blobs of merged GBA cartridges |
| `private_inputs.sha256` | name, size and sha256 of every file in `SURV` |
| `tools/` | rig scripts of the page cache and speed diagnosis: `rigpages.py` with `pages_report.py` and `respages_opt.py`, `rigmiss.py`, `rigspeed.py`, `rigsession.py`, `rigprobe1.py`, `rigicon.py`, `rigweapon.py` |
| `00_READ_ME_FIRST_FAST_EMULATOR.md` | the short note on the rig |

Kept with the private files, never in the repository: the run logs, the Track A image built here with LLVM 18.1.3
(EXE, ISO, ELF, step logs), emulator screenshots of it, the three function-rank sets (172, 216, 289), the Track B
tree with b0 to b8 done (170 MB) and the worktree used to test the fixes of section 6.

## 9. The current release

The scripts take every path from the environment (`ROM`, `SURV`, `AMIGA`, `REPO`; README.md). The current release
is built from a tree prepared from the main line, with Track A, then packed with the CD audio:

1. `python3 ps1/tools/prepare.py --output TREE`
2. `ROM=... SURV=... bash ps1/rebuild/track_a_reuse.sh TREE NAME ""`
3. `python3 TREE/tools7/mkdisc2.py --iso TREE/out/NAME.iso --out OUT/NAME --region U --default-tracks` (the CD audio
   tracks are the owner's remix MP3 files in `MUSIC_MODS` and `MUSIC_PB`, not in the repository)
4. `python3 ps1/stage5/discpack/verify_disc.py OUT/NAME.cue`
5. `chdman createcd -i OUT/NAME.cue -o OUT/NAME.chd`

Since stage 19, `tools12/build.sh` takes the 62 measured resident ROM pages of `t/resident62.txt` and builds the
release without the menu assist and without `PADDBG`, so the numbers of section 3 (56 pages, `-DPADDBG`, the EXE
hash) belong to the PR head only.
