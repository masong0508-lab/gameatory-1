@ MERGE build only: Payback calls this in place of its keypad reader (the bl at 0x0800e9a8).
@ It runs the reader, then lets sf_keys (merge.c) change what Payback sees.
    .syntax unified
    .thumb
    .section .text.sf_keyhook, "ax"
    .global sf_keyhook
    .thumb_func
sf_keyhook:
    push {r0, r4, lr}
    ldr r4, =0x08072f69
    bl 1f
    str r0, [sp]
    bl sf_keys
    pop {r0, r4}
    pop {r1}
    bx r1
1:  bx r4
    .pool
