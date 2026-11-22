# PS1 gameplay QA: independent evidence gate

**Status:** GPT-6's assigned QA task (see repository `AGENTS.md`). This is an
independent **audit of existing emulator rig results**, not a new emulator,
a release-ready declaration, or a replacement for the owner's **DuckStation
for Android** acceptance test. Claude owns the original 8 MiB Payback PS1
runtime, PS1 rc7, performance work and private release integration.

## What this checks

The existing `ps1/rig/` scripts write `OUTROOT/<session>/result.json`,
`speed.json`, screenshots, logs, save-state and card files. This tool reads
**only** their structured result files and produces a *sanitized* JSON summary:
session ID, check totals, last emulator frame, failure codes and numeric
speed measurements. No game text, screenshots, controller scripts, TTY logs,
private paths, saves, executables, or disc bytes appear in the summary.

| QA requirement | Actual existing rig evidence | Status in `audit.py` |
| --- | --- | --- |
| Cold boot, menus and new game | `a_boot_to_title`, `b_new_game_to_level` | Required by all profiles |
| Walking, turning, weapons, firing, pause, death, vehicle interaction | `c_in_level` | Requires a passing check in **each** category, not merely an open level |
| All 11 original city/map slots | `d_maps` | Requires passing results that mention maps 0–10 |
| Card creation, save payload CRC and **cold-boot** restore | `e_save_load`, `e_save_load/reboot` | Both runs required, on the **same disc EXE SHA-1** |
| Long-running game time without a reported stall | `f_soak` | Passing soak assertion **and** at least 600 × 30 level-clock ticks by default |
| Measured gameplay speed | `h_speed/speed.json` | Three *in-level* scenes, finite game-frame and presented-frame rates; optional user-approved minimums |
| Emulator save-state replay and deterministic input replay | `g_state_check`, `j_replay_script` | Added by `extended` profile |
| Source and disc identity | Each result's `meta.core`, `meta.exe_sha1`, `meta.syms_match_disc` | One intended core and the **same executable** across the batch; mismatches fail |
| Low-level guest faults | Each result's `tty_faults` | Nonempty faults fail even if ordinary assertions say PASS |

**Not automatically certified by this audit:** every vehicle class (the current
`in_level` session targets a nearby example and may use RAM intervention),
radio/actual audio listening, visual flicker and flashing, controller mapping
on a phone, **DuckStation Android**, physical PS1, or full 16 MiB merged
Star-FlyBack gameplay. Those remain **separate acceptance tasks**. The rig's
saved states and automated button presses must not be passed off as an
unassisted user playthrough.

## Run it after an actual private emulator session

Use a **new, clean OUTROOT**, outside the repository, for each disc/core/profile
combination. The existing rig documentation describes how to install its
cores, compile `openboot`, and build the private disc:

```sh
# From repository root; this is only an EXAMPLE layout of private paths.
cd ps1/rig
./run_all.sh /private/disc/payback.cue /private/results/swan /private/disc/payback.elf swanstation
cd ../..

# The 'gameplay' profile requires a,b,c,d,e,f,h. The rig also runs other
# diagnostic sessions, which may have independent failures of their own.
python3 ps1/qa/audit.py \
  --root /private/results/swan \
  --core swanstation --profile gameplay \
  --output /private/results/swan-qa-summary.json

# Only after the owner has agreed thresholds, apply them as *hard gates*.
# Example values here are illustrative, NOT agreed release targets:
python3 ps1/qa/audit.py --root /private/results/swan \
  --core swanstation --profile gameplay \
  --min-guest-fps 20 --min-presented-fps 10

# Without a finished disc, these 12 deterministic tests need NO ROM/BIOS/core:
python3 -m unittest discover -s ps1/qa -p 'test_*.py' -v
```

The audit exits **0** only when its selected evidence profile passes; missing,
empty, inconsistent, crashed, wrong-core, mixed-disc, or failing sessions exit
**1**. It does **not** convert the pass into a claim that gameplay is pleasant,
full-speed, or working on Android. With no minimum FPS requested, speed is
**measured, not evaluated against a release threshold**.

### Profiles

- `boot`: cold boot + real input into a level (`a`, `b`); useful as an early gate
- `gameplay` (default): boot + in-level interactions, full map tour, save/reload,
  long soak and speed measurements (`a`, `b`, `c`, `d`, `e`, `f`, `h`)
- `extended`: gameplay plus save-state and replay checks (`g`, `j`)

The rig's diagnostic assist-path, CPU-interpreter, and emulator-specific flicker
sessions remain useful but are **not** counted as substitute proof for user
input, audio, DuckStation or GPU display safety. Failed diagnostics should
still be investigated, even when not part of the selected profile.

## Reporting defects back to Claude

For each failure, investigate **privately** using the rig's corresponding
`<session>.log`, `script.txt` (frame-indexed input), `result.json`, contact
sheet and core-option settings. The sanitized report supplies failure codes and
the session's total frames, **not the exact moment of the fault**: capture the
exact emulator frame from the private trace before opening a GitHub issue.

The GitHub issue should contain only the problem, repository/source SHA,
selected emulator/core version and options, scene, exact emulated frame,
reproduction steps **in your own words**, and numeric performance data. No
private logs, game dialogue, raw render captures, ROM/audio bytes, BIOS, CD
images, converted world data or save files should be posted to GitHub.

Don't merge emulator-test fixes without the source-only CI, the documented
private PS1 build gates, and a regression run from power-on through gameplay
on SwanStation and Beetle. Release acceptance still requires a separate
**DuckStation for Android** owner run with version, BIOS region, Fast Boot
setting, device performance, input and memory-card tests.