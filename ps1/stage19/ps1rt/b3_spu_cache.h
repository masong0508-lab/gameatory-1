/* Optional exclusive read-only ROM backing store for the merged PS1
 * CDDA-only profile. DMA4 and SPU RAM [0x10000,0x70000) are reserved.
 * Never enable with sample playback, voice/reverb allocation, or CDSIM.
 * Data in this cache are disposable; CD remains authoritative.
 */
#ifndef B3_SPU_CACHE_H
#define B3_SPU_CACHE_H
#define B3_SPU_N 96u
#define B3_SPU_U16(a) (*(volatile u16*)(a))
#define B3_SPU_U32(a) (*(volatile u32*)(a))
#define B3_SPU_CTRL B3_SPU_U16(0x1f801daau)
#define B3_SPU_STAT B3_SPU_U16(0x1f801daeu)
#define B3_SPU_ADDR B3_SPU_U16(0x1f801da6u)
#define B3_SPU_D4_CH B3_SPU_U32(0x1f8010c8u)
#define B3_SPU_D4_MA B3_SPU_U32(0x1f8010c0u)
#define B3_SPU_D4_BC B3_SPU_U32(0x1f8010c4u)
#define B3_SPU_DPCR B3_SPU_U32(0x1f8010f0u)
#define B3_SPU_DICR B3_SPU_U32(0x1f8010f4u)
#define B3_SPU_DEV4 B3_SPU_U32(0x1f801014u)
static u16 b3_spu_owner[B3_SPU_N];
static u32 b3_spu_hash[B3_SPU_N];
static u32 b3_spu_hand;
u32 b3_spu_hits,b3_spu_writes,b3_spu_errors,b3_spu_disabled;

static u32 b3_spu_page_hash(const u8 *p){
  const u32 *w=(const u32*)p; u32 h=0x811c9dc5u;
  for(u32 j=0;j<1024;j++){ h=(h<<5)|(h>>27); h^=w[j]; }
  return h;
}
static int b3_spu_wait(u32 mask,u32 value){
  for(u32 i=0;i<500000u;i++) if((B3_SPU_STAT&mask)==value) return 1;
  return 0;
}
static __attribute__((noinline)) int b3_spu_copy(u32 slot,u8 *p,int write){
  if(b3_spu_disabled || slot>=B3_SPU_N || ((u32)p&3)) return 0;
  u16 orig=B3_SPU_CTRL;
  u32 dp=B3_SPU_DPCR,dev=B3_SPU_DEV4;
  /* Do not take over an active transfer. Disable rather than fighting it. */
  if((orig&0x30)||(B3_SPU_D4_CH&0x01000000u)){
    b3_spu_disabled=1; b3_spu_errors++; return 0;
  }
  u32 mode=write?0x20u:0x30u; int ok=0;
  B3_SPU_U16(0x1f801dacu)=4;
  B3_SPU_DEV4=0x220931e1u; B3_SPU_DPCR=dp|0x00080000u;
  B3_SPU_CTRL=orig&~0x30u;
  if(!b3_spu_wait(0x30u,0)) goto done;
  B3_SPU_ADDR=(0x10000u+slot*4096u)>>3;
  B3_SPU_CTRL=(orig&~0x30u)|mode;
  if(!b3_spu_wait(0x30u,mode)) goto done;
  B3_SPU_D4_MA=(u32)p&0x1fffffu; B3_SPU_D4_BC=0x00400010u;
  B3_SPU_D4_CH=write?0x01000201u:0x01000200u;
  for(u32 j=0;j<500000u;j++) if(!(B3_SPU_D4_CH&0x01000000u)){ok=1;break;}
  if(ok&&write&&!b3_spu_wait(0x400u,0)) ok=0;
done:
  if(B3_SPU_D4_CH&0x01000000u) B3_SPU_D4_CH=0;
  B3_SPU_CTRL=orig;
  if(!b3_spu_wait(0x30u,orig&0x30u)) ok=0;
  /* DICR status bits are write-one-to-clear; acknowledge channel 4 only. */
  if(B3_SPU_DICR&0x10000000u) B3_SPU_DICR=(B3_SPU_DICR&0x00ffffffu)|0x10000000u;
  B3_SPU_DPCR=dp; B3_SPU_DEV4=dev;
  if(!ok){b3_spu_errors++;b3_spu_disabled=1;}
  return ok;
}
/* Also used when pause/pair/resident reads put a page into the base pool:
 * any backing entry for a newly resident page is expendable. */
static void b3_spu_forget(u32 pg){
  if(b3_spu_disabled) return;
  for(u32 i=0;i<B3_SPU_N;i++) if(b3_spu_owner[i]==pg+1){b3_spu_owner[i]=0;return;}
}
static int b3_spu_restore(u32 pg,u8 *d){
  if(b3_spu_disabled) return 0;
  for(u32 i=0;i<B3_SPU_N;i++) if(b3_spu_owner[i]==pg+1){
    if(!b3_spu_copy(i,d,0)) return 0;
    if(b3_spu_page_hash(d)!=b3_spu_hash[i]){b3_spu_errors++;b3_spu_disabled=1;return 0;}
    b3_spu_owner[i]=0; b3_spu_hits++; return 1;
  }
  return 0;
}
/* Prefer empty slots, avoid duplicating an existing entry, and never
 * overwrite the page about to be restored when storing its L1 victim. */
static u32 b3_spu_pick(u32 pg,u32 wanted){
  if(pg==wanted) return B3_SPU_N;
  u32 i=B3_SPU_N;
  for(u32 j=0;j<B3_SPU_N;j++){
    if(b3_spu_owner[j]==pg+1) return B3_SPU_N;
    if(!b3_spu_owner[j]) i=j;
  }
  if(i==B3_SPU_N) for(u32 j=0;j<B3_SPU_N;j++){
    u32 k=b3_spu_hand; b3_spu_hand=k+1<B3_SPU_N?k+1:0;
    if(b3_spu_owner[k]!=wanted+1){i=k;break;}
  }
  return i;
}
static void b3_spu_store(u32 pg,u8 *d,u32 wanted){
  if(b3_spu_disabled) return;
  u32 i=b3_spu_pick(pg,wanted);
  if(i==B3_SPU_N) return;
  b3_spu_owner[i]=0;
  if(b3_spu_copy(i,d,1)){
    b3_spu_hash[i]=b3_spu_page_hash(d); b3_spu_owner[i]=pg+1; b3_spu_writes++;
  }
}
#endif
