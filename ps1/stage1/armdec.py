#!/usr/bin/env python3
"""Own ARM7TDMI decoder (Thumb-1 and ARM) into one small IR used by the translator. No capstone semantics are trusted."""
import struct
AND,EOR,SUB,RSB,ADD,ADC,SBC,RSC,TST,TEQ,CMP,CMN,ORR,MOV,BIC,MVN=range(16)
OPN=['and','eor','sub','rsb','add','adc','sbc','rsc','tst','teq','cmp','cmn','orr','mov','bic','mvn']
LSL,LSR,ASR,ROR,RRX=range(5)
CC=['eq','ne','cs','cc','mi','pl','vs','vc','hi','ls','ge','lt','gt','le','al','nv']
class I:
    __slots__=('addr','size','mode','cond','op','opc','s','rd','rn','rm','rs','rdhi','imm','sh','shamt','shreg','ld','sz','sg','pre','up','wb','regs','target','kind','raw','acc','uns','psr')
    def __init__(self,**k):
        for a in I.__slots__: setattr(self,a,None)
        self.cond=14
        for a,v in k.items(): setattr(self,a,v)
    def __repr__(self):
        d={a:getattr(self,a) for a in I.__slots__ if getattr(self,a) is not None and a not in('raw',)}
        return 'I(%s)'%', '.join('%s=%s'%(k,hex(v) if isinstance(v,int) and k in('addr','target') else v) for k,v in d.items())
def sx(v,b): return v-(1<<b) if v&(1<<(b-1)) else v
def dp(addr,size,mode,opc,s,rd,rn,imm=None,rm=None,sh=LSL,shamt=0,shreg=None,cond=14,raw=0):
    return I(addr=addr,size=size,mode=mode,op='dp',opc=opc,s=s,rd=rd,rn=rn,imm=imm,rm=rm,sh=sh,shamt=shamt,shreg=shreg,cond=cond,raw=raw)
def mem(addr,size,mode,ld,sz,sg,rd,rn,imm=None,rm=None,sh=LSL,shamt=0,pre=1,up=1,wb=0,cond=14,raw=0):
    return I(addr=addr,size=size,mode=mode,op='mem',ld=ld,sz=sz,sg=sg,rd=rd,rn=rn,imm=imm,rm=rm,sh=sh,shamt=shamt,pre=pre,up=up,wb=wb,cond=cond,raw=raw)
def undef(addr,size,mode,raw): return I(addr=addr,size=size,mode=mode,op='undef',raw=raw)

def thumb(h,addr,h2=None):
    """decode one Thumb instruction at addr from halfword h (h2 = next halfword for bl). returns I"""
    M='T'; r=h
    top=h>>13
    if top==0:
        op=(h>>11)&3
        if op<3:
            sa=(h>>6)&31
            if sa==0 and op in(1,2): sa=32
            return dp(addr,2,M,MOV,1,h&7,0,rm=(h>>3)&7,sh=op,shamt=sa,raw=h)
        rd=h&7; rn=(h>>3)&7; o=(h>>6)&7
        opc=SUB if (h>>9)&1 else ADD
        if (h>>10)&1: return dp(addr,2,M,opc,1,rd,rn,imm=o,raw=h)
        return dp(addr,2,M,opc,1,rd,rn,rm=o,raw=h)
    if top==1:
        op=(h>>11)&3; rd=(h>>8)&7; imm=h&0xff
        opc=[MOV,CMP,ADD,SUB][op]
        return dp(addr,2,M,opc,1,rd if op!=1 else 0,rd,imm=imm,raw=h)
    if top==2:
        if (h>>10)==0x10:  # 010000 ALU
            op=(h>>6)&15; rd=h&7; rs=(h>>3)&7
            if op==0: return dp(addr,2,M,AND,1,rd,rd,rm=rs,raw=h)
            if op==1: return dp(addr,2,M,EOR,1,rd,rd,rm=rs,raw=h)
            if op in(2,3,4,7):  # lsl lsr asr ror by register
                return dp(addr,2,M,MOV,1,rd,0,rm=rd,sh={2:LSL,3:LSR,4:ASR,7:ROR}[op],shreg=rs,raw=h)
            if op==5: return dp(addr,2,M,ADC,1,rd,rd,rm=rs,raw=h)
            if op==6: return dp(addr,2,M,SBC,1,rd,rd,rm=rs,raw=h)
            if op==8: return dp(addr,2,M,TST,1,0,rd,rm=rs,raw=h)
            if op==9: return dp(addr,2,M,RSB,1,rd,rs,imm=0,raw=h)
            if op==10: return dp(addr,2,M,CMP,1,0,rd,rm=rs,raw=h)
            if op==11: return dp(addr,2,M,CMN,1,0,rd,rm=rs,raw=h)
            if op==12: return dp(addr,2,M,ORR,1,rd,rd,rm=rs,raw=h)
            if op==13: return I(addr=addr,size=2,mode=M,op='mul',rd=rd,rm=rd,rs=rs,rn=None,s=1,raw=h)
            if op==14: return dp(addr,2,M,BIC,1,rd,rd,rm=rs,raw=h)
            if op==15: return dp(addr,2,M,MVN,1,rd,0,rm=rs,raw=h)
        if (h>>10)==0x11:  # hi reg ops
            op=(h>>8)&3; rd=(h&7)|((h>>4)&8); rm=(h>>3)&15
            if op==3:
                return I(addr=addr,size=2,mode=M,op='bx',rm=rm,raw=h)   # (bit7 set = blx on v5; undefined here)
            if op==0: return dp(addr,2,M,ADD,0,rd,rd,rm=rm,raw=h)
            if op==1: return dp(addr,2,M,CMP,1,0,rd,rm=rm,raw=h)
            return dp(addr,2,M,MOV,0,rd,0,rm=rm,raw=h)
        if (h>>11)==9:  # ldr pc-rel
            return mem(addr,2,M,1,4,0,(h>>8)&7,15,imm=(h&0xff)*4,raw=h)
        # 0101: reg offset
        rd=h&7; rb=(h>>3)&7; ro=(h>>6)&7; o=(h>>9)&7
        t={0:(0,4,0),1:(0,2,0),2:(0,1,0),3:(1,1,1),4:(1,4,0),5:(1,2,0),6:(1,1,0),7:(1,2,1)}[o]
        return mem(addr,2,M,t[0],t[1],t[2],rd,rb,rm=ro,raw=h)
    if top==3:
        B=(h>>12)&1; L=(h>>11)&1; imm=(h>>6)&31; rb=(h>>3)&7; rd=h&7
        return mem(addr,2,M,L,1 if B else 4,0,rd,rb,imm=imm if B else imm*4,raw=h)
    if top==4:
        if not (h>>12)&1:  # 1000 L: strh/ldrh imm
            return mem(addr,2,M,(h>>11)&1,2,0,h&7,(h>>3)&7,imm=((h>>6)&31)*2,raw=h)
        return mem(addr,2,M,(h>>11)&1,4,0,(h>>8)&7,13,imm=(h&0xff)*4,raw=h)
    if top==5:
        if not (h>>12)&1:   # 1010 add rd,pc/sp
            return dp(addr,2,M,ADD,0,(h>>8)&7,13 if (h>>11)&1 else 15,imm=(h&0xff)*4,raw=h)
        if (h>>8)==0xb0:
            v=(h&0x7f)*4
            return dp(addr,2,M,SUB if (h>>7)&1 else ADD,0,13,13,imm=v,raw=h)
        if ((h>>9)&3)==2:  # push/pop 1011 L10 R
            L=(h>>11)&1; R=(h>>8)&1; rl=h&0xff
            if L: 
                if R: rl|=1<<15
                return I(addr=addr,size=2,mode=M,op='ldm',ld=1,rn=13,regs=rl,pre=0,up=1,wb=1,raw=h)
            if R: rl|=1<<14
            return I(addr=addr,size=2,mode=M,op='ldm',ld=0,rn=13,regs=rl,pre=1,up=0,wb=1,raw=h)
        return undef(addr,2,M,h)
    if top==6:
        if not (h>>12)&1:   # 1100 L rb rlist
            return I(addr=addr,size=2,mode=M,op='ldm',ld=(h>>11)&1,rn=(h>>8)&7,regs=h&0xff,pre=0,up=1,wb=1,raw=h)
        cond=(h>>8)&15
        if cond==15: return I(addr=addr,size=2,mode=M,op='swi',imm=h&0xff,raw=h)
        if cond==14: return undef(addr,2,M,h)
        return I(addr=addr,size=2,mode=M,op='b',cond=cond,target=(addr+4+sx(h&0xff,8)*2)&0xffffffff,raw=h)
    if top==7:
        hh=(h>>11)&3
        if hh==0: return I(addr=addr,size=2,mode=M,op='b',target=(addr+4+sx(h&0x7ff,11)*2)&0xffffffff,raw=h)
        if hh==2:   # bl prefix
            if h2 is not None and (h2>>11)==0x1f:
                off=(sx(h&0x7ff,11)<<12)+((h2&0x7ff)<<1)
                return I(addr=addr,size=4,mode=M,op='bl',target=(addr+4+off)&0xffffffff,raw=h|(h2<<16))
            return undef(addr,2,M,h)
        return undef(addr,2,M,h)
    return undef(addr,2,M,h)

def armimm(v):
    rot=((v>>8)&15)*2; imm=v&0xff
    val=((imm>>rot)|(imm<<(32-rot)))&0xffffffff if rot else imm
    return val,rot
def arm(w,addr):
    M='A'; cond=w>>28; raw=w
    if cond==15: return undef(addr,4,M,w)
    t=(w>>25)&7
    if t==0 or t==1:
        if t==0 and (w&0x0ffffff0)==0x012fff10: return I(addr=addr,size=4,mode=M,op='bx',rm=w&15,cond=cond,raw=w)
        if t==0 and (w&0x90)==0x90:
            if (w&0x60)==0:   # multiply / swp
                if (w&0x0fc000f0)==0x00000090:
                    return I(addr=addr,size=4,mode=M,op='mul',rd=(w>>16)&15,rm=w&15,rs=(w>>8)&15,rn=((w>>12)&15) if (w>>21)&1 else None,s=(w>>20)&1,cond=cond,raw=w)
                if (w&0x0f8000f0)==0x00800090:
                    return I(addr=addr,size=4,mode=M,op='mull',rdhi=(w>>16)&15,rd=(w>>12)&15,rm=w&15,rs=(w>>8)&15,uns=not (w>>22)&1,acc=(w>>21)&1,s=(w>>20)&1,cond=cond,raw=w)
                if (w&0x0fb00ff0)==0x01000090:
                    return I(addr=addr,size=4,mode=M,op='swp',sz=1 if (w>>22)&1 else 4,rd=(w>>12)&15,rn=(w>>16)&15,rm=w&15,cond=cond,raw=w)
                return undef(addr,4,M,w)
            # halfword / signed transfers
            L=(w>>20)&1; sh=(w>>5)&3; P=(w>>24)&1; U=(w>>23)&1; W=(w>>21)&1; I_=(w>>22)&1
            if sh==0: return undef(addr,4,M,w)
            if not L and sh!=1: return undef(addr,4,M,w)
            sz,sg={1:(2,0),2:(1,1),3:(2,1)}[sh]
            if I_: return mem(addr,4,M,L,sz,sg,(w>>12)&15,(w>>16)&15,imm=((w>>4)&0xf0)|(w&15),pre=P,up=U,wb=W if P else 0,cond=cond,raw=w)
            return mem(addr,4,M,L,sz,sg,(w>>12)&15,(w>>16)&15,rm=w&15,pre=P,up=U,wb=W if P else 0,cond=cond,raw=w)
        opc=(w>>21)&15; S=(w>>20)&1
        if 8<=opc<=11 and not S:   # mrs/msr
            if t==0 and (w&0x0fbf0fff)==0x010f0000: return I(addr=addr,size=4,mode=M,op='mrs',rd=(w>>12)&15,psr=(w>>22)&1,cond=cond,raw=w)
            if (w&0x0fb0fff0)==0x0120f000 or (w&0x0fb0f000)==0x0320f000 or (w&0x0db0f000)==0x0120f000:
                if t==1:
                    v,rot=armimm(w&0xfff)
                    return I(addr=addr,size=4,mode=M,op='msr',psr=(w>>22)&1,imm=v,regs=(w>>16)&15,cond=cond,raw=w)
                return I(addr=addr,size=4,mode=M,op='msr',psr=(w>>22)&1,rm=w&15,regs=(w>>16)&15,cond=cond,raw=w)
            return undef(addr,4,M,w)
        rd=(w>>12)&15; rn=(w>>16)&15
        if t==1:
            v,rot=armimm(w&0xfff)
            i=dp(addr,4,M,opc,S,rd,rn,imm=v,cond=cond,raw=w); i.shamt=rot; return i
        rm=w&15; st=(w>>5)&3
        if (w>>4)&1:
            return dp(addr,4,M,opc,S,rd,rn,rm=rm,sh=st,shreg=(w>>8)&15,cond=cond,raw=w)
        amt=(w>>7)&31
        if st==LSR and amt==0: amt=32
        elif st==ASR and amt==0: amt=32
        elif st==ROR and amt==0: st=RRX; amt=1
        return dp(addr,4,M,opc,S,rd,rn,rm=rm,sh=st,shamt=amt,cond=cond,raw=w)
    if t==2 or t==3:
        if t==3 and (w&0x10): return undef(addr,4,M,w)
        P=(w>>24)&1; U=(w>>23)&1; B=(w>>22)&1; W=(w>>21)&1; L=(w>>20)&1
        if t==2: return mem(addr,4,M,L,1 if B else 4,0,(w>>12)&15,(w>>16)&15,imm=w&0xfff,pre=P,up=U,wb=W if P else (1 if False else 0),cond=cond,raw=w)
        amt=(w>>7)&31; st=(w>>5)&3
        if st==LSR and amt==0: amt=32
        elif st==ASR and amt==0: amt=32
        elif st==ROR and amt==0: st=RRX; amt=1
        return mem(addr,4,M,L,1 if B else 4,0,(w>>12)&15,(w>>16)&15,rm=w&15,sh=st,shamt=amt,pre=P,up=U,wb=W if P else 0,cond=cond,raw=w)
    if t==4:
        P=(w>>24)&1; U=(w>>23)&1; S=(w>>22)&1; W=(w>>21)&1; L=(w>>20)&1
        return I(addr=addr,size=4,mode=M,op='ldm',ld=L,rn=(w>>16)&15,regs=w&0xffff,pre=P,up=U,wb=W,s=S,cond=cond,raw=w)
    if t==5:
        off=sx(w&0xffffff,24)*4
        return I(addr=addr,size=4,mode=M,op='bl' if (w>>24)&1 else 'b',cond=cond,target=(addr+8+off)&0xffffffff,raw=w)
    if t==7 and (w>>24)&15==15: return I(addr=addr,size=4,mode=M,op='swi',imm=w&0xffffff,cond=cond,raw=w)
    return undef(addr,4,M,w)

# --- flag semantics of an IR instruction: bits N=1 Z=2 C=4 V=8
NF,ZF,CF,VF=1,2,4,8
CONDUSE=[ZF,ZF,CF,CF,NF,NF,VF,VF,CF|ZF,CF|ZF,NF|VF,NF|VF,ZF|NF|VF,ZF|NF|VF,0,0]
ARITH=(SUB,RSB,ADD,ADC,SBC,RSC,CMP,CMN)
def flag_use_def(i):
    """returns (use_mask, def_mask, partial_def_mask): bits read (incl. condition), bits fully defined unconditionally, bits defined but kept when condition false"""
    use=CONDUSE[i.cond] if i.cond<14 else 0
    d=0
    if i.op=='dp':
        if i.opc in (ADC,SBC,RSC): use|=CF
        if i.sh==RRX and i.rm is not None: use|=CF
        if i.s:
            if i.opc in ARITH: d=NF|ZF|CF|VF
            else:
                d=NF|ZF
                if i.rm is None and i.imm is not None:
                    if i.mode=='A' and i.shamt: d|=CF   # rotated immediate: C = bit31
                elif i.shreg is not None: use|=CF; d|=CF   # C kept when amount==0: reads and writes the explicit C
                elif i.sh==RRX or i.shamt>0 or i.sh in(LSR,ASR) : d|=CF
    elif i.op in('mul','mull'):
        if i.s: d=NF|ZF
    elif i.op=='mrs': use=NF|ZF|CF|VF|use
    elif i.op=='msr':
        if i.regs&8: d=NF|ZF|CF|VF
    elif i.op in('bl','swi'): d=0
    return use,d
def clobbers_flags(i): return i.op in('bl','swi')
