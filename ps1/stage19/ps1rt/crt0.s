.set noreorder
.section .text.start,"ax"
.global _start
_start:
  # stage 19: SR written whole, not OR-ed into what the kernel left: CU2 (the GTE) on; IEc = 0 and IM = 0, so no interrupt is taken whatever
  # I_MASK and the devices say; BEV = 0 (kernel exception vectors in RAM), kernel mode.  main() then clears I_MASK and acknowledges I_STAT.
  lui $t0,0x4000
  mtc0 $t0,$12
  nop
  nop
  lui $sp,0x801f
  ori $sp,$sp,0xd000
.ifdef EXEPACK
  # speed item M11: the EXE is packed (ps1rt/exepack.py): the runtime up to __bss_start is in place, the run table follows it
  # ('PKX1', n, zero_end, n x (dest, len), ascending), then the bytes of the runs.  1. copy the runs highest first, each one
  # backward (every source lies below its destination); 2. zero the gaps highest first, the table's own gap [__bss_start, first
  # run) last; 3. FlushCache once, before any moved code runs.  Nothing below __bss_start is written.  No table: a plain image.
.global __exepack_v1
__exepack_v1:
  la $a0,__bss_start
  lw $t0,0($a0)
  lui $t1,0x3158
  ori $t1,$t1,0x4b50
  bne $t0,$t1,19f
  lw $a1,4($a0)                 # n
  lw $a2,8($a0)                 # zero_end
  addiu $a3,$a0,12              # first entry
  sll $t0,$a1,3
  addu $t9,$a3,$t0              # end of the entries = start of the run bytes
  move $t8,$t9                  # end of the run bytes = start + sum of the lengths
  move $t2,$a3
10: beq $t2,$t9,11f
  nop
  lw $t3,4($t2)
  addiu $t2,$t2,8
  b 10b
  addu $t8,$t8,$t3
11: move $t2,$t9                # 1. the runs, last entry first
12: beq $t2,$a3,15f
  nop
  addiu $t2,$t2,-8
  lw $t4,0($t2)                 # dest
  lw $t3,4($t2)                 # len
  nop
  subu $t8,$t8,$t3              # source of this run
  addu $t5,$t8,$t3              # source cursor (end)
  addu $t6,$t4,$t3              # destination cursor (end)
13: beq $t6,$t4,12b
  nop
  addiu $t5,$t5,-4
  lw $t7,0($t5)
  addiu $t6,$t6,-4
  b 13b
  sw $t7,0($t6)
15: move $t2,$t9                # 2. the gaps, highest first
  move $t6,$a2                  # end of the gap = zero_end
16: beq $t2,$a3,18f
  nop
  addiu $t2,$t2,-8
  lw $t4,0($t2)                 # dest
  lw $t3,4($t2)                 # len
  nop
  addu $t5,$t4,$t3              # the gap starts at the end of this run
17: beq $t5,$t6,171f
  nop
  sw $zero,0($t5)
  b 17b
  addiu $t5,$t5,4
171: b 16b
  move $t6,$t4                  # the next gap ends where this run starts
18: beq $a0,$t6,181f            # the table's gap [__bss_start, first run)
  nop
  sw $zero,0($a0)
  b 18b
  addiu $a0,$a0,4
181: li $t1,0x44                # 3. FlushCache, BIOS A(44h): moved code must not run from stale cache lines
  addiu $sp,$sp,-16
  li $t0,0xA0
  jalr $t0
  nop
  addiu $sp,$sp,16
19:
.endif
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
