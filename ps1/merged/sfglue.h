/* Milestone B stage B2 (PS1, -DMERGED_NATIVE): the runtime side of Stunt Fox compiled natively (ps1/merged/README.md).  Included by rt.c after
   interp_glue.h.  Code only: no Payback code or data.

   Guest -> native.  Payback reaches a Stunt Fox function through a call that the merged ROM's patches point into the mod's span (0x081aa8e0..):
   translated code takes RT_MISS -> h_miss -> not in the cold table -> interp_enter; interpreted code (Stunt Fox's own assembly hooks, which
   stay interpreted from the ROM: keyhook.s, guard.s, cart32.s, radiodec.s) takes its branch.  Both end in ip_hle(), which asks sf_hle() first:
   a guest address that sfnat_gen.c lists (a Stunt Fox C function compiled natively) is called natively with r0-r3 and the first twelve stack
   words as arguments, on the native stack, and r0/r1 take the result (AAPCS and MIPS O32 pass ints, pointers, structs and 64-bit values in the
   same words and pairs).
   Native -> guest.  A call of a Payback function (a constant or a pointer, irmem.py -> __sf_fnmap) or of Stunt Fox's assembly (guest stubs in
   sfnat_gen.c) is sf_guest_call(): the translated entry if there is one (ip_lookup loads its cold group), else the interpreter, with the guest
   stack the hook was entered with.  It may come back into native code (a Payback function calling a hook): the native stack then continues
   below the frame that made the call.
   Memory: sf_rd / sf_wr are the slow paths of sfmem.c (guest addresses: ROM pages, IO, guest-form RAM); host addresses never reach them. */
#ifndef SF_NAT_STACK_TOP
#error "MERGED_NATIVE needs the native stack (sfnat_place.h from ps1/merged/place.py)"
#endif
typedef unsigned long long u64;
extern const u32 sfnat_nent; extern const u32 sfnat_ent[][2];
/* SF_NARG argument words cross each way: AAPCS and O32 both pass a struct by value (V3: three words) in the argument words, so a call such
   as city_scan(V3, V3, len, lim, range, *ray, *cand, *at) takes twelve; the words past the real ones are whatever the caller's stack holds. */
#define SF_NARG 16
extern u64 sf_call_on(u32 sp, u32 fn, const u32 *a);         /* below: switch to sp, fn(a[0..15]), switch back */
__asm__(".set push\n.set noreorder\n.set noat\n.text\n.globl sf_call_on\nsf_call_on:\n"
        "  addiu $4,$4,-96\n  sw $29,88($4)\n  sw $31,92($4)\n  move $29,$4\n  move $25,$5\n"
        "  lw $8,16($6)\n  lw $9,20($6)\n  lw $10,24($6)\n  lw $11,28($6)\n  lw $12,32($6)\n  lw $13,36($6)\n  lw $14,40($6)\n  lw $15,44($6)\n  sw $8,16($29)\n  sw $9,20($29)\n  sw $10,24($29)\n  sw $11,28($29)\n  sw $12,32($29)\n  sw $13,36($29)\n  sw $14,40($29)\n  sw $15,44($29)\n"
        "  lw $8,48($6)\n  lw $9,52($6)\n  lw $10,56($6)\n  lw $11,60($6)\n  sw $8,48($29)\n  sw $9,52($29)\n  sw $10,56($29)\n  sw $11,60($29)\n"
        "  lw $4,0($6)\n  lw $5,4($6)\n  lw $7,12($6)\n  lw $6,8($6)\n  jalr $25\n  nop\n"
        "  lw $31,92($29)\n  lw $29,88($29)\n  jr $31\n  nop\n.set pop\n");
u32 sf_gtarget, sf_gsp, sf_ns_cur, sf_depth, sf_calls_n, sf_gcalls_n, sf_gcalls_ip, sf_depth_max;
u32 sf_last_fn, sf_last_t, sf_last_lr, sf_last_r0, sf_prof_lines, sf_prof_f[16], sf_prof_l[16], sf_prof_n[16];

u16 sf_pgm[1024];        /* diagnostic: native reads of ROM pages that were not mapped, by page (first 4 MiB) */
u32 sf_rd(u32 a, u32 kind){
  if((a>>24)==8){ u32 pg=(a>>12)&0xfffu; const u8*p=rom_pg[pg];
    if(!p&&pg<1024&&sf_pgm[pg]<0xffff) sf_pgm[pg]++;
    if(p){ p+=a&4095u; if(kind==4){ if(!(a&3u)) return *(const u32*)p; } else if(kind==2){ if(!(a&1u)) return *(const u16*)p; } else return *p; } }
  return h_memrd(a,kind);
}
/* A native store below 0x02000000 is a store into the GBA's BIOS area, which the GBA's bus ignores: ignored here as there, and counted with the
   outermost native function (diagnostic).  With eight argument words city_scan's result pointers came in as 0 and it stored to 4. */
u32 sf_bios_wr_n, sf_bios_wr_fn, sf_bios_wr_a;
void sf_wr(u32 a, u32 size, u32 v){
  if(a<0x02000000u){ sf_bios_wr_n++; sf_bios_wr_fn=sf_last_fn; sf_bios_wr_a=a; return; }
  h_memwr(a,size,v);
}
void *sf_resolve(u32 a, u32 *avail){
  if((a>>24)==8||(a>>24)==2||(a>>24)==3||(a>>24)==5||(a>>24)==6||(a>>24)==7) return resolve(a,avail);
  return 0;
}
void *sf_native_of(u32 a){
  u32 g=a&~1u, lo=0, hi=sfnat_nent;
  while(lo<hi){ u32 m=(lo+hi)>>1; u32 v=sfnat_ent[m][0]; if(v==g) return (void*)sfnat_ent[m][1]; if(v<g) lo=m+1; else hi=m; }
  return 0;
}
static inline u32 sf_cur_sp(void){ u32 s; __asm__ volatile("move %0,$29":"=r"(s)); return s; }
/* a native call with guest arguments a[0..SF_NARG-1], from wherever the runtime is (interpreter stack, RT_CC stack, the native stack itself) */
static u64 sf_native_call(u32 fn, const u32 *a, u32 gsp){
  u32 keep_gsp=sf_gsp, sp=sf_cur_sp(), nsp;
  if(sp-SF_NAT_STACK_LO<SF_NAT_STACK_TOP-SF_NAT_STACK_LO) nsp=sp-64;      /* already on the native stack (an interpreted guest call from native code) */
  else nsp=sf_depth?sf_ns_cur:SF_NAT_STACK_TOP;
  if(nsp-SF_NAT_STACK_LO<0x400u||nsp>SF_NAT_STACK_TOP) fatal_screen("NATIVE STACK: ",nsp);
  sf_gsp=gsp; sf_depth++; if(sf_depth>sf_depth_max) sf_depth_max=sf_depth; sf_calls_n++; sf_last_fn=fn;
  u32 t0=sf_depth==1?(*(volatile u32*)0x1F801110)&0xffffu:0;
  u64 r=sf_call_on(nsp&~7u,fn,a);
  if(sf_depth==1){ u32 dl=((*(volatile u32*)0x1F801110)-t0)&0xffffu; sf_prof_lines+=dl; u32 i=0;      /* TEST/diagnostic: hblank lines in native calls from the guest, by function */
    for(;i<16&&sf_prof_f[i]&&sf_prof_f[i]!=fn;i++){}
    if(i<16){ sf_prof_f[i]=fn; sf_prof_l[i]+=dl; sf_prof_n[i]++; } }
  sf_depth--; sf_gsp=keep_gsp;
  return r;
}
/* __builtin_return_address(0) in native Stunt Fox (natbuild.py): the guest's lr of the entry being run */
void *__sf_guest_lr(void){ return (void*)sf_last_lr; }
/* ip_hle's first question: is t a Stunt Fox function compiled natively?  then run it and return to the guest lr */
extern const u32 sfnat_niw; extern const u32 sfnat_iw[][2];
static int sf_hle(IS*s,u32 t){
  void*f=sf_native_of(t);
  if(!f&&(t>>24)==3&&s->r[14]-0x081b0000u<0x00100000u){      /* Stunt Fox's IWRAM code, called by Stunt Fox (interpreted from the ROM) */
    u32 g=t&~1u; for(u32 i=0;i<sfnat_niw;i++) if(sfnat_iw[i][0]==g){ f=(void*)sfnat_iw[i][1]; break; } }
  if(!f) return 0;
  sf_last_t=t; sf_last_lr=s->r[14]; sf_last_r0=s->r[0];
  u32 a[SF_NARG], sp=s->r[13];
  for(int i=0;i<4;i++) a[i]=s->r[i];
  for(int i=0;i<SF_NARG-4;i++) a[4+i]=ip_rd(sp+4*i,4);
  u64 r=sf_native_call((u32)f,a,sp);
  s->r[0]=(u32)r; s->r[1]=(u32)(r>>32); s->r[2]=s->r[3]=0; s->r[12]=0;
  s->pc=s->r[14];
  return 1;
}
/* native -> guest: t is the guest entry (bit 0: Thumb), a[0..SF_NARG-1] the arguments */
u64 sf_guest_call(u32 t, const u32 *a){
  IS s; for(int i=0;i<16;i++) s.r[i]=0; s.f=0; s.ev=0;
  for(int i=0;i<4;i++) s.r[i]=a[i];
  u32 gsp=(sf_gsp-64u)&~7u;
  for(int i=0;i<SF_NARG-4;i++) ip_wr(gsp+4*i,4,a[4+i]);
  s.r[13]=gsp;
  u32 keep=sf_ns_cur; sf_ns_cur=sf_cur_sp()-256u; sf_gcalls_n++;
  u32 h=ip_lookup(t&~1u);
  if(!h){ sf_gcalls_ip++; interp_target=t&~1u; h=(u32)interp_enter; }     /* not translated: through interp_enter, as RT_MISS does (it returns to lr) */
  ip_call(&s,h);
  sf_ns_cur=keep;
  return (u64)s.r[0]|(u64)s.r[1]<<32;
}
/* a call through __sf_fnmap to a guest address: the arguments are this function's (O32: a0-a3, then the caller's stack words) */
u64 sf_gthunk(u32 a0, u32 a1, u32 a2, u32 a3, u32 a4, u32 a5, u32 a6, u32 a7, u32 a8, u32 a9, u32 a10, u32 a11, u32 a12, u32 a13, u32 a14, u32 a15){
  u32 t=sf_gtarget; u32 a[SF_NARG]={a0, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, a12, a13, a14, a15};
  return sf_guest_call(t,a);
}
