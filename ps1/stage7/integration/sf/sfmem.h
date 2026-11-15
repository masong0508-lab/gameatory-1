/* Stage 3 memory map of the renderer's big buffers.  All of it lives in the span the boot image occupied (0x800438d0..0x800a4570, dead once rt.c has copied
   the image into the guest windows), written after boot.  An overlay group of Payback's cold code that is loaded into this span would overwrite it:
   rt.c's h_miss refuses such a load and logs it (SF3_GUARD). */
#ifndef SFMEM_H
#define SFMEM_H
#define SF_PBUF   0x80108000u      /* primitive buffer, SF_PBW words (40 KB); stage 4: moved above SF_WORLD, the scenario's cold prefix (0x800438b8..0x800c8b3c) now covers the old spot */
#define SF_PBW    8192          /* stage 7: 32 KB (peak seen on all maps: 594 primitives, about 6000 words) */
#define SF_OT     0x80110000u      /* 1024-entry ordering table (4 KB) */
#define SF_ST     0x80111000u      /* visit stamps (12.5 KB) */
#ifndef SF_WORLD_ADDR
#define SF_WORLD_ADDR 0x800C9000u
#endif
#define SF_WORLD  SF_WORLD_ADDR    /* SF3W.BIN of the current map, up to 238 KB (stage 7: all 11 maps; the biggest is 234 KB), ends before SF_SIDE */
#define SF_SIDE   0x80118000u      /* the per-map fields of SIDE.BIN (7144 bytes, 448 tile slots; the sin table is static), after the TMP span (SF_TMP..+64 KB ends at 0x80118000); the world window ends at SF_PBUF: 0x80108000 - SF_WORLD >= 239616 (map 1) is asserted by the build */
#define SF_TMP    0x80108000u      /* init-time upload buffer (64 KB atlas page): the primitive buffer + ordering table span, unused until the first frame */
#endif
