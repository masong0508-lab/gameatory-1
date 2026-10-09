@ Stunt Fox start-up: cartridge entry, stacks, section copies, IRQ handler and runtime helpers.
    .syntax unified
    .section .crt0, "ax"
    .arm
    .global _start
_start:
    b       start
    .fill   188, 1, 0               @ cartridge header, filled in by build.py

start:
    mov     r0, #0x12               @ IRQ mode stack
    msr     cpsr_c, r0
    ldr     sp, =0x03007fa0
    mov     r0, #0x1f               @ system mode stack
    msr     cpsr_c, r0
    ldr     sp, =0x03007f00

    ldr     r0, =__iwram_lma        @ copy IWRAM code and data from ROM
    ldr     r1, =__iwram_start
    ldr     r2, =__iwram_end
1:  cmp     r1, r2
    ldrlo   r3, [r0], #4
    strlo   r3, [r1], #4
    blo     1b

    mov     r3, #0                  @ clear .bss (IWRAM) and .sbss (EWRAM)
    ldr     r1, =__bss_start
    ldr     r2, =__bss_end
2:  cmp     r1, r2
    strlo   r3, [r1], #4
    blo     2b
    ldr     r1, =__sbss_start
    ldr     r2, =__sbss_end
3:  cmp     r1, r2
    strlo   r3, [r1], #4
    blo     3b

    ldr     r0, =irq_handler
    ldr     r1, =0x03007ffc
    str     r0, [r1]
    ldr     r0, =main
    mov     lr, pc
    bx      r0
    b       .
    .pool

@ IRQ handler (called by the BIOS in ARM mode): acknowledge, tell VBlankIntrWait, count frames.
    .section .iwram, "ax"
    .arm
    .global irq_handler
    .type irq_handler, %function
irq_handler:
    mov     r3, #0x04000000
    add     r3, r3, #0x200
    ldr     r2, [r3]                @ IE | IF << 16
    and     r1, r2, r2, lsr #16
    strh    r1, [r3, #2]            @ acknowledge
    ldr     r2, =0x03007ff8
    ldrh    r0, [r2]
    orr     r0, r0, r1
    strh    r0, [r2]
    tst     r1, #1
    ldrne   r2, =frame_count
    ldrne   r0, [r2]
    addne   r0, r0, #1
    strne   r0, [r2]
    bx      lr
    .pool

    .section .text
    .arm
@ Division through the BIOS (signed). Results: r0 quotient, r1 remainder.
    .global __aeabi_idiv, __aeabi_idivmod
    .type __aeabi_idiv, %function
__aeabi_idiv:
    .type __aeabi_idivmod, %function
__aeabi_idivmod:
    cmp     r1, #0
    moveq   r0, #0
    bxeq    lr
    swi     0x060000
    bx      lr

@ Unsigned division by shift and subtract.
    .global __aeabi_uidiv, __aeabi_uidivmod
    .type __aeabi_uidiv, %function
__aeabi_uidiv:
    .type __aeabi_uidivmod, %function
__aeabi_uidivmod:
    cmp     r1, #0
    moveq   r0, #0
    bxeq    lr
    mov     r2, r0                  @ remainder
    mov     r0, #0                  @ quotient
    mov     r3, #1
4:  cmp     r1, #0x80000000
    cmpcc   r1, r2
    movcc   r1, r1, lsl #1
    movcc   r3, r3, lsl #1
    bcc     4b
5:  cmp     r2, r1
    subcs   r2, r2, r1
    orrcs   r0, r0, r3
    movs    r3, r3, lsr #1
    movne   r1, r1, lsr #1
    bne     5b
    mov     r1, r2
    bx      lr

@ 64-bit multiply (low 64 bits).
    .global __aeabi_lmul
    .type __aeabi_lmul, %function
__aeabi_lmul:
    stmfd   sp!, {r4, lr}
    mul     r4, r0, r3
    mla     r4, r1, r2, r4
    umull   r0, r1, r2, r0
    add     r1, r1, r4
    ldmfd   sp!, {r4, lr}
    bx      lr

@ memset / memcpy and their AEABI names.
    .global memset, memcpy, __aeabi_memcpy, __aeabi_memcpy4, __aeabi_memset, __aeabi_memset4, __aeabi_memclr, __aeabi_memclr4
    .type __aeabi_memclr, %function
__aeabi_memclr:
    .type __aeabi_memclr4, %function
__aeabi_memclr4:
    mov     r2, #0                  @ (dest, n) -> value 0
    b       aeabi_set
    .type __aeabi_memset, %function
__aeabi_memset:
    .type __aeabi_memset4, %function
__aeabi_memset4:                    @ (dest, n, value)
aeabi_set:
    mov     r3, r1
    mov     r1, r2
    mov     r2, r3
    .type memset, %function
memset:                             @ (dest, value, n)
    mov     r3, r0
6:  subs    r2, r2, #1
    strbge  r1, [r3], #1
    bgt     6b
    bx      lr
    .type __aeabi_memcpy, %function
__aeabi_memcpy:
    .type __aeabi_memcpy4, %function
__aeabi_memcpy4:
    .type memcpy, %function
memcpy:                             @ (dest, src, n)
    mov     r3, r0
7:  subs    r2, r2, #1
    ldrbge  r12, [r1], #1
    strbge  r12, [r3], #1
    bgt     7b
    bx      lr
