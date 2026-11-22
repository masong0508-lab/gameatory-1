# Star-FlyBack PS1: glue between translated guest code and the interpreter (C).  Guest register map (t2m): r0-r7 = $16-$23, r8-r12 = $11-$15, sp = $30, lr = $31,
# NZCV = $4-$7 (dead across calls).  Scratch for the translator: $1,$2,$3,$8,$9,$10,$24,$25,$28.
# IS layout (interp.h): r[0..15] at 0..60, f at 64, pc at 68, ev at 72.  Slab size 128 bytes.
.set noreorder
.set noat
.text
.global interp_enter
.global ip_call_asm
.global ip_ret
.global ip_stubs
.global ip_sthunks
# interp_enter: entered by "jr $2" from RT_MISS with all guest registers live and interp_target (global) = guest target.
interp_enter:
  la $24,ip_depth
  lw $25,0($24)
  nop
  addiu $1,$25,1
  sw $1,0($24)
  sll $25,$25,7
  la $24,ip_slab
  addu $24,$24,$25               # $24 = &slab[depth]
  sw $16,0($24)
  sw $17,4($24)
  sw $18,8($24)
  sw $19,12($24)
  sw $20,16($24)
  sw $21,20($24)
  sw $22,24($24)
  sw $23,28($24)
  sw $11,32($24)
  sw $12,36($24)
  sw $13,40($24)
  sw $14,44($24)
  sw $15,48($24)
  sw $30,52($24)
  sw $31,56($24)
  sw $0,60($24)
  sw $0,64($24)                  # flags
  la $2,interp_target
  lw $2,0($2)
  nop
  sw $2,68($24)                  # pc (state bit fixed in interp_top)
  sw $0,72($24)
  la $2,ip_stacks                # C stack for this depth: ip_stacks + (depth+1)*4096
  sll $3,$1,10
  addu $29,$2,$3
  addiu $29,$29,-16
  jal interp_top
  move $4,$24
  move $25,$2                    # host address to continue at
  la $24,ip_depth
  lw $1,0($24)
  nop
  addiu $1,$1,-1
  sw $1,0($24)
  sll $3,$1,7
  la $2,ip_slab
  addu $24,$2,$3                 # same slab
  lw $16,0($24)
  lw $17,4($24)
  lw $18,8($24)
  lw $19,12($24)
  lw $20,16($24)
  lw $21,20($24)
  lw $22,24($24)
  lw $23,28($24)
  lw $11,32($24)
  lw $12,36($24)
  lw $13,40($24)
  lw $14,44($24)
  lw $15,48($24)
  lw $30,52($24)
  lw $31,56($24)
  nop
  jr $25
  nop
# void ip_call_asm(IS *s, u32 host): run translated code at host; $31 = ip_ret; guest r0-r12, sp from s; on return s is updated.  C callee-saved registers and $29 are saved in a frame.
ip_call_asm:
  la $2,ip_cs_sp
  lw $3,0($2)
  nop
  sw $16,0($3)
  sw $17,4($3)
  sw $18,8($3)
  sw $19,12($3)
  sw $20,16($3)
  sw $21,20($3)
  sw $22,24($3)
  sw $23,28($3)
  sw $30,32($3)
  sw $29,36($3)
  sw $31,40($3)
  sw $4,44($3)
  addiu $8,$3,48
  sw $8,0($2)
  move $25,$5
  lw $16,0($4)
  lw $17,4($4)
  lw $18,8($4)
  lw $19,12($4)
  lw $20,16($4)
  lw $21,20($4)
  lw $22,24($4)
  lw $23,28($4)
  lw $11,32($4)
  lw $12,36($4)
  lw $13,40($4)
  lw $14,44($4)
  lw $15,48($4)
  lw $30,52($4)
  la $31,ip_ret
  jr $25
  nop
ip_ret:
  la $2,ip_cs_sp
  lw $3,0($2)
  nop
  addiu $3,$3,-48
  sw $3,0($2)
  lw $4,44($3)
  nop
  sw $16,0($4)
  sw $17,4($4)
  sw $18,8($4)
  sw $19,12($4)
  sw $20,16($4)
  sw $21,20($4)
  sw $22,24($4)
  sw $23,28($4)
  sw $11,32($4)
  sw $12,36($4)
  sw $13,40($4)
  sw $14,44($4)
  sw $15,48($4)
  sw $30,52($4)
  lw $16,0($3)
  lw $17,4($3)
  lw $18,8($3)
  lw $19,12($3)
  lw $20,16($3)
  lw $21,20($3)
  lw $22,24($3)
  lw $23,28($3)
  lw $30,32($3)
  lw $29,36($3)
  lw $31,40($3)
  nop
  jr $31
  nop

# ip_resume_k (k = 0..IP_RECN-1): host-form lr handed to translated code in place of a guest return address; slot k of the record table (ip_rec) holds that guest address.  If the callee
# really returns through lr (jr $31 / bx lr / pop {pc}) we arrive here with the guest registers live: the record k is used and it and every record above it (activations that were
# abandoned by long jumps) are dropped; control re-enters through RT_BX with $25 = the guest return address (hash hit: translated; miss: the interpreter continues at that address).
.set ip_k,0
ip_stubs:
.rept 64
  ori $24,$0,ip_k
  j ip_resume_common
  nop
.set ip_k,ip_k+1
.endr
ip_resume_common:
  la $25,ip_rec_n
  lw $2,0($25)
  la $9,ip_rec
  sltu $3,$24,$2
  beqz $3,3f                    # record gone: cannot happen
  sll $1,$24,3
  addu $1,$1,$9
  lw $2,4($1)
  sw $24,0($25)                 # n = k
  move $25,$2
  la $1,RT_BX_HOST
  lw $1,0($1)
  nop
  jr $1
  nop
3:
  b 3b
  nop

# ip_sthunks: thunk k (24 bytes) = RT_STUB with $25 = stub id k+1 (prune.STUBS ids are 1..7), entered like a translated call to a pruned renderer function ($31 = host-form return address).
.set ip_sid,1
ip_sthunks:
.rept 8
  ori $25,$0,ip_sid
  la $1,RT_STUB_HOST
  lw $1,0($1)
  nop
  jr $1
  nop
.set ip_sid,ip_sid+1
.endr

# intro fix (interp_glue.h).  rt_ovmiss: the host entry of the hash slots whose keys lie in the IWRAM overlay area while overlay 1 (the film player) is
# resident (ov_slots).  rt_found (t2m.py runtime()) jumps here with $24 = the key (guest target); like rt_miss it goes to RT_MISS (blob + 8, ps1.ld) with
# $25 = the target, so h_miss decides (film_miss, or the restored slot once overlay 0 is back).  $1 is free here, as in rt_hash.
.global rt_ovmiss
rt_ovmiss:
  lui $1,0x8003
  ori $1,$1,0x0008
  jr $1
  addu $25,$24,$0
# rt_ret0 / rt_ret1: the return of an overlay-1 entry point that is not run (film_miss): r0 = 0 (decoder init), r0 = 1 (the player: 'skipped by a key');
# back to the caller ($31 intact)
.global rt_ret0
.global rt_ret1
rt_ret0:
  jr $31
  addu $16,$0,$0
rt_ret1:
  jr $31
  addiu $16,$0,1
