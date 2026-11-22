/* ob.h: openboot, a minimal PlayStation boot ROM + call tracer.  Own work, written from the public hardware
   documentation (psx-spx: memorycontrol, cdromdrive, kernelbios, interrupts, iomap).  No Sony code or data.
   Shared between the assembly and C parts and mirrored by tools/obrig.py (decode_trace). */
#ifndef OB_H
#define OB_H

/* ---- fixed RAM layout (physical = KUSEG addresses; all below 0x8000 so the resident code can reach them
        with a 16 bit offset from $zero and needs no base register) */
#define OB_TRACE        0x1000      /* trace table, 0x1000 bytes */
#define OB_SAVE         0x1e00      /* register save slots of the exception handler (inside the trace page) */
#define OB_RES_ADDR     0x80002000  /* resident services + boot loader code/data (copied from the ROM), at most 12 KiB */
#define OB_TTY          0x5000      /* u32 write counter, u32 reserved, then the ring */
#define OB_TTY_BUF      0x5008
#define OB_TTY_MASK     0x3fff      /* ring of 16 KiB */
#define OB_SCRATCH      0x8000a000  /* boot-time buffers (sector, directory) */
#define OB_STACK        0x8000fff0  /* boot stack (not used after the game has been started) */

/* ---- trace table word offsets (from OB_TRACE) */
#define TR_MAGIC        0x000       /* 'OBT1' */
#define TR_STAGE        0x004       /* boot progress, see BOOTROM.md */
#define TR_ERROR        0x008       /* 0 = none */
#define TR_FLAGS        0x00c       /* behaviour flags (copied from the ROM word at 0xBFC00150) */
#define TR_PC0          0x010
#define TR_TADDR        0x014
#define TR_TSIZE        0x018
#define TR_EXELBA       0x01c
#define TR_SP           0x020
#define TR_GP           0x024
#define TR_RETURNED     0x028       /* the game returned to its caller (count) */
#define TR_TTYCHARS     0x02c
#define TR_LAST_CAUSE   0x030
#define TR_LAST_EPC     0x034
#define TR_LAST_BADV    0x038
#define TR_EXC_TOTAL    0x03c
#define TR_IRQ_TOTAL    0x040
#define TR_UNK_CALL     0x044       /* last call with no implementation: table letter << 8 | function */
#define TR_LAST_RA      0x048       /* return address of the last A/B/C call */
#define TR_IMASK_FIRST  0x04c       /* I_MASK when the first interrupt was taken */
#define TR_SR_ENTRY     0x050       /* COP0 SR given to the game */
#define TR_BOOT_SECTORS 0x054
#define TR_BOOT_RETRIES 0x058
#define TR_KCD_ACKS     0x05c       /* CD-ROM interrupts acknowledged by the kernel-style handler */
#define TR_EXC          0x060       /* 16 words: exceptions by cause code */
#define TR_IRQ          0x0a0       /* 16 words: interrupts by I_STAT bit; [11] = none pending (spurious) */
#define TR_SYS          0x0e0       /* 8 words: syscall by r4 (0..6), [7] = any other */
#define TR_BRK          0x100       /* 4 words: total, last code, division by zero (1C00h), overflow (1800h) */
#define TR_BD           0x110       /* exceptions raised in a branch delay slot that had to be skipped */
#define TR_ISTAT_BOOT   0x114       /* I_STAT just before the game is started */
#define TR_CNF_TCB      0x118
#define TR_CNF_EVENT    0x11c
#define TR_CNF_STACK    0x120
#define TR_CD_STAT      0x124       /* last CD-ROM status byte seen by the boot loader */
#define TR_FLUSHES      0x128       /* cache flushes really executed */
#define TR_SITES_OVF    0x12c       /* unresolved exceptions that found the site table full */
#define TR_CDI_STEP     0x130       /* boot loader, CD init: last step << 8 | INT received (1,2 Nop  3 Init  4 Init complete  5 Demute  6 Setmode) */
#define TR_CDI_FAIL     0x134       /* the same word at the first failed CD init attempt (0 = never failed) */
#define TR_EXTRA_INT3   0x138       /* INT3 received where the second response of Init/Pause was due (tolerated) */
#define TR_SITES        0x140       /* 12 x { EPC, count }: where unresolved exceptions (not interrupt, not syscall) were raised */
#define TR_A            0x200       /* 256 words: A(nn) calls */
#define TR_B            0x600       /* 256 words: B(nn) calls */
#define TR_C            0xa00       /* 128 words: C(nn) calls */
#define TR_CDLOG        0xc00       /* boot loader: count, then up to 63 CD-ROM events: command << 16 | first result byte << 8 | INT */

#define OB_MAGIC        0x3154424f

/* ---- behaviour flags (ROM word at 0xBFC00150, followed by the magic word; mkvariant.py patches it) */
#define OBF_REGS        0x01    /* A/B/C calls return with r1,r3..r15,r24,r25,hi,lo destroyed (the documented right of a kernel function) */
#define OBF_SMASH1      0x02    /* putchar overwrites the caller's [sp+0..3] (documented: a function with N parameters may use N words there) */
#define OBF_SMASH4      0x04    /* putchar overwrites the caller's [sp+0..15] (the whole o32 argument area; beyond the documented N words) */
#define OBF_DIRTY       0x08    /* RAM 0x80010000..0x801fffff is filled with a non-zero pattern before the EXE is loaded */
#define OBF_KIRQ        0x10    /* start the game like LoadExec does: IEc=1, IM2=1, I_MASK=CDROM|DMA, and a handler that acknowledges CD-ROM interrupts as a kernel driver would */
#define OBF_KVBL        0x20    /* with OBF_KIRQ: VBLANK enabled in I_MASK too and acknowledged by the handler (hypothetical: see BOOTROM.md) */
#define OBF_NOFLUSH     0x40    /* A(44h) FlushCache returns without flushing (dependency test) */
#define OBF_GARBREGS    0x80    /* registers not defined by Exec hold a pattern, not zero, at the entry point */
#define OBF_STRICT      0x100   /* an unresolved exception stops the machine (what the documentation says a standard kernel does) instead of being skipped */

/* ---- error codes (TR_ERROR) */
#define OBE_CD_INIT     1
#define OBE_CD_READ     2
#define OBE_NO_PVD      3
#define OBE_NO_CNF      4       /* informational: PSX.EXE fallback used */
#define OBE_NO_EXE      5
#define OBE_BAD_EXE     6
#define OBE_EXC_BOOT    7       /* exception while the ROM vectors were still active */
#define OBE_UNRESOLVED  8       /* OBF_STRICT: stopped at an unresolved exception (TR_LAST_CAUSE/EPC) */

#endif
