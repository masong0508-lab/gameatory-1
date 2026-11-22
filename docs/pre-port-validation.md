# Pre-port cleanup and validation

This pass repairs the GBA build and test paths and prepares the staged PS1
sources for continued port work. It is not a finished PlayStation release.
The source repository and CI contain no game ROM, BIOS, extracted game assets,
or private save files.

## GBA changes

The standalone Stunt Fox build exceeded its IWRAM region by 6,384 bytes with
LLVM 19. Physics now uses Thumb ROM, as in the merged game, and model-normal
initialization runs from ROM. Drawing and fixed-point math remain in ARM IWRAM.
The linker reserves at least 3 KiB below the system stack, and startup takes
the stack addresses from that same linker definition. The tested build uses
28,500 bytes of IWRAM code/state and leaves 4,012 bytes below the system SP.

The host physics simulator read only 262,144 bytes of a 444,448-byte generated
world, then followed offsets past its buffer. It now reads the complete world,
checks section and geometry bounds, and rejects truncation or oversized inputs.
The larger buffer exists only in the host simulator. The real generated world
completed the documented 900-tick loop simulation.

The mission test runner now treats failed demo generation, fuzz processes and
golden-trace processes as failures even when an old file or matching stdout is
present. A failed `--update` cannot replace a reviewed golden trace.

Campaign route generation also had platform-dependent rounding: sequential
floating-point summation could turn an exact endpoint such as 4096 into
4095.999999999997 before integer conversion. Lengths now use `math.fsum` and
resampling keeps the final endpoint exact. Nine reviewed ring heights across
four generated maps rise by one world unit; horizontal positions, radii, axes,
mission definitions and persistent IDs are unchanged.

## PS1 source integration

The source preparation command now assembles 149 files with six ordered,
hash-checked patches. It preserves the later runtime while integrating the
model/tree changes, and runtime and renderer share one checked entity layout.
Build failures stop immediately in fresh work directories; compiler or disc
errors cannot silently reuse earlier objects.

The review also found shared-memory conflicts that a renderer-size check alone
missed. PPU palette/row scratch and cold-veneer reads now have separate reserved
regions outside renderer code. Model textures/palettes, PPU overlays and all
seven world texture pages use 19 bounded, disjoint VRAM allocations. Production
PPU cache/blit tests verify that the smaller backdrop cache preserves previously
drawn pages through eviction. The default ROM-page cache is eight pages, with
compiled allocation bounds checked by the linker.

The combined renderer fits its existing RAM region with `-Os`. Native positive
and negative link checks run in CI, but their generated tables are placeholders;
they do not constitute a playable PS1 image. The current runtime still has an
8 MiB ROM window and explicitly rejects the larger merged GBA ROM. Remaining
port work and emulator acceptance are recorded in [PS1 status](../ps1/STATUS.md).

## Actual emulator checks

All new integration runs used mGBA 0.10.5's stock libretro core. Each report
identifies the exact ROM by hash. These are scripted checks with the scope
below, not complete campaign playthroughs or hardware tests.

| Target | Checks | What was exercised |
| --- | ---: | --- |
| Existing `payback-mod` milestone | 28 | Native profile creation, a real car entry, Quit-committed statistics, EEPROM persistence, cold boots and early-close handling |
| Larger Stunt Fox merged build | 9 | Settings change/reopen, story start, walking, Arwing summon/boarding/takeoff, pause/resume, air bail-out and recovery |
| Stunt Fox standalone | 7 | Boot, acceleration, retry, Arwing entry/takeoff, return to the car and continued rendering |

The native-save test used **11 fresh OS processes** and prohibited emulator
savestates. Original-to-original, original-to-mod, mod-to-original and
mod-to-mod all restored the profile and its one carjacking statistic. Both
writers produced the same 512-byte EEPROM, and cold readers preserved it.
This evidence applies to `payback-mod` profiles and Quit statistics only. The
larger engine's 64 Kbit campaign save extension has separate host tests; its
device/cold-boot behavior is not established by this compatibility run.

The two larger-engine smoke paths use only real buttons and read-only state
inspection, with no teleports, debug commands or checkpoint loading. The
standalone's final sampled scene rendered 60 new game frames over 120 video
frames and reported 30 FPS. This is one emulated scene, not a game-wide or
hardware performance guarantee.

## ROM-free regression gates

`python3 tools/check.py --report test-results.json` runs the same required gates
as CI. They cover the Payback mod, content/arena validators, 66,595 campaign-save
assertions including interrupted writes, the mission VM with sanitizer and
optimized builds, deterministic fuzz, three golden traces, radio transitions,
and the new simulator and test-runner failure cases.

The ARM gate compiles and links every real standalone source against generated
tables and a synthetic world. It checks symbol placement and stack space and
verifies that the production linker rejects an image that invades the stack.
The PS1 gates assemble the pinned source layers, exercise build-failure paths,
and compile/link the native modules against the real RAM limits. Synthetic
tables in that native check cannot boot a game; they establish source and
layout compatibility only. See [the PS1 status](../ps1/STATUS.md).

CI uses Ubuntu 24.04 and LLVM 19. The local host sanitizer runs kept ASan and
UBSan active, with LeakSanitizer disabled because it cannot run under this
environment's ptrace supervision. CI uses the default sanitizer configuration.
`--rom ORIGINAL.gba` opts into private content/arena integration cases; the
untouched European source ROM is checked by SHA-1.

## Validated private artifacts

The merged validation build uses `--no-remixes`, retaining the original game
music. Optional remix rendering was not part of this pass. Its BPS patch was
applied with the independent decoder and reproduced the exact ROM; both new
ROMs have valid GBA header checksums.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Existing Payback milestone | 16,777,216 | `f6998c1a0839f913ced8281281a30a56ecfdbbab5a4775f935510140894b4a83` |
| Repaired standalone | 532,804 | `6867948855a8e2dbc9d68fca93e437464737b0b7554c0ab9bf94652f4b2d17b6` |
| Larger merged engine | 16,777,216 | `29aa80ac0032079861fc0915e65fd091699bbaed5f276b1640b7aa5a0a7cd961` |
| Larger merged engine's BPS | 3,303,928 | `f80bc8865d16e78e5b2fbfc136653e761b0f1b660c5ac4b7069caaea7bf38017` |

The merged GBA renderer still has only four bytes free in its main scratch
area (5,180 of 5,184 used). Its postlink guards remain enabled; future features
must respect that budget. Live builder edits in the smaller milestone still
reset on reload. Full story completion, extended soak tests, optional audio,
Pizza Boy A and physical hardware remain separate acceptance work.
