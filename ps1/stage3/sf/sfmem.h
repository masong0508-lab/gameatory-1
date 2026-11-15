/* Stage 3 memory map of the renderer's big buffers.  All of it lives in the span the boot image occupied (0x800438d0..0x800a4570, dead once rt.c has copied
   the image into the guest windows), written after boot.  An overlay group of Payback's cold code that is loaded into this span would overwrite it:
   rt.c's h_miss refuses such a load and logs it (SF3_GUARD). */
#ifndef SFMEM_H
#define SFMEM_H
#define SF_PBUF   0x800A8000u      /* primitive buffer, SF_PBW words (40 KB), cold groups 25-27 (never loaded in gameplay coverage) */
#define SF_PBW    10000
#define SF_OT     0x800B2000u      /* 1024-entry ordering table (4 KB) */
#define SF_ST     0x800C0000u      /* visit stamps (12.5 KB), cold groups 31-32 */
#define SF_WORLD  0x800D4000u      /* SF3W.BIN, 208 KB, cold groups 36-50 */
#define SF_TMP    0x80138000u      /* init-time upload buffer: the ROM page cache, still empty at that point */
#endif
