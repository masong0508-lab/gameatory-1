# Stage 6 CD-DA radio on the live level disc (code only; emulator-only, PCSXR HLE BIOS)
Files replace stage4/ps1rt/hw_cdda.h and hw_radio.h (rt.c already calls cdda_init, cdda_service, cdda_hold/release, radio_poll). Changes: cdda_play logs `CDDA play cmd 0x03 track N int R`; cdda_service end-of-track uses cdda_nextfn (mode range).
Tracks (mkdisc2.py --default-tracks): 2..12 eleven "PS1 remix final" tracker renders, 13..15 Star-FlyBack PS1 remix songs 1,2,4. Payback song 3 never.
Modes: REMIXES 2..12, ALL SONGS 2..15, ORIGINALS 13..15 (assumption: tracker originals do not fit the disc). Keys: SELECT+R1 next, SELECT+L1 prev, SELECT+Square next mode, SELECT+Triangle stop/start.
Test build: EXTRA="-DRADIO_TEST" t/mk_disc.sh scripts the keys; -DRADIO_AUTOPLAY starts track 2 at frame 10. Disc: mkdisc2.py --iso X.iso --out DIR/NAME --default-tracks.
CD audio output cannot be heard here; verified only by the logged play commands (INT3 ok) and PCSXR's TOC listing tracks 02-15.
