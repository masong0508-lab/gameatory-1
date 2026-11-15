/* Star-FlyBack PS1 stage 2 runtime: hosts the translated Payback blob (t2m, cfg 'P' layout).
   - GBA memory windows in PS1 RAM, IO model (port of gbaenv.Io), DMA3 immediate + EEPROM, ROM page store, scripted pad
   - C helpers called from the blob through RT_CC: memrd / memwr / miss / vbl
   - GPU: one frame per guest frame: markers derived from Payback's draw list (what the pruned renderer would have drawn) + game-state counters */
typedef unsigned int u32; typedef int s32; typedef unsigned short u16; typedef short s16; typedef unsigned char u8; typedef signed char s8;
#define GP0 (*(volatile u32*)0x1F801810)
#define GP1 (*(volatile u32*)0x1F801814)
#define ISTAT (*(volatile u32*)0x1F801070)
#define RC1_VAL (*(volatile u32*)0x1F801110)
#define RC1_MODE (*(volatile u32*)0x1F801114)
#define HELP ((volatile u32*)0x80028000)
#define EW ((u8*)0x801b0000)
#define IW ((u8*)0x801f0000)
#define PAL ((u8*)0x80180000)
#define OAM ((u8*)0x80180400)
#define VRAM ((u8*)0x80181000)
#define DL ((volatile u32*)0x8017c000)
extern u8 __blob_start[];
extern u8 bootimg[], rompack[];
extern void *memset(void*,int,unsigned);
void *memset(void*d,int c,unsigned n){u8*p=d;while(n--)*p++=c;return d;}
void *memcpy(void*d,const void*s,unsigned n){u8*p=d;const u8*q=s;while(n--)*p++=*q++;return d;}

static void dbgc(char c){ register u32 a0 __asm__("$4")=c; register u32 t1 __asm__("$9")=0x3c;
  __asm__ volatile("li $8,0xA0\n jalr $8\n nop":"+r"(a0),"+r"(t1)::"$1","$2","$3","$5","$6","$7","$8","$10","$11","$12","$13","$14","$15","$24","$25","$31","memory"); }
static void dbg(const char*p){ while(*p) dbgc(*p++); }
static void hex(u32 v){ for(int i=0;i<8;i++){int d=(v>>(28-4*i))&15; dbgc(d<10?48+d:87+d);} dbgc(' '); }
static void dec(u32 v){ char b[12]; int n=0; if(!v) b[n++]='0'; while(v){b[n++]='0'+v%10; v/=10;} while(n) dbgc(b[--n]); dbgc(' '); }

/* ---------------------------------------------------------------- ROM page store (resident pages shipped in the EXE) */
static u32 rp_n; static const u32 *rp_idx; static const u8 *rp_data; static u32 rom_miss_count, rom_miss_last, cd_sectors, cd_time_rc;
static const u8 *rom_pg[2048];
/* ---------------------------------------------------------------- CD-ROM (polling driver, no IRQ): sector reads of 2048 bytes
   ROM data pages (4 KiB = 2 sectors) are fetched on demand from ROM.BIN on the disc into a FIFO-replaced page cache. */
#define CD0 (*(volatile u8*)0x1F801800)
#define CD1 (*(volatile u8*)0x1F801801)
#define CD2 (*(volatile u8*)0x1F801802)
#define CD3 (*(volatile u8*)0x1F801803)
#define IMASK (*(volatile u32*)0x1F801074)
extern const u32 CD_ROM_LBA, CD_COLD_LBA, CD_COLD_PAGES, CD_SNAP_LBA, CD_SNAP_N, CD_SNAPST_LBA;
#ifndef PCACHE_ADDR
#define PCACHE_ADDR 0x80138000
#endif
#define PCACHE ((u8*)PCACHE_ADDR)
#ifndef NSLOT
#define NSLOT 64
#endif
static u32 slot_owner[NSLOT], slot_next, cd_ready;
static void cd_ack(void){ CD0=1; CD3=0x1f; }
static u32 cd_dbg;
static u32 cd_wait(void){ for(u32 n=0;n<3000000;n++){ CD0=1; u32 f=CD3&7; if(f) return f; } if(cd_dbg<20){ cd_dbg++; dbg("CD timeout\n"); } return 0; }
static void cd_cmd(u8 c,const u8*p,int n){ for(u32 w=0;(CD0&0x80);w++) if(w>2000000){ dbg("CD busy cmd "); dec(c); dbg("\n"); break; } CD0=0; for(int i=0;i<n;i++) CD2=p[i]; CD1=c; }
static u8 bcd(u32 v){ return (v/10)*16+v%10; }
#ifndef CDSIM
#include "hw_pad.h"     /* PS1 pad (SIO0) -> GBA KEYINPUT */
#include "hw_card.h"    /* memory card + EEPROM save layer */
#include "hw_cdda.h"    /* CD-DA playback */
#else
#include "hw_stub.h"
#endif
#include "hw_radio.h"
#ifdef CDSIM
#define SIMDISC ((const u8*)0x90000000)   /* sim only: disc image mapped at physical 0x10000000 */
static void cd_read(u32 lba,u32 nsec,u8*dst){ memcpy(dst,SIMDISC+lba*2048,nsec*2048); cd_sectors+=nsec; }
#else
static void cd_init(void){
  IMASK=0; cd_ready=1;
  u8 m=0x80; cd_cmd(0x0e,&m,1); cd_wait(); cd_ack();          /* Setmode: double speed, 2048-byte sectors */
}
/* read nsec consecutive 2048-byte sectors starting at disc LBA into dst */
static void cd_read(u32 lba,u32 nsec,u8*dst){
  cdda_hold();                                                    /* a data seek ends CD-DA playback: pause and remember the position */
  if(!cd_ready) cd_init();
  u32 a=lba+150; u8 p[3]={bcd(a/4500),bcd((a/75)%60),bcd(a%75)};
  if(cd_dbg<12){ cd_dbg++; dbg("cd_read lba "); dec(lba); dec(nsec); dbg("\n"); }
  cd_cmd(0x02,p,3); cd_wait(); cd_ack();                          /* Setloc */
  cd_cmd(0x06,0,0); cd_wait(); cd_ack();                          /* ReadN: INT3 then one INT1 per sector */
  for(u32 s=0;s<nsec;s++){
    u32 f=cd_wait(); if(f!=1){ dbg("CD error int "); dec(f); dbg("\n"); }
    CD0=0; CD3=0x80;                                              /* want data */
    for(int i=0;i<2048;i++) dst[s*2048+i]=CD2;
    cd_ack(); if(cd_dbg<12) dbg("s");
  }
  if(cd_dbg<12) dbg("pause\n");
  cd_cmd(0x09,0,0); cd_wait(); cd_ack(); cd_wait(); cd_ack();      /* Pause: INT3 then INT2 */
  cd_sectors+=nsec;
  cdda_release();                                                 /* ...and resume the music where it was */
}
#endif
static const u8 *cd_fetch(u32 pg){
  u32 base=pg&~3u;                                               /* fetch the aligned 16 KiB cluster (4 pages, 8 sectors) per seek */
  u32 s=slot_next; slot_next=(slot_next+4)%NSLOT;
  for(u32 k=0;k<4;k++){ if(slot_owner[s+k]) rom_pg[slot_owner[s+k]-1]=0; slot_owner[s+k]=0; }
  cd_read(CD_ROM_LBA+base*2,8,PCACHE+s*4096);
  for(u32 k=0;k<4;k++){ u32 q=base+k; if(rom_pg[q]) continue; slot_owner[s+k]=q+1; rom_pg[q]=PCACHE+(s+k)*4096; }
  rom_miss_count++; rom_miss_last=pg<<12;
  return rom_pg[pg];
}
static inline const u8 *rom_page(u32 pg){ pg&=2047; const u8*p=rom_pg[pg]; return p?p:cd_fetch(pg); }
static u32 rom_byte(u32 off){ return rom_page(off>>12)[off&4095]; }
static u32 rom_read(u32 ea,u32 size){
  u32 off=ea&0x01ffffff; u32 v=0;
  for(u32 k=0;k<size;k++) v|=rom_byte(off+k)<<(8*k);
  return v;
}
/* ---------------------------------------------------------------- guest memory access by guest address (DMA) */
static u8 *g2h(u32 a){
  switch(a>>24){
    case 2: return EW+(a&0x3ffff);
    case 3: return IW+(a&0x7fff);
    case 5: return PAL+(a&0x3ff);
    case 6: { u32 o=a&0x1ffff; if(o>=0x18000) o-=0x8000; return VRAM+o; }
    case 7: return OAM+(a&0x3ff);
  } return 0;
}
/* ---------------------------------------------------------------- IO model (port of gbaenv.Io) */
static u8 io[0x400]; static u32 io_vc, io_nread, io_tm[4], io_nd, io_keys=0x3ff, ee_addr; static u8 ee[1024*8]; static u32 ee_init;
#ifndef PRESENT_EVERY
#define PRESENT_EVERY 16
#endif
#ifdef SIMKEYS
volatile u32 sim_keys=0x3ff;
#endif
static u32 g_pres, g_gframes; static void present(void);
/* GBA time base (stage 4): io_cyc = GBA cycles (16.78 MHz) since boot, advanced by VCOUNT/DISPSTAT polls (1232 cycles per scanline), by SWI 5 (to the next vblank) and by
   96 cycles per timer/KEYINPUT poll.  Timers are derived from io_cyc (prescaler, cascade, reload) instead of the old +37-per-read counter, which made Payback's
   timed wait loops (title slide show: 0x7000 counts of TM3:TM2) expire after two polls so a key press was never sampled. */
#ifdef KPLAN
#include "kplan.h"       /* KPL[][3] menu plan {frame0,frame1,pressed_mask} (GBA frames from power-on); KPL2[][3] in-level plan (frames since the level clock first runs); CAR_T */
static u32 lvl_f0;
static u32 kplan_keys(u32 f){
  if(*(volatile u32*)(EW+0x1e00)){ if(!lvl_f0) lvl_f0=f; u32 t=f-lvl_f0; for(u32 i=0;i<NKPL2;i++) if(t>=KPL2[i][0]&&t<KPL2[i][1]) return 0x3ff&~KPL2[i][2]; return 0x3ff; }
  for(u32 i=0;i<NKPL;i++) if(f>=KPL[i][0]&&f<KPL[i][1]) return 0x3ff&~KPL[i][2]; return 0x3ff; }
#endif
static u32 io_cyc, io_acc, tm_t0[4], tm_rl[4], tm_ovb[4], tm_en[4];
static void adv_lines(u32 n){ io_cyc+=n*1232; while(n--){ io_vc=io_vc>=227?0:io_vc+1; if(io_vc==160){ g_gframes++; if((g_gframes&(PRESENT_EVERY-1))==0) present(); } } }
static void adv_poll(void){ io_acc+=96; if(io_acc>=1232){ io_acc-=1232; adv_lines(1); } }
static u32 tm_cnt(u32 k,u32*ov){
  u32 ctrl=io[0x102+4*k]|(io[0x103+4*k]<<8); u32 counts;
  if(!(ctrl&0x80)){ *ov=0; return tm_rl[k]&0xffff; }
  if(k>0&&(ctrl&4)){ u32 o; tm_cnt(k-1,&o); counts=o-tm_ovb[k]; }
  else counts=(io_cyc-tm_t0[k])>>(((ctrl&3)==0)?0:((ctrl&3)==1?6:((ctrl&3)==2?8:10)));
  u32 per=0x10000-(tm_rl[k]&0xffff); *ov=counts/per; return (tm_rl[k]+counts%per)&0xffff;
}
static void tm_write_check(void){
  for(u32 k=0;k<4;k++){ u32 ctrl=io[0x102+4*k]|(io[0x103+4*k]<<8); u32 en=(ctrl>>7)&1;
    if(en&&!tm_en[k]){ tm_rl[k]=io[0x100+4*k]|(io[0x101+4*k]<<8); tm_t0[k]=io_cyc; if(k>0){ u32 o; tm_cnt(k-1,&o); tm_ovb[k]=o; } }
    tm_en[k]=en; }
}
static u32 g_frames, g_dispcnt_writes, g_nvbl;
static const u16 PAD[6]={0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81};
#ifdef AUTOKEYS
/* scripted pad for the test discs, keyed on guest ticks (DISPCNT writes): A tap every 45 ticks (hold 6), plus extra DOWN taps from a table */
#ifndef LVL_T0
#define LVL_T0 1200
#endif
static u32 lvl_t0;
static u32 auto_keys(u32 f){
  extern const u32 KS[][3]; extern const u32 NKS;
  if(*(volatile u32*)(EW+0x1e00)&&*(volatile s16*)(IW+0xc)>=0){            /* in a level: walk/drive about */
    if(!lvl_t0) lvl_t0=f; u32 t=f-lvl_t0, c=t%100, k=0x40;
    if(c>=60&&c<75) k|=0x20; if(c>=20&&c<28) k|=0x10; if(t>40&&(t%240)<8) k|=1;
    return 0x3ff&~k; }
  for(u32 i=0;i<NKS;i++) if(f>=KS[i][0]&&f<KS[i][0]+KS[i][1]) return 0x3ff&~KS[i][2];
  if(f>=LVL_T0){ static const u16 T[][2]={{0,1},{86,1},{152,1},{218,1},{284,0x80},{300,0x80},{330,1},{396,1}}; u32 t=f-LVL_T0;
    for(u32 i=0;i<8;i++) if(t>=T[i][0]&&t<T[i][0]+6u) return 0x3ff&~(u32)T[i][1];
    if(t>1000&&(t%120)<6) return 0x3ff&~1u; return 0x3ff; }
  { static const u16 PD[6]={0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81}; return PD[(f/30)%6]; } }
#endif
const u32 KS[][3]={{0,0,0}}; const u32 NKS=0;
static u32 io16(u32 o){ return io[o]|(io[o+1]<<8); }
static void io16w(u32 o,u32 v){ io[o]=v; io[o+1]=v>>8; }
static u32 gread(u32 a,u32 n){
  if((a>>24)==4){ extern u32 io_read(u32,u32); return io_read(a&0x3ff,n); }
  if(((a>>24)==8)||((a>>24)==10)||((a>>24)==12)) return rom_read(a,n);
  if((a>>24)==13) return 1;
  u8*p=g2h(a); if(!p) return 0; u32 v=0; for(u32 k=0;k<n;k++) v|=p[k]<<(8*k); return v;
}
static void gwrite(u32 a,u32 n,u32 v){
  if((a>>24)==4){ extern void io_write(u32,u32,u32); io_write(a&0x3ff,n,v); return; }
  u8*p=g2h(a); if(!p) return; for(u32 k=0;k<n;k++) p[k]=v>>(8*k);
}
static void eeprom_dma(u32 src,u32 dst,u32 n,u32 unit){
  if(!ee_init){ for(u32 i=0;i<sizeof ee;i++) ee[i]=0xff; ee_init=1; sv_load(ee,sizeof ee); }
  if((dst>>24)==13){
    u8 bits[200]; if(n>200) return;
    for(u32 k=0;k<n;k++) bits[k]=gread(src+unit*k,unit)&1;
    if(bits[0]!=1) return;
    if(bits[1]==1){ u32 ab=n-3,addr=0; for(u32 k=0;k<ab;k++) addr=addr*2+bits[2+k]; ee_addr=addr&1023; }
    else{ u32 ab=n-67,addr=0; for(u32 k=0;k<ab;k++) addr=addr*2+bits[2+k]; addr&=1023;
      for(u32 i=0;i<8;i++){ u32 b=0; for(u32 j=0;j<8;j++) b=b*2+bits[2+ab+8*i+j]; ee[addr*8+i]=b; } sv_dirty(addr*8,8); }
  } else {
    u8 bits[68]; for(u32 i=0;i<4;i++) bits[i]=0;
    for(u32 i=0;i<8;i++) for(u32 j=0;j<8;j++) bits[4+i*8+j]=(ee[ee_addr*8+i]>>(7-j))&1;
    for(u32 k=0;k<n;k++) gwrite(dst+unit*k,unit,k<68?bits[k]:0);
  }
}
static u32 unmap_host(u32 h){
  if(h>=(u32)EW && h<(u32)EW+0x40000) return 0x02000000+(h-(u32)EW);
  if(h>=(u32)IW && h<(u32)IW+0x8000) return 0x03000000+(h-(u32)IW);
  if(h>=(u32)PAL && h<(u32)PAL+0x400) return 0x05000000+(h-(u32)PAL);
  if(h>=(u32)OAM && h<(u32)OAM+0x400) return 0x07000000+(h-(u32)OAM);
  if(h>=(u32)VRAM && h<(u32)VRAM+0x18000) return 0x06000000+(h-(u32)VRAM);
  return h;
}
static u8 *resolve(u32 a,u32 *avail){
  u32 o;
  switch(a>>24){
    case 2: o=a&0x3ffff; *avail=0x40000-o; return EW+o;
    case 3: o=a&0x7fff; *avail=0x8000-o; return IW+o;
    case 5: o=a&0x3ff; *avail=0x400-o; return PAL+o;
    case 6: o=a&0x1ffff; if(o>=0x18000) o-=0x8000; *avail=0x18000-o; return VRAM+o;
    case 7: o=a&0x3ff; *avail=0x400-o; return OAM+o;
    case 8: case 10: case 12: { u32 off=a&0x01ffffff; const u8*pp=rom_page(off>>12); *avail=4096-(off&4095); return (u8*)pp+(off&4095); }
  } return 0;
}
/* DMA3 immediate between plain windows / resident ROM pages: block loops instead of per-unit helpers.  returns 0 when it cannot (caller falls back) */
static int dma_fast(u32 src,u32 dst,u32 n,u32 unit,u32 sc,u32 dc){
  if(dc!=0&&dc!=3) return 0;
  if(sc==2){ u32 sa,da; u8*sp=resolve(src,&sa); if(!sp) return 0; u32 v=unit==4?*(u32*)sp:*(u16*)sp;
    while(n){ u8*dp=resolve(dst,&da); if(!dp) return 1; u32 k=da/unit; if(k>n) k=n; if(!k) return 1; n-=k; dst+=k*unit;
      if(unit==4){ u32*q=(u32*)dp; while(k--) *q++=v; } else { u16*q=(u16*)dp; while(k--) *q++=v; } }
    return 1; }
  if(sc!=0) return 0;
  while(n){ u32 sa,da; u8*sp=resolve(src,&sa); u8*dp=resolve(dst,&da); if(!sp||!dp) return 0;
    u32 k=(sa<da?sa:da)/unit; if(k>n) k=n; if(!k) return 0;
    n-=k; src+=k*unit; dst+=k*unit;
    if(unit==4){ const u32*q=(const u32*)sp; u32*r=(u32*)dp; while(k--) *r++=*q++; } else { const u16*q=(const u16*)sp; u16*r=(u16*)dp; while(k--) *r++=*q++; } }
  return 1;
}
static void dma_check(u32 ch){
  u32 base=0xb0+12*ch;
  u32 sad=io[base]|(io[base+1]<<8)|(io[base+2]<<16)|((u32)io[base+3]<<24), dad=io[base+4]|(io[base+5]<<8)|(io[base+6]<<16)|((u32)io[base+7]<<24);
  u32 cntl=io16(base+8), cnth=io16(base+10);
  if(!(cnth&0x8000)) return;
  u32 timing=(cnth>>12)&3; if(timing!=0||ch==1) return;
  u32 n=cntl?cntl:(ch==3?0x10000:0x4000); u32 unit=(cnth&0x400)?4:2; u32 dc=(cnth>>5)&3, sc=(cnth>>7)&3;
  u32 src=sad,dst=dad;
  if((dst>>24)==13||(src>>24)==13) eeprom_dma(src,dst,n,unit);
  else if(dma_fast(src,dst,n,unit,sc,dc)) {}
  else for(u32 k=0;k<n;k++){
    gwrite(dst,unit,gread(src,unit));
    if(sc==0) src+=unit; else if(sc==1) src-=unit;
    if(dc==0||dc==3) dst+=unit; else if(dc==1) dst-=unit;
  }
  if(!(cnth&0x200)) io16w(base+10,cnth&0x7fff);
}
static void tick(void){ io_nd++;

}
/* VCOUNT model.  Normal: one scanline per read (as the lockstep-verified IO model).  -DTESTFAST (TEST-ONLY, emulator runs, never for a release disc):
   each read advances up to 16 lines but always stops on 0, 159, 160, 161, 227 and the DISPSTAT LYC line, so poll loops that wait for vblank / a compare line still
   see them; the palette-fade / vblank-poll waits of Payback's menus then cost about 1/14 of the R3000 time. Game logic is unchanged (guest frame counts per fade
   step are the same); only the number of VCOUNT reads per guest frame drops. */
static u32 vc_n(u32 v){
#ifdef TESTFAST
  u32 lyc=io[5]; u32 n=16; static const u8 st[]={159,160,161,227};
  for(u32 i=0;i<4;i++) if(v<st[i]&&v+n>st[i]) n=st[i]-v;
  if(v<lyc&&v+n>lyc) n=lyc-v; if(v+1==lyc) n=1;
  if(v+n>=228) n=228-v;     /* v=227 -> 0 */
  return n;
#else
  return 1;
#endif
}
u32 io_read(u32 off,u32 size){
  io_nread++;
  if(off==0x130||off==0x131){
  adv_poll();
#ifdef SIMKEYS
 io_keys=sim_keys;          /* TEST-ONLY (unicorn sim): the host script writes sim_keys */
#endif
#ifdef KPLAN
 io_keys=kplan_keys(io_cyc/280896);   /* TEST-ONLY: pad plan keyed on GBA frames (cycles / 280896), generated from the stock game's menu timeline */
#endif
#ifdef AUTOKEYS
 io_keys=auto_keys(io_nd);
#endif
 u32 v=io_keys; return size==2?v:(size==1?(v>>(8*(off-0x130)))&0xff:v); }
  if(off==6||off==7){ adv_lines(vc_n(io_vc)); u32 v=io_vc; return size!=1?v:(v>>(8*(off-6)))&0xff; }
  if(off==4||off==5){ adv_lines(vc_n(io_vc)); u32 ds=io16(4);
    u32 v=((io_vc>=160&&io_vc<227)?1:0)|(((io_nread&3)==0)?2:0)|((io_vc==((ds>>8)&0xff))?4:0)|(ds&0xff38);
    return size==2?(v&0xffff):(size==1?(v>>(8*(off-4)))&0xff:v); }
  if(off==0x100||off==0x104||off==0x108||off==0x10c){ u32 k=(off-0x100)/4,o; adv_poll(); return tm_cnt(k,&o); }
  u32 v=0; for(u32 k=0;k<size;k++) v|=io[off+k]<<(8*k); return v;
}
void io_write(u32 off,u32 size,u32 val){
  if(size<4) val&=(1u<<(8*size))-1;
  if(size==4&&off>=0xb0&&off<0xe0&&((off-0xb0)%12==0||(off-0xb0)%12==4)) val=unmap_host(val);
  if(off==0x202&&size==2){ io16w(0x202,io16(0x202)&~val); return; }
  for(u32 k=0;k<size;k++) io[off+k]=val>>(8*k);
  for(u32 ch=0;ch<4;ch++){ u32 cnt=0xb0+12*ch+8; if(off<=cnt+2&&off+size>=cnt+4) dma_check(ch); }
  if(off>=0x100&&off<0x110) tm_write_check();
  if(off==0&&size>=2){ g_dispcnt_writes++; tick(); }
}
/* ---------------------------------------------------------------- C helpers called from RT_CC */
u32 h_memrd(u32 ea,u32 kind){
  static const u8 SZ[5]={1,1,2,2,4}; u32 size=SZ[kind]; u32 v;
  if((ea>>24)==8||(ea>>24)==10||(ea>>24)==12) v=rom_read(ea,size);
  else if((ea>>24)==13) v=1;
  else if(ea-0x8017f000u<0x400) v=io_read(ea-0x8017f000u,size);
  else if(ea>=0x80180000u&&ea<0x80200000u){ v=0; for(u32 k=0;k<size;k++) v|=((u32)((volatile u8*)ea)[k])<<(8*k); }
  else if((ea>>24)==4&&(ea&0xfffffc00u)==0x04000000u) v=io_read(ea&0x3ff,size);
  else if((ea>>24)>=2&&(ea>>24)<=7&&g2h(ea)){ const volatile u8*p=g2h(ea); v=0; for(u32 k=0;k<size;k++) v|=((u32)p[k])<<(8*k); }   /* raw guest RAM address that reached the slow path (runtime-built pointer, e.g. lsl #19 constants) */
  else { dbg("BADRD "); hex(ea); v=0; }
  if(kind==1&&(v&0x80)) v|=0xffffff00; if(kind==3&&(v&0x8000)) v|=0xffff0000;
  return v;
}
u32 h_memwr(u32 ea,u32 size,u32 val){
  if(ea-0x8017f000u<0x400) io_write(ea-0x8017f000u,size,val);
  else if(ea>=0x80180000u&&ea<0x80200000u){ for(u32 k=0;k<size;k++) ((volatile u8*)ea)[k]=val>>(8*k); }
  else if((ea>>24)==13) {}
  else if((ea>>24)==4&&(ea&0xfffffc00u)==0x04000000u) io_write(ea&0x3ff,size,val);
  else if((ea>>24)>=2&&(ea>>24)<=7&&g2h(ea)){ volatile u8*p=g2h(ea); for(u32 k=0;k<size;k++) p[k]=val>>(8*k); }   /* raw guest RAM address on the slow path (see h_memrd) */
  else { dbg("BADWR "); hex(ea); }
  return 0;
}
static void gpu_panic(const char*m,u32 a){ dbg(m); hex(a); dbg("\n"); for(;;){} }
extern const u32 COLD_HOST; extern const u8 coldtab[];
static int sf3_ok;
#ifndef COLDGROUPS
#define COLDGROUPS 64
#endif
static u8 cold_loaded[COLDGROUPS]; static u32 cold_loads, cold_calls;
static void flush_icache(void){ register u32 t1 __asm__("$9")=0x44;
  __asm__ volatile("li $8,0xA0\n jalr $8\n nop":"+r"(t1)::"$1","$2","$3","$4","$5","$6","$7","$8","$10","$11","$12","$13","$14","$15","$24","$25","$31","memory"); }
/* RT_MISS: a direct call/jump/function pointer reached a guest function that is not in the resident blob.  Overlay loader:
   find it in the cold table, read the 16 KiB groups of COLD.BIN that cover the function (and its out-of-line stubs) into their fixed
   home addresses, flush the I-cache, and return the host entry for RT_MISS to tail-jump to. */
u32 h_miss(u32 addr){
  u32 g=addr&~1u; const u32*ct=(const u32*)coldtab; u32 n=ct[0]; const u32*r=ct+1; u32 lo=0,hi=n; cold_calls++;
  while(lo<hi){ u32 m=(lo+hi)>>1; u32 v=r[m*4]; if(v==g){ lo=m; goto found; } if(v<g) lo=m+1; else hi=m; }
  gpu_panic("RT_MISS guest code not in cold set: ",addr); return 0;
found:;
  u32 host=r[lo*4+1], hs=r[lo*4+2], he=r[lo*4+3];
  u32 g0=(hs-COLD_HOST)>>14, g1=(he-1-COLD_HOST)>>14, loaded=0;
  { u32 lo=COLD_HOST+g0*16384, hi=COLD_HOST+(g1+1)*16384;
    if(sf3_ok && (hi>0x800D4000u && lo<0x8011b200u)) { dbg("SF3 CONFLICT cold load over renderer data, renderer off: "); hex(addr); dbg("\n"); sf3_ok=0; } }
  for(u32 k=g0;k<=g1;k++) if(!cold_loaded[k]){
    u32 left=CD_COLD_PAGES*2-k*8, dst=COLD_HOST+k*16384;
#ifdef CDSIM
    if(dst+16384>0x8017c000u && dst<0x80200000u){      /* group straddles the guest RAM window (sim build with COLD_GAP): the gap bytes are zeros in COLD.BIN, copy only what lies outside it (stage 4 fix: the zeros used to wipe the helper stack at 0x801fff00) */
      static u8 gtmp[16384]; cd_read(CD_COLD_LBA+k*8,left<8?left:8,gtmp);
      for(u32 q=0;q<16384;q++){ u32 a=dst+q; if(a<0x8017c000u||a>=0x80200000u) ((volatile u8*)a)[0]=gtmp[q]; } }
    else
#endif
    cd_read(CD_COLD_LBA+k*8,left<8?left:8,(u8*)dst);
    cold_loaded[k]=1; cold_loads++; loaded=1; }
  if(loaded){ flush_icache(); dbg("COLD load "); hex(addr); dec(g0); dec(g1); dbg("\n"); }
  return host;
}

/* ---------------------------------------------------------------- GPU */
static void gp0(u32 w){ while(!(GP1&0x04000000)){} GP0=w; }
#define XY(x,y) (((u32)(y)<<16)|((x)&0xffff))
static int cur_oy;
static void rect(int x,int y,int w,int h,u32 rgb){ if(w<=0||h<=0) return; gp0(0x60000000|rgb); gp0(XY(x,y+cur_oy)); gp0(XY(w,h)); }
#include "font.h"
static int chidx(char c){ if(c>='0'&&c<='9') return c-'0'; if(c>='a'&&c<='z') c-=32; if(c>='A'&&c<='Z') return 10+c-'A'; return -1; }
static void text(int x,int y,const char*s,int sc,u32 rgb){
  for(;*s;s++,x+=4*sc){ int i=chidx(*s); if(i<0) continue; u16 g=F35[i];
    for(int r=0;r<5;r++) for(int c=0;c<3;c++) if(g&(1<<(14-(r*3+c)))) rect(x+c*sc,y+r*sc,sc,sc,rgb); }
}
static void num(int x,int y,u32 v,int sc,u32 rgb){ char b[12]; int n=0; if(!v) b[n++]='0'; while(v){b[n++]='0'+v%10; v/=10;} char t[12]; for(int i=0;i<n;i++) t[i]=b[n-1-i]; t[n]=0; text(x,y,t,sc,rgb); }
static void gpu_init(void){
  GP1=0x00000000; GP1=0x03000000; GP1=0x06000000|(0x260|((0x260+320*8)<<12)); GP1=0x07000000|(0x10|((0x10+240)<<10)); GP1=0x08000001;
}
static void vsync(void){ ISTAT=~1u; for(volatile int n=0;n<400000;n++){ if(ISTAT&1) break; } ISTAT=~1u; }
static u32 last_dl, last_rc, logic_lines, max_lines, tot_lines, nfr_meas; static int buf;
static u32 rd32g(u32 off){ return rom_read(0x08000000+off,4); }
/* ---------------------------------------------------------------- stage 3: the PS1 city renderer (sf3.c) driven from Payback's state */
typedef struct { s32 x, y, z; u16 yaw; u8 kind, spare; } SfEnt;
extern int sf3_init(void); extern int sf3_frame(int oy,s32 px,s32 py,s32 pz,int heading,int pkind,const SfEnt*ents,int nents,int hud);
extern s32 sf3_score, sf3_hp, sf3_clock; extern u32 sf3_stat_eng, sf3_stat_prim, sf3_stat_ovf, sf3_stat_lod, sf3_frames;
void sf3_cd_read(u32 lba,u32 nsec,u8*dst){ cd_read(lba,nsec,dst); }
#ifndef PRINT_EVERY_SF3
#define PRINT_EVERY_SF3 63
#endif
static u32 st3_render, st3_hud_only, st3_lines_sum, st3_lines_max, st3_gather_lines, st3_id5;
static SfEnt ents3[40];
#ifdef SF3_DEMO
static const s16 S4[18]={0,1608,3196,4756,6270,7723,9102,10394,11585,12665,13623,14449,15137,15679,16069,16305,16384,16384};   /* sin(k*pi/32) in 1.14 */
static int sin_t(int a){ a&=0xffff; int q=a>>14, x=a&16383; if(q&1) x=16384-x; int k=x>>10, r=x&1023; int v=S4[k]+(((S4[k+1]-S4[k])*r)>>10); return (q&2)?-v:v; }
static int cos_t(int a){ return sin_t(a+16384); }
#endif
/* the level's player: Payback's entity list (IWRAM 0x03000c60, last index 0x0300000c), controlled index (EWRAM 0x02001db8), map 0x02001d40, clock 0x02001e00 */
/* an entity pointer in the guest's IWRAM table: a raw GBA address (0x02xxxxxx, as in the mGBA snapshots) or, in the translated guest, the host address inside the EWRAM window (stage 4: the translated game stores host pointers) */
static const u8 *entp(u32 p){ if((p>>24)==2) return EW+(p&0x3ffff); if(p>=(u32)EW&&p<(u32)EW+0x40000) return (const u8*)p; return 0; }
static int gather3(s32*px,s32*py,s32*pz,int*hd,int*pk,int*nents){
#ifdef SF3_DEMO
  /* renderer test without a level: a car drives a scripted route through Freedom City (heading 0 = +z) */
  { static s32 x=9728, z=2700; static int h=0; u32 f=st3_render; int ph=f%240; x+=(sin_t(h)*40)>>14; z+=(cos_t(h)*40)>>14;
    if(ph>=40&&ph<70) h+=300; if(ph>=110&&ph<150) h-=300; if(ph>=190&&ph<210) h+=300; h&=0xffff;
    *px=x; *pz=z; *py=0; *hd=h; *pk=1; *nents=0; return 1; }
#endif
  if(*(volatile u32*)(EW+0x1e00)==0 || *(volatile s16*)(EW+0x1d40)!=0) return 0;      /* in a level, on map 0 (Freedom City) */
  s32 nl=*(volatile s16*)(IW+0xc), ci=*(volatile s16*)(EW+0x1db8); if(nl<0||nl>100||ci<0||ci>nl) return 0;
  const u32*tab=(const u32*)(IW+0xc60); const u8*e=entp(tab[ci]); if(!e) return 0;
  *px=*(const s32*)(e+4)>>1; *pz=*(const s32*)(e+8)>>1; *py=((19904-(s32)*(const u16*)(e+0xc))>>1);
  *hd=((s32)*(const s16*)(e+0x12)*11651>>10)&0xffff;
  sf3_score=*(const s32*)(e+0x90); sf3_hp=*(const s16*)(e+0x68); sf3_clock=*(volatile u32*)(EW+0x1e00)/30;
  u32 d=*(const u32*)(e+0x1c); *pk=0; if(d-0x08354af4u<128*0x3c) *pk=(rom_byte((d+0x26)&0x01ffffff)==0);
  int n=0;
  for(s32 i=0;i<=nl&&n<40;i++){ if(i==ci) continue; const u8*o=entp(tab[i]); if(!o) continue;
    u32 dd=*(const u32*)(o+0x1c); if(dd-0x08354af4u>=128*0x3c) continue; u32 cl=rom_byte((dd+0x26)&0x01ffffff); if(cl>1) continue;
    s32 ox=*(const s32*)(o+4)>>1, oz=*(const s32*)(o+8)>>1; if(ox-*px>9000||*px-ox>9000||oz-*pz>9000||*pz-oz>9000) continue;
    ents3[n].x=ox; ents3[n].z=oz; ents3[n].y=(19904-(s32)*(const u16*)(o+0xc))>>1; ents3[n].yaw=((s32)*(const s16*)(o+0x12)*11651>>10)&0xffff; ents3[n].kind=cl?1:0; n++; }
  *nents=n; return 1;
}
#ifdef SF3_SNAP
/* renderer check against real Payback memory: EWRAM+IWRAM captured from the stock game (mGBA) in a level are loaded from SNAP.BIN, one after the other, and drawn
   through the same gather3 + sf3_frame path the live guest uses (the guest itself is not started in this build) */
static void snap_loop(void){
  static const char*const names[]={"foot start","foot walking","car 0","car 1","car 2","car 3","car 4","car 5","car 6","car 7","car 8","car 9","car 10","car 11"};
  u32 fr=0;
  for(;;) for(u32 k=0;k<CD_SNAP_N;k++){
    cd_read(CD_SNAP_LBA+k*144,128,EW); cd_read(CD_SNAP_LBA+k*144+128,16,IW);
    for(u32 f=0;f<24;f++){
      s32 px,py,pz; int hd,pk,ne; int oy=(fr&1)?240:0; fr++;
      int ok=gather3(&px,&py,&pz,&hd,&pk,&ne);
      if(ok){ u32 r0=RC1_VAL; sf3_frame(oy,px,py,pz,hd,pk,ents3,ne,1); u32 dl=(RC1_VAL-r0)&0xffff; st3_render++; st3_lines_sum+=dl; if(dl>st3_lines_max) st3_lines_max=dl;
        if(f==23){ dbg("SNAP "); dec(k); dbg(names[k]); dbg(" pos "); dec(px); dec(py); dec(pz); dbg("hd "); dec(hd); dbg("veh "); dec(pk); dbg("ents "); dec(ne); dbg("eng "); dec(sf3_stat_eng); dbg("prim "); dec(sf3_stat_prim); dbg("ovf "); dec(sf3_stat_ovf); dbg("lod "); dec(sf3_stat_lod); dbg("\n"); } }
      else if(f==0){ dbg("SNAP "); dec(k); dbg("gather failed\n"); }
      gp0(0x03000000); while(!(GP1&0x04000000)){} vsync(); GP1=0x05000000|(oy<<10);
    }
  }
}
#endif
void h_vbl(void){
#ifdef KPLAN
  { static u32 poked; if(!poked&&CAR_T&&lvl_f0&&io_cyc/280896-lvl_f0>=CAR_T){ poked=1; *(volatile u16*)(EW+0x1db8)=6; dbg("TEST-ONLY: controlled entity index set to 6 (car)\n"); } }
#endif
  { u32 n=(160+228-io_vc)%228; if(!n) n=228; io_cyc+=n*1232; } io_vc=160; io16w(0x202,io16(0x202)|1); tick(); g_nvbl++; g_gframes++;
  present();
}
static void present(void){
  sv_service(); cdda_service();
  g_pres++; if((g_pres%50)==1){ dbg("present "); dec(g_pres); dbg(" tick "); dec(io_nd); dbg("gf "); dec(g_gframes); dbg("clk "); dec(*(volatile u32*)(EW+0x1e00)); dbg("map "); dec(*(volatile u16*)(EW+0x1d40)); dbg("nent "); dec(*(volatile u16*)(IW+0xc)); dbg("dsp "); hex(io16(0)); dbg("keys "); hex(io_keys); dbg("\n"); }
  u32 rc=RC1_VAL; u32 lines=(rc-last_rc)&0xffff;   /* scanlines of CPU time since the previous present = guest logic time */
  /* ----- game-state tick (same clock as the lockstep proof): vblank = io_vc 160, IF bit0 */
  u32 n=DL[0]; u32 from=last_dl; if(n-from>256) from=n-256; last_dl=n;
  logic_lines=lines; if(lines>max_lines) max_lines=lines; tot_lines+=lines; nfr_meas++;
  int oy=buf?240:0; cur_oy=oy;
#ifndef AUTOKEYS
  io_keys=pad_poll(); radio_poll();
#endif
  if(sf3_ok){ s32 px,py,pz; int hd,pk,ne;
    u32 g0=RC1_VAL; int ok=gather3(&px,&py,&pz,&hd,&pk,&ne); st3_gather_lines=(RC1_VAL-g0)&0xffff;
    if(ok){ u32 r0=RC1_VAL; sf3_frame(oy,px,py,pz,hd,pk,ents3,ne,1); u32 dl=(RC1_VAL-r0)&0xffff; st3_render++; st3_lines_sum+=dl; if(dl>st3_lines_max) st3_lines_max=dl;
      if((st3_render&PRINT_EVERY_SF3)==1||st3_render<4){ dbg("SF3 frame "); dec(st3_render); dbg("pos "); dec(px); dec(py); dec(pz); dbg("hd "); dec(hd); dbg("veh "); dec(pk); dbg("ents "); dec(ne); dbg("eng "); dec(sf3_stat_eng); dbg("host "); dec(dl); dbg("lines prim "); dec(sf3_stat_prim); dbg("ovf "); dec(sf3_stat_ovf); dbg("lod "); dec(sf3_stat_lod); dbg("logic "); dec(lines); dbg("\n"); }
      goto flip; } }
  gp0(0xE1000000|(5)|(2<<7)); gp0(0xE3000000|XY(0,oy)); gp0(0xE4000000|XY(319,oy+239)); gp0(0xE5000000|XY(0,oy));
  gp0(0x02101018); gp0(XY(0,oy)); gp0(XY(320,240));
  /* the blit/effect draw calls the pruned renderer would have made: new ring entries go to a persistent scene list of the last 64 blits
     (position/size from the draw call + the image descriptor in ROM); the whole list is drawn every frame, older ones darker */
  static struct { s16 x,y,w,h; u8 id,age; } bl[64]; static u32 nbl;
  int nb=0, ne=0;
  u32 scrh=0, scrn=0;
  for(u32 k=from;k<n;k++){
    volatile u32*e=&DL[8+(k&255)*8]; u32 id=e[0], r0=e[1], r1=e[2], r2=e[3];
    if(id==2||id==4){ scrh=scrh*31+r0; scrn++; }
    if(id==2||id==4){
      u32 w=rom_read(r0,2), h=rom_read(r0+2,1); if(w>240) w=240; if(h>160) h=160;
      for(u32 q=0;q<64;q++) if(bl[q].id) bl[q].age=bl[q].age<250?bl[q].age+1:250;
      u32 slot=nbl++&63; bl[slot].x=(int)r1; bl[slot].y=(int)r2; bl[slot].w=w; bl[slot].h=h; bl[slot].id=id; bl[slot].age=0; nb++;
    } else if(id==3) ne++;
    else if(id==5){ static u32 n5; if(n5<16){ n5++; dbg("ID5 nd "); dec(io_nd); hex(r0); hex(r1); hex(r2); hex(e[4]); dbg("\n"); } }
    if((id==2||id==4)&&rom_read(r0,2)>=100){ static u32 lastimg; if(r0!=lastimg){ lastimg=r0; static u32 nimg; if(nimg<400){ nimg++; dbg("IMG gf "); dec(g_gframes); dbg("nd "); dec(io_nd); hex(r0); dbg("\n"); } } }
  }
  { static u32 hist[8]; static u32 nscr, hp; int seen=0; for(int q=0;q<8;q++) if(hist[q]==scrh) seen=1; if(scrn>2&&!seen&&nscr<400){ nscr++; hist[hp++&7]=scrh; dbg("SCR "); hex(scrh); dec(scrn); dbg("nd "); dec(io_nd); dbg("first "); hex(DL[8+((n-scrn)&255)*8+1]); dbg("\n"); } }
  for(u32 q=0;q<64;q++) if(bl[q].id){
    int ag=bl[q].age; u32 base=bl[q].id==2?0xe0c040:0x40e060; u32 sh=ag<8?0:(ag<24?1:2);   /* fade with age */
    u32 c=((((base>>16)&255)>>sh)<<16)|((((base>>8)&255)>>sh)<<8)|((base&255)>>sh);
    int sx=bl[q].x*4/3, sy=bl[q].y*3/2, sw=bl[q].w*4/3, sh_=bl[q].h*3/2; if(sw<2) sw=2; if(sh_<2) sh_=2; if(sy<84) sy=84+ (sy&7);
    rect(sx,sy,sw,1,c); rect(sx,sy+sh_-1,sw,1,c); rect(sx,sy,1,sh_,c); rect(sx+sw-1,sy,1,sh_,c);
  }
  /* the game's current palette (guest PAL, 256 BGR555 entries) as a 16x16 swatch grid: state straight from Payback's palette fades */
  for(int py=0;py<16;py++) for(int px=0;px<16;px++){
    u32 v=*(volatile u16*)(PAL+(py*16+px)*2); u32 r=(v&31)<<3, g=((v>>5)&31)<<3, b=((v>>10)&31)<<3;
    rect(236+px*5,6+py*5,5,5,(b<<16)|(g<<8)|r);   /* PS1 colour word is 0xBBGGRR */
  }
  /* ----- HUD: Payback state read from the translated game's RAM */
  text(4,4,"PAYBACK ON PS1  STAGE2",2,0xffffff);
  text(4,20,"GUEST TICK",1,0x80c0ff); num(60,20,io_nd,1,0xffffff);
  text(4,28,"GUEST FRAMES",1,0x80c0ff); num(70,28,g_gframes,1,0xffffff); text(120,28,"PRESENTS",1,0x80c0ff); num(160,28,g_pres,1,0xffffff);
  text(4,36,"BLITS THIS FRAME",1,0x80c0ff); num(100,36,nb,1,0xffffff);
  text(4,44,"DRAWLIST TOTAL",1,0x80c0ff); num(100,44,n,1,0xffffff);
  text(4,52,"LOGIC SCANLINES",1,0x80c0ff); num(100,52,logic_lines,1,0xffffff);
  text(4,60,"ROM PAGE LOADS",1,0x80c0ff); num(100,60,rom_miss_count,1,0xffffff); text(130,60,"CD SECTORS",1,0x80c0ff); num(180,60,cd_sectors,1,0xffffff);
  /* a second frame counter taken from the game itself: Payback's own vblank flag/ frame variable region in IWRAM (first words that count) */
  text(4,68,"OVERLAY LOADS",1,0x80c0ff); num(100,68,cold_loads,1,0xffffff); text(130,68,"MISS CALLS",1,0x80c0ff); num(180,68,cold_calls,1,0xffffff);
  text(4,76,"DISPCNT",1,0x80c0ff); num(100,76,io16(0),1,0xffffff); text(130,76,"EW FRAMEVAR",1,0x80c0ff); num(190,76,*(volatile u16*)(EW+0x2632),1,0xffffff);
  text(4,84,"BLITS TOTAL",1,0x80c0ff); num(100,84,nbl,1,0xffffff); text(130,84,"FX CALLS",1,0x80c0ff); num(180,84,ne,1,0xffffff);
  /* ----- present */
 flip:
  gp0(0x03000000); /* nothing; keeps GPU idle check */
  while(!(GP1&0x04000000)){}
  vsync();
  GP1=0x05000000|(oy<<10); buf^=1;
  last_rc=RC1_VAL;
}
#ifdef SNAPRESUME
/* TEST-ONLY resume from a guest-state snapshot taken in the unicorn sim at the entry of present() (called from h_vbl and from the VCOUNT poll in io_read) during the level: SNAPST.BIN on the disc (sector-aligned):
   sec 0 header: [0]=magic [1..32]=MIPS regs $0..$31 at h_vbl entry, [0x24..]=statics (see snap order below), 0x200..0x2ff = RT_CC stack 0x801fff00..;
   1: EWRAM 128 sec, 129: IWRAM 16, 145: VRAM shadow 48, 193: PAL+OAM, 194: io[], 195: ee[] 4 sec.  The guest code and the helpers are the same translation. */
extern void snap_resume(const u32*regs,u32 target);
static u32 snap_regs[32], snap_target;
static void snap_restore(void){
  u8*h=PCACHE; cd_read(CD_SNAPST_LBA,1,h); const u32*w=(const u32*)h;
  for(int i=0;i<32;i++) snap_regs[i]=w[1+i];
  snap_target=w[0x88/4];
  const u32*st=w+40;
  io_vc=st[0]; io_nread=st[1]; io_nd=st[2]; io_cyc=st[3]; io_acc=st[4]; g_gframes=st[5]; g_nvbl=st[6];
  for(int k=0;k<4;k++){ tm_t0[k]=st[7+k]; tm_rl[k]=st[11+k]; tm_ovb[k]=st[15+k]; tm_en[k]=st[19+k]; }
  ee_init=st[23];
#ifdef KPLAN
  lvl_f0=st[24];
#endif
  memcpy((void*)0x801fff00,h+0x200,256);
  cd_read(CD_SNAPST_LBA+1,128,EW); cd_read(CD_SNAPST_LBA+129,16,IW); cd_read(CD_SNAPST_LBA+145,48,VRAM);
  cd_read(CD_SNAPST_LBA+193,1,PCACHE+2048); memcpy(PAL,PCACHE+2048,1024); memcpy(OAM,PCACHE+2048+1024,1024);
  cd_read(CD_SNAPST_LBA+194,1,PCACHE+4096); memcpy(io,PCACHE+4096,0x400);
  cd_read(CD_SNAPST_LBA+195,4,ee);
  { /* the snapshot may be inside (or return into) overlay code: load the whole cold prefix of this disc (the scenario's groups, ahead of everything else, below the renderer buffers) */
    u32 ng=(CD_COLD_PAGES*2+7)/8; if(ng>COLDGROUPS) ng=COLDGROUPS;
    cd_read(CD_COLD_LBA,CD_COLD_PAGES*2,(u8*)COLD_HOST); for(u32 k=0;k<ng;k++) cold_loaded[k]=1; flush_icache(); dbg("cold prefix preloaded, groups "); dec(ng); { u32 sm=0; const u32*p=(const u32*)COLD_HOST; for(u32 q=0;q<136000;q++) sm=sm*31+p[q]; dbg("checksum "); hex(sm); } dbg("\n"); }
  dbg("snapshot restored: gba frame "); dec(io_cyc/280896); dbg("tick "); dec(io_nd); dbg("\n");
}
#endif
/* ---------------------------------------------------------------- start */
extern u32 GUEST_MAIN_HOST;       /* from payback_syms.c */
int main(void){
  dbg("PAYBACK PS1 stage2: start\n");
  gpu_init(); cdda_init();
  memset((void*)DL,0,0x2100);
  RC1_MODE=0x0100;       /* root counter 1 counts hblank */
  HELP[0]=(u32)h_memrd; HELP[1]=(u32)h_memwr; HELP[2]=(u32)h_miss; HELP[3]=(u32)h_vbl;
  const u32 *b=(const u32*)bootimg; const u8 *p=bootimg+160;
  memcpy(EW,p,0x40000); p+=0x40000; memcpy(IW,p,0x8000); p+=0x8000; memcpy(PAL,p,0x400); p+=0x400; memcpy(VRAM,p,0x18000); p+=0x18000; memcpy(OAM,p,0x400); p+=0x400; memcpy(io,p,0x400);
  io_vc=b[32]; io_nread=b[33]; for(int i=0;i<4;i++) io_tm[i]=b[34+i]; io_nd=b[38]; io_keys=PAD[(io_nd/30)%6];
  const u32 *rp=(const u32*)rompack; rp_n=rp[0]; rp_idx=rp+1; rp_data=(const u8*)(rp+1+rp_n);
  for(u32 i=0;i<rp_n;i++) rom_pg[rp_idx[i]&2047]=rp_data+i*4096;     /* optional pre-seeded pages (never evicted) */
  dbg("boot image loaded, rom pages "); dec(rp_n); dbg("\n");
  last_rc=RC1_VAL;
  static u32 regs[32]; for(int i=0;i<32;i++) regs[i]=b[i];
  { extern u8 __sfbss_start[],__sfbss_end[]; for(u8*q=__sfbss_start;q<__sfbss_end;q++) *q=0; }
  #ifdef NOSF3
  sf3_ok=0;    /* unicorn sim has no GTE */
#else
  sf3_ok=(sf3_init()==0);
#endif
  dbg("sf3_ok "); dec(sf3_ok); dbg("\n"); last_rc=RC1_VAL;
#ifdef SF3_SNAP
  snap_loop();
#endif
#ifdef SNAPRESUME
  snap_restore(); last_rc=RC1_VAL; snap_resume(snap_regs,snap_target==1?(u32)h_memrd:(u32)present);
#endif
  register u32 *r __asm__("$8")=regs; register u32 tgt __asm__("$9")=GUEST_MAIN_HOST;
  __asm__ volatile(
    "lw $4,16($8)\n lw $5,20($8)\n lw $6,24($8)\n lw $7,28($8)\n"
    "lw $11,44($8)\n lw $12,48($8)\n lw $13,52($8)\n lw $14,56($8)\n lw $15,60($8)\n"
    "lw $16,64($8)\n lw $17,68($8)\n lw $18,72($8)\n lw $19,76($8)\n lw $20,80($8)\n lw $21,84($8)\n lw $22,88($8)\n lw $23,92($8)\n"
    "lw $30,120($8)\n lw $31,124($8)\n nop\n jr $9\n nop" :: "r"(r),"r"(tgt));
  for(;;){}
}
