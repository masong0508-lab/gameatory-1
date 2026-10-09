@ Inner loops for Payback's tiles (ARM, IWRAM; MERGE build). See tex.c.
@
@ A texture position is packed in one word: bits 31..27 the column of the 32 x 32 tile and
@ 26..16 its fraction, bits 15..11 the row and 10..0 its fraction, so one add steps both and
@ each wraps around its tile by itself. Every texel covers 2 x 2 pixels.
    .syntax unified
    .section .iwram, "ax"
    .arm

@ void tex_hrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, int row2)
@ n texels along a row from dst (even), each also written row2 bytes further (240: the next
@ row, 0: none).
    .global tex_hrun
    .type tex_hrun, %function
tex_hrun:
    push    {r4-r8, lr}
    ldr     r4, [sp, #24]           @ tile
    ldr     r7, [sp, #28]           @ row2
    mov     r5, #0x3e0
    cmp     r1, #0
    ble     3f
    tst     r1, #1
    beq     2f
    and     r6, r5, r2, lsr #6      @ odd count: one first
    orr     r6, r6, r2, lsr #27
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    strh    r6, [r0, r7]
    strh    r6, [r0], #2
    subs    r1, r1, #1
    beq     3f
2:  and     r6, r5, r2, lsr #6      @ two a turn
    orr     r6, r6, r2, lsr #27
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    and     r8, r5, r2, lsr #6
    orr     r8, r8, r2, lsr #27
    ldrb    r8, [r4, r8]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    orr     r8, r8, r8, lsl #8
    strh    r6, [r0, r7]
    strh    r6, [r0], #2
    strh    r8, [r0, r7]
    strh    r8, [r0], #2
    subs    r1, r1, #2
    bgt     2b
3:  pop     {r4-r8, lr}
    bx      lr

@ void tex_vrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, const u8 *lut, int row2)
@ n texels down a column two pixels wide, two rows each (the second only if row2 is 240);
@ lut, if not 0, darkens them.
    .global tex_vrun
    .type tex_vrun, %function
tex_vrun:
    push    {r4-r9, lr}
    ldr     r4, [sp, #28]           @ tile
    ldr     r7, [sp, #32]           @ lut
    ldr     r8, [sp, #36]           @ row2
    mov     r5, #0x3e0
    mov     r9, #480
    cmp     r1, #0
    ble     3f
    cmp     r7, #0
    beq     2f
1:  and     r6, r5, r2, lsr #6
    orr     r6, r6, r2, lsr #27
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    ldrb    r6, [r7, r6]
    orr     r6, r6, r6, lsl #8
    strh    r6, [r0, r8]
    strh    r6, [r0], r9
    subs    r1, r1, #1
    bgt     1b
    pop     {r4-r9, lr}
    bx      lr
2:  and     r6, r5, r2, lsr #6
    orr     r6, r6, r2, lsr #27
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    strh    r6, [r0, r8]
    strh    r6, [r0], r9
    subs    r1, r1, #1
    bgt     2b
3:  pop     {r4-r9, lr}
    bx      lr
