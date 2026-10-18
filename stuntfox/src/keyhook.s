@ MERGE build only: where Payback's calls now go.

    .syntax unified
    .thumb

@ In place of Payback's keypad reader (the bl at 0x0800e9a8): it runs the reader, then lets
@ sf_keys (merge.c) change what Payback sees.
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

@ In place of its world renderer (build.py MERGE_CALLS), with that renderer's 8 arguments: sf_draw
@ (merge.c) draws the frame, or says Payback is to; then its renderer is jumped to with the
@ registers and stack it was called with, so it runs no deeper than in Payback alone.
    .section .text.sf_frame, "ax"
    .global sf_frame
    .thumb_func
sf_frame:
    push {r0-r4, lr}
    ldr r0, [sp, #36]              @ the view, the last of the 4 arguments on the stack
    bl sf_draw
    cmp r0, #0
    bne 2f
    ldr r0, [sp, #20]
    mov lr, r0
    ldr r4, =0x0800adad            @ (build.py MERGE_RENDERER)
    mov ip, r4
    pop {r0-r4}
    add sp, #4
    bx ip
2:  pop {r0-r4, pc}
    .pool
