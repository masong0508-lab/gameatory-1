# One-command PS1 rc8 private regression runner

**Status:** source-only harness prepared against the owner's rc7 draft test kit. Run the full matrix again **only after Claude supplies a private rc8 disc and matching ELF**. This file contains no licensed data, screenshots, CD audio, save files, game strings or binary test inputs. All output stays in the private directory supplied with `--out`.

## One command

```sh
python3 ps1/qa/run_rc8_matrix.py \
    --disc '/private/rc8/payback_rc8.cue' \
    --syms '/private/rc8/payback_rc8.elf' \
    --cores '/private/Payback-PS1-QA-kit/cores' \
    --system '/private/Payback-PS1-QA-kit/system' \
    --out '/private/rc8-qa-20261122'
```

The output directory **must not exist**: the runner refuses stale results from an earlier disc or settings. It requires the safe, fail-on-session-error `ps1/rig/run_all.sh` from **PR #8** and the `RIG_OPTS` propagation and accurate-core cold-boot fix from **PR #11**. It does not silently run a nominally recommended test at stock. Stock runs have *separate* output roots. To inspect the planned steps without loading a ROM or creating files, add `--dry-run`.

The runner executes these independent checks, keeps each full private log and writes only a private numeric `summary.json`:

1. **SwanStation accelerated:** `RIG_OPTS='swanstation_CPU_Overclock=400 swanstation_CDROM_ReadSpeedup=10 swanstation_CDROM_SeekSpeedup=0'`; real input boot, gameplay, walking, weapons, pause/quit, second level, save/load (including an openboot **second** process), maps, state validation, speed and replay. Invalid/empty rig sessions give nonzero exit. Menu-assist-only steps are SKIP when release ELF lacks KPL hooks.
2. **SwanStation accelerated 30-minute console soak:** dedicated `console_soak.py` runs **at least 108,000 emulator frames** with seeded movement; separately requires at least 600 seconds of **guest game-clock** progress and checks no unexpected level-end, long clock stalls, black intervals, missing city, fault-counter increments or runtime faults. This avoids the original rig's `soak.py` stopping when a shorter guest-clock target is reached, and avoids incorrectly demanding 30 min of *guest* time from 30 min of *emulated console* time.
3. **SwanStation accelerated 11-map picture scan:** dedicated `map_flicker.py` uses the same R2 **renderer-map test facility** as `rig/sessions/maps.py`, 180 warm-up frames followed by 1,200 per-map sampled frames, and reports unannounced RGB picture changes relative to **`g_flips`**, rc8's actual GPU display-start counter, as well as black flashes and large rapid brightness oscillations, with exact emulator frame numbers. `g_pres` records the beginning of `present()` and can advance out of phase with visible flips; using it as a GPU synchronization oracle previously caused a false rc7 issue. The scan now **requires** `g_flips` for release-grade evidence. An older rc7 disc can be inspected separately with `--allow-legacy-present-counter`, but its legacy `g_pres`-only results are explicitly marked **NOT CERTIFIED** and do not count as a GPU-synchronization pass. The frame comparison updates its previous flip counter on **every emulated frame**, even when two presented pictures look identical. A valid presentation change is not automatically a strobe, and zero events in the scan do not medically certify epilepsy safety.
4. **SwanStation stock:** repeat boot, walking/weapons, pause/quit, map and save/load, and the 11-map picture scan with CPU/CD overrides absent.
5. **Beetle stock:** repeat controller-input boot, in-level and save/load with openboot; Beetle's fast-CD options are intentionally not assumed equivalent to SwanStation's.
6. **Optional original GBA mGBA vehicle matrix:** if the owner sets `MGBA_CORE=/private/path/mgba_libretro.so` and passes `--gba-rom '/private/Payback (Europe).gba'`, run `payback-mod/harness/vehicle_matrix.py --require-all` as an additional job. It tests only **naturally spawned** descriptors, refuses model swapping, and records unobserved types. If no mGBA binary is available, the run does **not** fabricate GBA results.

Every nonzero job is counted as a failure, and **one failure makes the overall command exit 1**. Other jobs continue so one early failure does not hide later problems. `summary.json` records numeric job exits/times and explicitly sets `full_release_certified=false`, even when every automated job passes. It does not claim natural gameplay on all 11 maps, every vehicle type in every environment, phone missions and pickup completion, audible CD radio (silent QA kit), or DuckStation Android on a real phone.

### ROM-free checks

```sh
python3 -m unittest discover -s ps1/qa -p 'test_rc8_retest.py' -v
python3 -m unittest discover -s ps1/qa -p 'test_flicker_evidence.py' -v
python3 -m compileall -q ps1/qa
```

### Private validation on the owner's rc7 draft

The two new sessions were smoke-tested against the **actual private rc7 draft** under SwanStation and the exact recommended settings (not a newly built rc8):

- `console_soak.py --console-frames 120 --min-game-seconds 1` → **10 PASS, 0 FAIL**, and the observed number of emulated frames is exactly 120 after level setup. This is a short harness smoke, **not a 30-minute test**.
- `map_flicker.py --frames-per-map 600 --warmup-frames 180` → **56 PASS, 0 FAIL** across all 11 renderer maps (emulator frame 9,549), no all-black flashes or out-of-sync presents in that particular ~600-frame/map sample. A separate **30-frame/map** quick probe was expectedly too short to capture a picture on some maps and is **not** proof of an issue: rc7 presents only ~2 pictures per emulated second.

The earlier rc7 flicker smoke used the legacy `g_pres` counter; it was useful for black-flash and screen-change checks but cannot by itself prove actual display-flip synchronization. New rc8 results must show `flip_counter=g_flips` and `release_grade_flip_evidence=true` in the private `result.json`.

Run the complete **default 1,200-frame/map flicker scan and full 108,000-emulated-frame console soak on rc8** when its disc/ELF arrives. File actual reproducible regressions with core, options, disc/commit, session and emulator frame; repeat at stock before declaring them build defects. Do not upload private logs, ROM bytes, disc images, snapshots, emulator cores or game screenshots to GitHub.