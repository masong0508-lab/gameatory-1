# PS1 hardware replacements for the GBA ones (stage2/ps1rt)
Files: `hw_pad.h` (SIO0 pad), `hw_card.h` (memory card + EEPROM save layer), `hw_cdda.h` (CD-DA), `hw_radio.h` (pad keys for the radio), `hw_stub.h` (no-op API for the unicorn sim, -DCDSIM),
`hwtest.c` + `build_hwtest.sh` (standalone test program, no Payback data), `mkdisc.py` + `tracklist.txt` (cue/bin builder with CD-DA tracks), `tests/` (pcsxr drivers).
Build rule found here: clang MIPS-I needs `-mllvm -disable-mips-delay-filler` (the branch-delay filler broke load delays: at -O2 the save bitmap was corrupted, 17 instead of 3 frame writes; fixed in build.sh / build_hwtest.sh).
Real pad is the default; `SCRIPT=1 build.sh` (-DSCRIPTPAD) keeps the old scripted keys for unattended discs; -DCDSIM implies it.

## Pad (SIO0, polled once per guest frame from the KEYINPUT read; no IRQ handler)
| PS1 | GBA KEYINPUT bit | note |
| --- | --- | --- |
| Cross | A (bit 0) | |
| Circle, Square | B (bit 1) | either |
| Select | Select (2) | |
| Start | Start (3) | |
| D-pad Right/Left/Up/Down | bits 4/5/6/7 | left stick maps to the D-pad when the pad is analog (threshold 64 around 0x80) |
| R1 / L1 | R (bit 8) / L (bit 9) | |
| Triangle, L2, R2, L3, R3, right stick | none | `pad_extra` bits 0..4 (Tri, L2, R2, L3, R3), `pad_ax[0..1]` right stick, for the engine (camera, bail-out) |
Radio (when the disc has audio tracks): Select+R1 next track, Select+L1 previous, Select+Triangle stop / start.
Digital 0x41 and DualShock 0x73 ids are accepted; the driver sends the config sequence (0x43/0x44/0x43) to lock analog mode on DualShocks.

## Memory card saves
Payback's save is the 8 KiB EEPROM (1024 x 8 bytes) already modelled in rt.c (eeprom_dma): first access loads it from the card (`sv_load`), every EEPROM write marks its 128-byte frame dirty (`sv_dirty`),
`sv_service` writes ONE card frame per present() after 20 quiet presents (so a save never blocks a frame for more than one 138-byte transfer).
File `BESLES-99901SFBACK`, 2 blocks (16 KiB: 8 KiB payload + 512 B header; the 2nd block holds only 4 frames), slot 1 then slot 2.
Layout of the file image: frame 0 title ("STAR FLYBACK SAVE", Shift-JIS full width) + 4-colour CLUT, frame 1 16x16 icon (one static frame, display flag 0x11), frame 3 meta (magic "SFBF", version, sequence, size, CRC32 of the payload), payload at 0x200.
Write order: payload frames, meta, directory entries last (a torn first save leaves no half file). CRC mismatch on load = save ignored and EEPROM stays blank. There is one copy: a power loss between payload frames and meta loses that save.
Checks: both directory frames and the frame-0 / directory XOR checksums verified by an independent parser (tests/chk_mcd.py).

## Audio plan
- Music = CD-DA, tracks 2.. from `tracklist.txt`: the 11 "(PS1 remix final)" renders of the tracker modules (46.7 min, 44.1 kHz 16-bit stereo) leave 27 min of a 74 min disc for the PS1 Star-FlyBack remixes (songs 1, 2, 4, title, credits). Originals (mods/originals, 51 min) are alternates, not on the same disc. Payback song 3 is never listed; mkdisc.py refuses any name containing "song 3".
- mkdisc.py: ISO -> MODE2/2352 Form 1 data track (EDC/ECC computed), audio tracks via ffmpeg, 2 s pregap each, cue sheet. Audio bins are build output on the user's machine, never in the repo. A real disc additionally needs the PS1 licence data in the system area (mkpsxiso or equivalent): not done here.
- Driver: SPU enable + CD input volume, GetTN for the track count, Play(track) in mode CDDA+AutoPause, INT4 (end of track) polled once per vblank -> next track (or repeat with `cdda_loop`), Pause for stop, Stop for motor off.
- Data reads and CD-DA share one laser: every `cd_read` (ROM page miss, overlay load) now calls `cdda_hold` (GetlocP + Pause) and `cdda_release` (Setloc + Play), so music resumes at the saved position; on hardware each miss is an audible gap of the seek time (the emulator models none). Real fix = fewer misses (resident ROM pages) rather than more clever audio.
- XA: not implemented. XA-ADPCM (37.8/18.9 kHz, interleaved on the data track) would let music and data share the drive only for sequential streams; for SFX the plan stays SPU ADPCM voices in SPU RAM (no CD access), music on CD-DA.
