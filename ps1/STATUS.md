# PlayStation port: current handoff

The repository now has a reproducible, ROM-free assembly of the **stage16 runtime
plus stage17 models/trees, stage18 model refinements and the stage19
accurate-emulation fixes**. The combined native modules compile and link with
checked RAM allocations. A private 8 MiB baseline builds with the strict
physical linker; with the stage19 sources its disc, as built, plays from
power-on into the first level on the accurate cores SwanStation and Beetle
([stage19](#stage19-accurate-emulation-fixes-rc5-rc6)). No DuckStation, Sony BIOS
or hardware run exists yet.

The source manifest starts from repository commit
`109c747067bc4ab6ced2d9713656c658f00c9441` and explicitly records the integration
changes in this cleanup. Historical stage directories remain available for
comparison. Earlier plans and milestone READMEs describe their own snapshots,
not the current aggregate.

## Commands to use now

From the repository root:

```sh
# No ROM or compiler required; needs Python 3 and the standard patch utility.
python3 ps1/tools/prepare.py --check

# Assemble into a new directory; an existing destination is never replaced.
python3 ps1/tools/prepare.py --output /tmp/payback-ps1-work

# ROM-free build-driver, assembly, ABI, VRAM and PPU-cache regression tests.
python3 -m unittest discover -s ps1/tests -v

# Compile/link the native modules with Clang, LLD, LLVM objcopy and LLVM nm.
python3 ps1/tools/check_native.py
```

Preparation verifies **152 source files and four ordered patches**, checking the
SHA-256 of every input, each patch's starting file and its exact result. It
produces a deterministic `SOURCE_MANIFEST.json` in the assembled tree. A changed
input, incompatible patch or incorrect result aborts before publication.
`tools/source_manifest.json` is intentionally reviewed and updated when its
source inputs change; silently accepting local drift would defeat this check.

The prepared tree includes a [build handoff](PREPARED.md). Inspect the private
build prerequisites there with:

```sh
cd /tmp/payback-ps1-work
ROM=/absolute/path/to/Payback-Europe.gba sh ps1rt/build.sh --check
```

That preflight requires the matching translated guest, boot state and extracted
map data, plus the disc tools. Source preparation does not manufacture those
inputs. The old `stage7/integration/build_ps1.sh` is a historical snapshot build
script with environment-specific assumptions; it is not the supported release
orchestration entry point.

## Integration problems closed in this cleanup

| Problem | Current behavior |
| --- | --- |
| Compiler failures were filtered through `grep ... || true`; stale objects could reach a later link. | Each build has a fresh directory, every command must succeed, and full step logs are retained. |
| Earlier EXE/ISO outputs could be replaced before the two-pass sector check finished. | New artifacts are published only after both complete passes agree on required disc-file locations. Failed builds preserve earlier outputs. |
| Outer wrappers hid errors or embedded an obsolete private ROM path. | The stage16 wrappers require `ROM`, preserve the caller's relative ROM path and propagate failures. |
| The stage17 runtime patch was based on stage13 and failed against stage16. | An explicit stage16 integration patch preserves PPU, controls, map-follow and interpreter behavior while adding the model fields. Runtime and renderer use one checked `SfEnt` definition. |
| The combined model/tree renderer exceeded its reserved region with the old `-O2` default. | The renderer defaults to `-Os`, with `SFOPT` available for measured experiments. Linker bounds remain enforced. |
| PPU and cold-veneer scratch occupied memory used by the enlarged renderer, and the old scratch areas overlapped each other. | All three linker variants reserve separate 4 KiB PPU and veneer areas at `0x8017a000` and `0x8017b000`; ragdoll growth is checked against the first area. |
| PPU OBJ uploads overwrote model textures/palettes; the PPU page overwrote world atlas page 6. | Shared VRAM allocations move the models and PPU page into separate regions. All persistent regions are checked for bounds and overlap. |
| The direct build's default 64-page cache overlapped ragdoll code. | The default is eight pages. Partial four-page CD fetch groups are rejected, and the actual compiled cache bounds are checked against resident pages and the actual ragdoll location. |
| A larger merged ROM could be passed to an eight-MiB runtime window. | The build rejects ROM sizes other than 8 MiB. Extending the merged Stunt Fox address space is explicit remaining port work. |
| Physical cache bounds were also applied to the extended-memory discovery simulator. | Only the simulator linker permits a bounded virtual cache below `0x80800000`; both physical linkers still reject that address space. The 512-page discovery cache is explicitly tested. |
| The interpreter-disabled discovery build referenced an interpreter-only diagnostic counter. | Its diagnostic reports zero without interpreter code; normal physical runtime allocations are unchanged. |
| The discovery translator's old cold-code gap began after the new PPU scratch reservation. | Translation excludes `0x8017a000..0x80200000`, and the simulator's CD copy predicate uses the linker's `__ppu_start`. A straddling 16 KiB CD group preserves scratch and guest RAM. |

The PPU backdrop cache now uses two pages. Opaque blits copy their pixels into
the guest framebuffer immediately, so eviction cannot erase a previously drawn
backdrop. A native host test runs the production cache/blit functions using
synthetic pixels: it covers a maximum-sized cached image, eviction, preservation
of the other guest page, reloading and the direct-copy fallback.

The revised GPU allocation leaves all seven world atlas pages intact. Models
occupy `(960,64)` with a 32-halfword by 128-row atlas and palettes at `(992,0)`.
The PPU backdrop cache uses the two pages beginning at `(576,256)` and `(704,256)`;
its display page starts at `(832,256)`. The existing OBJ pages remain at
`(960,256)` and `(960,384)`. Model uploads, texture-page selection and UV offsets
use the same definitions as the allocation checks.

## Stage19: accurate-emulation fixes (rc5, rc6)

`stage19/` holds full copies of the prepared-tree files the fixes change
(`ps1rt/{build.sh,crt0.s,hw_cdda.h,hw_pad.h,ppu12.h,rt.c}`, `rd/ps1.h`,
`sf/{ps1.h,sf3.c}`, `t/{disc7.sh,final.sh,mkrompages.py,resident62.txt}`,
`tools12/{build.sh,build_test_assist.sh}`); manifest profile `stage16-19-source`
points those targets there. The two stage17 integration patches are folded
into the stage19 `rt.c` and `sf3.c` and removed. The faults are those the
accurate-core rig reported (DuckStation-class cores, openboot firmware):

| | Fault | Fix |
| --- | --- | --- |
| F1 | GP0 parameter words waited on GPUSTAT bit 26: the first frame never completes | Only command words wait for bit 26; parameters are written plainly; long A0h uploads go by DMA2; C0h keeps its bit-27 poll. Two-parameter commands share one out-of-line sender, so `gpuwait_classify.py` reports 0 parameter waits. |
| F2 | `teq` (MIPS II) after every division | `-mno-check-zero-division` in every build and in `check_native.py`; `tools/mips1_lint.py` checks every linked ELF and fails the build. |
| F3 | A DualShock starting in digital mode was left in configuration mode | The pad driver never switches modes; an ID 0xF3 reply gets Exit config; the button latch stays. |
| F4 | Interrupt state inherited from the kernel | `crt0.s` sets SR (CU2 on, IEc/IM off) and I_MASK 0, and acknowledges I_STAT and CD flags before `gpu_init`/`cdda_init`. |
| F5 | Kernel calls without an argument area | `dbgc`/`flush_icache` reserve 16 bytes and clobber every caller-saved register, `hi`/`lo` included. |
| F6 | Undefined picture at power-on | Display off, mode set, both buffers black; the display comes on with the first finished picture. |
| F7 | The CD driver took any interrupt as its answer and could not recover | Drain/acknowledge, expect specific answers, retry on INT5 or timeout, error screen (data never taken as good), DRQSTS wait, 924h-byte sectors with a header address check. |
| F8 | Picture outside the 224-line safe area | Guest 160 lines scale to 224 at y 8 for 2D, sprites and the 3D viewport; proportions and HUD alignment kept. |
| F9 | `t/final.sh` could hide failures and used its own memory geometry | `set -euo pipefail`, no output filter; its last step builds through `t/disc7.sh`, which derives the cache, ragdoll, world and cold geometry like every other disc build. |
| F10 | The menu assist (KPLAN) was in the release | Release builds without it; `tools12/build_test_assist.sh` makes the TEST variant (`*_TEST_assist`). |
| F11 | CD-bound speed | `PCACHE1` with 62 measured resident pages (`t/resident62.txt`); no page-trace (`PGTRACE`) instrumentation in any build; no Pause between reads that follow each other. |

The review of rc5 found five more faults; rc6 fixes them (same files):

| | Fault | Fix |
| --- | --- | --- |
| R1 | CD audio (the radio) resumed from the data track: the position was taken with GetlocP while the Play seek still ran, when GetlocP reports the last data sector read | `hw_cdda.h` takes a position only while Getstat shows Play without Seek and GetlocP reports the playing track, index 1 or more and an address inside the track's TOC range (GetTD); until then a resume is Play(track) from the track's start. |
| R2 | With the radio on, every ROM page miss paid a Pause, a Setloc and a Play: 0.17 instead of 1.33 guest frames/s | Data reads never resume the music. It comes back at a present once the disc has had no data read for 8 guest frames (doubled up to 64 when it is held again soon after); data is read at double speed with the radio on too; a resume the drive did not take is retried; music found stopped twice in a row (Getstat every 30 guest frames) is resumed. |
| R3 | The CD read error screen came up once per power-on, showed buffer 0 and left the draw offset at 240 | It comes up for every failure episode and the next picture replaces it once a read completes; it shows the buffer `present()` is not about to draw into and restores the draw offset. `-DCD_FAILTEST=N` (TEST builds only) makes two reads fail. |
| R4 | Sprite tiles' top edges were one line high in 28 % of the rows (`floor(7y/5)`) | Rounded, `round(7y/5)`: 14 % of the rows one line off, either way. A probe disc measured on SwanStation and Beetle that the GPU samples the page quad with a half-texel bias (GBA line L from PS1 line 8 + floor((7L+1)/5)); with that, `ceil(7y/5)` would put 28 % one line low. |
| R5 | The release carried the `PADDBG` pad/entity log | Only the TEST variant has it; `check_native.py` compiles both profiles and `tests/test_build_pipeline.py` checks the flags each profile passes. |

Results with the rc6 release disc as built (`tools12/build.sh`, US licence area,
CD audio, no test patches), openboot unless noted, all times emulated:

| Check | SwanStation | Beetle |
| --- | --- | --- |
| Power-on to the first level by pad presses | 13 PASS, level clock at 43 s (RC v2: 174 s) | 13 PASS, 45 s (RC v2: 160 s) |
| In the level: idle, walk, turn, weapons, fire, pause | 20 PASS with the pause press held until the game read it (unchanged session: 18 PASS, 2 FAIL, see below) | The same, with the core showing lines 8-231 (320x224) like SwanStation; its default bordered 350x240 frame stays under the classifier's 80 % lit pixels |
| openboot `strict`, `irq`, `f06` | 12 PASS each; with `irq` no CD timeout and all 15 tracks in the CD audio table | 12 PASS each |
| Open-source BIOS of the core | No halt; 12 PASS, level at 51 s | not run |
| DualShock starting digital / forced analog | ID 41 / 73, no configuration transfer, Down seen in 77 of 90 samples | not run |
| CD read speed-up 8, 10, instant seek, both | 12 PASS each; game retries 0, 53, 0, 53 (header mismatches, all recovered), no failure | not run |
| CD read error (TEST build, two reads made to fail at the level start) | The message comes up for both episodes (32 retries, 8 drive resets, then the reads succeed); the game's next picture replaces it, 4 s and 6 s after the disc reads again | Both episodes show it; the first is replaced within 4 s, the second still showed when the run ended 6 s after the disc read again (no new picture yet) |
| Radio (CD audio) from the level state | A walk runs at 1.33 guest frames/s with the radio on and off (rc5 with the radio on: 0.17). In five pause menus the music sounds in 89-94 % of the frames, 13 frames after each resume, from positions inside track 2 that move forward | Five pause menus: 89-93 %, 22 frames after each resume, positions as on SwanStation |
| Picture changes without a flip | Menus (TEST disc) as rc5: 816 changes for 888 presents, the 6 'extra' changes right after flips; level 7 changes for 6 presents; black only between screens (the game's own fades) | Level 6 changes for 5 presents |
| Memory card save | Created, checksums correct | Created, checksums correct |

The pause step needs the Cross press on "Return to game" to be held until the
game has read the pad. The rig's tap means to do that (it holds until the
runtime has polled the pad twice) but lets go early as soon as "PAUSED" is
missing from its read-back of the drawn text, and in the pause menu that
read-back is empty for 2 of every 7 frames with no input at all. The pause menu
of rc5 and rc6 gives the same trace frame for frame (8.6 pad reads and guest
frames a second; 258 of 900 frames without "PAUSED" in the read-back), so
whether the game read the press first depends only on where the press falls.
With the same rig the unchanged session passes that step on rc5 on SwanStation
(Cross held 6 frames, read once) and fails it on rc5 on Beetle and on rc6 on
both cores (4 frames, not read; the game stays paused: 18 PASS, 2 FAIL).
Holding the press until one read gives 20 PASS on both cores. A pause and
return from the level state passes on rc5 and rc6 with either kind of press,
with the same timings.

On PCSX-ReARMed (`run_all.sh`, rc6 release disc) the pad route, replay, maps,
save/load, state, speed and both CPU-interpreter sessions pass, as with rc5. The
FAILs are the known gaps that RC v2 shows too (the intro film is not drawn and
the title menu does not follow it; the in-level vehicle is out of reach), the
soak's 600 s of game time (148 s in its 33 minutes; rc5 157 s, RC v2 12 s; its
random presses follow the pad reads, so each build walks elsewhere), the rig's
classifier on a large grey wall, the assist session, which needs the TEST
variant (8 PASS there), and the in-level pause step as above: the game stays
paused, so the death and vehicle steps after it fail too (18 PASS, 6 FAIL).
With the press held until one read, the in-level session gives 29 PASS and
the one known vehicle FAIL (rc5: 28 PASS, the same FAIL).

The TEST variant, with the session the findings used for rc4 (before: rc4
test-patched; menu rate: RC v2; then rc5 -> rc6):

| Speed | SwanStation | Beetle |
| --- | --- | --- |
| Level clock starts | 994 s -> 93.1 s -> 93.1 s | 873 s -> 97.3 s -> 97.6 s |
| Guest frames/s in the menus | 1.11 -> 12.7 -> 12.7 | 1.27 -> 12.3 -> 12.3 |
| Guest frames/s in the level | 0.54 -> 6.60 -> 6.60 | 0.61 -> 6.36 -> 6.02 |
| Pictures/s in the level | 0.036 -> 0.44 -> 0.44 | 0.040 -> 0.42 -> 0.40 |
| CD fetches/s in the level | 3.56 -> 1.26 -> 1.26 | 3.89 -> 0.96 -> 1.23 |

SwanStation runs rc5 and rc6 identically here. On Beetle the first 119 page
fetches are the same pages in the same order; rc6 reaches the late steps of the
session (weapon change, shooting) a few guest frames later relative to the
emulated frames, and those steps fetch 12 pages more inside the measured window.

Limits: the resident pages were measured on the assist's route. The pad route
starts the rampage elsewhere and fetches about 9 single pages per second there
(each a seek of about 140 ms), standing or walking: about 1.3-1.9 guest frames
and 0.1 pictures per second (one present per 16 guest frames, unchanged). The
radio cannot play while the drive reads data, so at that spot its music stays
held (silent) during play and sounds in the pause menu; it plays during play
only where the page cache holds what the game needs. Read speed-up mostly slows
openboot's own loader (45 retries at 8x); the level starts at 51 s (8x) and
92 s (10x). The first picture of the level (about 1.1 s) shows the menu's
bridge in the level's colours, in rc5 as in rc6 (the PPU's unfinished BLDY
fades). After a CD read error the message stays up until the game's next
picture, which during a level load comes several seconds after the disc reads
again. Short presses (a few frames) can be missed where the game reads the pad
only a few times a second (about 8.6 in the pause menu). There is still no
DuckStation, Sony BIOS, hardware-renderer or console run.

## What the existing stages actually contain

| Area | Current source state | Remaining acceptance |
| --- | --- | --- |
| Guest execution | Stage8 interpreter fallback and stage10 packaging support are included with the stage16 runtime. | Rebuild matching private translation metadata and verify coverage in the final game. |
| Menus and HUD | Stage12 PPU-lite plus later stage16 composition are present. Older claims that no PPU exists are obsolete. | Finish the explicitly deferred glow/logo, menu 3D models and BLDY behavior; compare actual menu transitions. |
| Controls and saving | Later pad packet handling, latched input, memory-card save paths and saved-card-aware menu assistance are present. | Re-run blank and initialized cards, digital/analog pads, pause/resume and quit/restart on the combined build. |
| Cities | The runtime follows the guest map and uses an interpreter fallback for cold code that conflicts with world data. | Exercise all maps and real level changes on the combined image. |
| Vehicles, people and trees | Stage17 geometry/tree changes and stage18 wheel, shading and LOD refinements now assemble together. | Measure frame cost and visual behavior after the `-Os` and cache-allocation changes. Cached per-class display lists remain unfinished. |
| Full merged Stunt Fox game | [The merged-ROM scout](stage8/merged_plan.md) is an architectural plan, not a completed port. The current runtime still has a 2048-page/8-MiB ROM window. | Address-space expansion, merged-code discovery/overlay coverage, the GPU backend for the merged renderer, and the space/station/mission/settings paths still need implementation and gameplay proof. |

References: [stage10](stage10/README.md), [stage12](stage12/README.md),
[controls and saves](stage13/ctl_saves_gameplay/README.md),
[city following](stage13/cities/README.md), [stage17 models](stage17/models/README.md),
[stage17 trees](stage17/trees/README.md), and [stage18 refinements](stage18/models/README.md).
In particular, stage18 explicitly lists unfinished menu effects and model work;
the earlier [PS1 plan](PS1_PLAN.md) must be read alongside these later sources.

## Validation and its limits

The current ROM-free unit suite passes **38 tests**. The native module check
(stage19 sources, Clang/LLD 18.1.3) uses the real production linker script and
the interpreter-enabled title-boot configuration of the release profile, then
links the test profile (KPLAN and PADDBG) as well; every linked function must pass
`tools/mips1_lint.py`:

| Native allocation | Used | Reserved before the next owner |
| --- | ---: | ---: |
| C runtime and interpreter, with minimal generated-table fixtures (release / KPLAN test) | 91,332 / 94,612 bytes | 98,304 bytes |
| Ragdoll code and data | 79,492 bytes | 94,208 bytes |
| Combined renderer code and data | 90,684 bytes | 94,208 bytes |
| PPU scratch | 4,096 bytes | 4,096 bytes |
| Cold-veneer scratch | 4,096 bytes | 4,096 bytes |

The same check deliberately rejects an invalid three-page cache, the old
64-page cache overlapping ragdoll code, and a ragdoll allocation growing into
PPU scratch. It also links the full-cold simulator with a 512-page virtual
cache, rejects that cache under both physical linker scripts, and rejects a
cache that exceeds the simulator's upper bound. The host tests verify the
real simulator copy predicate at both scratch boundaries, the shared entity ABI and nonoverlapping
VRAM layout. These checks exercise real compilers and linker assertions; the
build-publication tests separately use mocked tools to reproduce failure paths.

Generated guest tables and game assets are placeholders in the ROM-free native
check. A separate private build below uses real inputs and passes the physical
linker assertions. The runtime, renderer and world allocations have limited
free space, so subsequent changes must pass those same assertions. Historical
stage17/18 results used PCSXR HLE; they do not replace the current evidence.

### Private baseline boot checkpoint

The supplied original 8 MiB guest was rediscovered and paired with all eleven
converted worlds. Three ARM-versus-MIPS boot snapshots matched without I/O or
memory differences. The discovery simulator first exposed a real scratch
collision: a cold function at `0x8017a25c` occupied the PPU reservation. Moving
the translation gap to the actual scratch boundary fixed that exception.

| Private check | Observed result |
| --- | --- |
| Guest discovery | 220,981 instructions |
| World pack | Eleven worlds, 5,847,040 bytes |
| Boot lockstep | Three matching snapshots, 3,196 I/O events each |
| Extended-memory discovery | Level starts at frame 1103; gameplay snapshot at 1165.7; run completes at frame 1501.7 with level clock 201 and ten entities |
| Cold-code exclusion | All 3,299 generated spans avoid `0x8017a000..0x80200000` |
| Physical EXE and ISO | Strict `ps1.ld` link passes; translated prefixes match; both disc passes agree on sector locations |
| PCSX-ReARMed HLE | Real language-selection screen rendered during a bounded 3,600-frame run |

The physical image uses 96,320 of the runtime region's 98,304 bytes, leaving
1,984 bytes. Its largest world fills the 239,616-byte world window. The actual
private EXE SHA-256 is
`9bd2ac66025e5e29d6e314b3533665a56cdb77708576c92a9c2a00a68f0ee075`;
the ISO SHA-256 is
`bdc0bd648d7fadea4c4390c7a85f6a033eff3206d6f04e3354f665fb40daedbc`.
Game-containing artifacts are not stored in this repository.

The HLE run ended at language selection with the guest level clock still zero.
It establishes boot and title-screen rendering, not physical-layout gameplay,
menu/controller acceptance, memory-card persistence, audio, performance, a
real BIOS or hardware behavior. Discovery's gameplay clock belongs to its
extended-memory simulator and is not substituted for that missing evidence.

## Next port milestone

1. Continue from the matching private 8 MiB translation/map set and the verified
   physical-layout boot image. Preserve its manifest and two-pass disc checks.
2. Advance beyond language selection, then run saved-card menu paths, every city,
   pause/resume, restart, vehicles/people, HUD, audio and map transitions; record
   screenshots and frame timing. Check texture persistence after both 4-bit and
   8-bit OBJ uploads.
3. Finish the documented menu/fade and performance gaps, then establish a
   real-BIOS emulator baseline before treating the image as a release candidate.
4. Continue the full merged Stunt Fox port with an explicit address-space and
   renderer-backend milestone. The larger GBA milestone cannot be substituted
   into this baseline by changing only the input filename.
