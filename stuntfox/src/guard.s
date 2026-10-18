@ MERGE build only: ten places in Payback go through these (build.py puts a bl over the two
@ instructions each one replaces; Payback's code there uses bl as a long jump, or has made a
@ call just before, so lr is free), so that what merge.c lists in sf_guard is let be: [0] the
@ man under the Arwing, by all of them; [1] our car, by a knock and a street object, and by a
@ blast all but 40 (never below 1); [2] the man on foot, by a blast or a shot that would end him
@ from full health in one go (he is left at 1,
@ and [3] is set: the rest of that tick's harm leaves him there too).
    .syntax unified
    .thumb

@ the explosion around a burning vehicle (0x08000b96): r1 an entity in range, r2 its health,
@ r4 that health before (signed), r0 after
    .section .text.sf_hook_blast, "ax"
    .global sf_hook_blast
    .thumb_func
sf_hook_blast:
    ldr r7, [sp, #0x5c]             @ (replaced)
    push {r3}
    ldr r3, =sf_guard
    ldr r3, [r3]
    cmp r1, r3
    beq 2f                          @ [0] the man under the Arwing: unhurt
    ldr r3, =sf_guard
    ldr r3, [r3, #8]
    cmp r1, r3
    bne 3f
    cmp r4, #100                    @ [2] the man on foot, at full health ...
    bge 4f
    ldr r3, =sf_guard
    ldr r3, [r3, #12]
    cmp r3, #0                      @ (or left at 1 earlier in this tick)
    beq 1f
4:  cmp r0, #1
    bge 1f
    movs r0, #1                     @ ... is left at 1 by a blast we do not draw
    ldr r3, =sf_guard
    str r3, [r3, #12]               @ [3] set
    b 1f
3:  ldr r3, =sf_guard                @ everyone else gets Payback's harm, but our car ([1])
    ldr r3, [r3, #4]                @ loses at most 40 to a blast, and is never wrecked by
    cmp r1, r3                      @ one: we do not draw Payback's burning traffic, and a
    bne 1f                          @ car pushed into one met it at no distance (-1000)
    adds r3, r4, #0
    subs r3, #40
    cmp r3, #1
    bge 5f
    movs r3, #1
5:  cmp r0, r3
    bge 1f
    cmp r4, r3                      @ (already at 0: Payback's)
    blt 1f
    adds r0, r3, #0
1:  pop {r3}
    strh r0, [r2]                   @ (replaced)
    bx lr
2:  pop {r3}
    adds r0, r4, #0                 @ unhurt
    bx lr
    .pool

@ a knock, when two records run into each other (a car into a man is FLATTENED!, and our car's
@ long steps meet things this way too): Payback takes the harm off both, the first record's
@ health at 0x080140da, the other's at 0x08014178. r4 the health, r2 after (which Payback then
@ tests for a death), \before the health before, \harm the harm. Payback's harm is the change of
@ velocity squared (a person's /256): one blow from a car at speed ends him. But a person it has
@ knocked reels slower than our car is driven, so ours (put back each frame) knocks him again
@ every other tick while it pushes him along and flattened him at a walking pace (th_carhits ped):
@ once he reels (18) or is down (7), our car's pushes hurt him only if one is a blow of its own
@ (40 or more, a change of 100: still the end of him at 48). Between our car and a vehicle there
@ is no harm, as no push (sf_hook_kick: car_bump gives both).
    .macro knock before, harm
    push {r3, r7}
    ldr r7, =sf_guard
    ldr r3, [r7]
    adds r3, #0x68
    cmp r3, r4
    beq 1f
    ldr r3, [r7, #4]
    adds r3, #0x68
    cmp r3, r4
    beq 1f
    subs r3, #0x68                  @ our car's record (0: not driving)
    beq 2f
    ldr r7, [sp, #0x188 + 8]        @ (the knock's two records)
    cmp r7, r3
    beq 3f
    ldr r7, [sp, #0x1ec + 8]
    cmp r7, r3
    bne 2f
3:  push {r0, r1, r2, lr}           @ our car and a vehicle: no harm while the push waits
    mov r3, ip                      @ (sf_kick_far, as sf_hook_kick)
    push {r3}
    ldr r0, [sp, #0x1ec + 28]
    ldr r1, [sp, #0x188 + 28]
    bl sf_kick_far
    pop {r3}
    mov ip, r3
    cmp r0, #0
    pop {r0, r1, r2, r3}
    mov lr, r3                      @ (the flags: Z, it hurts)
    bne 1f
    movs r3, #0x68
    subs r3, r4, r3                 @ the one hurt
    ldr r7, [r3, #0x1c]
    adds r7, #0x26
    ldrb r7, [r7]
    cmp r7, #1                      @ a person
    bne 2f
    movs r7, #0x87
    lsls r7, r7, #1
    adds r7, #1
    ldrb r7, [r3, r7]               @ +0x10f
    cmp r7, #18
    beq 4f
    cmp r7, #7
    bne 2f
4:  cmp \harm, #40
    blt 1f
2:  pop {r3, r7}
    strh r2, [r4]                   @ (replaced)
    bx lr
1:  pop {r3, r7}
    adds r2, \before, #0            @ unhurt
    bx lr
    .pool
    .endm

    .section .text.sf_hook_knock, "ax"
    .global sf_hook_knock
    .thumb_func
sf_hook_knock:
    subs r2, r0, r1                 @ (replaced)
    knock r0, r1

    .section .text.sf_hook_knock2, "ax"
    .global sf_hook_knock2
    .thumb_func
sf_hook_knock2:
    subs r2, r6, r5                 @ (replaced)
    knock r6, r5

@ a shot that hits (0x08015134): r1 the health of the one hit, r0 the harm; r2 is left the
@ health before, and r0 after (Payback stores it and tests it for a death)
    .section .text.sf_hook_shot, "ax"
    .global sf_hook_shot
    .thumb_func
sf_hook_shot:
    ldrh r2, [r1]                   @ (replaced)
    subs r0, r2, r0                 @ (replaced)
    push {r3}
    ldr r3, =sf_guard
    ldr r3, [r3]
    adds r3, #0x68
    cmp r3, r1
    beq 2f                          @ [0] under the Arwing: unhurt
    ldr r3, =sf_guard
    ldr r3, [r3, #8]
    adds r3, #0x68
    cmp r3, r1
    bne 1f
    lsls r3, r2, #16
    asrs r3, r3, #16                @ (his health before, signed)
    cmp r3, #100
    bge 4f
    ldr r3, =sf_guard
    ldr r3, [r3, #12]
    cmp r3, #0                      @ (or left at 1 earlier in this tick: a bullet hits twice)
    beq 1f
4:  cmp r0, #1
    bge 1f
    movs r0, #1                     @ [2] on foot, from full health: one unseen shot leaves 1
    ldr r3, =sf_guard
    str r3, [r3, #12]               @ [3] set
1:  pop {r3}
    bx lr
2:  pop {r3}
    adds r0, r2, #0                 @ unhurt
    bx lr
    .pool

@ a knock's push (0x080135bc): Payback adds the change of each record's velocity to its +0x40 and
@ +0x42, the other record's (fp) at 0x08013bbc and 0x08013bec (\at the field, \dv the change), the
@ first's ([sp, #0x1ec]) at 0x08013c74 and 0x08013ca6. Its knock sees the two meet a frame ahead:
@ between our car and a vehicle neither push comes (sf_kick_far in merge.c: car_bump gives the one
@ bounce, and the harm, so the knock's harm does not come either, sf_hook_knock). Our car's record ([1]) is written over
@ from our car every frame, so what lands on it is also added up in sf_knock (x, y), for
@ car_knocked (merge.c) to take into our car itself. (L's stop in sf_keys, bail_press, writes the record, not through here: no knock.)
    .macro kick sum, old, dv, at
    push {r0, r1, r2, r3, lr}
    mov r3, ip
    push {r3}
    ldr r0, =sf_guard
    ldr r0, [r0, #4]
    cmp r0, #0                      @ (not driving: Payback's)
    beq 2f
    ldr r0, [sp, #0x1ec + 24]       @ the knock's two records
    mov r1, fp
    bl sf_kick_far
    cmp r0, #0
2:  pop {r3}
    mov ip, r3
    pop {r0, r1, r2, r3}            @ (the flags: Z, it pushes now)
    bne 3f
    adds \sum, \old, \dv            @ (replaced)
    strh \sum, [\at]                @ (replaced)
    push {r6, r7}
    ldr r6, =sf_guard
    ldr r6, [r6, #4]
    subs r6, \at, r6
    subs r6, #0x40                  @ 0: +0x40 of [1], 2: +0x42
    cmp r6, #2
    bhi 1f
    ldr r7, =sf_knock
    adds r7, r7, r6
    ldrh r6, [r7]
    adds r6, r6, \dv
    strh r6, [r7]
1:  pop {r6, r7}
    pop {pc}
3:  adds \sum, \old, #0            @ it waits: as if no change
    pop {pc}
    .pool
    .endm

    .section .text.sf_hook_kick, "ax"
    .global sf_hook_kick
    .thumb_func
sf_hook_kick:
    kick r5, r2, r1, r0

    .section .text.sf_hook_kick2, "ax"
    .global sf_hook_kick2
    .thumb_func
sf_hook_kick2:
    kick r4, r0, r2, r5

@ the police, each officer or police car deciding whether to go for the player (0x08021472):
@ r3 points at the player's wanted level, ip the player; the flags of "wanted > 2" decide.
@ Nobody arrests the man under the Arwing (the stars stay for when he is on foot again).
    .section .text.sf_hook_police, "ax"
    .global sf_hook_police
    .thumb_func
sf_hook_police:
    ldrsb r0, [r3, r0]              @ (replaced)
    push {r1}
    ldr r1, =sf_guard
    ldr r1, [r1]
    cmp r1, ip
    pop {r1}
    bne 1f
    movs r0, #0                     @ as if not wanted
1:  cmp r0, #2                      @ (replaced)
    bx lr
    .pool

@ a vehicle's or a man's knock against a street object, a tree or a lamp (0x0800147a): Payback
@ takes its impact, r4, off the health at r2 + 0x68 every frame it finds them touching. Its circle
@ round a vehicle is wider than our footprint, so our car, which our own physics keeps off the
@ object, went on touching in Payback's test: a tank driven past a tree lost all its health in
@ half a second; and some object types we do not draw at all. Our car's crashes are ours
@ (car_crash), the man under the Arwing is let be. (r2 is the record r7 here.)
    .section .text.sf_hook_objhit, "ax"
    .global sf_hook_objhit
    .thumb_func
sf_hook_objhit:
    adds r2, #0x68                  @ (replaced)
    ldrh r0, [r2]                   @ (replaced)
    push {r1}
    ldr r1, =sf_guard
    ldr r1, [r1]
    adds r1, #0x68
    cmp r1, r2
    beq 1f
    ldr r1, =sf_guard
    ldr r1, [r1, #4]
    adds r1, #0x68
    cmp r1, r2
    bne 2f
1:  movs r4, #0                     @ unhurt (Payback reloads r4 after)
2:  pop {r1}
    bx lr
    .pool
