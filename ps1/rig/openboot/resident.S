/* resident.S: the part of openboot that stays in RAM while the game runs (linked at OB_RES_ADDR, KSEG0):
   the A0h/B0h/C0h call vectors with per-function counters, putchar into a RAM ring, FlushCache, and the
   exception handler (counts by cause / interrupt source / syscall / break, then returns harmlessly).
   Own work from the public documentation (psx-spx kernelbios: "Parameters, Registers, Stack", "BIOS Interrupt/
   Exception Handling", SYS(01h)/SYS(02h); interrupts; cdromdrive HCLRCTL).
   Register discipline: the call path uses only registers a kernel function may destroy (r1..r15, r24, r25);
   the exception handler restores everything except k0 (r26), which the documentation reserves for it.
   All counters live below 0x8000 and are addressed from $zero.  noreorder: delay slots are explicit, and a
   register loaded by lw/lbu/mfc0 is never used by the following instruction. */
#include "ob.h"
        .set noreorder
        .set noat
        .section .res.vec,"ax",@progbits

/* ---- 4-instruction templates, copied to 80000080h / A0h / B0h / C0h by ob_main */
        .globl  ob_vec_exc, ob_vec_a, ob_vec_b, ob_vec_c
ob_vec_exc:
        lui     $26, %hi(ob_exc)
        addiu   $26, $26, %lo(ob_exc)
        jr      $26
        nop
ob_vec_a:
        lui     $8, %hi(ob_a0)
        addiu   $8, $8, %lo(ob_a0)
        jr      $8
        nop
ob_vec_b:
        lui     $8, %hi(ob_b0)
        addiu   $8, $8, %lo(ob_b0)
        jr      $8
        nop
ob_vec_c:
        lui     $8, %hi(ob_c0)
        addiu   $8, $8, %lo(ob_c0)
        jr      $8
        nop

        .section .res.text,"ax",@progbits
/* ------------------------------------------------------------------ A(nn): r9 = function number */
ob_a0:
        andi    $10, $9, 0xff
        sll     $10, $10, 2
        lw      $11, (OB_TRACE+TR_A)($10)
        sw      $31, (OB_TRACE+TR_LAST_RA)($0)
        addiu   $11, $11, 1
        sw      $11, (OB_TRACE+TR_A)($10)
        andi    $10, $9, 0xff
        addiu   $11, $0, 0x3c
        beq     $10, $11, ob_putchar            /* A(3Ch) putchar */
        addiu   $11, $0, 0x44
        beq     $10, $11, ob_flush              /* A(44h) FlushCache */
        ori     $11, $10, 0x4100                /* 'A' << 8 | function */
        b       ob_ret0
        sw      $11, (OB_TRACE+TR_UNK_CALL)($0)
/* ------------------------------------------------------------------ B(nn) */
ob_b0:
        andi    $10, $9, 0xff
        sll     $10, $10, 2
        lw      $11, (OB_TRACE+TR_B)($10)
        sw      $31, (OB_TRACE+TR_LAST_RA)($0)
        addiu   $11, $11, 1
        sw      $11, (OB_TRACE+TR_B)($10)
        andi    $10, $9, 0xff
        addiu   $11, $0, 0x3d
        beq     $10, $11, ob_putchar            /* B(3Dh) putchar */
        ori     $11, $10, 0x4200
        b       ob_ret0
        sw      $11, (OB_TRACE+TR_UNK_CALL)($0)
/* ------------------------------------------------------------------ C(nn) */
ob_c0:
        andi    $10, $9, 0x7f
        sll     $10, $10, 2
        lw      $11, (OB_TRACE+TR_C)($10)
        sw      $31, (OB_TRACE+TR_LAST_RA)($0)
        addiu   $11, $11, 1
        sw      $11, (OB_TRACE+TR_C)($10)
        andi    $10, $9, 0x7f
        ori     $11, $10, 0x4300
        b       ob_ret0
        sw      $11, (OB_TRACE+TR_UNK_CALL)($0)

/* ---- putchar(r4): the byte goes into the RAM ring the test frontend drains (no TAB/LF expansion) */
ob_putchar:
        lw      $10, OB_TTY($0)
        lw      $12, (OB_TRACE+TR_TTYCHARS)($0)
        andi    $11, $10, OB_TTY_MASK
        sb      $4, OB_TTY_BUF($11)
        addiu   $10, $10, 1
        sw      $10, OB_TTY($0)
        addiu   $12, $12, 1
        sw      $12, (OB_TRACE+TR_TTYCHARS)($0)
        lw      $8, (OB_TRACE+TR_FLAGS)($0)
        lui     $9, 0x5ac5
        andi    $10, $8, (OBF_SMASH1|OBF_SMASH4)
        beq     $10, $0, 1f
        ori     $9, $9, 0xbad1
        sw      $9, 0($29)                      /* the one argument word a 1-parameter function may use */
        andi    $10, $8, OBF_SMASH4
        beq     $10, $0, 1f
        nop
        sw      $9, 4($29)
        sw      $9, 8($29)
        sw      $9, 12($29)
1:      b       ob_ret
        move    $2, $4

/* ---- FlushCache(): the real sequence, executed in the ROM (uncached) */
ob_flush:
        lw      $8, (OB_TRACE+TR_FLAGS)($0)
        lw      $9, (OB_TRACE+TR_FLUSHES)($0)
        andi    $8, $8, OBF_NOFLUSH
        bne     $8, $0, ob_ret0
        addiu   $9, $9, 1
        sw      $9, (OB_TRACE+TR_FLUSHES)($0)
        move    $24, $31
        lui     $8, %hi(rom_flush_body)
        addiu   $8, $8, %lo(rom_flush_body)
        jalr    $8
        nop
        move    $31, $24
        /* fall through */
ob_ret0:
        move    $2, $0
ob_ret:
        lw      $8, (OB_TRACE+TR_FLAGS)($0)
        nop
        andi    $8, $8, OBF_REGS
        beq     $8, $0, 1f
        nop
        lui     $1, 0xdead                      /* a kernel function may destroy r1..r15, r24, r25, hi, lo (r2 = result) */
        ori     $3, $1, 3
        ori     $4, $1, 4
        ori     $5, $1, 5
        ori     $6, $1, 6
        ori     $7, $1, 7
        ori     $8, $1, 8
        ori     $9, $1, 9
        ori     $10, $1, 10
        ori     $11, $1, 11
        ori     $12, $1, 12
        ori     $13, $1, 13
        ori     $14, $1, 14
        ori     $15, $1, 15
        ori     $24, $1, 24
        ori     $25, $1, 25
        mthi    $1
        mtlo    $1
        ori     $1, $1, 1
1:      jr      $31
        nop

/* ---- C entry for the boot loader: void ob_flush_now(void) */
        .globl  ob_flush_now
ob_flush_now:
        move    $24, $31
        lui     $8, %hi(rom_flush_body)
        addiu   $8, $8, %lo(rom_flush_body)
        jalr    $8
        nop
        jr      $24
        nop

/* ------------------------------------------------------------------ exception handler */
        .globl  ob_exc
ob_exc:
        sw      $1, (OB_SAVE+0)($0)
        sw      $8, (OB_SAVE+4)($0)
        sw      $9, (OB_SAVE+8)($0)
        sw      $10, (OB_SAVE+12)($0)
        sw      $11, (OB_SAVE+16)($0)
        mfc0    $8, $13                         /* CAUSE */
        mfc0    $9, $14                         /* EPC */
        mfc0    $10, $8                         /* BadVaddr */
        sw      $8, (OB_TRACE+TR_LAST_CAUSE)($0)
        sw      $9, (OB_TRACE+TR_LAST_EPC)($0)
        sw      $10, (OB_TRACE+TR_LAST_BADV)($0)
        lw      $10, (OB_TRACE+TR_EXC_TOTAL)($0)
        srl     $11, $8, 2
        addiu   $10, $10, 1
        sw      $10, (OB_TRACE+TR_EXC_TOTAL)($0)
        andi    $11, $11, 0x0f                  /* cause code (0..12 exist on this CPU) */
        sll     $10, $11, 2
        lw      $26, (OB_TRACE+TR_EXC)($10)
        nop
        addiu   $26, $26, 1
        sw      $26, (OB_TRACE+TR_EXC)($10)
        beq     $11, $0, exc_irq
        addiu   $10, $0, 8
        beq     $11, $10, exc_sys
        addiu   $10, $0, 9
        beq     $11, $10, exc_brk
        nop
/* ---- anything else is what the documentation calls an unresolved exception (a standard kernel locks up in
        SystemErrorUnresolvedException): the address is entered in the site table (12 x {EPC, count}) */
exc_unres:
        ori     $10, $0, (OB_TRACE+TR_SITES)
        ori     $1, $0, (OB_TRACE+TR_SITES+12*8)
1:      lw      $11, 0($10)
        nop
        beq     $11, $9, 2f                     /* this EPC has an entry */
        nop
        beq     $11, $0, 2f                     /* free entry */
        nop
        addiu   $10, $10, 8
        bne     $10, $1, 1b
        nop
        lw      $11, (OB_TRACE+TR_SITES_OVF)($0)
        nop
        addiu   $11, $11, 1
        b       3f
        sw      $11, (OB_TRACE+TR_SITES_OVF)($0)
2:      sw      $9, 0($10)
        lw      $11, 4($10)
        nop
        addiu   $11, $11, 1
        sw      $11, 4($10)
3:      lw      $10, (OB_TRACE+TR_FLAGS)($0)
        nop
        andi    $10, $10, OBF_STRICT
        beq     $10, $0, exc_skip
        nop
        ori     $10, $0, OBE_UNRESOLVED         /* OBF_STRICT: stop here, as the documented kernel would */
        sw      $10, (OB_TRACE+TR_ERROR)($0)
4:      b       4b
        nop
exc_skip:                                       /* resume behind the instruction that raised the exception */
        bltz    $8, exc_bd                      /* CAUSE.BD: it sat in a branch delay slot */
        nop
        addiu   $26, $9, 4
exc_ret:
        lw      $1, (OB_SAVE+0)($0)
        lw      $8, (OB_SAVE+4)($0)
        lw      $9, (OB_SAVE+8)($0)
        lw      $10, (OB_SAVE+12)($0)
        lw      $11, (OB_SAVE+16)($0)
        jr      $26
        .word   0x42000010                      /* rfe */
exc_bd:                                         /* the branch is not emulated: counted, execution resumes after the slot */
        lw      $10, (OB_TRACE+TR_BD)($0)
        addiu   $26, $9, 8
        addiu   $10, $10, 1
        b       exc_ret
        sw      $10, (OB_TRACE+TR_BD)($0)

/* ---- interrupt: count every pending+enabled source, acknowledge in I_STAT, return to the interrupted code */
exc_irq:
        lui     $1, 0x1f80
        lw      $8, 0x1070($1)                  /* I_STAT */
        lw      $10, 0x1074($1)                 /* I_MASK */
        lw      $11, (OB_TRACE+TR_IRQ_TOTAL)($0)
        and     $8, $8, $10
        bne     $11, $0, 1f
        addiu   $11, $11, 1
        sw      $10, (OB_TRACE+TR_IMASK_FIRST)($0)
1:      sw      $11, (OB_TRACE+TR_IRQ_TOTAL)($0)
        bne     $8, $0, 2f
        nop
        lw      $10, (OB_TRACE+TR_IRQ+44)($0)   /* nothing pending: counted as spurious */
        nop
        addiu   $10, $10, 1
        b       exc_irq_done
        sw      $10, (OB_TRACE+TR_IRQ+44)($0)
2:      move    $10, $0
        move    $11, $8
3:      andi    $26, $11, 1
        beq     $26, $0, 4f
        srl     $11, $11, 1
        lw      $26, (OB_TRACE+TR_IRQ)($10)
        nop
        addiu   $26, $26, 1
        sw      $26, (OB_TRACE+TR_IRQ)($10)
4:      bne     $11, $0, 3b
        addiu   $10, $10, 4
        /* OBF_KIRQ: a CD-ROM interrupt is handled the way a kernel CD driver would: its flags are acknowledged
           at the controller (which also drains the result FIFO), so a program that polls them never sees them */
        lw      $10, (OB_TRACE+TR_FLAGS)($0)
        andi    $11, $8, 0x0004
        andi    $10, $10, OBF_KIRQ
        beq     $10, $0, 5f
        nop
        beq     $11, $0, 5f
        nop
        lbu     $10, 0x1800($1)                 /* keep the register bank the program selected */
        ori     $11, $0, 1
        sb      $11, 0x1800($1)
        ori     $11, $0, 0x1f
        sb      $11, 0x1803($1)                 /* HCLRCTL: acknowledge */
        andi    $10, $10, 3
        sb      $10, 0x1800($1)
        lw      $10, (OB_TRACE+TR_KCD_ACKS)($0)
        nop
        addiu   $10, $10, 1
        sw      $10, (OB_TRACE+TR_KCD_ACKS)($0)
5:      nor     $8, $8, $0                      /* I_STAT: write 0 = acknowledge, 1 = keep */
        sw      $8, 0x1070($1)
exc_irq_done:
        b       exc_ret
        move    $26, $9                         /* EPC: the interrupted instruction (or its branch) runs again */

/* ---- syscall: r4 = function.  SYS(01h)/SYS(02h) are the two the documentation defines for programs. */
exc_sys:
        sltiu   $10, $4, 7
        bne     $10, $0, 1f
        sll     $10, $4, 2
        ori     $10, $0, 28
1:      lw      $11, (OB_TRACE+TR_SYS)($10)
        nop
        addiu   $11, $11, 1
        sw      $11, (OB_TRACE+TR_SYS)($10)
        addiu   $10, $0, 1
        beq     $4, $10, sys_enter
        addiu   $10, $0, 2
        beq     $4, $10, sys_exit
        nop
        b       exc_skip
        nop
sys_enter:                                      /* EnterCriticalSection: SR bits 2 and 10 off, r2 = 1 if both were on */
        mfc0    $10, $12
        nop
        andi    $11, $10, 0x0404
        xori    $11, $11, 0x0404
        sltiu   $2, $11, 1
        addiu   $11, $0, -0x0405
        and     $10, $10, $11
        mtc0    $10, $12
        b       exc_skip
        nop
sys_exit:                                       /* ExitCriticalSection: SR bits 2 and 10 on */
        mfc0    $10, $12
        nop
        ori     $10, $10, 0x0404
        mtc0    $10, $12
        b       exc_skip
        nop

/* ---- break: counted with its 20 bit code (1C00h = division by zero, 1800h = overflow), then skipped */
exc_brk:
        bltz    $8, 1f
        move    $10, $9
        b       2f
        nop
1:      addiu   $10, $9, 4
2:      lw      $10, 0($10)
        lw      $11, (OB_TRACE+TR_BRK)($0)
        srl     $10, $10, 6
        addiu   $11, $11, 1
        sw      $11, (OB_TRACE+TR_BRK)($0)
        lui     $11, 0x000f
        ori     $11, $11, 0xffff
        and     $10, $10, $11
        sw      $10, (OB_TRACE+TR_BRK+4)($0)
        addiu   $11, $0, 0x1c00
        bne     $10, $11, 3f
        addiu   $11, $0, 0x1800
        lw      $26, (OB_TRACE+TR_BRK+8)($0)
        nop
        addiu   $26, $26, 1
        sw      $26, (OB_TRACE+TR_BRK+8)($0)
3:      bne     $10, $11, exc_unres
        nop
        lw      $26, (OB_TRACE+TR_BRK+12)($0)
        nop
        addiu   $26, $26, 1
        b       exc_unres
        sw      $26, (OB_TRACE+TR_BRK+12)($0)

/* ------------------------------------------------------------------ start of the game
   void ob_launch(u32 pc0 (r4), u32 sp (r5), u32 gp (r6), u32 flags (r7))
   What Exec(headerbuf, 1, 0) defines: r4 = 1, r5 = 0, SP = FP = stack, GP = header value, RA = the caller.
   Everything else is undefined: zero, or a pattern with OBF_GARBREGS.  With OBF_KIRQ the game starts with
   IEc = 1 and IM2 = 1 (set through the KU/IE stack by rfe in the jump's delay slot). */
        .globl  ob_launch
ob_launch:
        move    $26, $4                         /* entry point */
        move    $29, $5
        move    $30, $5
        move    $28, $6
        andi    $8, $7, OBF_GARBREGS
        beq     $8, $0, 1f
        move    $1, $0
        lui     $1, 0xdead
1:      ori     $2, $1, 2
        ori     $3, $1, 3
        ori     $6, $1, 6
        ori     $9, $1, 9
        ori     $10, $1, 10
        ori     $11, $1, 11
        ori     $12, $1, 12
        ori     $13, $1, 13
        ori     $14, $1, 14
        ori     $15, $1, 15
        ori     $16, $1, 16
        ori     $17, $1, 17
        ori     $18, $1, 18
        ori     $19, $1, 19
        ori     $20, $1, 20
        ori     $21, $1, 21
        ori     $22, $1, 22
        ori     $23, $1, 23
        ori     $24, $1, 24
        ori     $25, $1, 25
        ori     $27, $1, 27
        mthi    $1
        mtlo    $1
        beq     $8, $0, 2f                      /* without the pattern the registers are really zero */
        nop
        b       3f
        nop
2:      move    $2, $0
        move    $3, $0
        move    $6, $0
        move    $9, $0
        move    $10, $0
        move    $11, $0
        move    $12, $0
        move    $13, $0
        move    $14, $0
        move    $15, $0
        move    $16, $0
        move    $17, $0
        move    $18, $0
        move    $19, $0
        move    $20, $0
        move    $21, $0
        move    $22, $0
        move    $23, $0
        move    $24, $0
        move    $25, $0
        move    $27, $0
3:      lui     $31, %hi(ob_returned)
        addiu   $31, $31, %lo(ob_returned)
        andi    $8, $7, OBF_KIRQ
        beq     $8, $0, 4f
        move    $8, $0                          /* SR before rfe: 0 -> the game starts with interrupts disabled */
        ori     $8, $0, 0x0404                  /* IM2 | IEp -> after rfe: IM2 | IEc */
4:      mtc0    $8, $12
        ori     $4, $0, 1
        move    $5, $0
        move    $7, $1
        move    $8, $1
        jr      $26
        .word   0x42000010                      /* rfe */

ob_returned:                                    /* the game returned to its caller */
        lw      $8, (OB_TRACE+TR_RETURNED)($0)
        nop
        addiu   $8, $8, 1
        sw      $8, (OB_TRACE+TR_RETURNED)($0)
1:      b       1b
        nop
