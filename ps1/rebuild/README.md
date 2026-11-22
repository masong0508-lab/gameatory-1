# ps1/rebuild: building the Payback PS1 port from the owner's files

The PS1 build needs private inputs made from the player's own ROM: the translated guest code (`pr_l/`, `pr_lb/`),
the boot state (`boot.bin`), the world pack (`SF3M.BIN`, from the Amiga maps) and a few lists. They are not in the
repository. `private_inputs.sha256` records the name, size and sha256 of every one of them, and two tracks get them:

- **Track A, `track_a_reuse.sh`**: reuses a surviving copy of the private inputs (`SURV`). It stages 14 files, checks
  their hashes and the layout (`verify_inputs.py`) and builds the EXE and the data-track ISO in about 11 seconds.
  This is how releases are built.
- **Track B, `track_b_regenerate.sh`**: regenerates the inputs from the ROM and the owner's Amiga Payback files
  (steps b0 to b12: about 10 minutes, plus up to 12 for the two simulator runs of b9, which run in parallel). It
  checks the deterministic steps against fixed hash prefixes and compares everything with the list (step `hashes`)
  and, when `SURV` is set, with the surviving files.

`REBUILD_PLAN.md` has the proof that the inputs fit the memory layout, the expected output of every step and the
pitfalls. `REBUILD.sh` is Track A for PR head d02652a (release candidate 4), with a layout report.

**Everything these scripts produce derives from the ROM and must never be committed**: the prepared tree's `out/`,
EXE, ISO, ELF and nm listings, `.cue`/`.bin`/`.chd` discs, logs, screenshots and the private inputs themselves, as
well as the ROM, the Amiga files and the music. Keep `TREE`, `SURV`, `OUTDIR` and the disc directory outside the
repository. Only names, sizes, hashes and our own measurements go in.

## What to run first (GPT-6)

From the top of the repository, with the owner's ROM and Amiga folder:

```sh
python3 ps1/tools/prepare.py --check                     # ROM-free
python3 -m unittest discover -s ps1/tests                # ROM-free
python3 ps1/tools/prepare.py --output /work/tree_b       # a new directory outside the repository
export ROM=/path/to/payback.gba AMIGA=/path/to/amiga/payback REPO="$PWD" SURV=
ps1/rebuild/track_b_regenerate.sh /work/tree_b b0 b1 b2 hashes     # about 40 s: tools, IWRAM image, guest discovery
nohup ps1/rebuild/track_b_regenerate.sh /work/tree_b b3 b4 b5 b6 b7 b8 b9 b10 b11 b12 hashes > /work/tree_b.log 2>&1 &
```

The first call stops with exit 3 at once if the ROM is not the expected dump (b1 checks the IWRAM image by hash).
Report the `hashes` lines (SAME or DIFF for each listed file; `kp/kplan.h` and `*/rompages_P.pkl` differ by design)
and the SAME/DIFF lines of b9 to b11. Track B was validated on a tree prepared at PR head d02652a, with `REPO` at that
commit and the b9 simulator outputs taken from stage 7; the two b9 runs themselves have not been run to the end. b7
builds the GBA cartridge from `REPO`: if a later `stuntfox/` builds other worlds, b7 stops on the `SF3M.BIN` hash, and
a checkout of d02652a as `REPO` (`git worktree add`) is the reference.

With a copy of the private inputs, check it against the list first and then run Track A:

```sh
awk '!/^#/ && NF == 3 {print $1 "  " $3}' ps1/rebuild/private_inputs.sha256 | (cd "$SURV" && sha256sum -c -)
python3 ps1/tools/prepare.py --output /work/tree_a
ROM=/path/to/payback.gba SURV=/path/to/private/inputs bash ps1/rebuild/track_a_reuse.sh /work/tree_a payback_rc ""
```

On 2026-11-22, Track A on a tree prepared at commit f1471a0 with clang 18.1.3 gave all 15 hash checks `ok`,
`RESULT: 0 failed checks`, disc LBAs `1209,24,180,5305,5305,0,0` and an EXE of 1,691,648 bytes, sha256
`612442e738c30112...` (any change to the PS1 sources or the compiler changes the EXE; the ISO hash changes with every
build). Steps 3 to 5 below passed on that ISO with 2-second audio tracks.

## How the current release is built

1. `python3 ps1/tools/prepare.py --output TREE`
2. `ROM=... SURV=... bash ps1/rebuild/track_a_reuse.sh TREE NAME ""`
3. `python3 TREE/tools7/mkdisc2.py --iso TREE/out/NAME.iso --out OUT/NAME --region U --default-tracks`
   (the CD audio tracks are the owner's remix MP3 files, not in the repository: set `MUSIC_MODS` and `MUSIC_PB` to
   their folders; the full disc is about 593 MiB, `--seconds 2` makes a 28 MiB test disc)
4. `python3 ps1/stage5/discpack/verify_disc.py OUT/NAME.cue` (expected `RESULT PASS`, 15 tracks)
5. `chdman createcd -i OUT/NAME.cue -o OUT/NAME.chd`

The release targets DuckStation on Android; every emulator result here is emulator-only. The rig for boot and
gameplay checks is `ps1/rig/` (`00_READ_ME_FIRST_FAST_EMULATOR.md`, `ps1/rig/README.md`).

## Environment

No script here has a default that points at a private location; a missing setting stops it with a message.

| variable | used by | what |
|---|---|---|
| `ROM` | all | the untouched 8 MiB Payback (Europe) cartridge image (required) |
| `SURV` | Track A, `REBUILD.sh` (required); Track B (required, may be empty) | a copy of the private inputs of `private_inputs.sha256`; Track B only compares with it |
| `AMIGA` | Track B step b7 | the owner's Amiga Payback folder with `maps/` (not needed when `GBA` and `ELF` are given) |
| `REPO` | Track B step b7 | a checkout of this repository: `stuntfox/build.py` builds the merged cartridge, its tools decode the maps |
| `GBA`, `ELF` | Track B step b7 | an existing merged cartridge and its `stuntfox-merge.elf` instead of building them |
| `SEED_TOUCHED` | Track B step b9 | validation only: take the simulator outputs from this directory instead of running it |
| `SIM_FRAMES` | Track B step b9 | test only: length of the simulator runs (default 1500) |
| `NAME` | Track B, `REBUILD.sh` | output name (defaults `payback_rc`, `payback-rc4`); Track A takes it as its second argument |
| `TREE`, `OUTDIR` | `REBUILD.sh` | the prepared tree and the results directory (required) |
| `PRWT` | `REBUILD.sh` | the checkout to prepare `TREE` from, when `TREE` does not exist yet |
| `PADDBG` | Track A, `REBUILD.sh` | passed on to `tools12/build.sh`: the pad debug log flags (test variants only) |
| `EXTRA` | `REBUILD.sh` | extra C flags for test variants; Track A takes them as its third argument |
| `MUSIC_MODS`, `MUSIC_PB` | `tools7/mkdisc2.py --default-tracks` | the owner's folders of remix MP3 files for the CD audio tracks |
| `PATH` | all | put `/usr/lib/llvm-19/bin` first to build with LLVM 19 instead of the default clang |

## Other files

- `verify_inputs.py PRIVATE_OUT_DIR PREPARED_TREE`: the layout proof Track A runs (reads only).
- `cmp_worlds.py ROM_A ROM_B ...`: compares the 11 world blobs of merged GBA cartridges (reads only).
- `tools/`: rig scripts of the page cache and speed diagnosis (PCSX-ReARMed through `ps1/rig`; they need the build's
  nm listing): `rigpages.py` with `pages_report.py` and `respages_opt.py`, `rigmiss.py`, `rigspeed.py`,
  `rigsession.py`, `rigprobe1.py`, `rigicon.py`, `rigweapon.py`. Their outputs show the game: keep them outside the
  repository.
