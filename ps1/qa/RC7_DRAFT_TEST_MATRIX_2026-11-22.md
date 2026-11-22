# Original Payback PS1 — rc7 draft independent QA matrix (2026-11-22)

**Scope:** private owner's rc7 US draft disc built from `c753516` (matching ELF, silent audio tracks), tested by GPT-6 using the owner's private, SHA-verified PlayStation QA kit. The game data track is the same as the intended rc7 disc. All **21/21** QA-kit components matched Claude's published SHA-256 and byte sizes. Executable identity: SHA-1 prefix `51882c238f25`. Private inputs, ROM bytes, music, emulator binaries, save states, screenshots, game strings and full logs **are not in GitHub**.

**Status:** review/testing handoff, **not** a DuckStation Android or full PS1 release certification. Code and performance fixes remain Claude's responsibility per [AGENTS.md](../../AGENTS.md). Only numeric outcomes and human-authored defect descriptions are recorded here.

## Test environments

| Profile | Emulator | Core options |
| --- | --- | --- |
| Recommended | SwanStation / openboot | `swanstation_CPU_Overclock=400`, `swanstation_CDROM_ReadSpeedup=10`, `swanstation_CDROM_SeekSpeedup=0` |
| Stock recheck | SwanStation / openboot | Unset/default CPU, CD read and seek options |
| Additional accurate-core | Beetle PSX / openboot | Stock defaults (Beetle speed options not calibrated) |

The recommended settings come from [ps1/EMULATOR_SETTINGS.md](../EMULATOR_SETTINGS.md). All elapsed frame counts below are **emulator frames**, not wall-clock seconds. Guest logic speed, pictures presented and actual game time are distinct measurements.

## Observed sessions

| Test | Core / profile | Result | Emulator frames | Qualification |
| --- | --- | --- | ---: | --- |
| Controller-only boot into first level | SwanStation recommended | **13 PASS / 0 FAIL** | 2,486 | Real game/disc; in-level sample ~32.6 guest frames/s and ~2.0 pictures/s |
| Controller-only boot into first level | SwanStation stock | **13 / 0** | 4,969 | Fresh stock boot |
| Controller-only boot into first level | Beetle stock | **13 / 0** | 5,282 | Fresh Beetle boot |
| Walk, turn, weapons, fire, pause/resume | Beetle stock | **16 / 0** | 8,525 | Actual first level, no vehicle step |
| Renderer-map R2 tour (all 11 visible worlds and return) | SwanStation recommended | **29 / 1** | 7,309 | All transitions succeeded; **one** image-classifier false negative, map 1; [issue #12](https://github.com/masong0508-lab/gameatory-1/issues/12) |
| R2 map 1 classification recheck | SwanStation stock | **6 / 0** | 499 | Rendered world accepted at stock; expected 3D content visible at recommended too |
| Save, quit, start second level | SwanStation recommended | **15 / 0** | 4,451 | Fresh blank card; save contents and second level verified |
| Cold-boot saved profile | SwanStation recommended | **8 / 1** | 904 | Profile, checksum and playable level pass; early TTY marker absent; [issue #13](https://github.com/masong0508-lab/gameatory-1/issues/13) |
| Save, quit, start second level | SwanStation stock | **15 / 0** | 9,600 | Fresh stock-generated save |
| Cold-boot saved profile | SwanStation stock | **8 / 1** | 3,325 | Same TTY-only false negative at stock |
| First-level full in_level sequence | SwanStation recommended | **30 / 5** | 89,265 | All five failures occurred after entering parked descriptor **k17**; [issue #14](https://github.com/masong0508-lab/gameatory-1/issues/14) |
| k17 vehicle-controls-only recheck | SwanStation stock | **9 / 5** | 59,985 | Same k17 entry, no acceleration/steer/reverse/exit; uses documented position adjustment |
| Tank descriptor **k11** | SwanStation recommended | **12 / 2** | 6,609 | Enter/accelerate/steer/reverse/exit **all pass**; one abbreviated approach and one pale-frame classifier false negative |
| Vehicle descriptor **k21** on actual city 10 | SwanStation recommended | **14 / 0** | 5,705 | Enter/accelerate/steer/reverse/exit pass |
| Game-over/continue | SwanStation recommended | **8 / 0** | 4,541 | Three **test-assisted** health-zero events: lives 3→2→1→0, game-over state and menu return |
| 30-minute seeded soak | SwanStation recommended | **6 / 2** | 108,001 | 108,000 running frames = ~30.1 min of **emulated console time**; guest game-time ~943.6 s, not the independently requested 1,800 s; false-positive color classifier; **no black frames, clock stalls, fault-counter increases, runtime TTY faults or renderer-off** |
| On-foot input & active renderer checks over 11 R2 viewer maps | SwanStation recommended | **23 / 0** | 16,903 | Render-map coverage, not proof that the guest simulation has loaded each city (R2 is a renderer test facility) |
| 11-map steady-state frame-hash flicker scan | SwanStation recommended | **12 / 1** | 16,807 | 1,200 scanned emulator frames/map after warm-up; zero all-black flashes, one unexpected picture update without present on Map 3 frame **4,873**, reproducible; [issue #15](https://github.com/masong0508-lab/gameatory-1/issues/15) |
| Isolated Map 3 flicker scan | SwanStation stock | **3 / 0** | 4,533 | No unannounced changes or black flashes in 1,200 scanned frames |

The 11 ordinary Rampage-menu city-selector positions were tested with **real controller presses**, producing **33 PASS / 0 FAIL** and actual guest map IDs **0, 3 and 10** in a repeating cycle; all three actually run the guest world and its renderer. Those results cannot certify natural playability of the eight other renderer maps. R2 11-map coverage is therefore deliberately tracked separately.

## Confirmed defects (human-readable GitHub issues)

1. [**#12**](https://github.com/masong0508-lab/gameatory-1/issues/12): color-based `view_state()` incorrectly flags a pale or dark **rendered 3D** city as a `menu`. Seen in Map 1 and a 1,620-frame interval of the long soak. Render counters and private frame inspection show active 3D.
2. [**#13**](https://github.com/masong0508-lab/gameatory-1/issues/13): save/load cold-boot session's early diagnostic TTY assertion fails in both stock and recommended profiles even though the saved profile, card checksum, save-slot selection and loaded 3D level all pass. Treat as a **harness instrumentation issue**, not evidence of corrupted saves.
3. [**#14**](https://github.com/masong0508-lab/gameatory-1/issues/14): entering parked descriptor **k17** switches control to the vehicle, but Cross, steering, reverse and exit fail despite normal level-clock progress, both **stock and recommended**. By contrast k11 and k21 drive/exit correctly. **Potential gameplay release blocker**, requires Claude's fix and a non-teleport approach retest.
4. [**#15**](https://github.com/masong0508-lab/gameatory-1/issues/15): one image update without `g_pres` advancing on Map 3 at recommended options, **frame 4,873**, reproducible in two 11-map scans and absent in a stock isolated scan. A **single possible GPU synchronization issue**, **not a proven recurring strobe**. All maps had zero all-black flashes.

## Not completed / limitations

- **Every vehicle type:** census from a dynamic entity snapshot observed up to 16 descriptor IDs in renderer-map tests, not all are accessible/drivable or necessarily stable across level transitions. Actual gameplay of **k11** and **k21** succeeded, **k17** failed, and a moving vehicle selected for k7 changed its descriptor before entry, so that cannot count as verified k7 gameplay. No blanket claim that every vehicle type has been played.
- **All 11 naturally playable cities:** the debugger/renderer R2 viewer rendered all 11, but normal Rampage menu selection cycled only guest maps 0, 3 and 10. Other story modes or unlock paths need separate tests.
- **Missions, phone prompts, pickups, naturally completed missions, tank cannon and vehicle collisions:** not yet independently certified. Documented ram-assisted teleports/deaths in the rig are clearly identified; they cannot substitute for full natural gameplay.
- **Radio audible output:** the QA-kit CD audio tracks are intentionally silent. Timing/state may be inspected but **audible radio quality cannot be certified** with this disc; rc7's CD-DA pauses during active reads are already known.
- **30-minute soak:** 30.1 minutes of **emulated console time**, not 30 minutes of in-game timer; guest clock advanced 943.6 seconds. This distinction is important when evaluating performance.
- **Flicker safety:** absence of all-black flashes in these sampled/continuous scans does not certify every possible gameplay/color transition. Issue #15 merits follow-up.
- **Phone hardware / DuckStation Android:** neither was used here; a SwanStation/Beetle pass remains emulator-specific.

## Required handoff before declaring PS1 playable

Claude to address [#14](https://github.com/masong0508-lab/gameatory-1/issues/14) (and independently review GPU [#15](https://github.com/masong0508-lab/gameatory-1/issues/15)), decide/test rig fixes [#12](https://github.com/masong0508-lab/gameatory-1/issues/12) and [#13](https://github.com/masong0508-lab/gameatory-1/issues/13), then supply an updated private rc7/rc8 disc and matching ELF for targeted retests. GPT-6 should also expand natural vehicle, mission and map routes. Continue improving **actually presented pictures/s** separately from guest game-logic frames/s. The real final acceptance remains DuckStation for Android on the owner's phone.

See [PR #11](https://github.com/masong0508-lab/gameatory-1/pull/11) for `RIG_OPTS` orchestration (stacked on #8; full ROM-free CI passed) and the input/soak option preservation needed to repeat the matrix. All private raw outputs are retained outside the public repository.
