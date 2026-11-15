import sys
from unicorn import *
from unicorn.arm_const import *
ROM=open('../../../roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
u.mem_map(0x08000000,0x800000); u.mem_write(0x08000000,ROM[:0x800000])
u.mem_map(0x02000000,0x40000); u.mem_map(0x03000000,0x8000)
u.mem_map(0x04000000,0x1000); u.mem_map(0x05000000,0x1000); u.mem_map(0x06000000,0x20000); u.mem_map(0x07000000,0x1000)
u.mem_map(0x0e000000,0x10000)
n=[0]
def h(uc,a,s,ud): 
    n[0]+=1
u.hook_add(UC_HOOK_CODE,h)
try: u.emu_start(0x08000000,0x08022dc8,count=2000000)
except Exception as e: print('exc',e)
print('insns',n[0],hex(u.reg_read(UC_ARM_REG_PC)),hex(u.reg_read(UC_ARM_REG_SP)),hex(u.reg_read(UC_ARM_REG_CPSR)))
iw=bytes(u.mem_read(0x03000000,0x8000)); open('/tmp/iwram_main.bin','wb').write(iw)
import struct
for a in range(0x1a0,0x200,4): print(hex(a),hex(struct.unpack('<I',ROM[a:a+4])[0]),end='; ')
