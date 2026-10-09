@ Span filling for the polygon rasteriser (ARM, IWRAM).
    .syntax unified
    .section .iwram, "ax"
    .arm

@ void fill_trap(u8 *row, int rows, s32 xl, s32 sl, s32 xr, s32 sr, u32 color4)
@ Fills `rows` scanlines from `row` between the 16.16 edges xl (left) and xr (right),
@ stepping them by sl and sr per row. A pixel is set when its centre lies between them.
@ Mode 4 VRAM takes no byte writes: odd ends are merged into their halfword.
    .global fill_trap
    .type fill_trap, %function
fill_trap:
    push    {r4-r11, lr}
    ldr     r4, [sp, #36]           @ xr
    ldr     r5, [sp, #40]           @ sr
    ldr     r6, [sp, #44]           @ colour in all four bytes
    mov     r7, r6
    mov     r8, r6
    mov     r9, r6
    mov     lr, #0x8000
    sub     lr, lr, #1              @ rounding: (x + 0x7fff) >> 16
.Lrow:
    add     r10, r2, lr
    add     r11, r4, lr
    add     r10, r0, r10, asr #16   @ first pixel
    add     r11, r0, r11, asr #16   @ one past the last
    cmp     r10, r11
    bge     .Lnext
    tst     r10, #1
    beq     1f
    ldrh    r12, [r10, #-1]         @ odd start: high byte of its halfword
    and     r12, r12, #0xff
    orr     r12, r12, r6, lsl #8
    strh    r12, [r10, #-1]
    add     r10, r10, #1
    cmp     r10, r11
    bhs     .Lnext
1:  tst     r11, #1
    beq     2f
    ldrh    r12, [r11, #-1]         @ odd end: low byte of its halfword
    and     r12, r12, #0xff00
    orr     r12, r12, r6, lsr #24
    strh    r12, [r11, #-1]
    sub     r11, r11, #1
    cmp     r10, r11
    bhs     .Lnext
2:  tst     r10, #2                 @ word align
    strhne  r6, [r10], #2
    sub     r12, r11, r10
    subs    r12, r12, #16
    blt     4f
3:  stmia   r10!, {r6-r9}
    subs    r12, r12, #16
    bge     3b
4:  adds    r12, r12, #16           @ 0..14 bytes left
    beq     .Lnext
    tst     r12, #8
    stmiane r10!, {r6, r7}
    tst     r12, #4
    strne   r6, [r10], #4
    tst     r12, #2
    strhne  r6, [r10]
.Lnext:
    add     r0, r0, #240
    add     r2, r2, r3
    add     r4, r4, r5
    subs    r1, r1, #1
    bgt     .Lrow
    pop     {r4-r11, lr}
    bx      lr
