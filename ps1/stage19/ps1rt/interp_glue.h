/* stage 7: interpreter fallback glue (included by rt.c after h_miss).  Guest code that is in neither the hot blob nor the cold overlay table is interpreted
   (interp.c) instead of halting at RT_MISS.  Nothing here contains Payback code or data. */
#include "interp.h"
extern const u32 HASH_HOST, HASH_NSLOTS, ARMTAB_N; extern const u32 ARMTAB[];
extern const unsigned STUBTAB_N, STUBTAB[];
extern void interp_enter(void); extern void ip_call_asm(IS*,u32); extern void ip_ret(void);
void h_vbl(void);
u32 interp_target, ip_depth;
#if defined(MERGED) && !defined(IP_MAXD)
#define IP_MAXD 8        /* Milestone B: the ROM page table (4096 pages) ends at 0x8002e000; 8 stacks of 1 KiB below 0x80030000 */
#endif
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
#ifdef MERGED
#define IP_STACKS ((u8*)0x8002c000)      /* Milestone B: ip_stacks stays 0x8002c000, but the 4096-entry ROM page table ends at 0x8002e000: the 8 depths x 1 KiB are 0x8002e000..0x80030000 */
#define IP_CANARY_AT ((volatile u32*)0x8002e000u)    /* lowest word of the stack area, just above rom_pg[0xfff]: a stack that reaches it would write the page table next */
#define IP_CANARY 0x5afe57acu
#else
#define IP_STACKS ((u8*)0x8002c000)      /* 16 depths x 1 KiB, between the ROM page table (0x8002a000..0x8002c000) and the blob (0x80030000) */
#endif
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
/* stage 20: instruction and data accesses of the interpreter to IWRAM, EWRAM, the PAL/OAM/VRAM shadows and ROM pages that are in RAM (resident or cached) are
   plain loads and stores; everything else (IO, guest VRAM/PAL/OAM addresses, a ROM page that must be fetched, the save chip) still goes through h_memrd/h_memwr.
   The callers align ea to the access size. */
static inline const u8 *ip_direct(u32 ea){
  u32 r=ea>>24;
  if(r==3) return IW+(ea&0x7fffu);
  if(r==2) return EW+(ea&0x3ffffu);
  if(ea-0x80180000u<0x19000u || ea-0x801b0000u<0x48000u) return (const u8*)ea;    /* host PAL, OAM, VRAM (to its end), EWRAM, IWRAM */
  return 0;
}
u32 ip_rd(u32 ea,u32 size){
  const u8*p; u32 r=ea>>24;
  #ifdef MERGED
  if(r==8||r==9){ u32 pg=(ea>>12)&0x1fffu; p=pg<ROM_NPG?rom_pg[pg]:0; if(p) p+=ea&4095; }      /* past the image: h_memrd -> rom_page stops */
#else
  if(r==8||r==9){ u32 pg=(ea>>12)&2047; p=rom_pg[pg]; if(p) p+=ea&4095; }
#endif
  else p=ip_direct(ea);
  if(p) return size==4?*(const u32*)p:size==2?(u32)*(const u16*)p:(u32)*p;
  return h_memrd(ea,size==1?0:size==2?2:4);
}
void ip_wr(u32 ea,u32 size,u32 val){
  u8*p=(u8*)ip_direct(ea);
  if(p){ if(size==4) *(u32*)p=val; else if(size==2) *(u16*)p=(u16)val; else *p=(u8)val; return; }
  h_memwr(ea,size,val);
}
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
/* intro fix (rc7): the boot intro and View intro reach the title menu, and a key skips them as on the GBA.
   (1) Code overlays.  Payback keeps two code overlays at IWRAM 0x03000d84 (guest loader 0x08077508(n), called only by the intro: loader(1) at 0x080235a6,
       loader(0) at 0x08023616): overlay 0, the game's IWRAM code (0x5f40 bytes: what the boot image holds and what the translation was made from), and
       overlay 1, the film player (0x2df0 bytes: init 0x03000d84, player 0x03001660), which the intro loads before its films and replaces by overlay 0
       afterwards.  While overlay 1 is resident the translated overlay-0 code and the hash entries of its addresses are stale: a call into
       [OV_BASE, OV_BASE+OV1_SIZE) must not run them (rc5 ran the overlay-0 translation at 0x03001660 in place of the player).  Overlay 0 is resident iff the
       first two IWRAM words of the overlay area are those of the boot image (ov_w, taken before the guest runs).  The translated code reaches IWRAM code
       only through the hash table (RT_BX and the other indirect branches): when loader(1) runs (ip_hle: its caller is interpreted), the hash slots whose
       keys lie in the overlay area are pointed at rt_ovmiss (interp_asm.s: RT_MISS with the key), so nothing is added to the RT_BX path.  loader(0) is
       translated, so the slots are put back lazily (ov_sync) by the first miss or interpreter lookup that finds overlay 0 resident again.  h_miss and
       ip_lookup keep the ov_stale check.
   (2) prune.STUBS id 3 (0x080234be 'gfx_effect') is not a function: it is the join point of the ZOO-logo wait inside the boot function (fall-through from
       0x080234bc after A/B, far-jump 'bl' at 0x08025554 on the timeout).  The stub returned into the DSI fade (timeout) or back into the wait (A/B), so the intro
       looped on the ZOO logo for ever.  The guest code from there (0x080234be..0x0802360c, 0x08025538) was never translated (discovery stops at a stub): the
       stub site is patched at boot into "li $25,0x080234be; j RT_MISS" so that h_miss hands it to the interpreter, and ip_stub_lookup no longer maps it.
       The real fix is a translation-input change (drop 0x080234be from prune.py STUBS and translate the intro); until then intro_fix_init checks every word
       it relies on and stops with an error screen if one differs (and tools/check_intro_site.py makes the same check on the ELF at build time).
   (3) The films cannot be shown (overlay 1 is not translated, the PPU has no mode 3, interpreted the player runs ~50x slower than the GBA: measured).
       A call of the player while overlay 1 is resident ends the film the way a key press ends it: VRAM picture cleared, DISPCNT = 0x404 (as the player
       leaves it), r0 = 1 ('skipped').  The intro then takes the game's own skip path (0x0802360e): the waits after the films go and film 2 is never called.
       The init call (0x03000d84: the player's decoder tables) returns 0 at once.  Every other stale overlay address is interpreted.
   (4) Two guest routines that the untranslated intro code calls are performed natively by the interpreter (ip_hle): the raw timer 0x08077c70 (r0 =
       TM3CNT_L<<16 | TM2CNT_L, the time base of the intro's waits) and the overlay loader 0x08077508 (byte-copy loops of 0x2df0..0x20980 bytes, ~6 s
       interpreted).  The raw timer adds no time of its own: with the films skipped the interpreter performs 3 such calls per intro in all (ip_hles,
       the loader's included), and a build that advanced 2 scanlines per raw-timer call reached the title on the same frame as one that does not
       (SwanStation, 1632 vs 1630 frames after the language press). */
#define OV_BASE    0x03000d84u
#define OV1_SIZE   0x2df0u
#define OV1_INIT   0x03000d84u
#define FILM_PLAY  0x03001660u
#define INTRO_JOIN 0x080234beu
#define RAW_TIMER  0x08077c70u
#define OV_LOADER  0x08077508u
#define RT_BLOB    0x80030000u   /* ps1.ld: the translated blob; RT_SWI at +0, RT_MISS at +8 (t2m.py runtime()); rt_ovmiss (interp_asm.s) jumps to RT_BLOB+8 */
#define OV_NSL 8                 /* hash slots with an overlay-area key (2 in this translation: 0x03001448, 0x03001660) */
static u32 ov_w[2], ov_nsl, ov_patched, *ov_sl[OV_NSL], ov_sh[OV_NSL];
u32 film_ends, ov_stale_n, ip_hles;
static int ov_res(void){ const volatile u32*w=(const volatile u32*)(IW+(OV_BASE&0x7fffu)); return w[0]==ov_w[0]&&w[1]==ov_w[1]; }
static int ov_stale(u32 a){ return ((a&~1u)-OV_BASE)<OV1_SIZE && !ov_res(); }
extern void rt_ovmiss(void); extern void rt_ret0(void); extern void rt_ret1(void); extern const unsigned RT_STUB_HOST;
static void ov_slots(u32 on){ for(u32 k=0;k<ov_nsl;k++) ov_sl[k][1]=on?(u32)rt_ovmiss:ov_sh[k]; ov_patched=on; if(on) dsp_mclear(); }   /* data words read by rt_hash: no I-cache flush; rc8: D1 may hold overlay-0 targets (h_miss) */
static inline void ov_sync(void){ if(ov_patched && ov_res()) ov_slots(0); }
static u32 film_skip(void){ film_ends++; for(u32 k=0;k<0x12c00u;k+=4) *(volatile u32*)(VRAM+k)=0; h_memwr(0x04000000u,2,0x404); dbg("FILM not shown, ended as skipped\n"); return 1; }
/* film_miss: h_miss for an address of the overlay area while overlay 1 is resident */
static u32 film_miss(u32 addr){
  u32 a=addr&~1u; ov_stale_n++;
#ifndef FILMTEST
  if(a==OV1_INIT) return (u32)rt_ret0;
  if(a==FILM_PLAY){ film_skip(); return (u32)rt_ret1; }
#endif
  interp_target=a; return (u32)interp_enter;
}
/* boot: the words the intro fix relies on, or an error screen (never a silent fallback) */
#ifdef MERGED
static __attribute__((noinline)) void iwk_init(void);
#endif
static RTCOLD void intro_fix_init(void){
  const volatile u32*w=(const volatile u32*)(IW+(OV_BASE&0x7fffu)); ov_w[0]=w[0]; ov_w[1]=w[1];
  const volatile u32*miss=(const volatile u32*)(RT_BLOB+8);
  u32 id=0, nid=0; for(u32 k=0;k<STUBTAB_N;k++) if(STUBTAB[2*k]==INTRO_JOIN){ id=STUBTAB[2*k+1]; nid++; }
  u32 n=0; volatile u32*site=0; u32 jst=0x08000000u|((RT_STUB_HOST>>2)&0x03ffffffu);
  for(volatile u32*q=(volatile u32*)(RT_BLOB+0x400);q+2<(volatile u32*)HASH_HOST;q++) if(q[0]==(0x34190000u|id) && q[1]==jst && q[2]==0){ site=q; n++; }
  u32 nk=0; const u32*t=(const u32*)HASH_HOST; for(u32 i=0;i<HASH_NSLOTS;i++) if(t[2*i]-OV_BASE<OV1_SIZE){ if(nk<OV_NSL){ ov_sl[nk]=(u32*)&t[2*i]; ov_sh[nk]=t[2*i+1]; } nk++; }
  /* rt_hash (RT_BX+8..) must compute key and slot as hot_lookup() does, and rt_found must jump to the slot's host word (what ov_slots rewrites) */
  static const u32 hw[][2]={{2,0x00190842u},{3,0x0001c040u},{4,0x000112c2u},{5,0x00220826u},{7,0x000108c0u},{10,0x00220821u},{11,0x8c220000u},{20,0x8c390004u},{22,0x03200008u}};
  const volatile u32*bx=(const volatile u32*)RT_BX_HOST; u32 hok=(bx[0]>>16)==0x0720u && bx[1]==0 && (bx[13]>>16)==0x1058u && bx[6]==(0x30210000u|((HASH_NSLOTS-1)&0xffffu))
    && bx[8]==(0x3c020000u|(HASH_HOST>>16)) && bx[9]==(0x34420000u|(HASH_HOST&0xffffu));
  for(u32 k=0;k<sizeof hw/sizeof hw[0];k++) if(bx[hw[k][0]]!=hw[k][1]) hok=0;
#ifdef MERGED
  /* Milestone B: the intro is translated (prune.py without id 3): no stub of the join point and no call site of it may exist */
  u32 bad=miss[0]!=0x0320c021u?1:nid!=0?2:n!=0?3:nk-1u>=OV_NSL?4:(ov_w[0]|ov_w[1])==0?5:!hok?6:0;
#else
  u32 bad=miss[0]!=0x0320c021u?1:nid!=1||id-1u>=0xffffu?2:n!=1?3:nk-1u>=OV_NSL?4:(ov_w[0]|ov_w[1])==0?5:!hok?6:0;
#endif
#ifdef TEST_INTRO_FIX_FAIL
  bad=TEST_INTRO_FIX_FAIL;          /* TEST-ONLY: take the error path, to show that a failed check is a visible stop */
#endif
  if(bad) fatal_screen("INTRO FIX: runtime words differ, check ",bad<<28|n<<16|nk<<8|nid);
  ov_nsl=nk;
#ifdef MERGED
  (void)site; (void)jst; dbg("INTRO FIX: intro translated, overlay hash slots "); dec(nk); dbg("\n"); iwk_init(); return;
#endif
  site[0]=0x3c190000u|(INTRO_JOIN>>16);                  /* lui $25,0x0802 */
  site[1]=0x08000000u|(((RT_BLOB+8)>>2)&0x03ffffffu);    /* j RT_MISS */
  site[2]=0x37390000u|(INTRO_JOIN&0xffffu);              /* ori $25,$25,0x34be (delay slot) */
  flush_icache();
  dbg("INTRO FIX: stub site "); hex((u32)site); dbg("overlay hash slots "); dec(nk); dbg("\n");
}
/* ip_hle: called by the interpreter for a branch/call target t (and at its entry): 1 if the guest routine at t was performed here (pc = lr) */
static void ov_copy(u32 src,u32 n,u8*dst){ while(n){ u32 off=src&0x01ffffffu, c=4096-(off&4095); if(c>n) c=n; const u8*p=rom_page(off>>12)+(off&4095); for(u32 k=0;k<c;k++) dst[k]=p[k]; src+=c; dst+=c; n-=c; } }
u32 ip_hle(IS*s,u32 t){
  u32 a=t&~1u;
  if(a==RAW_TIMER){
    u32 hi=ip_rd(0x0400010cu,2), lo=ip_rd(0x04000108u,2), r1=hi<<16, r0=r1+lo;
    s->r[0]=r0; s->r[1]=r1; s->r[2]=lo; s->r[3]=0x04000108u;
    s->f=(r0&IF_N)|(r0==0?IF_Z:0)|(r0<r1?IF_C:0)|((((r1^r0)&(lo^r0))>>31)?IF_V:0);   /* adds r0,r1,r2 */
  } else if(a==OV_LOADER){        /* 0x08077508(n): n==0 overlay 0 (ROM 0x087da83c..0x087e077c -> IWRAM 0x03000d84, 0x087e5254..0x087ffc8c -> 0x02001ce8), else overlay 1 */
    u32 n=s->r[0];
    if(n==0){ ov_copy(0x087da83cu,0x5f40u,IW+(OV_BASE&0x7fffu)); ov_copy(0x087e5254u,0x1aa38u,EW+0x1ce8u); }
    else    { ov_copy(0x087e077cu,0x2df0u,IW+(OV_BASE&0x7fffu)); ov_copy(0x087ffc8cu,0x20u,EW+0x1ce8u); }
    ov_slots(n!=0);
    s->r[0]=s->r[14]; s->r[1]=s->r[2]=s->r[3]=0;
  }
#ifndef FILMTEST          /* TEST-ONLY measurement: the film player and its init are interpreted (the PPU has no bitmap mode: the picture is wrong) */
  else if((a==FILM_PLAY||a==OV1_INIT) && ov_stale(a)){ ov_stale_n++; s->r[0]=a==FILM_PLAY?film_skip():0; }   /* the overlay-1 entry points, called from interpreted code */
#endif
  else return 0;
  ip_hles++; s->pc=s->r[14]; return 1;
}
#ifdef MERGED
/* Milestone B: prune id 3 (the join point) is gone and the ids have a gap: the thunk of id n is the (n-1)th */
u32 ip_stub_lookup(u32 t){ for(u32 k=0;k<STUBTAB_N;k++) if(STUBTAB[2*k]==t) return (u32)ip_sthunks+24*(STUBTAB[2*k+1]-1u); return 0; }
#else
u32 ip_stub_lookup(u32 t){ if(t==INTRO_JOIN) return 0; for(u32 k=0;k<STUBTAB_N;k++) if(STUBTAB[2*k]==t) return (u32)ip_sthunks+24*k; return 0; }
#endif       /* ip_sthunks: one RT_STUB thunk per stub id, in the runtime (the translated entry may sit in a cold group that is not loaded) */
#ifdef MERGED
/* Milestone B: Star-FlyBack copies its own ARM code over parts of Payback's IWRAM image (stuntfox merge.c hot_install) and patches single words of it
   (hot_words).  The hot hash and the cold table still hold Payback's translations at those addresses (SF's model_draw 0x03006930 is a hash key, five
   more keys lie inside SF's code), so a lookup by address alone would leave the interpreter for Payback's old code.  At boot (IWRAM = the image the
   translation was made from, boot.bin) every IWRAM key of both tables keeps the two halfwords at its address; ip_lookup answers 0 (interpret what is
   there now) for a key whose halfwords differ.  The overlay-1 area keeps its own test (ov_stale), which comes first.  Payback itself changes two
   keys at the title (0x03000d78 holds data, 0x03005a90 is an immediate it patches; rc10 shows the same words): an interpreted jump there now runs
   what IWRAM holds, as the GBA does.  Calls from translated code are not affected. */
#define IWK_MAX 96         /* 35 keys in B1 (hash and cold table); a fuller table stops at boot with an error screen */
static u16 iwk_o[IWK_MAX]; static u32 iwk_w[IWK_MAX]; u32 iwk_n, iwk_stale_n;
static u32 iwk_word(u32 o){ const volatile u16*p=(const volatile u16*)(IW+o); return p[0]|((u32)p[1]<<16); }
static void iwk_add(u32 g){
  if(g-0x03000000u>=0x7ffcu) return; u32 o=g&0x7ffeu, k=0;
  while(k<iwk_n&&iwk_o[k]<o) k++;
  if(k<iwk_n&&iwk_o[k]==o) return;
  if(iwk_n>=IWK_MAX) fatal_screen("IWRAM KEY TABLE FULL: ",iwk_n);
  for(u32 j=iwk_n;j>k;j--){ iwk_o[j]=iwk_o[j-1]; iwk_w[j]=iwk_w[j-1]; }
  iwk_o[k]=(u16)o; iwk_w[k]=iwk_word(o); iwk_n++;
}
static __attribute__((noinline)) void iwk_init(void){
  const u32*t=(const u32*)HASH_HOST; for(u32 i=0;i<HASH_NSLOTS;i++) if(t[2*i]) iwk_add(t[2*i]);
  const u32*ct=(const u32*)coldtab; for(u32 i=0;i<ct[0];i++) iwk_add(ct[1+4*i]);
  *IP_CANARY_AT=IP_CANARY;
  dbg("IWRAM keys "); dec(iwk_n); dbg("\n");
}
static int iwk_stale(u32 t){
  if(t-0x03000000u>=0x7ffcu) return 0; u32 o=t&0x7ffeu, lo=0, hi=iwk_n;
  while(lo<hi){ u32 m=(lo+hi)>>1; if(iwk_o[m]<o) lo=m+1; else if(iwk_o[m]>o) hi=m; else return iwk_word(o)!=iwk_w[m]; }
  return 0;
}
#endif
u32 ip_lookup(u32 t){
  ov_sync(); if(ov_stale(t)) return 0;
#ifdef MERGED
  if(iwk_stale(t)&&!ip_stub_lookup(t)){ iwk_stale_n++; return 0; }      /* (a prune stub keeps its thunk: never interpreted) */
#endif
  u32 h=hot_lookup(t); if(h) return h; h=ip_stub_lookup(t); if(h) return h; return cold_find(t); }
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
#ifdef MERGED
u32 ip_swi6;
#endif
void ip_swi(IS*s,u32 n){
  ip_swis++;
#ifdef MERGED
  /* Milestone B: an ARM-state swi carries its number in bits 16..23 (interp.c passes the 24-bit field).  Star-FlyBack's libgcc division
     (__aeabi_uidivmod, ARM) calls the BIOS Div (6) for two non-negative operands; translated Payback never does (t2m RT_SWI is a no-op). */
  if(n>0xffu) n=(n>>16)&0xffu;
  if(n==6){ s32 a=(s32)s->r[0], b=(s32)s->r[1]; if(b){ s32 q=a/b; s->r[0]=(u32)q; s->r[1]=(u32)(a-q*b); s->r[3]=(u32)(q<0?-q:q); } ip_swi6++; return; }
#endif
  if(n==5){ call_on_rtstack(h_vbl); u32 h=hot_lookup(0x100); if(h){ s->r[12]=(u32)ip_ret; ip_call_asm(s,h); } }
}
u32 interp_top(IS*g){
  if(ip_depth>=IP_MAXD) gpu_panic("INTERP depth overflow: ",ip_depth);
#ifdef MERGED
  if(*IP_CANARY_AT!=IP_CANARY) gpu_panic("INTERP stack reached the ROM page table: ",ip_depth);
#endif
  u32 t=g->pc&~1u; g->pc=t|(ip_arm_code(t)?0:1); ip_enters++; ip_hle(g,g->pc); if(ip_depth>ip_depth_max) ip_depth_max=ip_depth;
  { u32 k; for(k=0;k<ip_nseen;k++) if(ip_seen[k]==t) break; if(k==ip_nseen&&ip_nseen<64){ ip_seen[ip_nseen++]=t; dbg("INTERP guest "); hex(t); dbg("depth "); dec(ip_depth); dbg("\n"); } }
  u32 h=interp_run(g);
#ifdef MERGED
  if(*IP_CANARY_AT!=IP_CANARY) gpu_panic("INTERP stack reached the ROM page table: ",ip_depth);
#endif
#ifdef IP_NORM_ALL
  ip_norm(g);
#endif
  return h;
}
