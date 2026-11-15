.set noreorder
.section .text.start,"ax"
.global _start
_start:
  mfc0 $t0,$12
  lui $t1,0x4000        # SR.CU2: enable the GTE
  or $t0,$t0,$t1
  mtc0 $t0,$12
  nop
  lui $sp,0x801f
  ori $sp,$sp,0xd000
  la $t0,__bss_start
  la $t1,__bss_end
1: sltu $t2,$t0,$t1
  beq $t2,$zero,2f
  nop
  sw $zero,0($t0)
  b 1b
  addiu $t0,$t0,4
2: jal main
  nop
3: b 3b
  nop

.global snap_resume
snap_resume:            # a0 = u32 regs[32] (MIPS $0..$31), a1 = jump target; every register but $0,$26,$27 is loaded
  move $27,$4
  move $26,$5
  lw $1,4($27)
  lw $2,8($27)
  lw $3,12($27)
  lw $4,16($27)
  lw $5,20($27)
  lw $6,24($27)
  lw $7,28($27)
  lw $8,32($27)
  lw $9,36($27)
  lw $10,40($27)
  lw $11,44($27)
  lw $12,48($27)
  lw $13,52($27)
  lw $14,56($27)
  lw $15,60($27)
  lw $16,64($27)
  lw $17,68($27)
  lw $18,72($27)
  lw $19,76($27)
  lw $20,80($27)
  lw $21,84($27)
  lw $22,88($27)
  lw $23,92($27)
  lw $24,96($27)
  lw $25,100($27)
  lw $28,112($27)
  lw $30,120($27)
  lw $31,124($27)
  lw $29,116($27)
  nop
  jr $26
  nop
