# PS1 pause/resume latency probe

Independently measure the **visible delay between restarting the guest game clock and seeing a newly rendered, flipped 3D frame**. This complements the existing `ps1/rig/sessions/in_level.py` checks, which verify that the city and HUD eventually return but do not isolate the visible pause-image linger.

The probe is deliberately a **QA script only**. It changes no PS1 runtime code, no controller mapping, no disc layout, no graphics settings and no performance optimization. All screenshots, emulator logs, guest text, memory cards and saves remain in the caller's **private** `--out` path; none are committed or uploaded to GitHub.

## rc8: run with a matching private disc and ELF

```sh
export RIG_CORES=/private/qa-kit/cores
export RIG_SYSTEM=/private/qa-kit/system
python3 ps1/rig/tools/ob_session.py ps1/qa/pause_resume_latency.py \
  --disc /private/rc8/payback_rc8.cue \
  --syms /private/rc8/payback_rc8.elf \
  --core swanstation \
  --out /private/qa/rc8_pause_recommended \
  --opt swanstation_CPU_Overclock=400 \
  --opt swanstation_CDROM_ReadSpeedup=10 \
  --opt swanstation_CDROM_SeekSpeedup=0
```

Repeat on SwanStation with **no** `--opt` flags and on Beetle stock. Optionally add `--from-state /private/level_start.state` when the state belongs to the **same exact disc and core**.

The result's `extra.timing` reports emulator frame numbers for clock restart, first displayed image change, first actual GPU display flip, first renderer frame, and the first 3D view that satisfies **all** of those conditions. It also reports `visible_linger_after_clock_restart_frames` and the time from the resume button press. Image classification is only an additional gate: the 3D renderer, video flip and clock must independently progress. The pause/clock transition is observed **every emulator frame**, including during the button hold.

**The default session measures rather than asserts an arbitrary comfort target.** Pass an owner-approved `--max-visible-linger-frames N` to make a specific threshold a hard gate. This is not a DuckStation Android test. For rc8, `g_flips` is required; `g_pres` is only the beginning of `present()`, not a GPU display change.

## rc7 diagnostic baseline (private QA-kit draft)

The attached owner rc7 US draft disc and matching symbols passed a real SwanStation + openboot run with the recommended CPU/CD options. Because rc7 lacks `g_flips`, the command explicitly used `--allow-legacy-present-counter` and thus **cannot certify physical display-flip synchronization**. Outcome: **10 PASS / 0 FAIL** in 934 emulator frames; clock restarted 12 frames after the resume press, first new renderer frame 2 frames earlier, and the first newly rendered playable city picture appeared 15 frames after the clock restarted (27 frames after the press). This is only a diagnostic baseline for the new script and is **not** a measurement of Claude's rc8 pause-picture issue, which remains pending an actual private rc8 disc.

```sh
python3 -m unittest discover -s ps1/qa -p 'test_pause_latency_metrics.py' -v
```

Six synthetic tests ensure that a menu animation before clock restart, a clock restart without a visual update, or an unchanged 3D renderer cannot falsely qualify as a resumed playable view. They require no ROM, BIOS, emulator core or generated assets.