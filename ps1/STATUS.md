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

## Stage19 rc7: a disc that plays

rc7 changes only stage19 copies (`ps1rt/{rt.c,interp_glue.h,build.sh,ps1.ld}`,
`interp/{interp.c,interp.h,interp_asm.s,test_host.c}`, `rd/doll.c`) and adds
`tools/check_intro_site.py`; the manifest points the targets there (153 files).
The faults are those that kept rc6 from being played through:

| | Fault in rc6 | Fix in rc7 |
| --- | --- | --- |
| I1 | The boot intro never ended: `prune.py` STUBS id 3 (`0x080234be`) is not a function but the join point of the ZOO-logo wait, and its stub returned into the wait | The stub site is patched at boot into `li $25,0x080234be; j RT_MISS`, so the interpreter runs the untranslated intro code. `intro_fix_init` checks every word it relies on (stub id, site, `RT_MISS`, the `RT_BX` hash code, the overlay-area hash slots) and stops on a PORT ERROR screen if one differs; `tools/check_intro_site.py` makes the same checks on every linked ELF and fails the build (proved on altered scratch copies: 0 stub sites, a changed `RT_BX` word). The real fix is a translation-input change: drop `0x080234be` from `prune.py` STUBS at the next regeneration and translate the intro. |
| I2 | The film player (code overlay 1 at IWRAM `0x03000d84`) cannot run: rc5 ran the overlay-0 translation in its place | While overlay 1 is resident the hash slots whose keys lie in the overlay area point at `rt_ovmiss` (nothing added to `RT_BX`; `h_miss` and `ip_lookup` keep the `ov_stale` check); a call of the player ends the film as a key press does (picture cleared, DISPCNT 0x404, r0 = 1 'skipped'), so the intro takes the game's own skip path and film 2 is never called. No clock skip and no film-header parsing remain. The raw timer and the overlay loader that the intro calls are performed natively by the interpreter; the extra timer advance of the first attempt (`IP_TIMER_EXTRA`) is gone: title 1632 frames after the language press with it, 1630 without (SwanStation). |
| I3 | No key left the intro | Cross and Circle (GBA A and B) skip where the GBA skips (guest frames 250..526 after the language press); the title comes 35 guest frames later (GBA: 22). Start never skips; a press on the Nintendo screen or during the ZOO fade (from guest frame 527) does nothing, as on the GBA. |
| I4 | The guest time base (TM3:TM2) wrapped after 256 s of GBA time: deadlines set before the wrap were never reached (View intro black or locked, 41 raw-timer callers such as the white fades at `0x080273c6` / `0x08022e40`) | `io_hi` carries `io_cyc` into a 64-bit cycle count wherever it grows, and the timers count from the 64-bit difference to `tm_t0`: TM3:TM2 wraps after 72.8 hours, as on the GBA. (`io_hi` is the virtual-clock build's time base; the rc8 release, built with `RTC_TIMERS`, counts the timers from `clk.h`'s line clock, see rc8 row M.) |
| L1 | Getting into a vehicle crashed the game: the interpreter folded a computed `height << 23` into a host EWRAM address and the span loop wrote past the VRAM shadow into the 3D renderer's code | A shift folds only a value that an immediate move put into its register (`ip_km`, saved and restored around nested runs); a host VRAM pointer that runs past the shadow is folded back the way GBA VRAM mirrors, and the first such fold is reported on the TTY ('overflow', a rig fault word). |
| L2 | In a vehicle the level read 17 pages beyond the resident set in a cycle: with 8 FIFO slots each came from the CD again about every second guest frame (tank 0.48 guest frames/s) | From the first level on, the 62 resident pages and the 8 slots are one pool with CLOCK replacement (a reference bit set by every read of a page in RAM); the hit path is a load, a store and a test (`cd_fetch` out of line); `rom_read` looks a page up once per page, not per byte. |
| L3 | After Quit to title the held 3D view showed through every index-0 pixel of the game menu | The last 3D view is held only while the guest still has its level's entity table (count 0..100 at IWRAM `0x0300000c`). |
| L4 | A second level took about 3.4 M interpreter steps and 54-83 s of the menu picture: with the renderer up, the menu and level-loader code (`0x0803c4cc..0x0803cf4c`, cold groups 42/43 over the renderer's world window) was refused and interpreted | When the guest leaves a level (entity count -1 and the level clock standing still for three pictures) the renderer goes off, the menus present at their own rate and that code runs natively; the next level start runs the deferred `sf3_init` again. |
| R | Ragdoll events assumed one 3D frame per 30 Hz tick: leaving a car that crawled against a tree read as a bail-out at about 300 m/s and the player's doll hid him for minutes; a quit from a moving vehicle carried the doll into the next level | Velocities are the position change over the level-clock ticks between two gathered frames (jumps count as no movement); the player's own doll is released after 90 ticks (3 s of game time); leaving a level clears every doll and restarts the events. |
| ROOM | The runtime region had 6,832 bytes left and the fixes needed more | One-time and fault-only code (`main`, `gpu_init`, `cd_init`, `cdda_init`, `sv_load`, `intro_fix_init`, `fatal_screen`, `cd_error_screen`, `text`) is in a new `.rtcold` section at `0x80028040..0x8002a000`, RAM nothing else uses (between the helper table and t2m's ROM page-table area); `ps1.ld` asserts both ends, no constant of the hot blob, the cold code or the runtime points into it, and it is part of the EXE image, so the BIOS loads it and flushes the cache with the rest before `main` runs. |

Callers: the overlay loader `0x08077508` has two callers in the whole ROM
(`0x080235a6` loader(1), `0x08023616` loader(0)) and the film player
`0x03001660` is named only in the boot function's literal pools (`0x080236c0`
film 1, `0x08025534` film 2); a scan of every Thumb and ARM `bl` and every
literal word finds no other. Only the boot intro and View intro (the same
function) call them. Credits never calls the film player. On the fast core
the credits end by themselves; on the accurate cores they run almost entirely
in the interpreter (3.6 guest frames/s on Beetle, 6.1 on SwanStation at a 400 %
clock, against 60 on the GBA, which returns to the title after about 140 s)
and did not end within 11 emulated minutes. Cross leaves them in 0.7-1.8 s.

Memory of the rc7 release (rc6 in brackets): runtime ends at `0x80026d60`,
93,536 of 98,304 bytes, 4,768 free below `0x80028000` (6,832); `.rtcold`
`0x80028040..0x80029c38`, 7,160 bytes, 968 free below `0x8002a000` (new);
page cache `0x8015e000..0x80166000` and the 62 resident pages unchanged;
ragdoll `0x80166000..0x801797a4`, 2,140 bytes free below the PPU scratch
(2,428); renderer ends `0x801af23c`, 3,524 bytes free (3,524). The TEST_assist
variant has 1,456 bytes of runtime left, TEST_introfail 5,184.

The rig's ROM-cache view: the compiler drops `slot_owner` and `rom_miss_last`
in this mode (nothing reads them under `PCACHE1`; neither is in
`payback_rc7.nm.txt`). The pool is read from `fr_pg` (u16 per frame: page + 1,
0 = empty; frames `0..pool_rp-1` are the resident pages, then the 8 slots of the
page cache), `pool_rp`, `rom_ref` (one byte per ROM page: the CLOCK reference
bit), `pool_hand` and `rom_miss_count`.

Results with the rc7 discs as built (`tools12/build.sh`; the full US disc, or
its data track as a test image where a rig check needs it), openboot unless
noted, all times emulated (core frames / 59.94):

| Check | SwanStation | Beetle |
| --- | --- | --- |
| Hands off from the language press to the title (the GBA, which plays its films: 4,538 frames, about 76 s; rc6: never, ZOO loop) | 27.2 s | 32.7 s |
| Black between the last ZOO fade step and the first title fade step, every frame | 174 frames, 2.9 s | 209 frames, 3.5 s |
| Cross / Circle at guest frames +310, +461, +521 | title 35 guest frames later, 3.4-3.5 s; Start, +159 and +545..+590 do not skip | the same at +303, +459 (3.3-3.4 s); +527 is in the fade: no skip |
| View intro three times in a row; started at a time base of 236.0, 254.2, 254.4, 254.6, 255.3 s; white flash across 256.0 s | title back after 25.7-26.0 s every time (I1-I2 without I4: black until a key at 236.0 s, hung for good at 254.4 s) | not run |
| Power-on to the first level by pad presses | 13 PASS, level clock at 42.9 s (rc6 43.2 s) | 13 PASS, 45.4 s (rc6 45.1 s) |
| In the level (`in_level.py`): idle, walk, turn, weapons, fire, pause, death | 30 PASS | 30 PASS |
| Tank: enter, drive, turn, fire, reverse, pause, exit | PASS, renderer code unchanged | PASS, renderer code unchanged |
| Car: enter, drive (4,800 units, into a tree), steer, exit | PASS | PASS, with a pause in the car |
| Helicopter: enter, take off (L1), fly, land (L1), exit | PASS | PASS |
| Guest frames/s on foot (standing / walking), tank, car (rc6 on foot about 1.3; rc5 tank 0.48) | 7.7 / 7.6, 4.4, 4.1 | 6.1 / 6.0, 3.6, 3.3 |
| Quit from foot, tank, car; GAME OVER | clean game menu and GAME OVER pictures, no SF3 hold line | foot and tank: the same |
| Play game to the second level's city (rc6: 54-83 s, 3.4 M interpreter steps) | 13.0 s after a quit on foot (6 interpreter steps), 12.1-14.1 s after a vehicle quit (0.8 M) | 13.9 s on foot (0 steps), 12.1 s after a tank quit |
| Picture changes without a flip | level 0 (30 changes, 29 flips in 60 s); vehicles 0; second level 0; intro and menus: only the fade steps of the logos and title (menus identical to rc6) | level 0; vehicles 0; intro: fade steps |
| Radio on the full disc, 2 min walking in the level / 2 min in the menus after it | music 51 % / 95 % of the time (rc6 0 % / 96 %); page fetches 6 / 0.5 a minute (rc6 533 / 0.5); CD-audio pauses 3 / 1 a minute; longest silence 16.6 s / 3.9 s | not run |
| openboot `strict`, `irq`, `f06`; open-source BIOS | 12 PASS each; open-source BIOS 12 PASS, level at 50.6 s | `strict`, `irq`, `f06`: 12 PASS each |
| CD read speed-up 8, 10, instant seek, both | 12 PASS each | not run |
| DualShock starting digital / forced analog | ID 41 / 73, Down seen, no configuration transfer | not run |
| Memory card | save created, CRC good, a cold boot with the card lists and loads it | the same |
| Europe disc (licence area E, PAL console; PAL display since the review round) | language screen and title, picture in PAL lines 21..244 of 268 | language screen and title, picture in lines 31..254 of 288 (before: black) |

On PCSX-ReARMed (`run_all.sh`, data track of the release) the map tour gives 30
PASS; pad route, replay, save/load, state, speed and both CPU-interpreter
sessions pass. The FAILs left are by design or the rig: the intro film is not
drawn (films end as skipped), the soak's 600 s of game time and its "3D city
missing for more than a second", the assist session (8 PASS on the TEST
variant) and one vehicle check where the classifier calls the grey 3D view
'menu' (the picture shows the vehicle in the city). `in_level.py`'s own vehicle
step steers to the nearest parked vehicle, which on the accurate cores is the
helicopter: Cross does not drive a helicopter on the ground and L1 is its
take-off, on the GBA too, so its five drive checks fail there; vehicles are
judged with the `vtest` plans above.

Limits: the music plays about half the time in the level: each of the 6 holds
in 2 minutes was followed by 11-17 s of silence, because the quiet interval
(8 guest frames, doubled up to 64 when the music is held again within 64 guest
frames of coming back) sits at 64 guest frames, 8 s at the level's 7-8 guest
frames a second, plus the length of the burst of reads; now that the level
fetches about 6 pages a minute a lower ceiling would shorten the gaps (not
tried). The films are not shown. The pause
menu stays on the picture until the next 3D frame (2-4 s). After a vehicle quit
the next level start still interprets about 0.8 M steps. The game runs at about
an eighth of the GBA's speed in the level (3.9 level ticks a second of 30).
There is still no DuckStation, Sony BIOS, hardware-renderer or console run.

Review round (rc7 as shipped): the Europe disc was black on Beetle, because
the licence area makes the console PAL and the runtime always programmed the
GPU for NTSC; Beetle/Mednafen shows nothing in that case. `gpu_region()` (in
`.rtcold`, once at boot) reads the licence sector (LBA 4) and, when it names
Europe, programs PAL (GP1(08h) bit 3) with the 240 lines centred in PAL's
range (Y `2Bh..11Bh`); the US disc and data-only test discs stay NTSC. On a
PAL console the display runs at 50 Hz; the game is CPU-bound, so the intro
still takes 27.2 s of emulated time on SwanStation. Not fixed: a line of
coloured dots along the bottom picture line from the first pause on (it
predates rc7). It is drawn by `pp_obj`: the pause effect's two affine,
double-size, additive 8 bpp sprites (OAM 8 and 12, 64x64 magnified 2x at
y = 128, tiles `0x300`/`0x310`) put texels on PS1 line 231 that the GBA
does not show at row 159 (page row 159 is empty, the page quad and the CLUTs
were ruled out with marker lines in a test build). The fix belongs in the
edge rounding of affine tiles in `pp_obj` and was not made in this round.

## Stage19 rc8: rc7 + speed wave 1

rc8 merges speed wave 1 (`ps1speed` 81d4087: one clock, dispatch D1-D4,
boot/CD changes) into rc7 (`ps1play` e9791f5) and fixes what the two together
and the open issues showed. Speed is in emulated time (core frames / 59.94).

| | Problem | rc8 |
| --- | --- | --- |
| M | rc7's `.rtcold` overlapped wave 1's D1 table and D2 queue; rc7's CLOCK pool and `io_hi` time base overlapped D3 and the Stage 1 clock | One guest clock: in the release (`RTC64`/`RTC_TIMERS`) the timers count from `clk.h`'s 64-bit GBA-cycle count `G`; `io_hi` is only compiled in the virtual-clock build (round 2: `G` was computed from the 32-bit line count, see row K). The D1 table (`dsp_mcache`) and the D2 queue (`dsp_lq`) are BSS/`.sfbss` arrays, not fixed addresses. D3 keeps the ROM page table in `ROMPG` (`0x8002a000`, every build) and the rc7 CLOCK pool marks a page unmapped there, so a D3 hit still sets the reference bit. `.sfbss` is NOLOAD and cleared first in `main`. `ps1.ld` asserts every region end (runtime, `.rtcold`, ROMPG, the cold table at `0x8011c000`, ragdoll, renderer). `check_native` links all eight layouts. |
| C | Car hang at clock multiplier 5 (wave 1): entering a vehicle overwrote the renderer's code (6 words at `0x80199000`, frame 2694 in a helicopter, a traffic car froze the run at 28 ticks/s) | This is rc7's L1 (`height << 23` folded into a host address); rc8 carries rc7's `ip_km` / VRAM-fold fix over wave 1's dispatch. Renderer code unchanged in every rc8 vehicle run (tank, car k9/k14, helicopter). |
| #14 | Vehicle `k17` unknown | `k17` is the helicopter: on the GBA (mGBA) ground inputs do not move it, L takes off, A flies (85k units), L lands; the PS1 does the same. No fix needed. Parked: `k11` tank, `k17` helicopter, `k9` sports car; `k3..k7`, `k14` are traffic. |
| #15 | Map 3 at 400 % showed more picture changes than presents | A counter artifact: `g_pres` counts at the start of `present()`; every extra change is a real display flip. New `g_flips` counts display-start changes. 11 maps x 1200 frames at 400 %: 6,604 changes, 54 extra, all flips, 0 changes without a flip, 0 black. |
| B | Junk on the last picture line (231) in the pause menu, game menu and View replay | The pause effect's 2x affine sprites (OAM 8/12) put texture row 16 on line 231: the PS1 GPU rounds an interpolated texture coordinate to the nearest texel, the GBA truncates. `pp_obj` places each affine texture corner half a texel further on. The 224-line area is not cropped. Line 231 clean on SwanStation and Beetle in the pause menu, the game menu and the View replay screen. |
| R | Long music gaps (rc7 level 51 % sound, silences to 16.6 s) | `CDDA_HMAX` (= `CDDA_QMAX/2`): after a hold of 4 s or more the radio resumes after the short quiet interval (1 s) and the back-off resets; ROM page reads are never blocked. Round 2: this early resume backs off too (row H). |

Memory of the release (round 1 / rc7 in brackets): runtime ends `0x800270f0`,
3,856 bytes free (4,464 / 4,768); `.rtcold` ends `0x80029fb4`, 76 free (76 / 968);
ROMPG `0x8002a000`; page cache `0x8015e000..0x80166000`, 62 resident pages;
ragdoll 2,140 free (2,140 / 2,140); renderer ends `0x801afe2c`, 468 free (468 / 3,524).
`check_native` runtime free: Release 3,948, KPLAN test 636, SPEEDPROF 220,
virtual clock 5,884, D1CHK 2,188, D3 only 9,804, D2 only 8,652, D1 D4 5,084.
TEST_assist 544.

Speed, SwanStation, emulated time; stock = 100 % CPU and 1x CD,
recommended = `CPU_Overclock=400`, `CDROM_ReadSpeedup=10`,
`CDROM_SeekSpeedup=0`. Driving rows are level ticks/s / 3D pictures/s
(the GBA: 30 / 30).

| build | settings | language s | title s | power-on to level s | on foot | idle | tank | car | menus pictures/s (language/title/game menu) |
|---|---|---|---|---|---|---|---|---|---|
| rc7 | stock | 13.05 | 26.21 | 43.86 | 3.83 / 0.48 | 3.50 / 0.43 | 2.18 / 0.28 | 2.06 / 0.26 | 19.2 / 5.0 / 19.5 |
| rc7 | rec | 2.07 | 6.57 | 11.08 | 15.94 / 1.98 | 15.32 / 1.92 | 14.79 / 1.84 | 13.73 / 1.72 | 59.9 / 20.0 / 59.9 |
| wave 1 | stock | 10.88 | 18.30 | 27.58 | 6.12 / 1.47 | 3.70 / 0.77 | renderer overwritten | no car reached | 19.2 / 12.0 / 19.9 |
| wave 1 | rec | 1.94 | 6.27 | 9.58 | 28.62 / 16.15 | 28.52 / 15.75 | renderer overwritten | hang after entering | 59.9 / 30.0 / 59.9 |
| rc8 round 1 | stock | 11.18 | 18.67 | 27.98 | 27.74 / 10.88 | 29.02 / 12.08 | 28.97 / 13.05 | 26.63 / 8.67 | 19.9 / 12.0 / 19.9 |
| rc8 round 1 | rec | 1.94 | 6.29 | 9.66 | 29.80 / 29.62 | 29.87 / 29.80 | 29.81 / 29.61 | 29.23 / 28.29 | 59.9 / 30.0 / 59.9 |
| rc8 | stock | 11.14 | 18.57 | 27.78 | 27.57 / 11.97 | 28.54 / 11.40 | 28.81 / 12.59 | 28.77 / 9.41 (traffic car) | 19.9 / 12.0 / 19.9 |
| rc8 | rec | 1.94 | 6.26 | 9.56 | 29.85 / 29.77 | 29.90 / 29.87 | 29.71 / 29.31 | 29.85 / 29.83 (traffic car) | 59.9 / 30.0 / 59.9 |

Music, round 1, full US disc, SwanStation stock: level 91.4 % of the time
with sound, longest silence 3.3 s; menus 97.5 % (rc7: 51 % / 95 %, longest
16.6 s). The review showed that the same build without `CDDA_HMAX` gave the
same 91.4 % from that state (4 page fetches in 2 minutes): that figure was not
caused by `CDDA_HMAX`, which mattered only under steady page reads and there
cost 12-20 % of the level speed on SwanStation (row H).

### rc8 round 2: review findings

| | Finding | Fix |
| --- | --- | --- |
| H | (medium) `CDDA_HMAX` resumed the music every 4 s under steady page reads (fast driving, teleports): 19-23 resumes in 2-4 min, each a seek to the music and back that the game waits for, 12-20 % of the level ticks/s on SwanStation | The early resume backs off: when music that came back through it is held again before it has played 4 s, the hold needed for the next early resume doubles (`cdda_hmax`, up to `CDDA_HMAXX` = 32 s); music that plays 8 s sets it back to 4 s. Data reads are still never delayed. |
| K | (low) `clk_gba` computed `G` from the 32-bit `clk_lines`: at its wrap (75.8 h after power-on) TM3:TM2 stepped back about 3 h, `g_gframes` jumped by about 11,500 and the level clock stood still | `clk_hi` counts the wraps of `clk_lines` in `clk_poll`; `G = (lo*K >> 16) + (hi*K << 16)` (two 32x32 multiplies) is the exact 64-bit value. `clk_now32()` and its differences stay 32-bit. |
| D | (low) Overlay-area targets with a cold-table entry (`0x03000da8`, `OV1_INIT`) went through the D2 link and the D1 fill, which could later run overlay-0 code while the film overlay is resident | `h_miss` never D2-links an overlay-area target (a call site cannot be unlinked); it fills D1 only while overlay 0 is resident, and `ov_slots(1)` (the film overlay comes in) empties D1. Not caching them at all cost the menus 4-7 % (pad route 66 frames later on SwanStation, 114 on Beetle), so D1 keeps them. |
| G | (low, not reproduced) A bail-out at 191 m/s after a Beetle helicopter crash | The bail-out launch is halved until the sum of its absolute x and z speeds is 64 m/s or less (the sum taken unsigned). Driving bail-outs were 9-95. |

Measured on the round-2 release discs, emulated time:

- Radio under page-read stress (radspeed, a teleport every 600 frames, 2 min, level
  ticks/s): SwanStation 22.60 as built, 23.59 with the early resume disabled
  (rc7 behaviour), 25.13 radio off (round 1: 21.15 / 24.68 / 24.02); Beetle
  24.71 / 25.70 / 25.76. Every 450 frames over 4 min, SwanStation: 12.88 /
  13.74 / 14.14 (round 1: 11.19 / 14.02 / 14.14). The cost against the rc7
  behaviour is 4-6 % (round 1: 14-20 %); sound under this stress 13 % / 4 %
  (round 1 25 %), longest silence 37 s.
- Radio in normal play (radspeed without teleports, 2 min, 8 page fetches):
  SwanStation 78.0 % sound, longest silence 5.3 s, 27.95 ticks/s; with the
  early resume disabled 69.5 %, 16.9 s, 28.18. Beetle 82.2 %, 4.9 s, 28.94;
  disabled 80.4 %, 14.9 s, 29.05. music.py (level, then menus): SwanStation
  stock 78 % / 94 %, recommended 95 % / 96 %; Beetle stock 82 % / 97 %,
  recommended 80 % / 93 %. The level share depends on the state (8 fetches in
  these 2 minutes against 4-5 in round 1's state, which gave 91 %).
- Clock: `clk_lines` moved to 20 s before its wrap (rig intervention): the
  level clock keeps running (1,771 ticks in the last 60 s of 10 min on
  SwanStation, 1,796 of 2 min on Beetle), `g_gframes` advances with the frames,
  `clk_hi` = 1. The TM3:TM2 pair wrap: clock recovers (as round 1).
- View intro after a level (both cores): D1 held `0x03000da8` in the level
  and at the title, held no overlay-area key while the film overlay was
  resident, back at the title after 1,020 / 1,110 frames, Play game works.
- Pad route to the level: SwanStation 1,665 frames (27.78 s), Beetle 1,615;
  recommended 573 / 873 (round 1: 1,677 / 1,611 / 579 / 871).

Verified on the round-2 release discs (SwanStation and Beetle unless noted):
the static gates (`mips1_lint`, gpuwait, loaddelay, `prepare --check`, 71
unit tests, `check_native`, `check_intro_site`, `disp_patch_check`,
`verify_inputs` 40/40, `rtcold_proof`); pad route 13/13 at stock and
recommended; the two boot logos and the title (own `logos.py`); tank, a
traffic car (SwanStation stock and recommended, Beetle stock) and the
helicopter (enter, fly, get out; renderer intact); quit from foot, tank, car
and helicopter, a second level; GAME OVER (SwanStation); the in-level session
35/35 (SwanStation; the man is moved by the rig and held there for 30 frames
before L1, and entered the traffic car next to him); flicker in the level and
while driving (0 changes without a flip, 0 black), the 11-map scan (6,600
changes, 0 without a flip); memory card save and cold-boot load; invariant
soaks (code, page pool, pages equal to `ROM.BIN`, interpreter stacks, D1
overlay keys, black pictures): SwanStation stock 30 min, Beetle stock 20 min,
SwanStation recommended 30 min, all clean; a 30-minute soak at recommended
settings (1,800 s of game time, no fault); the Europe disc to the title on
both cores and to the level (Beetle; SwanStation reaches the level, its city
classifier misreads the PAL picture, the picture shows the city).
Expected FAILs: `boot_to_title` (5: the GBA's third logo and the intro film
are the film overlay, which this port skips, rc7 design I2; its logo samples
at fixed GBA frames land on fades and the title), the `clkprobe` control run
(a jump of one hour that leaves TM3:TM2 in its upper half: the game stops its
clock there, as on the GBA), the soak's "3D missing 10 s" (the man stood
against a grey wall, picture viewed), the TEST_assist level check "three
lives" (the assist takes a mode with five lives). Open: the intro film still
does not play, the pause picture lingers 2-4 s after the pause menu.

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
