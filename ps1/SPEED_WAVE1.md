# PS1 speed, wave 1 (stages 0-3): integration result

Branch `ps1speed` (worktree `S/ps1speed/wt`, from 16a963b). S = the session scratchpad.
All speeds are in emulated time: core frames / 59.94. Firmware is openboot unless a row says otherwise.

## 0. Review fixup (supersedes the release of section 2 and open failure 1 of section 5)

**New release: `payback_w1b`** (build `pbw5`), in `S/ps1speed/out/`:
- `payback_w1b.bin` / `.cue` / `.chd` / `.elf` / `.exe` / `.nm.txt`; checksums in `sha256_w1b.txt` (bin 507b453f…, chd bbc142ee…, EXE 449205f4…).
- verify_disc RESULT PASS: US licence, 15 tracks (songs 1, 2, 4 of the remix set, no song 3), data track 7,776 sectors. chdman exit 0.
- CFLAGS: the wave-1 list plus `-DPADSPLIT` (now in `BOOTF` of tools12/build.sh).
- Runtime 8,656 bytes free (was 9,040); renderer 3,540; ragdoll 2,428. Helper table and fixed addresses unchanged; verify_inputs 0 failed.
- mips1_lint 0 invalid of 53,158 words; gpuwait_classify 14 waits, all before a command; prepare --check 156 files; unit tests 70 OK; check_native OK.
- Test disc (data track only): `S/ps1speed/wave1fix/discs/pbw5.cue`. Runs: `S/ps1speed/runs/wave1fix`.

**Findings and what was done**

| finding | verdict | change |
|---|---|---|
| 1 (medium) title menu ignores the pad = rig artifact | **Half right.** The rig's 2-frame taps were an artifact, but with fixed-length presses the release still failed. | rig copy `wave1fix/sessions/tapfix.py` (tap() holds and releases at least 8 emulator frames); two runtime fixes below |
| 2 (low) D2 queue full: neither linked nor cached | Confirmed | `d2_link` returns 0 when the queue is full, so the target goes into D1 |
| 3 (low) P6 polls bypassed by D1/D2/D4 | Right by the code; no lost press measured in the cases P6 targets | comment in rt.c now states the real coverage; no new poll site |
| 4 (low) COLD1_QUIET in virtual frames | Confirmed by the code | 30 real frames (0.5 s) under RTC_GFRAMES; 4 otherwise |

**Finding 1, what really happens.** With the tap fix the release (pbw3) still failed boot_to_title. Control setup and Credits did not open, even with Cross held 82 frames.
- Trace (`wave1fix/sessions/title_trace.py`, run `sw_ttrace8cold_pbw4`): after a cursor move the title menu waits for ROM pages. The guest then reads KEYINPUT only once in 30-40 real frames.
- A player who lets go of DOWN and presses Cross inside that gap gives the guest both changes in one read (DOWN up and A down together). Payback's title menu then takes no A: no entry opens however long A is held. Cross pressed with a read in between opens the entry.
- This depends on the real-time clock and not on CDPADPOLL. The clock-only build w1c with the fixed taps still fails (`sw_b2t_w1c`: 4 of 5 entries do not open).
- CDPADPOLL made it worse. It latched a DOWN that the guest had already seen, and delivered it again together with the Cross (`io_keys 037e` in `sw_ttrace8_pbw3`).
- Fix 1, in CDPADPOLL: the P6 latch is edge-triggered. Only a button that goes down after the guest's last look is latched (`pad_cddn`).
- Fix 2, new flag **PADSPLIT**, rt.c io_read: while the level clock stands still (menus, pause), a read that sees one button go up and another go down reports only the release. The new press is reported from the next guest frame on, and it is kept even if released meanwhile.
- Not in a running level: there a guest frame is a whole iteration.
- The bisection of section 5 is replaced by:

  | build | SW boot_to_title, fixed taps: entries that open |
  |---|---|
  | pbw3 (wave 1) | 2 of 5 |
  | pbw4 (edge-triggered P6 only) | 2 of 5 |
  | w1c (clock only) | 1 of 5 |
  | **pbw5 (both fixes)** | **5 of 5** (SW data disc and full disc, BE, PCSX full disc) |

- Before the fix, the title_trace repro with 8-frame cursor taps failed on its first Cross. With the fix it opens.

**Gates of the fixup (pbw5, openboot unless noted)**

| check | SW | BE |
|---|---|---|
| power-on -> level (pad route) | 27.28 s (= pbw3) | 26.38 s (pbw3 26.23) |
| language / title reached | 10.88 / 18.30 s | 10.21 / 17.23 s |
| logo 1 static | 2.252 s | 2.135 s |
| pad route cold boot to the level (ngl_boot) | 10/10 | 10/10 |
| boot_to_title, tap fix (data disc / full disc) | 29 PASS 8 FAIL / 29 / 8: all 5 entries open and return | 29 PASS 8 FAIL: all 5 entries open |
| foot 60 s: ticks/s, it/s, fetches per 1000 ticks | 5.87, 1.30, 1,267 | 6.53, 1.45, 969 |
| idle 60 s: ticks/s, it/s | 4.85, 1.02 | 3.55, 0.70 |
| foot 180 s ticks/s (pbw1 in brackets) | 4.89 (4.88) | 4.65 (3.32) |
| idle 180 s ticks/s (pbw1 in brackets) | 4.31 (4.65) | 3.44 (3.89) |
| level gf/s | 59.81 | 60.11 |
| menus pictures/s (language / title / game menu) | 19.24 / 11.97 / 19.94 | 19.2 / 10.0 / 14.97 |
| level-start taps (3/6/12 frames, taps_level_vf) | 0 lost | 0 lost |
| language-screen taps of 3 frames | 6/6 | 6/6 |
| pause / unpause (pausek) | 8/8 | 8/8 |
| in_level steps | 20/20 | 19/20 (the ANSWER THE PHONE banner, as pbw3; sheet viewed) |
| flicker in the level (60 s): changes / presents / extra / black | 43 / 42 / 0 / 0 | 34 / 33 / 0 / 0 |
| flicker in the menus (120 s) | 2,354 / 2,367 / 0 / 0 | 2,364 / 2,377 / 1 / 0 (frame 603, the language fade-in step as in wave 1; shot viewed, whole picture) |
| soak 10 min with L1, seed 7 (SW) | 6 PASS 2 FAIL as in the review: speed, and "3D missing 3 s" (shot 011 viewed: city and HUD drawn) | - |
| PCSX-ReARMed boot_to_title, full release disc, tap fix | 29 PASS 8 FAIL, all 5 entries open (wave 1: 15 / 10) | |

Remaining boot_to_title FAILs on every core:
- Two "logo drawn" checks: the rig's snapshot timing against the faster logos.
- Five checks of the intro film / View intro: the rc6 intro bug (rc6 fails the same; rc7 has the fix).

Also in boot_to_title: 4 of about 20 cursor presses (40 frames, about 1 guest frame) right after coming back from Credits or Set language moved the cursor only on the rig's retry. The title menu runs at about 1.5 guest frames/s after Credits, because it waits for ROM pages (`sw_tseq_pbw5`: 33 fetches in 280 frames). That is Stage 6 (page pool).

**D2 queue (finding 2), measured.** The 204 "full" of the review's soak all came before the level state, during the boot and the level load. A 10-minute replay of the same soak inputs from the level state (`wave1fix/sessions/d2count.py`) has 0 full on both builds. Counters at the level state:

| build | linked | full |
|---|---|---|
| pbw3 | 314 | 204 |
| pbw5 | 269 | 62 |

Cold calls up to the level state: 53,754 on pbw3, 53,465 on pbw5. Level throughput does not change measurably: cold_find runs about 100 times a minute in the level.

**Finding 3.** The review reads the code correctly: D1/D2 send repeated cold calls past cold_find, and D4 stores to EWRAM/IWRAM without h_memwr.
- No lost press was measured in the cases P6 is meant for:
  - level-start taps of 3/6/12 frames: 0 lost on both cores;
  - language taps of 3 frames: 6/6.
- The menu losses the review cites were 2-frame presses, shorter than one guest frame. That is sampling, not P6.
- Adding a poll site costs SIO transfers in the level. So the coverage is written down in rt.c and not extended. A wave-2 item if a measured loss appears.

**Finding 4.** The power-on times are unchanged (SW 27.28 s, the same frame). The one-pass COLD.BIN read starts from the black-screen trigger on this route, so the fallback in present() did not fire. The fallback path was not forced in a run.

## 1. What was merged

| commit | what |
|---|---|
| 4bed857 | Merge ps1fix rc6 (340d953) |
| 39c8d2e | Merge spd-clock (8eb21c2): Stage 0 stamps and the Stage 1 real-time clock |
| c732dd5 | Merge spd-disp (b8b0baa): Stage 2 dispatch D3 D1 D4 D2 |
| 705db3b | Merge spd-boot (5bc717f): Stage 3 EXEPACK, COLD1PASS, PCPAIR, CDPADPOLL |
| c1a654c | Ties the Stage 1 clock to the rc6 radio and covers it in the checks |
| 1be18b9 | Fix: interpreter C stacks are handed out from the top of their area, so they no longer sit on the ROM page table (see 4) |

- All merges are `--no-ff`; both sides were kept.
- The manifest was recomputed: 155 files, 156 with this report (ps1/SPEED_WAVE1.md).
- c1a654c contents:
  - CDDA_QUIET / QMAX / WD defaults set in real frames under RTC_GFRAMES.
  - `clk_gba()` added before `cd_rd_gf` in cd_read.
  - check_native variants for SPEEDPROF and the virtual clock.
  - A profile test that requires the clock and dispatch items in the release.

## 2. Release (wave 1 as integrated; superseded by payback_w1b, section 0)

- Full disc in `S/ps1speed/out/`, made with `mkdisc2 --region U --default-tracks`:
  - `payback_w1.bin`, `.cue`, `.chd`, `.elf`, `.exe`, `.nm.txt`.
  - Checksums are in `sha256_w1.txt`.
  - verify_disc: RESULT PASS. 15 tracks, US licence, no song 3, data track 7,775 sectors.
  - chdman exit 0.
- Build: `pbw3`, from the tree at 1be18b9. EXE sha256 2b3b4e4d…
- CFLAGS: `-DSF3_DEFER -DPCACHE1 -DRTC64 -DRTC_TIMERS -DRTC_PRESENT -DRTC_PMAX=100 -DRTC_GFRAMES -DRTC_QUANT -DRTC_DT -DDISP_D3 -DDISP_D1 -DDISP_D4 -DDISP_D2 -DEXEPACK -DCOLD1PASS -DPCPAIR -DCDPADPOLL`
- Test-only flags off: SPEEDPROF, DISP_PROF, DISP_D1CHK, DISP_FREEZE_GF, CDSTAT, CDDA_DATARADIO, CDPADPOLL_AB, PCPAIR_LEVEL, KPLAN, PADDBG.
- Free bytes: runtime 9,040; renderer about 3,540; ragdoll 2,428.
- Test builds and data-track discs are in `S/ps1speed/wave1/discs`:
  - `pbw3` (release);
  - `pbw3p` (+SPEEDPROF);
  - the bisection builds w1c, w1cd, w1cb, w1db, w1d, w1b, w1bnp, w1none, w1rc6m, w1nod1, w1nod2, w1nod3, w1nod4 (each `.flags` file names its env).
- Checks:
  - prepare --check: 156 files verified.
  - Unit tests: 70 OK.
  - check_native: OK.
  - mips1_lint: 0 invalid of 53,066 words.
  - gpuwait_classify: 14 waits, all before a command.

## 3. Numbers (SwanStation / Beetle)

All numbers below are from openboot and the pad route.

Notes on the columns:
- "Wave 1" is the release pbw3. It measures the same as pbw1 (before the fix) to the frame on every scene that was run on both.
- "Stage 1-3" is what each engineer reported for their stage alone.
- Level windows: 60 s from the level state settled to clock 150.

| metric | base (BASELINE.md, b0) | stage engineers | wave 1 | PLAN target (stage 3 row) | verdict |
|---|---|---|---|---|---|
| power-on -> level | 43.03 / 45.76 s | S1 38.81 / 37.85; S2 37.34 / 39.24; S3 37.32 / 38.41 | **27.28 / 26.23 s** | ≤ 30 / ≤ 33 s | PASS |
| language screen / title | 12.78 / 25.88; 12.98 / 28.21 s | S3 11.73 / 23.16; 11.31 / 25.01 | 10.88 / 18.30; 10.24 / 17.18 s | - | better |
| logo 1 static (GBA 2.04 s) | 6.54 / 8.26 s | S1 2.236 / 2.119 | 2.252 / 2.119 s | GBA ± 5 % | SW +10 % (as S1), BE PASS |
| CD requests to the level (misses + cold loads) | 85+31 / 85+31 (rc6) | S3 53+0 / 54+0 | 55+0 / 56+0, plus the one-pass COLD.BIN read | -25 % | PASS (-52 %) |
| foot ticks/s | 0.57 / 0.47 | S1 6.92 / 5.22 | 5.10 / 4.00 | 28-32 / 27-32 | FAIL (CD-bound, Stage 6) |
| foot it/s = pictures/s | 0.57 / 0.45 (pictures 0.07 / 0.05) | S1 1.52 / 1.07 | 1.13 / 0.82 | ≥ 13.5 / ≥ 11 | FAIL |
| foot gf/s | 1.15 / 0.90 (virtual) | S1 59.86 / 59.82 | 59.82 / 59.92 | 59.7 ± 0.3 | PASS |
| foot CD fetches/s | 8.10 / 6.27 | S1 6.57 / 5.72 | 7.92 / 7.43 | - | - |
| fetches per 1,000 ticks | 14,294 / 13,429 | S1 949 / 1,096 | 1,552 / 1,858 | ≤ Stage 0 + 10 % | PASS |
| idle ticks/s / it/s | 0.57 / 0.57; 0.43 / 0.45 | S1 5.53 / 1.12; 4.22 / 0.85 | 4.75 / 0.95; 4.75 / 0.98 | as foot | FAIL |
| LOD 0 on foot | 100 % / 0 % | S1 24 % / 0 % | 10 % / 0 % | - | adaptive LOD (S1 note) |
| car ticks/s (60 s, full disc) | 0.05 / 0.12 | S1 0 (hang) | **0 / 0 (hang in the first car picture)** | - | FAIL (pre-existing mult-5 hang, see 5) |
| menus pictures/s (language / title / game menu) | 19.2 / 4.63 / 15.0; 15.0 / 5.0 / 14.97 | S2 19.2 / 12.0 / 19.94; 19.2 / 10.0 / 14.97 | 19.5 / 11.97 / 19.94; 19.2 / 10.0 / 15.0 | Stage 4 row | better than base |
| menus gf/s | 19.2 / 4.6 / 15 (virtual) | S1 about 59.9 | 59.87 / 59.77 / 59.84; 59.84 / 59.91 / 59.91 | 59.7 | PASS |

Notes on the table:
- The ticks/s and it/s targets of Stages 1-2 (28-32 ticks/s) cannot be met while the level is CD-bound.
  - On foot, a level iteration is about 955k lines, of which about 800k are CD wait (SPEEDPROF build pbw1p: CDL / ITL).
  - The step multiplier sits at 5, period 19.
- The level path depends on time-scripted input, so steady ticks/s varies with the walk.
  - 180 s windows, SW foot: pbw1 4.88, clock only 5.63, clock+dispatch 5.28, clock+boot 5.68.
  - 180 s windows, BE foot: 3.32, 3.56, 4.19, 4.59.
  - The spread is about ±15 % and has no order by item, so no item makes the level slower.
  - Clock only (w1c) reproduces the clock engineer's b1 to the frame: boot 38.81 s, foot 6.92 ticks/s over 60 s.
- SPEEDPROF build (pbw1p, before the stack fix):
  - Boot 27.33 / 26.59 s.
  - Foot ticks/s 5.55 / 5.18; idle 5.33 / 5.28.
  - Iteration trigger C3 in 100 % of iterations (C3MISS 0).
  - Present split, SW foot, per present: SVC 849, eng 374, DMA 193, pp_draw 138, vsync 128 lines.
  - SW CD options and firmware variants, power-on to level:

    | option or firmware | SW | BE |
    |---|---|---|
    | read speed-up 8 | 27.93 s | - |
    | read speed-up 10 | 41.88 s (CD retries, recovered, no error screen) | - |
    | instant seek | 21.14 s | - |
    | openboot strict | 27.28 s | 26.23 s |
    | built-in OpenBIOS | 35.07 s | 32.37 s |

## 4. Combination fault found and fixed (D3 x interpreter stacks)

**Symptom.** The all-on release on PCSX-ReARMed (full disc, rig `save_load`) broke after Pause > Quit to title screen > Yes:
- the game menu picture had corrupted colours;
- the second level stayed on a white screen (tick frozen, then BADRD lines);
- or the core crashed with "invalid load/store at 0x08077bf8".

The contact sheet is `pcsx_all_full/e_save_load/sheet.png`. rc6 (`S/ps1fix/runs6/pcsx_all/e_save_load/sheet.png`) is clean.

**Bisection.** Full discs, PCSX-ReARMed, rig session e:

| build | result |
|---|---|
| clock only | pass |
| clock + boot items | pass |
| clock + dispatch | crash |
| all items, no D1 | crash |
| all items, no D2 | crash |
| all items, no D4 | crash |
| all items, no D3 | pass |
| no D3, with the non-D3 page table moved onto ROMPG | crash again |

The last row shows the fault is the memory at ROMPG, not D3's patch.

**Cause.**
- `interp_enter` (stage8 `interp/interp_asm.s`) gave interpreter depth d the 1 KiB C stack ending at `ip_stacks + (d+1) KiB` (ip_stacks = 0x8002c000).
- Depth 0, nearly every call, therefore grew down directly into the top of ROMPG (0x8002a000..0x8002c000).
- The quit path's interpreted code used more than 1 KiB and wrote guest values (such as 0x08077bf8) into page-table slots.
- Without D3 the table was a separate BSS array and ROMPG was unused, so nothing showed.

**Fix (1be18b9).**
- Depth d now starts at `ip_stacks + 0x4000 - d KiB`, so a deep depth-0 stack runs into the unused deeper slots.
- D3 stays on.
- pbw3 now passes save/load: quit, then a second level with the city (`pcsx_full_pbw3/e_save_load/sheet.png`, viewed).
- All scene numbers are unchanged.

## 5. Regression

| check | SW | BE | evidence (runs/wave1/...) |
|---|---|---|---|
| in_level steps idle, walk, turn, weapons, fire, pause | 20/20 PASS | 19/20 | `sw_inlevel_pbw3`, `be_inlevel_pbw3` |
| pause / unpause (pausek) | 8/8 | 8/8 | `*_pausek_pbw3` |
| flicker in the level (60 s) | 43 changes / 42 presents / 0 extra / 0 black | 37 / 36 / 0 / 0 | `*_flickerlvl_pbw3` |
| flicker in the menus (120 s) | 2,361 / 2,374 / 0 / 0 | 2,365 / 2,376 / 1 / 0 | `*_flickermenus_pbw1` |
| boot route flicker (ngl_flicker) | 3 black / 6 extra | 3 black / 6 extra | `*_nglflicker_pbw1` |
| level-start fade from white | 4 pictures | 2 pictures | `*_boot_pbw1/flash` |
| level-start pad taps (3 / 6 / 12 frames) | 0 lost of 12 / 12 / 12 | 0 lost | `*_tapslevelvf_pbw3` |
| language-screen taps of 3 frames | 6/6 | 6/6 | `*_taps_pbw3` |
| DualShock in digital mode | pad id 41, Down seen in 90 samples | pad id 73 (analog by default), Down seen | `*_ds_pbw3` |
| SW read speed-up 8 / 10 / instant seek | level reached, no faults | - | `sw_boot_pbw3_rd8`, `_rd10`, `_seek0` |
| openboot strict / built-in OpenBIOS | PASS | PASS | `*_boot_pbw3_strict`, `_openbios` |
| memory card save (save file, CRC) | PASS | PASS | scene boot `card1.mcd` |
| radio hold / resume (full disc) | 7/7 PASS | 7/7 PASS | `*_radiocycle_pbw3` |
| car (full disc) | FAIL: hang | FAIL: hang | `*_car_pbw3_full` |
| fast core run_all.sh (PCSX-ReARMed, full disc) | see below | | `pcsx_all_w3.log` |
| rig boot_to_title + save_load (SW, full disc) | see below | | `sw_all_w3.log` |

Notes on the rows:
- in_level on BE: the one fail is "3D city stays on screen". The classifier counted the ANSWER THE PHONE banner over the city as 'menu' once. The picture was viewed and the city is there.
- The menus-flicker extra on BE is at the window's second frame: a step of the language screen's own fade-in. The picture was viewed and is whole.
- ngl_flicker counts are the same as rc6 and the boot engineer's d7: the game's own fades.
- Level-start fade from white: Stage 1 b1 had 4 / 3.
- Level-start taps:
  - The boot engineer's `taps_level.py` counts guest frames in `g_gframes`, which counts real frames under Stage 1. It reported 31 of 39 lost.
  - The copy `wave1/sessions/taps_level_vf.py` counts g_vf + the level clock, as clkrig does. With it, no tap is lost. The earlier loss was a measurement artifact.
- Memory card: BE `mc_err` 1, one retried transfer, also in Stage 1 b1.

Fast core run_all (PCSX-ReARMed, full disc). Results by session, wave 1 vs rc6 (`S/ps1fix/runs6`):

| session | wave 1 | rc6 |
|---|---|---|
| a boot_to_title | 15 PASS / 10 FAIL | 32 / 6 |
| b new_game_to_level | 13 / 0 | 13 / 0 |
| b assist | 2 / 1 | 2 / 1 |
| j replay | 5 / 0 | 5 / 0 |
| d maps | 30 / 0 | 30 / 0 |
| e save_load | 17 / 1 | 24 / 0 |
| f soak | 7 / 1 | 6 / 2 |
| c in_level | 22 PASS, then a rig TypeError (player entity None) | 18 / 6 |
| g state_check | 7 / 0 | 7 / 0 |
| h speed | 2 / 0 | 2 / 0 |
| i strict_cpu, plain and patched | 4 / 0 each | 4 / 0 each |

- Data-track-only discs stop at the language screen on this core: the language list is never drawn. rc6's ISO passed only because the rig picked up its full-disc .cue.
  - The full disc is required here.
  - Same code, same ISO bytes but the date: w1rc6m behaves the same way.

**Open failures, not fixed here (each bisected):**

1. **Title menu stops taking the pad after the first cursor move.** FIXED in the review fixup (section 0): the cause was a release and a press merged into one KEYINPUT read during the menu's ROM waits (real-time clock), made worse by CDPADPOLL re-delivering a seen DOWN. The bisection below used the rig's 2-frame taps and is superseded.
   - rig boot_to_title, SW and PCSX: Control setup, Credits, Set language and Delete game do not open; the cursor stays on Delete game.
   - Two DOWN presses of 10-12 frames (167-200 ms) did not move the cursor within 3,000 frames.
   - Bisected on SwanStation, data discs:

     | build | result |
     |---|---|
     | rc6 | pass |
     | all items off (w1none) | pass |
     | rc6 merge rebuilt (w1rc6m) | pass |
     | dispatch only | pass |
     | boot items without CDPADPOLL | pass |
     | boot items (w1b) | FAIL |
     | clock only (w1c) | FAIL |

   - So **CDPADPOLL** and the **Stage 1 clock** each cause it on their own. It is not a combination effect.
   - Turning CDPADPOLL off alone would not fix the release, and turning the clock off removes Stage 1. Both flags stay on, and this is reported as a FAIL for the fixup.
   - The pad route used by the scenes (title > Play game > ... > Single player rampage) still works on both cores, so short menu routes pass.
2. **Car: hang in the first car picture** on both cores (0 ticks, g_pres +1).
   - Stage 0 found the cause: base at a frozen step period of 19 (mult 5) hangs the same way. present() starts; stage7_pre or sf3_frame never return.
   - Stage 1 makes mult 5 the normal case.
   - It was not fixed by the stack fix. The Stage 1 report already asks to fix it before shipping.
3. **Cold boot with a save, rig save_load process 2.**
   - The rig presses Cross at frame 10300. It lands on the ZOO logo, because the logos are faster now. The pre-existing rc6 intro bug then keeps the game there ("Cross during the intro brings the title menu" fails on rc6 too; rc7 has the intro fix).
   - On SwanStation the runtime also did not print "MC loaded" in that process.
4. **Logo 1 / logo 3 "drawn" checks** (lit pixels 0 %): the rig's snapshot timing against the faster logos. The logos are seen in the scene runs.

## 6. Not done

Fixup round:
- Finding 3: no new P6 poll site (see section 0). Finding 4: the present() fallback of COLD1PASS was not forced in a run.
- Car hang (open failure 2) and the save_load intro case (open failure 3) are unchanged; full-disc car, radio, memory card, strict/OpenBIOS and CD-speed runs were not repeated for pbw5 (the fixup changes only the pad read in menus, the D2 queue-full return and a boot constant that did not fire).
- Cursor presses right after Credits / Set language sometimes need a second try while the title menu waits for ROM pages (about 1.5 guest frames/s): Stage 6.

Wave 1:

- PLAN throughput targets for Stages 1-2: 28-32 ticks/s, ≥ 13.5 / ≥ 11 it/s. The level is CD-bound (Stage 6 page pool).
- "100 % C3 over 1,000 iterations": 70 iterations measured, all C3.
- rc7 (ps1play d03e538 and later) is not merged. Its `.rtcold` section (0x80028040..0x8002a000) overlaps the D1 table (0x80028400) and the D2 queue (0x80029400). Its CLOCK page pool and io_hi time base overlap D3, M3 and Stage 1. This merge needs its own plan.
- SPEEDPROF numbers are from pbw1p, before the stack fix. pbw3p was built, but its runs were not repeated: the fix changes only where interpreter stacks live.
