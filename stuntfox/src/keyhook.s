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

@ In place of Payback's cap on the people and traffic it adds (at 0x080039fc, 0x08003b20, 0x08003b98:
@ the list's last index under min(0x02001dfc + 8, 20)): that cap, moved by GAME SETTINGS'
@ traffic (traffic_add, 8 = as it was; anything past 20, as in memory not ours yet, counts as 8).
@ Keeps r0 (the tries) and r2 (the count), returns the cap in r3, as the code it stands in for.
    .section .text.sf_hook_traffic, "ax"
    .global sf_hook_traffic
    .thumb_func
sf_hook_traffic:
    ldr r1, =0x02001dfc
    ldr r3, [r1]
    adds r3, #8
    cmp r3, #20
    ble 1f
    movs r3, #20
1:  ldr r1, =traffic_add
    ldrb r1, [r1]
    cmp r1, #20
    bls 2f
    movs r1, #8
2:  adds r3, r1
    subs r3, #8
    bx lr
    .pool
