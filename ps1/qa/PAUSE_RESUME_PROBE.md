# PS1 pause/resume latency probe

Independently measure the **visible delay from the resume-button press to the first newly changed city frame**. The guest-clock restart is recorded separately, not used as the main linger or release threshold. This complements the existing `ps1/rig/sessions/in_level.py` checks, which verify that the city and HUD eventually return but do not isolate the visible pause-image linger.

The probe is deliberately a **QA script only**. It changes no PS1 runtime code, no controller mapping, no disc layout, no graphics settings and no performance optimization. All screenshots, emulator logs, guest text, memory cards and saves remain in the caller's **private** `--out` path; none are committed or uploaded to GitHub.

## rc8/rc9: run with a matching private disc and nm symbol listing

```sh
export RIG_CORES=/private/qa-kit/cores
export RIG_SYSTEM=/private/qa-kit/system
python3 ps1/rig/tools/ob_session.py ps1/qa/pause_resume_latency.py \
  --disc /private/rc8/payback_rc8.cue \
  --syms /private/rc8/payback_rc8.nm.txt \
  --core swanstation \
  --out /private/qa/rc8_pause_recommended \
  --opt swanstation_CPU_Overclock=400 \
  --opt swanstation_CDROM_ReadSpeedup=10 \
  --opt swanstation_CDROM_SeekSpeedup=0
```

Repeat on SwanStation with **no** `--opt` flags and on Beetle stock. Optionally add `--from-state /private/level_start.state` when the state belongs to the **same exact disc and core**.

The result's `extra.timing` reports the primary **`visible_linger_after_resume_press_frames`**, equivalent to `first_new_picture_after_press_frames`, as well as clock restart, first any image change, first changed **city** picture, first flip backed by a changed city picture, renderer evidence and eventual clock-confirmed playable frame. A GPU flip or renderer counter increment on the **unchanged pause picture** does not count as a visible new frame. The old `visible_linger_after_clock_restart_frames` remains a *secondary diagnostic* based on the first clock-confirmed playable picture and must not be used as the main delay or hard gate.

By default the observer also runs for **120 additional emulator frames after the first new city image**, recording picture-change counts, the longest static run and up to 25 still-image intervals with press-relative frame IDs. This detects short freezes *after* the picture first returns. Raise `--observe-frames` if the first return occurs too close to that maximum; `--post-new-frame-observe-frames N` sets the follow-up window. Every frame is sampled, including during the resume button hold.

**The default session measures rather than asserts an arbitrary comfort target.** Pass an owner-approved `--max-visible-linger-frames N` to gate **press-to-first-new-city-frame**, never the later guest-clock restart. This is not a DuckStation Android test. For rc8, `g_flips` is required; `g_pres` is only the beginning of `present()`, not a GPU display change.

## rc7 diagnostic baseline (private QA-kit draft)

The attached owner rc7 US draft disc and matching symbols passed a real SwanStation + openboot run with the recommended CPU/CD options. Because rc7 lacks `g_flips`, the command explicitly used `--allow-legacy-present-counter` and thus **cannot certify physical display-flip synchronization**. Outcome: **10 PASS / 0 FAIL** in 934 emulator frames; clock restarted 12 frames after the resume press, first new renderer frame 2 frames earlier, and the first newly rendered playable city picture appeared 15 frames after the clock restarted (27 frames after the press). This is only a diagnostic baseline for the new script and is **not** a measurement of Claude's rc8 pause-picture issue, which remains pending an actual private rc8 disc.

```sh
python3 -m unittest discover -s ps1/qa -p 'test_pause_latency_metrics.py' -v
```

Nine synthetic tests cover early counter increments on unchanged pictures, press-relative timing when the clock restarts later, separate menu changes, and post-return intermittent freezes. They require no ROM, BIOS, emulator core or generated assets.
## Claude's rc8 private review measurements (not a new GPT-6 emulator run)

On the rc8 disc Claude reported **stock: first newly changed picture at +185 emulator frames (approximately 3.1 s), clock restart +142, and early unchanged-picture render/flip counters at +6/+7**. With SwanStation 400% CPU / 10x CD / instant seek, the first changed picture was reported at **+2 frames**, clock +8; short pauses followed around +4 to +11 and +14 to +21. The old probe incorrectly reported the stock linger as only 43 frames by subtracting the clock-restart frame. These numbers are the **previous private rc8 baseline**, not measured on rc9. When rc9 is available, repeat independently at stock and recommended settings with a clean private output for each disc/core/configuration.
