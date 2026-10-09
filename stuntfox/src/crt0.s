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
