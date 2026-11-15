#!/usr/bin/env python3
"""differential fuzz: interp.c (host build) vs unicorn ARM, one instruction at a time (ARM and Thumb).  usage: fuzz.py N [seed] [arm|thumb|both]"""
import sys,os,random,ctypes,struct
from unicorn import *
from unicorn.arm_const import *
HERE=os.path.dirname(os.path.abspath(__file__))
L=ctypes.CDLL(os.path.join(HERE,'test_host.so'))
class IS(ctypes.Structure): _fields_=[('r',ctypes.c_uint32*16),('f',ctypes.c_uint32),('pc',ctypes.c_uint32),('ev',ctypes.c_uint32),('pad',ctypes.c_uint32*2)]
L.t_unal.restype=ctypes.c_uint32; L.t_arena.restype=ctypes.c_void_p; L.t_code.restype=ctypes.c_void_p; L.t_wr.restype=ctypes.POINTER(ctypes.c_uint32)
N=int(sys.argv[1]); seed=int(sys.argv[2]) if len(sys.argv)>2 else 1; mode=sys.argv[3] if len(sys.argv)>3 else 'both'
rnd=random.Random(seed)
AR=0x02000000; AS=0x40000; CD=0x08000000
RK=[UC_ARM_REG_R0+i for i in range(13)]+[UC_ARM_REG_SP,UC_ARM_REG_LR]
u=Uc(UC_ARCH_ARM,UC_MODE_ARM); u.mem_map(AR,AS); u.mem_map(CD,0x1000)
def rnd_reg():
    k=rnd.random()
    if k<0.45: return AR+rnd.randrange(0x100,AS-0x100)                  # pointer into the arena
    if k<0.55: return AR+rnd.randrange(0x100,AS-0x100)&~3
    if k<0.8: return rnd.randrange(0,64)
    if k<0.9: return rnd.choice([0,1,0xffffffff,0x80000000,0x7fffffff,31,32,33,255,256,0xffff,0x8000])
    return rnd.getrandbits(32)
def thumb_ins():
    # sample from encodings
    f=rnd.randrange(19)
    if f==0: return (rnd.randrange(3)<<11)|(rnd.randrange(32)<<6)|(rnd.randrange(8)<<3)|rnd.randrange(8)
    if f==1: return 0x1800|(rnd.randrange(4)<<9)|(rnd.randrange(8)<<6)|(rnd.randrange(8)<<3)|rnd.randrange(8)
    if f==2: return 0x2000|(rnd.randrange(4)<<11)|(rnd.randrange(8)<<8)|rnd.randrange(256)
    if f==3: return 0x4000|(rnd.randrange(16)<<6)|(rnd.randrange(8)<<3)|rnd.randrange(8)
    if f==4:
        op=rnd.randrange(4); rd=rnd.randrange(16); rs=rnd.randrange(16)
        if op==3: rd=0
        if rd==15 and op==1: rd=14
        return 0x4400|(op<<8)|((rd>>3)<<7)|(rs<<3)|(rd&7)
    if f==5: return 0x4800|(rnd.randrange(8)<<8)|rnd.randrange(256)
    if f==6: return 0x5000|(rnd.randrange(8)<<9)|(rnd.randrange(8)<<6)|(rnd.randrange(8)<<3)|rnd.randrange(8)
    if f==7: return 0x6000|(rnd.randrange(4)<<11)|(rnd.randrange(32)<<6)|(rnd.randrange(8)<<3)|rnd.randrange(8)
    if f==8: return 0x8000|(rnd.randrange(2)<<11)|(rnd.randrange(32)<<6)|(rnd.randrange(8)<<3)|rnd.randrange(8)
    if f==9: return 0x9000|(rnd.randrange(2)<<11)|(rnd.randrange(8)<<8)|rnd.randrange(256)
    if f==10: return 0xa000|(rnd.randrange(2)<<11)|(rnd.randrange(8)<<8)|rnd.randrange(256)
    if f==11: return 0xb000|(rnd.randrange(2)<<7)|rnd.randrange(128)
    if f==12: return 0xb400|(rnd.randrange(2)<<11)|(rnd.randrange(2)<<8)|rnd.randrange(256)
    if f==13: return 0xc000|(rnd.randrange(2)<<11)|(rnd.randrange(8)<<8)|rnd.randrange(1,256)
    if f==14: return 0xd000|(rnd.randrange(14)<<8)|rnd.randrange(256)
    if f==15: return 0xe000|rnd.randrange(0x800)
    if f==16: return 0xf000|rnd.randrange(0x800)
    if f==17: return 0x4000|(rnd.randrange(16)<<6)|(rnd.randrange(8)<<3)|rnd.randrange(8)
    return 0xb400|rnd.randrange(256)
def arm_ins():
    cc=rnd.choice([14]*6+list(range(14)))
    k=rnd.randrange(12)
    if k<4:   # data processing
        op=rnd.randrange(16); S=rnd.randrange(2)
        if 8<=op<=11: S=1
        if rnd.random()<0.5:
            imm=rnd.randrange(256); rot=rnd.randrange(16); body=0x02000000|(op<<21)|(S<<20)|(rnd.randrange(16)<<16)|(rnd.randrange(15)<<12)|(rot<<8)|imm
        else:
            rm=rnd.randrange(16); sh=rnd.randrange(4)
            if rnd.random()<0.5: body=(op<<21)|(S<<20)|(rnd.randrange(16)<<16)|(rnd.randrange(15)<<12)|(rnd.randrange(32)<<7)|(sh<<5)|rm
            else: body=(op<<21)|(S<<20)|(rnd.randrange(15)<<16)|(rnd.randrange(15)<<12)|(rnd.randrange(15)<<8)|(sh<<5)|0x10|rm
        return (cc<<28)|body
    if k==4:  # mul/mla
        return (cc<<28)|(rnd.randrange(2)<<21)|(rnd.randrange(2)<<20)|(rnd.randrange(15)<<16)|(rnd.randrange(15)<<12)|(rnd.randrange(15)<<8)|0x90|rnd.randrange(15)
    if k==5:  # long mul
        return (cc<<28)|0x00800090|(rnd.randrange(4)<<21)|(rnd.randrange(2)<<20)|(rnd.randrange(15)<<16)|(rnd.randrange(15)<<12)|(rnd.randrange(15)<<8)|rnd.randrange(15)
    if k==6:  # ldr/str
        I=rnd.randrange(2); P=rnd.randrange(2); U=rnd.randrange(2); B=rnd.randrange(2); W=rnd.randrange(2) if P else 0; Lb=rnd.randrange(2)
        if I: off=(rnd.randrange(32)<<7)|(rnd.randrange(4)<<5)|rnd.randrange(15)
        else: off=rnd.randrange(0x40)
        return (cc<<28)|0x04000000|(I<<25)|(P<<24)|(U<<23)|(B<<22)|(W<<21)|(Lb<<20)|(rnd.randrange(16 if Lb else 15)<<16)|(rnd.randrange(15)<<12)|off
    if k==7:  # halfword
        P=rnd.randrange(2); U=rnd.randrange(2); I=rnd.randrange(2); W=rnd.randrange(2) if P else 0; Lb=rnd.randrange(2); sh=rnd.randrange(1,4)
        if not Lb: sh=1
        if I: off=(rnd.randrange(4)<<8)|0x90|(sh<<5)|rnd.randrange(16)
        else: off=0x90|(sh<<5)|rnd.randrange(15)
        return (cc<<28)|(P<<24)|(U<<23)|(I<<22)|(W<<21)|(Lb<<20)|(rnd.randrange(15)<<16)|(rnd.randrange(15)<<12)|off
    if k==8:  # ldm/stm
        P=rnd.randrange(2); U=rnd.randrange(2); W=rnd.randrange(2); Lb=rnd.randrange(2)
        return (cc<<28)|0x08000000|(P<<24)|(U<<23)|(W<<21)|(Lb<<20)|(rnd.randrange(15)<<16)|(rnd.randrange(1,0x8000))
    if k==9:  # b/bl
        return (cc<<28)|0x0a000000|(rnd.randrange(2)<<24)|rnd.randrange(0x1000000)
    if k==10: # swp
        return (cc<<28)|0x01000090|(rnd.randrange(2)<<22)|(rnd.randrange(15)<<16)|(rnd.randrange(15)<<12)|rnd.randrange(15)
    return (cc<<28)|0x012fff10|rnd.randrange(15)   # bx
mism=0; ran=0; skipped=0; stats={}
for t in range(N):
    th=(mode=='thumb') or (mode=='both' and rnd.random()<0.5)
    ins=thumb_ins() if th else arm_ins()
    if (not th) and ((ins>>25)&7)==0 and (ins&0x10) and not (ins&0x80) and (((ins>>16)&15)==15 or (ins&15)==15 or ((ins>>8)&15)==15): continue   # register-specified shift with pc operand: ARM ARM says pc+12, QEMU differs
    if (not th) and ((ins>>25)&7)==2 and ((ins>>16)&15)==15: continue   # self-referencing literal load in the code window (unicorn quirk)
    regs=[rnd_reg() for _ in range(15)]
    flags=rnd.getrandbits(4)<<28
    mem=bytes(rnd.getrandbits(8) for _ in range(256))
    base=AR+0x1000 if False else AR
    # memory image: random bytes around every arena pointer is expensive; fill a random page set
    arena=bytearray(rnd.getrandbits(8) for _ in range(0x1000))
    # place the code
    pcv=CD+0x100
    code=struct.pack('<H',ins) if th else struct.pack('<I',ins)
    if th and (ins>>11)==0x1e:   # bl pair: append a second half
        code+=struct.pack('<H',0xf800|rnd.randrange(0x800))
    # unicorn side
    u.mem_write(CD,b'\0'*0x1000); u.mem_write(pcv,code)
    for k in range(0,AS,0x1000): pass
    u.mem_write(AR,bytes(AS))
    # random contents near each pointer register
    pts=[v for v in regs if AR<=v<AR+AS]
    img=bytearray(AS)
    for v in pts:
        o=(v-AR)&~3
        for q in range(max(0,o-0x80),min(AS,o+0x80)): img[q]=rnd.getrandbits(8)
    u.mem_write(AR,bytes(img))
    cpsr=flags|(0x20 if th else 0)|0x10
    u.reg_write(UC_ARM_REG_CPSR,cpsr)
    for i in range(13): u.reg_write(UC_ARM_REG_R0+i,regs[i])
    u.reg_write(UC_ARM_REG_SP,regs[13]); u.reg_write(UC_ARM_REG_LR,regs[14])
    # interp side
    s=IS(); 
    for i in range(15): s.r[i]=regs[i]
    s.f=flags; s.pc=pcv|(1 if th else 0)
    a=L.t_arena(); ctypes.memmove(a,bytes(img),AS); c=L.t_code(); ctypes.memmove(c,bytes(0x1000),0x1000); ctypes.memmove(c+0x100,code,len(code))
    L.t_unal()
    rc=L.t_step(ctypes.byref(s))
    nsteps=2 if (th and (ins>>11)==0x1e) else 1
    if nsteps==2: rc=L.t_step(ctypes.byref(s)) or rc
    if L.t_unal(): skipped+=1; continue
    try:
        u.emu_start(pcv|(1 if th else 0),pcv+len(code),count=1)     # a Thumb bl pair is one 32-bit instruction for QEMU/unicorn (count=2 ran an extra instruction at the target)
    except UcError as e:
        skipped+=1; continue
    if rc==1: skipped+=1; continue
    if rc==2: skipped+=1; continue
    ran+=1
    ur=[u.reg_read(r) for r in RK]; ucp=u.reg_read(UC_ARM_REG_CPSR); upc=u.reg_read(UC_ARM_REG_PC)
    if (upc&~0xfff)==CD and (upc&0xfff)<0x20 or (ucp&0x1f)!=(0x10|0 if False else ucp&0x1f) : pass
    if (upc&~0xfff)==CD and (upc&0xfff)<0x40: uc_exc=globals().get('uc_exc',0)+1; globals()['uc_exc']=uc_exc; continue     # unicorn took an exception vector (abort on a pc-relative / unmapped access, or an instruction it treats as undefined): not a semantic comparison
    isr=[s.r[i] for i in range(15)]
    um=bytes(u.mem_read(AR,AS)); im=ctypes.string_at(a,AS)
    bad=[]
    # unicorn reports pc after the instruction; compare when it is a real transfer
    if ur[:13]+ur[13:15]!=isr[:15]: bad.append('regs')
    if (ucp&0xf0000000)!=s.f: bad.append('flags')
    if um!=im: bad.append('mem')
    # next pc: unicorn stops at the end address for sequential flow
    ipc=s.pc&~1 if th else s.pc
    if s.ev in(3,1) or True:
        exp=upc&~1 if (ucp&0x20) else upc
        if (s.pc&1)!=(1 if (ucp&0x20) else 0) and s.ev==3: bad.append('state')
        elif exp!=(s.pc&~1): bad.append('pc')
    if bad==['mem']:
        # known ARM7TDMI vs QEMU difference: STM with the base register in the list and not first stores the NEW base on ARM7TDMI
        if (th and (ins>>11)==0x18) or ((not th) and (ins>>25)&7==4 and not (ins>>20)&1 and (ins>>21)&1): bad=[]; stm_skip=globals().get('stm_skip',0)+1; globals()['stm_skip']=stm_skip
    if bad==['pc'] and (not th) and (((ins>>25)&7) in (2,3) and ((ins>>16)&15)==15): bad=[]; globals()['pcq']=globals().get('pcq',0)+1     # unicorn leaves pc at pc+8 after a load/store whose base is the pc (registers, flags, memory agree)
    if bad==['state'] and th and (ins&0xff00)==0xbd00: bad=[]; globals()['popq']=globals().get('popq',0)+1     # Thumb pop {..,pc} of an even value: ARM7TDMI (ARMv4T) stays in Thumb state, unicorn (ARMv7) interworks
    if bad:
        mism+=1
        if mism<=40: print('MISMATCH',bad,'thumb' if th else 'arm','ins %08x'%ins,'regs',[hex(x) for x in regs],'flags %x'%flags,'\n   uc',[hex(x) for x in ur],hex(ucp),hex(upc),'\n   ip',[hex(x) for x in isr],hex(s.f),hex(s.pc))
    k=('thumb' if th else 'arm', ins>>11 if th else (ins>>25)&7); stats[k]=stats.get(k,0)+1
print('thumb pop {pc} with an even value (ARMv4T: no interworking; unicorn is ARMv7):',globals().get('popq',0)); print('unicorn pc+8 quirk after pc-based ldr/str (all else equal):',globals().get('pcq',0)); print('uc exception-vector cases (not compared):',globals().get('uc_exc',0)); print('ran',ran,'skipped',skipped,'mismatches',mism,'stm-base-in-list (known QEMU difference, skipped)',globals().get('stm_skip',0))
