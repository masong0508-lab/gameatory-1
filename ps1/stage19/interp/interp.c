#include "interp.h"
u32 ip_stat_steps, ip_stat_calls, ip_stat_undef;
#define SIGN8(x)  ((u32)(s32)(s8)(x))
#define SIGN16(x) ((u32)(s32)(s16)(x))
static inline u32 ror32(u32 v,u32 n){ n&=31; return n?((v>>n)|(v<<(32-n))):v; }
/* ---------------------------------------------------------------- shifter */
static u32 sh_imm(u32 type,u32 v,u32 amt,u32 *c){          /* ARM immediate-amount shift semantics (amount 0 is special for LSR/ASR/ROR) */
  switch(type){
  case 0: if(amt==0) return v; *c=(v>>(32-amt))&1; return v<<amt;
  case 1: if(amt==0){ *c=v>>31; return 0; } *c=(v>>(amt-1))&1; return v>>amt;
  case 2: if(amt==0){ *c=v>>31; return (u32)((s32)v>>31); } *c=(v>>(amt-1))&1; return (u32)((s32)v>>amt);
  default: if(amt==0){ u32 r=(v>>1)|(*c<<31); *c=v&1; return r; } *c=(v>>(amt-1))&1; return ror32(v,amt);
  }
}
static u32 sh_reg(u32 type,u32 v,u32 amt,u32 *c){          /* register-amount shift: amt = low byte of the register */
  amt&=0xff; if(amt==0) return v;
  switch(type){
  case 0: if(amt<32){ *c=(v>>(32-amt))&1; return v<<amt; } if(amt==32){ *c=v&1; return 0; } *c=0; return 0;
  case 1: if(amt<32){ *c=(v>>(amt-1))&1; return v>>amt; } if(amt==32){ *c=v>>31; return 0; } *c=0; return 0;
  case 2: if(amt<32){ *c=(v>>(amt-1))&1; return (u32)((s32)v>>amt); } *c=v>>31; return (u32)((s32)v>>31);
  default: amt&=31; if(amt==0){ *c=v>>31; return v; } *c=(v>>(amt-1))&1; return ror32(v,amt);
  }
}
/* ---------------------------------------------------------------- ALU */
static void setnz(IS*s,u32 r){ s->f=(s->f&~(IF_N|IF_Z))|(r&IF_N)|(r==0?IF_Z:0); }
static u32 addc(IS*s,u32 a,u32 b,u32 cin,int sf){
  u32 t=a+b; u32 c=t<a; u32 r=t+cin; c|=r<t;
  if(sf){ u32 v=((a^r)&(b^r))>>31; s->f=(r&IF_N)|(r==0?IF_Z:0)|(c?IF_C:0)|(v?IF_V:0); }
  return r;
}
static u32 subc(IS*s,u32 a,u32 b,u32 cin,int sf){ return addc(s,a,~b,cin,sf); }
/* dp opcode 0..15 (AND EOR SUB RSB ADD ADC SBC RSC TST TEQ CMP CMN ORR MOV BIC MVN); shc = shifter carry for logical ops; returns result, *wr=1 if rd is written */
static u32 dp(IS*s,u32 op,u32 a,u32 b,u32 shc,int sf,int *wr){
  u32 r; *wr=1; u32 cin=(s->f&IF_C)?1:0;
  switch(op){
  case 0: r=a&b; goto lg; case 1: r=a^b; goto lg; case 12: r=a|b; goto lg; case 14: r=a&~b; goto lg; case 13: r=b; goto lg; case 15: r=~b; goto lg;
  case 8: r=a&b; *wr=0; goto lg; case 9: r=a^b; *wr=0; goto lg;
  case 2: return subc(s,a,b,1,sf); case 3: return subc(s,b,a,1,sf);
  case 4: return addc(s,a,b,0,sf); case 5: return addc(s,a,b,cin,sf);
  case 6: return subc(s,a,b,cin,sf); case 7: return subc(s,b,a,cin,sf);
  case 10: *wr=0; return subc(s,a,b,1,sf); default: *wr=0; return addc(s,a,b,0,sf);   /* 11 CMN */
  }
lg: if(sf){ setnz(s,r); s->f=(s->f&~IF_C)|(shc?IF_C:0); } return r;
}
/* 32x32 -> 64 multiply without 64-bit types: hi,lo */
static void umul64(u32 a,u32 b,u32 *hi,u32 *lo){
  u32 a0=a&0xffff,a1=a>>16,b0=b&0xffff,b1=b>>16;
  u32 p00=a0*b0,p01=a0*b1,p10=a1*b0,p11=a1*b1;
  u32 mid=(p00>>16)+(p01&0xffff)+(p10&0xffff);
  *lo=(p00&0xffff)|(mid<<16); *hi=p11+(p01>>16)+(p10>>16)+(mid>>16);
}
static void smul64(u32 a,u32 b,u32 *hi,u32 *lo){
  umul64(a,b,hi,lo);
  if((s32)a<0) *hi-=b; if((s32)b<0) *hi-=a;
}
static void add64(u32 *hi,u32 *lo,u32 h2,u32 l2){ u32 l=*lo+l2; *hi=*hi+h2+(l<*lo); *lo=l; }
/* ---------------------------------------------------------------- memory with ARM7TDMI alignment rules */
#ifdef IP_TRACK_UNAL
unsigned int ip_unal;
#define UNAL(ea,m) do{ if((ea)&(m)) ip_unal++; }while(0)
#else
#define UNAL(ea,m) do{}while(0)
#endif
static u32 ld32(u32 ea){ UNAL(ea,3); u32 v=ip_rd(ea&~3u,4); return ror32(v,8*(ea&3)); }
static u32 ld16(u32 ea){ UNAL(ea,1); u32 v=ip_rd(ea&~1u,2); return (ea&1)?ror32(v,8):v; }
static u32 ld16s(u32 ea){ UNAL(ea,1); if(ea&1) return SIGN8(ip_rd(ea,1)); return SIGN16(ip_rd(ea,2)); }
static u32 ld8(u32 ea){ return ip_rd(ea,1); }
static void st32(u32 ea,u32 v){ UNAL(ea,3); ip_wr(ea&~3u,4,v); }
static void st16(u32 ea,u32 v){ UNAL(ea,1); ip_wr(ea&~1u,2,v&0xffff); }
static void st8(u32 ea,u32 v){ ip_wr(ea,1,v&0xff); }
static u32 cond_ok(u32 cc,u32 f){
  u32 n=(f>>31)&1,z=(f>>30)&1,c=(f>>29)&1,v=(f>>28)&1;
  switch(cc){
  case 0: return z; case 1: return !z; case 2: return c; case 3: return !c; case 4: return n; case 5: return !n; case 6: return v; case 7: return !v;
  case 8: return c&&!z; case 9: return !c||z; case 10: return n==v; case 11: return n!=v; case 12: return !z&&n==v; case 13: return z||n!=v; case 14: return 1; default: return 0;
  }
}
static u32 popcnt16(u32 x){ u32 n=0; while(x){ n+=x&1; x>>=1; } return n; }
/* a branch-exchange / pc write: set state from bit 0 */
static void bx(IS*s,u32 t){ s->pc=t; s->ev=3; }
/* Region-constant folding at the producer (stage 8).  The translator rewrites literals and mov/lsl-built bases of the GBA RAM/IO/PAL/VRAM/OAM windows to host addresses at translation time (const-prop);
   the interpreter does the same at the instruction that builds them: pc-relative literals (ip_map), ARM mov/mvn immediates, and lsl-by-immediate of a byte-sized value (movs r0,#3; lsls r0,r0,#24).
   Nothing folds a register on exit any more: stage 7 normalised r0-r12 on every exit, which rewrote data that merely looked like a region address (a bit accumulator 0x03404000 became 0x801f4000). */
/* stage 20: only a value that an immediate move put into the source register (and nothing has changed since) is folded by a shift: ip_km has a bit per register
   holding such an immediate, ip_kv its value (set from ip_knew after the step, cleared once the register holds another value).  A computed small value shifted left is data, not a region base:
   the IWRAM span renderer (0x03002e14) builds its row counter as height<<23, and height 4 gave 0x02000000 = EWRAM, folded to 0x801b0000; the 255-row loop that
   followed wrote past the VRAM shadow into the 3D renderer's code (vehicle crash).  The translator folds translation-time constants only. */
static u32 ip_km, ip_knew, ip_kv[15];
static inline u32 fold_lsl(u32 rs,u32 src,u32 amt,u32 res){ return (amt>=16 && src<=0xffu && ((ip_km>>rs)&1))?ip_map(res):res; }
/* ---------------------------------------------------------------- Thumb */
static u32 thumb_step(IS*s){
  u32 pc=s->pc&~1u; u32 hw=ip_rd(pc,2); u32 *r=s->r; s->pc=(pc+2)|1;
  u32 rd,rs,rn,imm,v,c,res; int wr;
  switch(hw>>11){
  case 0: case 1: case 2: {            /* shift by immediate */
    rd=hw&7; rs=(hw>>3)&7; imm=(hw>>6)&31; c=(s->f&IF_C)?1:0;
    r[rd]=sh_imm((hw>>11)&3,r[rs],imm,&c); if(!((hw>>11)&3)) r[rd]=fold_lsl(rs,r[rs],imm,r[rd]); setnz(s,r[rd]); s->f=(s->f&~IF_C)|(c?IF_C:0); return 0; }
  case 3: {                             /* add/sub reg or imm3 */
    rd=hw&7; rs=(hw>>3)&7; v=(hw&0x400)?((hw>>6)&7):r[(hw>>6)&7];
    r[rd]=(hw&0x200)?subc(s,r[rs],v,1,1):addc(s,r[rs],v,0,1); return 0; }
  case 4: case 5: case 6: case 7: {     /* mov/cmp/add/sub imm8 */
    rd=(hw>>8)&7; imm=hw&0xff;
    switch((hw>>11)&3){
    case 0: r[rd]=imm; setnz(s,imm); ip_knew|=1u<<rd; break;
    case 1: subc(s,r[rd],imm,1,1); break;
    case 2: r[rd]=addc(s,r[rd],imm,0,1); break;
    default: r[rd]=subc(s,r[rd],imm,1,1); }
    return 0; }
  case 8: {
    if((hw&0xfc00)==0x4000){            /* ALU */
      rd=hw&7; rs=(hw>>3)&7; u32 a=r[rd],b=r[rs]; c=(s->f&IF_C)?1:0; u32 op=(hw>>6)&15;
      switch(op){
      case 0: r[rd]=a&b; setnz(s,r[rd]); break;
      case 1: r[rd]=a^b; setnz(s,r[rd]); break;
      case 2: r[rd]=sh_reg(0,a,b,&c); setnz(s,r[rd]); s->f=(s->f&~IF_C)|(c?IF_C:0); break;
      case 3: r[rd]=sh_reg(1,a,b,&c); setnz(s,r[rd]); s->f=(s->f&~IF_C)|(c?IF_C:0); break;
      case 4: r[rd]=sh_reg(2,a,b,&c); setnz(s,r[rd]); s->f=(s->f&~IF_C)|(c?IF_C:0); break;
      case 5: r[rd]=addc(s,a,b,c,1); break;
      case 6: r[rd]=subc(s,a,b,c,1); break;
      case 7: r[rd]=sh_reg(3,a,b,&c); setnz(s,r[rd]); s->f=(s->f&~IF_C)|(c?IF_C:0); break;
      case 8: setnz(s,a&b); break;
      case 9: r[rd]=subc(s,0,b,1,1); break;
      case 10: subc(s,a,b,1,1); break;
      case 11: addc(s,a,b,0,1); break;
      case 12: r[rd]=a|b; setnz(s,r[rd]); break;
      case 13: r[rd]=a*b; setnz(s,r[rd]); break;
      case 14: r[rd]=a&~b; setnz(s,r[rd]); break;
      default: r[rd]=~b; setnz(s,r[rd]); break;
      }
      return 0; }
    /* hi register ops / bx: 010001 */
    {
      u32 op=(hw>>8)&3; rd=(hw&7)|((hw>>4)&8); rs=(hw>>3)&15;
      u32 b=(rs==15)?(pc+4):r[rs]; u32 a=(rd==15)?(pc+4):r[rd];
      if(op==0){ v=a+b; if(rd==15){ bx(s,v&~1u|1u); s->ev=3; } else r[rd]=v; return 0; }
      if(op==1){ subc(s,a,b,1,1); return 0; }
      if(op==2){ if(rd==15){ s->pc=(b&~1u)|1u; s->ev=3; } else r[rd]=b; return 0; }
      /* bx rs (BLX is ARMv5: treated as bx) */
      if(rs==15) b=(pc+4)&~3u; bx(s,b); return 0;
    } }
  case 9: {                              /* ldr rd,[pc,#imm] : literal pool (host-pointer form) */
    rd=(hw>>8)&7; u32 ea=((pc+4)&~3u)+((hw&0xff)<<2); r[rd]=ip_map(ld32(ea)); return 0; }
  case 10: case 11: {                    /* load/store register offset (format 7 and 8) */
    rd=hw&7; u32 ea=r[(hw>>3)&7]+r[(hw>>6)&7];
    switch((hw>>9)&7){
    case 0: st32(ea,r[rd]); break; case 1: st16(ea,r[rd]); break; case 2: st8(ea,r[rd]); break;
    case 3: r[rd]=SIGN8(ld8(ea)); break; case 4: r[rd]=ld32(ea); break; case 5: r[rd]=ld16(ea); break;
    case 6: r[rd]=ld8(ea); break; default: r[rd]=ld16s(ea); }
    return 0; }
  case 12: case 13: case 14: case 15: {  /* ldr/str/ldrb/strb imm5 */
    rd=hw&7; u32 b=r[(hw>>3)&7]; imm=(hw>>6)&31;
    if(!(hw&0x1000)){ u32 ea=b+(imm<<2); if(hw&0x800) r[rd]=ld32(ea); else st32(ea,r[rd]); }
    else { u32 ea=b+imm; if(hw&0x800) r[rd]=ld8(ea); else st8(ea,r[rd]); }
    return 0; }
  case 16: case 17: {                    /* ldrh/strh imm5 */
    rd=hw&7; u32 ea=r[(hw>>3)&7]+(((hw>>6)&31)<<1); if(hw&0x800) r[rd]=ld16(ea); else st16(ea,r[rd]); return 0; }
  case 18: case 19: {                    /* sp-relative ldr/str */
    rd=(hw>>8)&7; u32 ea=r[13]+((hw&0xff)<<2); if(hw&0x800) r[rd]=ld32(ea); else st32(ea,r[rd]); return 0; }
  case 20: case 21: {                    /* add rd,pc/sp,#imm */
    rd=(hw>>8)&7; imm=(hw&0xff)<<2; r[rd]=(hw&0x800)?r[13]+imm:ip_map(((pc+4)&~3u)+imm); return 0; }
  case 22: case 23: {                    /* misc: add sp, push/pop */
    if((hw&0xff00)==0xb000){ imm=(hw&0x7f)<<2; if(hw&0x80) r[13]-=imm; else r[13]+=imm; return 0; }
    if((hw&0x0600)==0x0400){             /* push / pop */
      u32 list=hw&0xff; int R=(hw>>8)&1;
      if(!(hw&0x800)){                   /* push */
        u32 n=popcnt16(list)+R; u32 a=r[13]-4*n; r[13]=a;
        for(u32 i=0;i<8;i++) if(list&(1u<<i)){ st32(a,r[i]); a+=4; }
        if(R) st32(a,r[14]);
      } else {                           /* pop */
        u32 a=r[13];
        for(u32 i=0;i<8;i++) if(list&(1u<<i)){ r[i]=ld32(a); a+=4; }
        if(R){ u32 t=ld32(a); a+=4; r[13]=a; bx(s,t|1u); s->pc=t|1u; return 0; }
        r[13]=a;
      }
      return 0; }
    return 1; }                          /* undefined */
  case 24: case 25: {                    /* stmia/ldmia rn!,{list} */
    rn=(hw>>8)&7; u32 list=hw&0xff; u32 a=r[rn];
    if(list==0){ if(hw&0x800){ u32 t=ld32(a); r[rn]=a+0x40; bx(s,t|1u); s->pc=t|1u; } else { st32(a,pc+6); r[rn]=a+0x40; } return 0; }
    if(hw&0x800){ for(u32 i=0;i<8;i++) if(list&(1u<<i)){ r[i]=ld32(a); a+=4; } if(!(list&(1u<<rn))) r[rn]=a; }
    else { u32 first=1,n=popcnt16(list),oldb=r[rn];
      for(u32 i=0;i<8;i++) if(list&(1u<<i)){ st32(a,(i==rn&&!first)?oldb+4*n:r[i]); a+=4; first=0; } r[rn]=a; }
    return 0; }
  case 26: case 27: {                    /* conditional branch / swi */
    u32 cc=(hw>>8)&15;
    if(cc==15){ r[15]=hw&0xff; s->ev=2; return 0; }
    if(cc==14) return 1;
    if(cond_ok(cc,s->f)){ s->pc=((pc+4)+(SIGN8(hw&0xff)<<1))|1u; s->ev=3; }
    return 0; }
  case 28: {                             /* b */
    u32 off=hw&0x7ff; if(off&0x400) off|=0xfffff800u; s->pc=((pc+4)+(off<<1))|1u; s->ev=3; return 0; }
  case 30: {                             /* bl, first half */
    u32 off=hw&0x7ff; if(off&0x400) off|=0xfffff800u; r[14]=(pc+4)+(off<<12); return 0; }
  case 31: {                             /* bl, second half */
    u32 t=r[14]+((hw&0x7ff)<<1); r[14]=(pc+2)|1u; s->pc=t|1u; s->ev=1; return 0; }
  default: return 1;
  }
}
/* ---------------------------------------------------------------- ARM */
static u32 arm_step(IS*s){
  u32 pc=s->pc&~3u; u32 in=ip_rd(pc,4); u32 *r=s->r; s->pc=pc+4;
  if(!cond_ok(in>>28,s->f)) return 0;
#define RV(i) ((i)==15?(pc+8):r[i])
  u32 c=(s->f&IF_C)?1:0;
  switch((in>>25)&7){
  case 0:
    if((in&0x0ffffff0)==0x012fff10){ u32 t=RV(in&15); bx(s,t); return 0; }                    /* BX */
    if((in&0x0fc000f0)==0x00000090){                                                          /* MUL/MLA */
      u32 rd=(in>>16)&15,rn=(in>>12)&15,rs=(in>>8)&15,rm=in&15; u32 v=r[rm]*r[rs]; if(in&0x200000) v+=r[rn];
      r[rd]=v; if(in&0x100000) setnz(s,v); return 0; }
    if((in&0x0f8000f0)==0x00800090){                                                          /* long multiply */
      u32 rdh=(in>>16)&15,rdl=(in>>12)&15,rs=(in>>8)&15,rm=in&15; u32 hi,lo;
      if(in&0x400000) smul64(r[rm],r[rs],&hi,&lo); else umul64(r[rm],r[rs],&hi,&lo);
      if(in&0x200000) add64(&hi,&lo,r[rdh],r[rdl]);
      r[rdl]=lo; r[rdh]=hi; if(in&0x100000){ s->f=(s->f&~(IF_N|IF_Z))|(hi&IF_N)|((hi|lo)==0?IF_Z:0); } return 0; }
    if((in&0x0fb00ff0)==0x01000090){                                                          /* SWP/SWPB */
      u32 rn=(in>>16)&15,rd=(in>>12)&15,rm=in&15; u32 a=r[rn],t;
      if(in&0x400000){ t=ld8(a); st8(a,r[rm]); } else { t=ld32(a); st32(a,r[rm]); }
      r[rd]=t; return 0; }
    if((in&0x90)==0x90 && (in&0x60)){                                                         /* halfword / signed transfer */
      u32 rn=(in>>16)&15,rd=(in>>12)&15; u32 off=(in&0x400000)?(((in>>4)&0xf0)|(in&15)):r[in&15];
      u32 base=RV(rn); u32 ea=(in&0x1000000)?((in&0x800000)?base+off:base-off):base; u32 nb=(in&0x800000)?base+off:base-off;
      if(in&0x100000){ u32 v; switch((in>>5)&3){ case 1: v=ld16(ea); break; case 2: v=SIGN8(ld8(ea)); break; default: v=ld16s(ea); }
        if(!(in&0x1000000)||(in&0x200000)) r[rn]=nb; r[rd]=v; if(rd==15){ s->pc=v&~3u; s->ev=3; } }
      else { u32 v=r[rd]; if(rd==15) v=pc+12; st16(ea,v); if(!(in&0x1000000)||(in&0x200000)) r[rn]=nb; }
      return 0; }
    if((in&0x0fbf0fff)==0x010f0000){ r[(in>>12)&15]=s->f; return 0; }                       /* MRS cpsr (flags only) */
    if((in&0x0fb0fff0)==0x0120f000){ /* MSR reg form */ u32 v=r[in&15]; if(in&0x80000) s->f=v&0xf0000000u; return 0; }
    /* fallthrough: data processing, register operand */
  case 1: {
    u32 op=(in>>21)&15,rn=(in>>16)&15,rd=(in>>12)&15; int sf=(in>>20)&1; u32 a,b,shc=c; int wr;
    if(((in>>25)&7)==1){
      if((op&12)==8&&!sf){ if(op==9||op==11){ if(in&0x80000) s->f=ror32(in&0xff,((in>>8)&15)*2)&0xf0000000u; } return 0; }   /* MSR immediate */
      b=ror32(in&0xff,((in>>8)&15)*2); if(((in>>8)&15)) shc=b>>31; a=RV(rn);
    } else {
      u32 rm=in&15,type=(in>>5)&3;
      if(in&0x10){ u32 amt=r[(in>>8)&15]; if((in>>8&15)==15) amt=pc+12; a=(rn==15)?pc+12:r[rn]; u32 v=(rm==15)?pc+12:r[rm]; b=sh_reg(type,v,amt,&shc); }
      else { a=RV(rn); b=sh_imm(type,RV(rm),(in>>7)&31,&shc); }
    }
    u32 res=dp(s,op,a,b,shc,sf,&wr);
    if(wr&&op==13){ if(((in>>25)&7)==1){ u32 m=ip_map(res); if(m==res) ip_knew|=1u<<rd; res=m; } else if(!(in&0x10)&&((in>>5)&3)==0) res=fold_lsl(in&15,RV(in&15),(in>>7)&31,res); }     /* mov rd,#imm / mov rd,rm,lsl #n of an immediate (ip_km) */
    if(wr){ if(rd==15){ s->pc=res&~3u; s->ev=3; } else r[rd]=res; }
    return 0; }
  case 2: case 3: {                      /* single data transfer */
    if((in&0x02000010)==0x02000010) return 1;                                                  /* undefined */
    u32 rn=(in>>16)&15,rd=(in>>12)&15,off; u32 base=(rn==15)?pc+8:r[rn];
    if(in&0x02000000){ u32 cc=c; off=sh_imm((in>>5)&3,RV(in&15),(in>>7)&31,&cc); } else off=in&0xfff;
    u32 up=in&0x800000,pre=in&0x1000000; u32 nb=up?base+off:base-off; u32 ea=pre?nb:base;
    if(in&0x100000){
      u32 v; if(in&0x400000) v=ld8(ea); else v=ld32(ea);
      if(rn==15&&!(in&0x2000000)&&pre&&!(in&0x200000)&&!(in&0x400000)) v=ip_map(v);           /* literal pool word */
      if(!pre||(in&0x200000)) r[rn]=nb;
      if(rd==15){ s->pc=v&~3u; s->ev=3; } else r[rd]=v; }
    else { u32 v=(rd==15)?pc+12:r[rd]; if(in&0x400000) st8(ea,v); else st32(ea,v); if(!pre||(in&0x200000)) r[rn]=nb; }
    return 0; }
  case 4: {                              /* block transfer */
    u32 rn=(in>>16)&15,list=in&0xffff; u32 base=r[rn]; u32 n=popcnt16(list); u32 up=in&0x800000,pre=in&0x1000000;
    u32 start,nb; if(up){ start=pre?base+4:base; nb=base+4*n; } else { start=pre?base-4*n:base-4*n+4; nb=base-4*n; }
    if(n==0){ nb=up?base+0x40:base-0x40; start=up?(pre?base+4:base):(pre?base-0x40:base-0x3c); if(in&0x100000){ u32 t=ld32(start); if(in&0x200000) r[rn]=nb; s->pc=t&~3u; s->ev=3; } else { st32(start,pc+12); if(in&0x200000) r[rn]=nb; } return 0; }
    u32 a=start;
    if(in&0x100000){
      for(u32 i=0;i<16;i++) if(list&(1u<<i)){ u32 v=ld32(a); a+=4; if(i==15){ s->pc=v&~3u; s->ev=3; } else r[i]=v; }
      if((in&0x200000)&&!(list&(1u<<rn))) r[rn]=nb;
    } else {
      u32 first=1;
      for(u32 i=0;i<16;i++) if(list&(1u<<i)){ u32 v=(i==15)?pc+12:r[i]; if(i==rn&&!first&&(in&0x200000)) v=nb; st32(a,v); a+=4; first=0; }
      if(in&0x200000) r[rn]=nb;
    }
    return 0; }
  case 5: {                              /* B / BL */
    u32 off=in&0xffffff; if(off&0x800000) off|=0xff000000u; u32 t=pc+8+(off<<2);
    if(in&0x1000000){ r[14]=pc+4; s->ev=1; } else s->ev=3;
    s->pc=t; return 0; }
  case 7:
    if(in&0x1000000){ r[15]=in&0xffffff; s->ev=2; return 0; }                                  /* SWI */
    return 1;
  default: return 1;                      /* coprocessor / undefined */
  }
}
u32 interp_step(IS*s){ s->ev=0; ip_stat_steps++; ip_knew=0;
  u32 u=(s->pc&1)?thumb_step(s):arm_step(s);
  if(ip_km|ip_knew){ u32 m=ip_km, i; for(i=0;m;i++,m>>=1) if((m&1)&&s->r[i]!=ip_kv[i]) ip_km&=~(1u<<i);
    m=ip_knew&0x7fffu; for(i=0;m;i++,m>>=1) if(m&1){ ip_kv[i]=s->r[i]; ip_km|=1u<<i; } }
  return u; }
/* ---------------------------------------------------------------- run loop */
static u32 interp_run1(IS*s);
/* A run nested in another one (SWI 5 in interpreted code -> h_vbl and the translated IRQ handler -> a miss into the interpreter) starts with no immediates
   and must not drop or replace the ones of the run it interrupts: the outer run's ip_km/ip_kv are kept across it. */
u32 interp_run(IS*s){
  u32 km=ip_km, kv[15], i; for(i=0;i<15;i++) kv[i]=ip_kv[i];
  ip_km=0; u32 h=interp_run1(s);
  ip_km=km; for(i=0;i<15;i++) ip_kv[i]=kv[i];
  return h;
}
static u32 interp_run1(IS*s){
  for(;;){
    u32 pc=s->pc;
    if(pc>=0x80000000u){ u32 g=ip_is_host_iw(pc&~1u); if(g) s->pc=g|(pc&1); else return pc&~3u; }     /* leaving to translated code (a host return address) */
    if(interp_step(s)) { ip_stat_undef++; continue; }       /* undefined instruction: counted and skipped */
    u32 ev=s->ev;
    if(ev==2){ ip_swi(s,s->r[15]); continue; }
    if(ev==0) continue;
    /* ev 1 = call (bl), 3 = jump.  Targets are guest addresses (bit0 = state) or host addresses. */
    u32 t=s->pc; u32 g=(t>=0x80000000u)?ip_is_host_iw(t&~1u):0; if(g){ t=g|(t&1); s->pc=t; }
    if(t>=0x80000000u) { if(ev==1) { /* call into host code through a host pointer: cannot happen for guest code, treat as jump */ } continue; }
    if(ip_hle(s,t)) continue;                    /* a routine the embedding performs natively (pc = lr) */
    u32 h=ip_lookup(t&~1u);
    if(!h) continue;                              /* not translated: interpret it */
    /* bl / b / bx / pop {pc} into translated code: hand over all registers and leave the interpreter (no nested call).  Thumb-1 code uses 'bl' as a long jump into the middle of a
       function (the callee then ends with pop {pc} and never comes back to lr), so a nested ip_call would strand the interpreter frame.  Translated code needs a host-form lr (bx lr is a
       plain jr), so a guest-form lr becomes the resume stub, which re-enters the interpreter at that guest address if the callee really returns through lr. */
    ip_stat_calls++;
    if(s->r[14]<0x80000000u) s->r[14]=ip_res_push(ip_map(s->r[13]),s->r[14]);
    return h;
  }
}
