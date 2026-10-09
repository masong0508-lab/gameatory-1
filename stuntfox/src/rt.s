@ Runtime helpers the compiler calls: division, 64-bit multiply, memset and memcpy (ARM).
    .syntax unified
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
