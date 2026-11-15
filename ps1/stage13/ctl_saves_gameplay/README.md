# Stage 13: controls, saves and gameplay (Payback PS1, original game) - code only

No Payback code, assets, ROM or audio here. Results are EMULATOR-ONLY (PCSXR + HLE BIOS) or SIM-ONLY (unicorn-MIPS with a modelled SIO0). Disc: `builds/ps1/Payback PS1 (original game, release candidate 2 - controls and saves)`; evidence next to it.

Apply on top of the stage 10 tree (stage10/README.md + patches): `patches/*.patch` are `diff -u` against that tree (`ps1rt/rt.c`, `ps1rt/hw_pad.h`, `ps1rt/hw_radio.h`, `ps1rt/hw_stub.h`, `sf/sf3.c`, `tools7/mkkplan.py`). Build the disc as in stage 10 (`t/disc7.sh`, flags `-DSF3_DEFER`; test discs add `-DPADDBG -DTESTPOKE`).

## Changes
- hw_pad.h: `sio_pad_xfer()` one transfer sized by the id byte (digital 5 bytes, analog 9); `pad_poll()` uses it.
- rt.c pad path: poll once per guest frame (`pad_frame_poll`, `io_read` 0x130), `pad_latch` ORs every raw word since the last present, edge words `pad_new_extra` (Triangle, L2, R2, L3, R3) and `radio_poll(lat,np)` use the latch, so taps shorter than a present (16 guest frames) are kept.
- Menu assist (KPLAN): `plan_classify()` checks the loaded EEPROM image (header "Payback." and the unused-profile pattern) -> plan 0 blank card (absolute frames, mGBA recording), plan 1 profile in slot 1, plan 2 initialised without a profile. Plans 1/2 pulse A from frame 240 until the first big image blit (`img_f0`) and then replay times relative to it (`KPLB`, `KPLC`, `tools7/mkkplan.py`, recordings by `w13/padlogB.py`, `w13/padlogC.py`, data/). Triangle held in the first 300 frames turns the assist off; in the level it returns no key.
- Renderer recovery (SF3_DEFER builds): group(s) of cold overlay code that overlap the renderer's data window (`SF_WORLD_LO`..0x8011b200) are loaded by weapon switch and Pause. `cold_find` now records `sf3_cfl`; `present()` waits for the level clock to advance 8 ticks, then re-reads the overwritten world-file sectors (`sf3_w_lba/sf3_w_len`, set in `sf3_map_load`) and invalidates the groups; if a group reaches 0x80111000.. (stamps, side tables) the whole map is re-read (`sf3_init`). While recovering the last 3D frame is held (no debug page).
- TEST-ONLY (`-DTESTPOKE`): a fresh Select press sets the controlled entity index to the nearest traffic car so the renderer's car view, bail-out (Triangle) and hit paths can be exercised through real keys. Not in the release disc.

## Tools (tools13/, t/)
- `t/sim13.py`, `t/mksim13.sh`: unicorn sim with DualShock (digital/config/analog) and memory card in slot 1 on SIO0; the runtime's real pad and card drivers run unchanged (`-DSIMSIO`). `mksim13.sh NAME "extra cflags"` builds `out/NAME.exe/.iso` (`-DCDSIM -DNOSF3 -DTESTFAST`).
- `tools13/simsession.py EXE CARD OUT LEVEL_FRAMES [--poke-car]`: scripted real-pad session (menu through the pad function, no assist), state checks, key-echo, Pause, free roaming, Quit to title (Start, Down, Cross, Left, Cross), EEPROM-write and card-write counters, JSON out.
- `tools13/rtrip.py EXE CARD PREV_EE`: boots with a card written by an earlier session, compares the guest EEPROM image (8192 bytes) at frame 120 with the earlier end state.
- `tools13/pcx.py` (PCSXR driver: own Xvfb, xdotool keys through DFInput defaults), `padmap.py` (15-button PADRAW check), `pcxboot.py` (boot with a given card, report plan and level time), `pcxsession.py` (real-key session with log-line state: walk, turns, weapons, shoot, L1, pause/resume, renderer recovery, walk to nearest car, TEST-ONLY car, bail-out; `--short` skips the walk and car).
- `w13/`: mGBA reference scripts (need the stage 9/10 mGBA shim `mgba/emu.py`, `scenes.py` and the ROM): `padlogB/C.py` (menu recordings), `ctl17/19/20/21.py` (car entry attempts), `ctl23.py` (Pause > Quit path), `bot.py`/`common.py` helpers.

## Findings worth knowing
- Up/Down are weapon keys in Payback (not movement); L = enter/exit vehicle; Pause menu = Return to game / Quit to title screen (then an "Are you sure?" prompt with No preselected: Left selects Yes).
- With a valid save the game waits for a key before its first screen and its KEYINPUT polling windows differ from a blank card, which is why absolute-frame plans never reached the level.
- Pause > Quit to title writes 14 EEPROM blocks (3 card frames). The profile is written at the name screen (117 EEPROM writes, 77 card frame writes through the real card driver).
- Cold group overlap: weapon switch (08072eb0, 08072e50) and Pause (08077ed4) hit groups 34, 35, 44 (weapon switch) and 34, 36, 37, 38, 41, 43, 44 (Pause) of the cold overlay, all inside the renderer's world window. A real fix is moving those functions out of the window in the translator's cold layout (not done).
