/* stage 7: interpreter fallback glue (included by rt.c after h_miss).  Guest code that is in neither the hot blob nor the cold overlay table is interpreted
   (interp.c) instead of halting at RT_MISS.  Nothing here contains Payback code or data. */
#include "interp.h"
extern const u32 HASH_HOST, HASH_NSLOTS, ARMTAB_N; extern const u32 ARMTAB[];
extern const unsigned STUBTAB_N, STUBTAB[];
extern void interp_enter(void); extern void ip_call_asm(IS*,u32); extern void ip_ret(void);
void h_vbl(void);
u32 interp_target, ip_depth;
#ifndef IP_MAXD
#define IP_MAXD 16
#endif
#ifdef IP_EXT
extern u32 ip_slab[][32]; extern u32 ip_cs_stk[];     /* TEST-ONLY (sim): placed by the linker command line (--defsym) in free RAM */
#else
u32 ip_slab[IP_MAXD][32];
u32 ip_cs_stk[IP_MAXD*12];
#endif
u32 ip_cs_sp=(u32)ip_cs_stk;
#define IP_STACKS ((u8*)0x8002c000)      /* 16 depths x 1 KiB, between the ROM page table (0x8002a000..0x8002c000) and the blob (0x80030000) */
#define IP_RECN 64      /* must match the .rept in interp_asm.s */
u32 ip_rec[IP_RECN][2], ip_rec_n, ip_rec_hi; extern void ip_stubs(void); extern const unsigned RT_BX_HOST;
u32 ip_res_push(u32 S,u32 L){
  while(ip_rec_n && ip_rec[ip_rec_n-1][0]<S) ip_rec_n--;                                   /* activations whose frame is gone */
  for(int k=(int)ip_rec_n-1;k>=0 && ip_rec[k][0]>=S;k--) if(ip_rec[k][0]==S && ip_rec[k][1]==L){ ip_rec_n=(u32)k; break; }     /* same call site, same sp: the earlier call was abandoned (long jump) */
  if(ip_rec_n>=IP_RECN) gpu_panic("INTERP resume stack overflow: ",ip_rec_n);
  u32 k=ip_rec_n++; ip_rec[k][0]=S; ip_rec[k][1]=L; if(ip_rec_n>ip_rec_hi) ip_rec_hi=ip_rec_n;
  return (u32)ip_stubs+12*k;
}
u32 ip_enters, ip_undef, ip_swis, ip_depth_max; static u32 ip_seen[64], ip_nseen;
u32 ip_rd(u32 ea,u32 size){ return h_memrd(ea,size==1?0:size==2?2:4); }
void ip_wr(u32 ea,u32 size,u32 val){ h_memwr(ea,size,val); }
u32 ip_map(u32 v){
  if(v-0x02000000u<=0x40000u) return (u32)EW+(v-0x02000000u);
  if(v-0x03000000u<0x01000000u) return (u32)IW+(v&0x7fffu);
  if(v-0x04000000u<=0x400u) return 0x8017f000u+(v-0x04000000u);
  if(v-0x05000000u<=0x400u) return (u32)PAL+(v-0x05000000u);
  if(v-0x06000000u<=0x18000u) return (u32)VRAM+(v-0x06000000u);
  if(v-0x07000000u<=0x400u) return (u32)OAM+(v-0x07000000u);
  return v;
}
u32 ip_is_host_iw(u32 a){ return (a-(u32)IW<0x8000u)?0x03000000u+(a-(u32)IW):0; }
u32 ip_arm_code(u32 a){
  if((a>>24)!=8) return (a>>24)==3||(a>>24)==2;
  u32 lo=0,hi=ARMTAB_N; while(lo<hi){ u32 m=(lo+hi)>>1; if(a<ARMTAB[2*m]) hi=m; else if(a>=ARMTAB[2*m+1]) lo=m+1; else return 1; }
  return 0;
}
static u32 hot_lookup(u32 g){
  u32 x=g>>1; u32 h=(x^(x>>11))&(HASH_NSLOTS-1); const u32*t=(const u32*)HASH_HOST+2*h;
  for(;;t+=2){ u32 k=t[0]; if(k==g) return t[1]; if(k==0) return 0; }
}
/* the pruned renderer entry points (prune.STUBS) are not translated: a call to one of them goes to its RT_STUB thunk; the guest code behind them (software renderer, runtime-patched IWRAM
   spans) must never be interpreted */
extern void ip_sthunks(void);
u32 ip_stub_lookup(u32 t){ for(u32 k=0;k<STUBTAB_N;k++) if(STUBTAB[2*k]==t) return (u32)ip_sthunks+24*k; return 0; }       /* ip_sthunks: one RT_STUB thunk per stub id, in the runtime (the translated entry may sit in a cold group that is not loaded) */
u32 ip_lookup(u32 t){ u32 h=hot_lookup(t); if(h) return h; h=ip_stub_lookup(t); if(h) return h; return cold_find(t); }
#ifdef IP_NORM_ALL
static void ip_norm(IS*s){ for(int i=0;i<13;i++) s->r[i]=ip_map(s->r[i]); }
#endif
void ip_call(IS*s,u32 host){
#ifdef IP_NORM_ALL
  ip_norm(s);
#endif
  ip_call_asm(s,host); }
static void call_on_rtstack(void (*f)(void)){
  u32 keep; __asm__ volatile("move %0,$29\n li $29,0x801fff90\n jalr %1\n nop\n move $29,%0":"=&r"(keep):"r"(f):"$1","$2","$3","$4","$5","$6","$7","$8","$9","$10","$11","$12","$13","$14","$15","$24","$25","$31","memory");
}
void ip_swi(IS*s,u32 n){
  ip_swis++;
  if(n==5){ call_on_rtstack(h_vbl); u32 h=hot_lookup(0x100); if(h){ s->r[12]=(u32)ip_ret; ip_call_asm(s,h); } }
}
u32 interp_top(IS*g){
  if(ip_depth>=IP_MAXD) gpu_panic("INTERP depth overflow: ",ip_depth);
  u32 t=g->pc&~1u; g->pc=t|(ip_arm_code(t)?0:1); ip_enters++; if(ip_depth>ip_depth_max) ip_depth_max=ip_depth;
  { u32 k; for(k=0;k<ip_nseen;k++) if(ip_seen[k]==t) break; if(k==ip_nseen&&ip_nseen<64){ ip_seen[ip_nseen++]=t; dbg("INTERP guest "); hex(t); dbg("depth "); dec(ip_depth); dbg("\n"); } }
  u32 h=interp_run(g);
#ifdef IP_NORM_ALL
  ip_norm(g);
#endif
  return h;
}
