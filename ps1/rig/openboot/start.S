/* start.S: openboot reset vector and the parts that must run from the ROM (KSEG1).
   Own work from the public hardware documentation.  .set noreorder throughout: every delay slot is explicit,
   and no value loaded by lw/mfc0 is used by the next instruction (R3000 load delay). */
#include "ob.h"
        .set noreorder
        .set noat
        .section .rom.reset,"ax",@progbits
        .globl _reset
_reset:                                         /* 0xBFC00000 */
        /* psx-spx memorycontrol: the first writes of a boot ROM: ROM delay/size, then the RAM configuration */
        lui     $8, 0x0013
        ori     $8, $8, 0x243f
        lui     $1, 0x1f80
        sw      $8, 0x1010($1)                  /* DEV2 (BIOS ROM) delay/size */
        nop
        ori     $8, $0, 0x0b88
        lui     $1, 0x1f80
        sw      $8, 0x1060($1)                  /* DRAM_CTRL: the value later consoles write */
        nop
        j       reset2
        nop

        /* documented header position: BCD date, console type, maker/version strings (our own, not Sony's) */
        .org    0x100
        .word   0x20261122                      /* build date, BCD */
        .word   0x00000003                      /* "console type" word: retail-style value */
        .asciz  "openboot 1 (own-work test boot ROM, no Sony code)"
        .org    0x150
        .globl  ob_rom_flags
ob_rom_flags:                                   /* 0xBFC00150: behaviour flags, patched by tools/mkvariant.py */
        .word   0
        .word   OB_MAGIC

        /* general exception vector while SR.BEV=1 (boot time only): record and stop */
        .org    0x180
rom_exc:
        mfc0    $26, $13
        mfc0    $27, $14
        sw      $26, (OB_TRACE+TR_LAST_CAUSE)($0)
        sw      $27, (OB_TRACE+TR_LAST_EPC)($0)
        mfc0    $26, $8
        ori     $27, $0, OBE_EXC_BOOT
        sw      $26, (OB_TRACE+TR_LAST_BADV)($0)
        sw      $27, (OB_TRACE+TR_ERROR)($0)
1:      b       1b
        nop

reset2:
        /* the other memory control registers: the documented usual values */
        lui     $1, 0x1f80
        lui     $8, 0x1f00
        sw      $8, 0x1000($1)                  /* DEV0 base 1F000000h */
        lui     $8, 0x1f80
        ori     $8, $8, 0x2000
        sw      $8, 0x1004($1)                  /* DEV8 base 1F802000h */
        lui     $8, 0x0013
        ori     $8, $8, 0x243f
        sw      $8, 0x1008($1)                  /* DEV0 delay/size */
        ori     $8, $0, 0x3022
        sw      $8, 0x100c($1)                  /* DEV1 delay/size */
        lui     $8, 0x2009
        ori     $8, $8, 0x31e1
        sw      $8, 0x1014($1)                  /* SPU delay/size */
        lui     $8, 0x0002
        ori     $8, $8, 0x0843
        sw      $8, 0x1018($1)                  /* CD-ROM delay/size */
        lui     $8, 0x0007
        ori     $8, $8, 0x0777
        sw      $8, 0x101c($1)                  /* DEV8 delay/size */
        lui     $8, 0x0003
        ori     $8, $8, 0x1125
        sw      $8, 0x1020($1)                  /* COM_DELAY */
        /* interrupts off and acknowledged; exceptions stay on the ROM vector (BEV) until RAM is set up */
        lui     $8, 0x0040                      /* SR: BEV=1, everything else 0 */
        mtc0    $8, $12
        nop
        mtc0    $0, $13                         /* CAUSE: clear the software interrupt bits */
        sw      $0, 0x1074($1)                  /* I_MASK = 0 */
        sw      $0, 0x1070($1)                  /* I_STAT = 0 (acknowledge all) */
        /* instruction cache: tags invalid, then normal operation (same routine as A(44h)) */
        bal     rom_flush_body
        nop
        /* clear the kernel's 64 KiB (through KSEG1: nothing of it is cached yet) */
        lui     $8, 0xa000
        lui     $9, 0xa001
1:      sw      $0, 0($8)
        sw      $0, 4($8)
        sw      $0, 8($8)
        sw      $0, 12($8)
        addiu   $8, $8, 16
        bne     $8, $9, 1b
        nop
        /* copy the resident image (services + loader, linked at OB_RES_ADDR) from the ROM to RAM */
        la      $8, __res_lma
        la      $9, __res_start
        la      $10, __res_end
1:      lw      $11, 0($8)
        addiu   $8, $8, 4
        sw      $11, 0($9)
        addiu   $9, $9, 4
        sltu    $12, $9, $10
        bne     $12, $0, 1b
        nop
        /* flags from the ROM header into the trace table, boot stack, and into the C part */
        la      $8, ob_rom_flags
        lw      $9, 0($8)
        lui     $10, %hi(OB_MAGIC)
        ori     $10, $10, %lo(OB_MAGIC)
        sw      $9, (OB_TRACE+TR_FLAGS)($0)
        sw      $10, (OB_TRACE+TR_MAGIC)($0)
        la      $29, OB_STACK
        move    $30, $29
        la      $8, ob_main
        jr      $8
        nop

/* ---- cache flush: must execute uncached (KSEG1).  The sequence documented for the BIU/cache control register
        (psx-spx memorycontrol, FFFE0130h): tag test mode with the cache isolated, one store per 4-word line; then
        cache-line clear with plain isolation; 8 dummy reads from uncached RAM; normal configuration 0001E988h.
        Uses r8..r13 only; r31 = return address. */
        .globl  rom_flush_body
rom_flush_body:
        mfc0    $13, $12                        /* caller's SR */
        lui     $8, 0xfffe
        ori     $9, $0, 0x0804                  /* TAG | IS1 */
        sw      $9, 0x0130($8)
        lui     $10, 0x0001                     /* SR.IsC */
        mtc0    $10, $12
        nop
        nop
        move    $11, $0
        ori     $12, $0, 0x1000
1:      sw      $0, 0($11)
        addiu   $11, $11, 16
        bne     $11, $12, 1b
        nop
        mtc0    $0, $12
        nop
        nop
        ori     $9, $0, 0x0800                  /* IS1 */
        sw      $9, 0x0130($8)
        mtc0    $10, $12
        nop
        nop
        move    $11, $0
2:      sw      $0, 0($11)
        addiu   $11, $11, 4
        bne     $11, $12, 2b
        nop
        lui     $11, 0xa000
        lw      $9, 0($11)
        lw      $9, 0($11)
        lw      $9, 0($11)
        lw      $9, 0($11)
        lw      $9, 0($11)
        lw      $9, 0($11)
        lw      $9, 0($11)
        lw      $9, 0($11)
        mtc0    $0, $12
        nop
        nop
        lui     $9, 0x0001
        ori     $9, $9, 0xe988                  /* RAM | DS | IBLKSZ_4 | IS1 | RDPRI | NOPAD | BGNT | LDSCH */
        sw      $9, 0x0130($8)
        mtc0    $13, $12                        /* SR back */
        nop
        nop
        jr      $31
        nop
