# DuckStation settings for the Payback PS1 port

Measured on 2026-11-22 on the rc6 and rc7 discs in SwanStation (DuckStation's libretro fork) with our own boot ROM
openboot (no Sony BIOS), in emulated time: seconds are core frames / 59.94, gf/s are guest (GBA) frames per emulated
second (the GBA runs 59.73). Not yet measured on a phone. rc7 here is the draft built from c753516.

## Recommended

| DuckStation setting | value | SwanStation core option |
| --- | --- | --- |
| CPU overclocking | 400% | `swanstation_CPU_Overclock=400` |
| CD-ROM read speedup | 10x ("10x (20x Speed)") | `swanstation_CDROM_ReadSpeedup=10` |
| CD-ROM seek speedup | Infinite/Instantaneous | `swanstation_CDROM_SeekSpeedup=0` |

DuckStation's speed display must stay at 100%. If the phone cannot hold it, lower the overclock to 300%, 200%, then
150% (read speedup 10x stays clean from 150%). At 100% CPU use read speedup 7x: from 8x up, at 100% CPU, the disc loader
and the game's CD driver retry and loading gets slower (read 10x at 100%: the level at 77.6 s with 164 + 53 retries).
Seek speedup 10x is within a few per cent of instant. Above about 600% places run faster than the GBA, and save states
made at 600% or more do not load at 100%.

## What it changes

| disc, setting | power-on to language / title / level, s | street gf/s stand / walk | park gf/s stand / walk | title menu gf/s | game menu gf/s |
| --- | --- | --- | --- | --- | --- |
| rc7 stock | 12.78 / 26.03 / 42.88 | 7.63 / 7.60 | 9.07 / 8.93 | 4.97 | 19.54 |
| rc7 seek instant | 9.68 / 20.47 / 33.48 | 7.70 / 7.93 | 9.13 / 9.13 | 4.97 | 19.54 |
| rc7 + read 10x, CPU 200% | 2.54 / 8.31 / 14.81 | 15.54 / 15.97 | 18.37 / 18.34 | 9.97 | 29.94 |
| rc7 + read 10x, CPU 400% (recommended) | 2.00 / 6.39 / 10.06 | 30.64 / 32.74 | 36.70 / 35.44 | 19.97 | 59.91 |
| rc7 read 7x, CPU 100% | 4.64 / 14.53 / 26.54 | 7.70 / 7.97 | 9.13 / 9.17 | 4.97 | 19.54 |
| rc6 stock | 12.78 / 26.01 / 43.16 | 1.57 / 1.60 | 8.90 / 8.93 | 4.60 | 14.97 |
| rc6 recommended | 2.00 / 6.42 / 10.46 | 22.60 / 25.87 | 36.77 / 35.50 | 14.97 | 59.91 |

Street and park are 30 s standing and 30 s walking from the same saved state for every setting. Menus are locked to the
video frame. In levels the game shows a new picture only about every 16 guest frames (about 2 pictures a second at the
recommended setting), because its frame limiter spins on the port's virtual clock; the speed work replaces that clock.
rc7's ROM page pool removed most CD waits: 2 page fetches in 30 s standing in the street, against 278 on rc6. So on rc7
the CD settings shorten booting and loading, and play speed comes from the overclock.

## Checks at the recommended setting (rc6 and rc7)

- Pictures: the first 8 new pictures after the state load are byte-identical to stock, except ground-texture pixels in
  the rc6 park that change with CPU speed alone (the renderer's time-budgeted detail, likely).
- Flicker (`ps1/rig/sessions_ob/flicker.py`): no picture change without a present, no black pictures.
- Radio: 7 checks pass; the music pauses while the disc reads and plays when the disc is quiet.
- In-level session (idle, walk, turn, weapons, fire, pause): 20 PASS, 0 FAIL on both discs.
- Strict openboot: boot 13 PASS, 0 exceptions, 830 sectors read without a retry.

## 8 MB RAM

`swanstation_Console_Enable8MBRAM=true` boots and plays unchanged (no speed gain; the port does not use it yet). The PS1
sees separate RAM at 0x80200000-0x807FFFFF, not mirrors of the first 2 MiB. A save state made without the option brings
2 MiB back even with the option on.

## Option keys

- SwanStation: `swanstation_CPU_Overclock` 50-1000 (per cent); `swanstation_CDROM_ReadSpeedup` 1-10 (1 is none, double
  speed); `swanstation_CDROM_SeekSpeedup` 1 (none), 0 (instant), 2-10; `swanstation_Console_Enable8MBRAM` false/true.
- Beetle PSX: `beetle_psx_cpu_freq_scale` 50%-750%; `beetle_psx_cd_fastload` 2x-14x in steps of 2x;
  `beetle_psx_cd_access_method` sync/async/precache; no seek or 8 MB option. Not measured with these discs.
- Rig sessions take them as `--opt KEY=VALUE` (repeatable).

Caveat: a phone boots through a real BIOS or DuckStation's fast boot, not openboot, so openboot's loader retries do not
predict the phone; retries in the game's own CD driver do.
