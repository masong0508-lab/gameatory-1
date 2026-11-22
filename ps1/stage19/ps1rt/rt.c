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
/* rc7: code that runs once or only on a fault (boot set-up, boot-time patchers, error screens) goes into .rtcold, which ps1.ld places in the RAM
   between the helper table and the ROM page-table area (0x80028040..0x8002a000) that nothing else uses; it is part of the EXE image (the BIOS loads and
   flushes it with the rest), so it needs no loading of its own */
#define RTCOLD __attribute__((noinline,section(".rtcold.text")))
#define EW ((u8*)0x801b0000)
#define IW ((u8*)0x801f0000)
#define PAL ((u8*)0x80180000)
#define OAM ((u8*)0x80180400)
#define VRAM ((u8*)0x80181000)
#define DL ((volatile u32*)0x8017c000)
extern u8 __blob_start[];
extern u8 bootimg[], rompack[];
extern u8 __ppu_start[], __veneer_scratch[];
extern void *memset(void*,int,unsigned);
void *memset(void*d,int c,unsigned n){u8*p=d;while(n--)*p++=c;return d;}
void *memcpy(void*d,const void*s,unsigned n){u8*p=d;const u8*q=s;while(n--)*p++=*q++;return d;}

/* kernel putchar A(3Ch).  The inline call reserves the 16-byte argument area of the MIPS calling convention below the caller's frame (the kernel
   may use [SP+0..15], psx-spx "BIOS Function Summary") and tells the compiler that every caller-saved register, HI and LO are destroyed. */
static __attribute__((noinline)) void dbgc(char c){ register u32 a0 __asm__("$4")=c; register u32 t1 __asm__("$9")=0x3c;
  __asm__ volatile("addiu $29,$29,-16\n li $8,0xA0\n jalr $8\n nop\n addiu $29,$29,16":"+r"(a0),"+r"(t1)::"$1","$2","$3","$5","$6","$7","$8","$10","$11","$12","$13","$14","$15","$24","$25","$31","hi","lo","memory"); }
static __attribute__((noinline)) void dbg(const char*p){ while(*p) dbgc(*p++); }     /* out of line: one copy instead of one per message */
static void hex(u32 v){ for(int i=0;i<8;i++){int d=(v>>(28-4*i))&15; dbgc(d<10?48+d:87+d);} dbgc(' '); }
static void dec(u32 v){ char b[12]; int n=0; if(!v) b[n++]='0'; while(v){b[n++]='0'+v%10; v/=10;} while(n) dbgc(b[--n]); dbgc(' '); }

/* ---------------------------------------------------------------- ROM page store (resident pages shipped in the EXE) */
static u32 rp_n; static const u32 *rp_idx; static const u8 *rp_data; static u32 rom_miss_count, rom_miss_last, cd_sectors, cd_time_rc;
static const u8 *rom_pg[2048];
static u32 g_pres, g_gframes;   /* presented pictures, guest (GBA) frames */
static u32 cd_rd_gf;            /* the guest frame in which the last data read ended (hw_cdda.h resumes the music after a quiet interval) */
/* ---------------------------------------------------------------- CD-ROM (polling driver, no IRQ): whole sectors, every one identified by its own header
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
#define NSLOT 8
#endif
#ifdef PCACHE1
#if NSLOT < 1
#error "NSLOT must be at least one (single-page CD fetches)"
#endif
#elif NSLOT < 4 || (NSLOT % 4) != 0
#error "NSLOT must be at least four and a multiple of four (CD fetch batches)"
#endif
/* Export the actual compiled cache configuration to the linker. This tiny
 * retained function is never called; its absolute symbols let all linker
 * variants reject overlap with resident pages or a relocated ragdoll module.
 */
__attribute__((used)) static void ps1_memory_layout(void){
  __asm__ volatile(".globl __ps1_pcache_start\n.set __ps1_pcache_start, %0\n"
                   ".globl __ps1_pcache_end\n.set __ps1_pcache_end, %1\n"
                   : : "i"(PCACHE_ADDR), "i"(PCACHE_ADDR+NSLOT*4096u));
}
static u32 slot_owner[NSLOT], slot_next, cd_ready;
static u8 bcd(u32 v){ return (v/10)*16+v%10; }
static u32 unbcd(u32 v){ return (v>>4)*10+(v&15); }
static u32 cd_dbg;
/* Driver record, read by the test rig: passes restarted, waits that ran out, INT5 answers, sectors with an address outside the request,
   drive resets, interrupts acknowledged before a command, reads that reached the error screen. */
u32 cd_retries, cd_timeouts, cd_int5, cd_badsec, cd_reinits, cd_drained, cd_failed;
u32 cdda_ended;          /* INT4 (end of a CD-DA track) seen by the data driver; hw_cdda.h acts on it */
static u32 cd_mode=0xffu, cd_reading;   /* the drive's mode as last set (Setmode), and "ReadN still running" (the Pause is sent lazily) */
static u8 cd_stat;
#ifndef CDSIM
/* psx-spx "CDROM Controller I/O Ports": 1F801800h = index/status (bit 5 response FIFO not empty, bit 6 DRQSTS data request, bit 7 BUSYSTS);
   index 1: 1F801803h read = interrupt flags (bits 0-2 = INT1..INT5), write = acknowledge (bits 0-4) / bit 6 reset the parameter FIFO;
   index 0: 1F801803h write = request register (bit 7 BFRD: 0 resets the data FIFO, 1 loads the current sector into it).
   Every wait is bounded in TIME by root counter 1 (horizontal blanks, 15734 per second), whatever the CPU, the drive or an emulator's speed-up do. */
static u32 hl_t, hl_acc;
static void hl_start(void){ hl_t=RC1_VAL&0xffff; hl_acc=0; }
static u32 hl_past(void){ u32 t=RC1_VAL&0xffff; hl_acc+=(t-hl_t)&0xffff; hl_t=t; return hl_acc; }
#define HL_RESP 16000u      /* about 1 s: the first response of a command, a further sector of a running read */
#define HL_LONG 80000u      /* about 5 s: a second response (Pause, Init), the first sector after a seek or a spin-up */
static void cd_ack(void){ CD0=1; CD3=0x1f; }
static u32 cd_flags(void){ CD0=1; u32 f=CD3&7; if(f) f=CD3&7; return f; }        /* psx-spx: the first non-zero read may be unstable: read again */
static void cd_result(u8*r){ for(u32 n=0;(CD0&0x20)&&n<16;n++){ u8 b=CD1; if(!n) cd_stat=b; if(r&&n<8) r[n]=b; } }
static u32 cd_waitint(u32 lim){
  hl_start(); for(;;){ u32 f=cd_flags(); if(f) return f; if(hl_past()>lim) break; }
  cd_timeouts++; if(cd_dbg<40){ cd_dbg++; dbg("CD timeout\n"); } return 0; }
/* acknowledge whatever is pending (a sector of a read that is still running, a late second response, the end of a track) before a new command:
   psx-spx: responses queue up behind an unacknowledged one, so a command must never be sent with an interrupt pending */
static void cd_drain(void){
  for(u32 k=0;k<16;k++){ u32 f=cd_flags(); if(!f) return; if(f==4) cdda_ended=1; cd_result(0); cd_ack(); cd_drained++; for(volatile u32 d=0;d<64;d++){} } }
/* send a command: returns the interrupt of its first response (3 = acknowledged, 5 = error, 0 = no answer), the response bytes in r.
   Sector interrupts (INT1) of a read still in progress and INT4 (end of track) that arrive first are acknowledged and skipped. */
static u32 cd_cmd(u8 c,const u8*p,int n,u8*r){
  cd_drain();
  hl_start(); while(CD0&0x80){ if(hl_past()>HL_RESP){ cd_timeouts++; break; } }        /* BUSYSTS: the previous command is still being taken */
  CD0=1; CD3=0x40;                                                                        /* reset the parameter FIFO */
  CD0=0; for(int i=0;i<n;i++) CD2=p[i]; CD1=c;
  for(u32 k=0;k<64;k++){ u32 f=cd_waitint(HL_RESP); cd_result(r); cd_ack();
    if(f==1||f==4){ if(f==4) cdda_ended=1; continue; }
    if(f==5) cd_int5++; return f; }
  return 0; }
/* the second response of Pause / Init / Stop: 2 (complete), 5 (error) or 0; a further INT3 (SwanStation answers Init with INT3, INT3, INT2) or a
   sector that was still on its way is skipped */
static u32 cd_done(u8*r){
  for(u32 k=0;k<64;k++){ u32 f=cd_waitint(HL_LONG); cd_result(r); cd_ack();
    if(f==1||f==3||f==4){ if(f==4) cdda_ended=1; continue; }
    if(f==5) cd_int5++; return f; }
  return 0; }
static u32 cd_pause(void){ u8 r[8]; u32 f=cd_cmd(0x09,0,0,r); if(f==3) f=cd_done(r); cd_reading=0; return f; }   /* Pause: INT3, then INT2 */
static u32 cd_setmode(u8 m){ if(cd_mode==m) return 3; u8 r[8]; u32 f=cd_cmd(0x0e,&m,1,r); cd_mode=(f==3)?m:0xffu; return f; }
static u32 cd_err_on;    /* the CD READ ERROR message is on the screen (from the first failing pass of a read until a read completes) */
static void cd_error_screen(u32 lba); static void cd_error_gone(void);
#endif
#if !defined(CDSIM) || defined(SIMSIO)
#include "hw_pad.h"     /* PS1 pad (SIO0) -> GBA KEYINPUT */
int sv_load(u8*ee,u32 n) RTCOLD;          /* rc7: once, at the first save-chip access */
#include "hw_card.h"    /* memory card + EEPROM save layer */
#endif
#ifndef CDSIM
void cdda_init(void) RTCOLD;              /* rc7: once, at boot */
#include "hw_cdda.h"    /* CD-DA playback */
#else
#include "hw_stub.h"
#endif
#include "hw_radio.h"
#ifdef CDSIM
#define SIMDISC ((const u8*)0x90000000)   /* sim only: disc image mapped at physical 0x10000000 */
static void cd_read(u32 lba,u32 nsec,u8*dst){ memcpy(dst,SIMDISC+lba*2048,nsec*2048); cd_sectors+=nsec; }
static void cd_idle(void){}
static void cd_resume(void){}
#else
/* (re)start the drive in a known state: Init (motor on, all commands aborted; INT3 then INT2), Demute, Setmode A0h (double speed, sectors of
   924h bytes: the address header comes with the data; the data mode is hw_cdda.h cdda_dmode) */
static RTCOLD void cd_init(void){      /* rc7 .rtcold: at the first read and on every fourth failed pass */

  u8 r[8]; IMASK=0; if(cd_ready) cd_reinits++; cd_ready=1;
  cd_ack(); CD0=0; CD3=0x00; CD0=1; CD2=0x1f;                     /* acknowledge everything, data FIFO reset, all interrupt sources enabled (HINTMSK 1Fh) */
  cd_cmd(0x01,0,0,r);                                             /* Getstat */
  if(cd_cmd(0x0a,0,0,r)==3) cd_done(r);                           /* Init */
  cd_cmd(0x0c,0,0,r);                                             /* Demute */
  cd_mode=0xffu; cd_setmode(cdda_dmode()); cd_reading=0;
}
#define CD_RUN 256u                 /* sectors per request in one map; longer requests are split */
#ifndef CD_TRIES
#define CD_TRIES 12u                /* failed passes in a row before the error screen; the read is retried for as long as it takes, never taken as good */
#endif
static u32 cd_map[CD_RUN/32];
/* One Setloc + ReadN pass from the first sector of the request that is still missing.  Every sector the drive delivers is identified by the
   MM:SS:FF address in its own header and stored if it belongs to the request and is still missing, so a sector that the drive skipped (buffer
   overrun with a read speed-up), delivered late or delivered twice can never be taken for another one.
   Returns 0 when the request is complete, -1 on an error answer or a timeout, -2 when the drive went past the request with sectors missing. */
static int cd_pass(u32 lba,u32 n,u8*dst,u32*left){
  u32 first=0; while(first<n&&((cd_map[first>>5]>>(first&31))&1)) first++;
  u32 a=lba+first+150; u8 p[3]={bcd(a/4500),bcd((a/75)%60),bcd(a%75)}, r[8];
  if(cd_cmd(0x02,p,3,r)!=3) return -1;                            /* Setloc */
  if(cd_cmd(0x06,0,0,r)!=3) return -1;                            /* ReadN: INT3 now, then INT1 for every sector */
  cd_reading=1; u32 lim=HL_LONG, got=0, junk=0;
  while(*left){
    u32 f=cd_waitint(lim); cd_result(r);
    if(f!=1){ cd_ack(); if(f==4){ cdda_ended=1; continue; } if(f==5) cd_int5++; return -1; }
    CD0=0; CD3=0x00; CD3=0x80;                                    /* BFRD: reset the data FIFO, then load this sector into it */
    hl_start(); while(!(CD0&0x40)&&hl_past()<200){}               /* DRQSTS: the data is there */
    cd_ack();                                                     /* psx-spx order: request the data, acknowledge, then read it */
    u8 h[12]; for(int i=0;i<12;i++) h[i]=CD2;                     /* MM SS FF mode, then (mode 2) the sub-header */
    u32 s=unbcd(h[0])*4500+unbcd(h[1])*75+unbcd(h[2])-150-lba;   /* this sector's index in the request (huge when it lies before it) */
    lim=HL_RESP;
    if(s<n&&!((cd_map[s>>5]>>(s&31))&1)){
      u8*d=dst+s*2048;
      if(h[3]==2){ for(int i=0;i<2048;i++) d[i]=CD2; }           /* mode 2 form 1: the data follows the sub-header */
      else { for(int i=0;i<8;i++) d[i]=h[4+i]; for(int i=8;i<2048;i++) d[i]=CD2; }   /* mode 1: the data follows the 4-byte header */
      cd_map[s>>5]|=1u<<(s&31); (*left)--; got++;
    } else if(s>=n){                                              /* not part of the request */
      cd_badsec++;
      if((got&&s<0x80000000u)||++junk>16){ CD0=0; CD3=0x00; return -2; }   /* past the end with sectors missing (or nothing but strangers) */
    }
    CD0=0; CD3=0x00;                                              /* reset the data FIFO: EDC/ECC are not needed */
  }
  return 0;
}
/* read nsec consecutive 2048-byte sectors starting at disc LBA into dst.  The drive is left reading: cd_idle() (once per presented picture)
   pauses it, so a read that follows at once costs no Pause and no seek back.  CD audio stays held until cd_resume() finds the disc quiet. */
static void cd_read(u32 lba,u32 nsec,u8*dst){
  while(nsec>CD_RUN){ cd_read(lba,CD_RUN,dst); lba+=CD_RUN; nsec-=CD_RUN; dst+=CD_RUN*2048; }
  cdda_hold();                                                    /* a data seek ends CD-DA playback: remember the position, pause */
  if(!cd_ready) cd_init();
  for(u32 i=0;i<CD_RUN/32;i++) cd_map[i]=0;
  if(cd_dbg<12){ cd_dbg++; dbg("cd_read lba "); dec(lba); dec(nsec); dbg("\n"); }
  u32 left=nsec, fails=0;
#ifdef CD_FAILTEST
  /* TEST builds only, never a release: the CD_FAILTEST-th and the (CD_FAILTEST+40)-th data read fail CD_TRIES+4 passes in a row, each failed
     pass a tenth of a second long, so the CD READ ERROR screen comes up twice and is replaced by the next picture each time */
  static u32 ft_reads; u32 ft_left=0; ft_reads++; if(ft_reads==CD_FAILTEST||ft_reads==CD_FAILTEST+40) ft_left=CD_TRIES+4;
#endif
  while(left){
    u32 l0=left; int e=-1;
#ifdef CD_FAILTEST
    if(ft_left){ ft_left--; hl_start(); while(hl_past()<1600u){} } else
#endif
    if(cd_setmode(cdda_dmode())==3) e=cd_pass(lba,nsec,dst,&left);
    if(!e) break;
    if(left<l0) fails=0;
    fails++; cd_retries++;
    if(cd_dbg<40){ cd_dbg++; dbg("CD retry lba "); dec(lba); dec(nsec); dbg("missing "); dec(left); dbg("err "); dec((u32)-e); dbg("stat "); hex(cd_stat); dbg("\n"); }
    cd_pause();
    if((fails&3)==0) cd_init();                                   /* every fourth failed pass in a row: reset the drive */
    if(fails>=CD_TRIES) cd_error_screen(lba);
  }
  cd_sectors+=nsec; cd_rd_gf=g_gframes;
  if(cd_err_on) cd_error_gone();                                  /* the disc reads again: the next picture replaces the message */
}
/* at the start of present(): pause a data read left running since the last picture */
static void cd_idle(void){ if(cd_reading) cd_pause(); }
/* at the end of present(): CD audio held for data reads comes back once the disc has been quiet for a while (hw_cdda.h) */
static void cd_resume(void){ cdda_idle(); }
#endif
#ifdef PCACHE1
/* stage 19: one 4 KiB page (2 sectors) per fetch into the next of NSLOT single-page slots (FIFO replacement).  With the measured resident set
   (t/resident62.txt) the rest of the working set is small, and a single page per seek reads 4 times less than a 16 KiB cluster.
   stage 20: from the first level on (rom_pool, set by present() once the 3D renderer is up) the resident pages and the slots are one pool of
   pool_rp+NSLOT frames with CLOCK replacement: rom_ref[page] is set by every read of a page in RAM and cleared when the hand passes its frame; the victim is
   the first frame under the hand whose page was not read since the last pass.  In a vehicle the level reads 17 pages beyond the resident set in a cycle:
   with 8 FIFO slots each of them came from the CD again about every second guest frame (5.5 fetches per second, 0.6 guest frames/s on SwanStation).
   Boot and the menus before the first level keep the stage 19 behaviour (FIFO over the slots, resident pages kept).  Nothing holds a page pointer across a
   fetch: rom_read resolves every byte, rom_copy and the DMA path one page at a time, ip_rd every access. */
#define RP_MAX 64
static u16 fr_pg[RP_MAX+NSLOT];         /* page+1 held by each frame, 0 = empty: frames 0..pool_rp-1 are resident pages (rompack), then the slots */
static u8 rom_ref[2048];
static u32 rom_pool, pool_rp, pool_hand;
#define ROM_REF(pg) (rom_ref[pg]=1)
static u8 *pool_frame(u32 f){ return f<pool_rp?(u8*)rp_data+f*4096:PCACHE+(f-pool_rp)*4096; }
static __attribute__((noinline)) const u8 *cd_fetch(u32 pg){
  u32 f;
  if(!rom_pool){ f=pool_rp+slot_next; slot_next=(slot_next+1)%NSLOT; }
  else { u32 n=pool_rp+NSLOT; for(;;){ f=pool_hand; pool_hand=f+1<n?f+1:0; u32 o=fr_pg[f]; if(!o||!rom_ref[o-1]) break; rom_ref[o-1]=0; } }
  if(fr_pg[f]) rom_pg[fr_pg[f]-1]=0;
  fr_pg[f]=0; if(f>=pool_rp) slot_owner[f-pool_rp]=0;
  u8 *d=pool_frame(f);
  cd_read(CD_ROM_LBA+pg*2,2,d);
  fr_pg[f]=pg+1; rom_pg[pg]=d; rom_ref[pg]=1;
  if(f>=pool_rp) slot_owner[f-pool_rp]=pg+1;     /* slot_owner (page+1 per slot) stays the rig's view of the 8 slots; fr_pg holds every frame of the pool */
  rom_miss_count++; rom_miss_last=pg<<12;
  return d;
}
#else
#define ROM_REF(pg) ((void)0)
static __attribute__((noinline)) const u8 *cd_fetch(u32 pg){
  u32 base=pg&~3u;                                               /* fetch the aligned 16 KiB cluster (4 pages, 8 sectors) per seek */
  u32 s=slot_next; slot_next=(slot_next+4)%NSLOT;
  for(u32 k=0;k<4;k++){ if(slot_owner[s+k]) rom_pg[slot_owner[s+k]-1]=0; slot_owner[s+k]=0; }
  cd_read(CD_ROM_LBA+base*2,8,PCACHE+s*4096);
  for(u32 k=0;k<4;k++){ u32 q=base+k; if(rom_pg[q]) continue; slot_owner[s+k]=q+1; rom_pg[q]=PCACHE+(s+k)*4096; }
  rom_miss_count++; rom_miss_last=pg<<12;
  return rom_pg[pg];
}
#endif
static inline const u8 *rom_page(u32 pg){ pg&=2047; const u8*p=rom_pg[pg]; if(p){ ROM_REF(pg); return p; } return cd_fetch(pg); }
static u32 rom_byte(u32 off){ return rom_page(off>>12)[off&4095]; }
/* one page lookup (and one reference mark) per access that stays inside its page, and cd_fetch out of line: the hit path of rom_page is a load, a store
   and a test.  With the mark in rom_page, a lookup per byte through an out-of-line rom_page with a full register save made every ROM access of translated
   code slower than rc5's, before the first level too (cold boot to the title menu 81 frames later on SwanStation). */
static u32 rom_read(u32 ea,u32 size){
  u32 off=ea&0x01ffffff, o=off&4095; u32 v=0;
  if(o+size<=4096){ const u8*p=rom_page(off>>12)+o; v=p[0]; if(size>=2) v|=(u32)p[1]<<8; if(size>=4) v|=(u32)p[2]<<16|(u32)p[3]<<24; return v; }
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
#ifndef PRESENT_MENU
#define PRESENT_MENU 2      /* menus: the 2D layer is cheap, present every 2nd guest frame */
#endif
#ifdef SIMKEYS
volatile u32 sim_keys=0x3ff;
#endif
static u32 pad_gba=0x3ff; static void present(void); static void ppu_flush(void); static void pp_dispcnt(u32 v); static int sf3_ok;
/* stage 13 pad path: the pad is polled once per GBA frame in which the guest reads KEYINPUT (lazily, at most once per frame), and again at present() when the guest did not.  pad_latch = OR of the
   raw pad words seen since the last present, so a tap shorter than one present (16 GBA frames) still reaches the radio / map switch / bail-out edge detectors (pad_new_extra, radio_poll). */
static u32 pad_gf=0xffffffffu, pad_latch, pad_lastp, pad_new_extra, pad_gpolls;
static u32 assist_off;
static void pad_frame_poll(void){ pad_gba=pad_poll(); pad_latch|=pad_raw; pad_gpolls++; if(g_gframes<300&&(pad_raw&0x1000)) assist_off=1; }
/* GBA time base (stage 4): io_cyc = GBA cycles (16.78 MHz) since boot, advanced by VCOUNT/DISPSTAT polls (1232 cycles per scanline), by SWI 5 (to the next vblank) and by
   96 cycles per timer/KEYINPUT poll.  Timers are derived from io_cyc (prescaler, cascade, reload) instead of the old +37-per-read counter, which made Payback's
   timed wait loops (title slide show: 0x7000 counts of TM3:TM2) expire after two polls so a key press was never sampled. */
#ifndef TESTTOURCAR
#define TESTTOURCAR 0
#endif
static u32 img_f0;   /* 1 + the GBA frame of the first big image blit (0 = none yet) */
#ifdef KPLAN
#include "kplan.h"       /* KPL[][3] menu plan {frame0,frame1,pressed_mask} (GBA frames from power-on); KPL2[][3] in-level plan (frames since the level clock first runs); CAR_T */
static u32 lvl_f0;
/* stage 13: the menu path depends on the save the game finds in its EEPROM (= the memory card file), so the assist picks one of three recorded plans when the EEPROM has been loaded:
   0 = blank / uninitialised EEPROM (first boot: language and init timeline, name screen), 1 = initialised EEPROM with a profile in slot 1 (no name screen), 2 = initialised EEPROM, slot 1 unused (name screen).
   Holding Triangle during the first 300 GBA frames switches the assist off (manual menus).  Timelines of the three plans were recorded from the stock game in mGBA (mgba/padlog*.py). */
static int plan_sel=-1;     /* img_f0 = 1 + the GBA frame of the first big image the guest blits (0 = none yet): the anchor of plans 1 and 2 */
static void plan_classify(const u8*ee){
  static const u8 HDR[8]={'P','a','y','b','a','c','k','.'}, UN1[16]={0x07,0xa1,0x20,0x76,0x98,0x45,0x10,0x01,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff};
  int hdr=1,un=1; for(int i=0;i<8;i++) if(ee[i]!=HDR[i]) hdr=0; for(int i=0;i<16;i++) if(ee[16+i]!=UN1[i]) un=0;
  plan_sel=!hdr?0:(un?2:1); dbg("ASSIST plan "); dec(plan_sel); dbg(plan_sel==0?"blank save":plan_sel==1?"profile in slot 1":"no profile in slot 1"); dbg("\n"); }
/* stage 16 state-aware title step: the title menu's cursor index lives in guest IWRAM 0x03007e68 (0 = Play game ... 5 = Set language, found by diffing the stock game in mGBA while pressing Down/Up).  The timed
   A of 'Play game' (plan 0: frame 750; plans 1/2: the first entry) is only pressed when the cursor is on Play game; if a real pad press moved it, Up is pulsed (6 of 12 frames, at most 300 frames) until it is back. */
#ifndef KPL_TITLE
#define KPL_TITLE 5
#endif
static u32 tg_a0, tg_ups, tg_shift;   /* tg_shift = frames the title step was delayed by cursor corrections: the rest of the timed path is shifted by the same amount */
static u32 title_gate(u32 t,u32 a){
  if(tg_a0) return t<tg_a0+6?(0x3ff&~1u):0x3ff;
  s32 cur=*(volatile s8*)(IW+0x7e68);
  if(cur>0&&cur<6&&t-a<300){ if((t-a)%12==0){ tg_ups++; dbg("ASSIST title cursor "); dec(cur); dbg("not on Play game: Up\n"); } return ((t-a)%12)<6?(0x3ff&~64u):0x3ff; }
  { static u32 c0; if(tg_ups){ if(!c0) c0=t; if(t<c0+36) return 0x3ff; }   /* the title ignores an A that follows a cursor move too closely (animation): settle first */
    tg_a0=t; tg_shift=t-a; return 0x3ff&~1u; } }
static u32 kplan_keys(u32 f){
#ifdef TESTUNLOCK
  /* TEST-ONLY: unlock all 11 maps in the rampage setup (Payback's progress halfwords at EWRAM 0x020026d0) so the scripted path can pick a city/arena that a blank card does not offer */
  if(!*(volatile u32*)(EW+0x1e00) && f>=TESTUNLOCK) for(int i=0;i<16;i++) *(volatile u16*)(EW+0x26d0+2*i)=5;
#endif
  if(*(volatile u32*)(EW+0x1e00)){ if(!lvl_f0) lvl_f0=f;
#ifdef TESTTOUR
    u32 t=f-lvl_f0; for(u32 i=0;i<NKPL2;i++) if(t>=KPL2[i][0]&&t<KPL2[i][1]) return 0x3ff&~KPL2[i][2];
#endif
    return 0x3ff; }
  if(assist_off) return 0x3ff;
  if(plan_sel<0&&f>=330) plan_sel=0;
  if(plan_sel==0){ if(f>=KPL[KPL_TITLE][0]&&(tg_a0||f<KPL[KPL_TITLE][1]+300)){ u32 r=title_gate(f,KPL[KPL_TITLE][0]); if(r!=0x3ff||f<KPL[KPL_TITLE][1]) return r; }
    { u32 fe=f-tg_shift; for(u32 i=0;i<NKPL;i++) if(i!=KPL_TITLE&&fe>=KPL[i][0]&&fe<KPL[i][1]) return 0x3ff&~KPL[i][2]; } return 0x3ff; }
  /* plans 1/2 (a valid save): the game waits for a key before its first screen and the wait window depends on the save, so A is pulsed (6 of 24 frames) from frame 240 until the first big image is blitted;
     the rest of the path is timed from that moment (relative times recorded from the stock game) */
  if(!img_f0) return (f>=240&&(f%24)<6)?(0x3ff&~1u):0x3ff;
  { const u32 (*T)[3]=plan_sel==1?KPLB:KPLC; u32 n=plan_sel==1?NKPLB:NKPLC; u32 t=f-(img_f0-1);
    if(t>=T[0][0]&&(tg_a0||t<T[0][1]+300)){ u32 r=title_gate(t,T[0][0]); if(r!=0x3ff||t<T[0][1]) return r; }
    { u32 te=t-tg_shift; for(u32 i=1;i<n;i++) if(te>=T[i][0]&&te<T[i][1]) return 0x3ff&~T[i][2]; } return 0x3ff; } }
#endif
/* rc7: io_cyc is the low word of a 64-bit GBA cycle count; io_hi takes its carry wherever io_cyc grows (IO_ADV: adv_lines, which adv_poll and the
   interpreter's raw timer use, and h_vbl), and the timers count from the 64-bit difference to their start (tm_t0h:tm_t0).  TM3:TM2 (TM2 at /1024,
   TM3 cascaded) is then the GBA's 32-bit pair and wraps after 72.8 hours instead of 256 s, when the old 32-bit difference wrapped and the time base the
   game reads went back to 0 (its 1-s waits never ended).  TM0/TM1 at /1 still wrap their counts after 256 s (32-bit counts; Payback reads only TM2/TM3). */
static u32 io_cyc, io_hi, io_acc, tm_t0[4], tm_t0h[4], tm_rl[4], tm_ovb[4], tm_en[4];
#define IO_ADV(c) do{ u32 c_=(c); io_cyc+=c_; if(io_cyc<c_) io_hi++; }while(0)
static void adv_lines(u32 n){ IO_ADV(n*1232); while(n--){ io_vc=io_vc>=227?0:io_vc+1; if(io_vc==160){ g_gframes++; ppu_flush(); if((g_gframes&(sf3_ok?(PRESENT_EVERY-1):(PRESENT_MENU-1)))==0) present(); } } }
static void adv_poll(void){ io_acc+=96; if(io_acc>=1232){ io_acc-=1232; adv_lines(1); } }
static u32 tm_cnt(u32 k,u32*ov){
  u32 ctrl=io[0x102+4*k]|(io[0x103+4*k]<<8); u32 counts;
  if(!(ctrl&0x80)){ *ov=0; return tm_rl[k]&0xffff; }
  if(k>0&&(ctrl&4)){ u32 o; tm_cnt(k-1,&o); counts=o-tm_ovb[k]; }
  else { u32 lo=io_cyc-tm_t0[k], hi=io_hi-tm_t0h[k]-(io_cyc<tm_t0[k]?1u:0u), ps=ctrl&3;     /* 64-bit difference hi:lo, shifted by the prescaler */
    counts=ps==0?lo:ps==1?(lo>>6)|(hi<<26):ps==2?(lo>>8)|(hi<<24):(lo>>10)|(hi<<22); }
  u32 per=0x10000-(tm_rl[k]&0xffff); *ov=counts/per; return (tm_rl[k]+counts%per)&0xffff;
}
static void tm_write_check(void){
  for(u32 k=0;k<4;k++){ u32 ctrl=io[0x102+4*k]|(io[0x103+4*k]<<8); u32 en=(ctrl>>7)&1;
    if(en&&!tm_en[k]){ tm_rl[k]=io[0x100+4*k]|(io[0x101+4*k]<<8); tm_t0[k]=io_cyc; tm_t0h[k]=io_hi; if(k>0){ u32 o; tm_cnt(k-1,&o); tm_ovb[k]=o; } }
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
  if(!ee_init){ for(u32 i=0;i<sizeof ee;i++) ee[i]=0xff; ee_init=1; sv_load(ee,sizeof ee);
#ifdef KPLAN
    plan_classify(ee);
#endif
  }
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
#elif !defined(AUTOKEYS)
 if(pad_gf!=g_gframes){ pad_gf=g_gframes; pad_frame_poll(); io_keys=pad_gba; }
#endif
#ifdef KPLAN
 io_keys=pad_gba&kplan_keys(io_cyc/280896);   /* MENU ASSIST: the stock game's title -> rampage menu path (frames from power-on) OR-ed with the real pad (active low: AND); the in-level plan is TESTTOUR (test only) */
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
  if(off==0&&size>=2){ g_dispcnt_writes++; pp_dispcnt(io16(0)); tick(); }
}
/* ---------------------------------------------------------------- C helpers called from RT_CC */
/* stage 20: a host-form VRAM pointer that runs past the 96 KiB VRAM shadow (0x80199000..: the 3D renderer's code and data) is folded back the way GBA VRAM
   mirrors (128 KiB period, 0x06018000..0x0601FFFF = 0x06010000..0x06017FFF), as a guest-form address would be by g2h(); nothing outside the guest windows is touched */
static u32 vram_over_n;      /* the first fold is reported on the TTY ('overflow' is one of the rig's fault words): the guard hides the damage, not the bug */
static inline u32 vram_over(u32 ea){ if(ea-((u32)VRAM+0x18000u)<0x801b0000u-((u32)VRAM+0x18000u)){ if(!vram_over_n++){ dbg("VRAM shadow overflow folded back "); hex(ea); dbg("\n"); } u32 o=(ea-(u32)VRAM)&0x1ffffu; if(o>=0x18000u) o-=0x8000u; ea=(u32)VRAM+o; } return ea; }
u32 h_memrd(u32 ea,u32 kind){
  static const u8 SZ[5]={1,1,2,2,4}; u32 size=SZ[kind]; u32 v; ea=vram_over(ea);
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
  ea=vram_over(ea);
  if(ea-0x8017f000u<0x400) io_write(ea-0x8017f000u,size,val);
  else if(ea>=0x80180000u&&ea<0x80200000u){ for(u32 k=0;k<size;k++) ((volatile u8*)ea)[k]=val>>(8*k); }
  else if((ea>>24)==13) {}
  else if((ea>>24)==4&&(ea&0xfffffc00u)==0x04000000u) io_write(ea&0x3ff,size,val);
  else if((ea>>24)>=2&&(ea>>24)<=7&&g2h(ea)){ volatile u8*p=g2h(ea); for(u32 k=0;k<size;k++) p[k]=val>>(8*k); }   /* raw guest RAM address on the slow path (see h_memrd) */
  else { dbg("BADWR "); hex(ea); }
  return 0;
}
static void fatal_screen(const char*m,u32 a) __attribute__((noreturn));
static void gpu_panic(const char*m,u32 a){ fatal_screen(m,a); }
extern const u32 COLD_HOST; extern const u8 coldtab[];
#ifndef SF_WORLD_ADDR
#define SF_WORLD_ADDR 0x800C9000u
#endif
#ifndef SF_WORLD_LO
#define SF_WORLD_LO SF_WORLD_ADDR
#endif
_Static_assert(SF_WORLD_LO == SF_WORLD_ADDR, "runtime and renderer world bounds must match");
static int sf3_ok; static u32 sf3_cfl, sf3_cfl_clk; static u32 sf3_tried, sf3_left, sf3_left_clk;   /* rc7: deferred start done; the renderer went off because the guest left a level (at that level clock) */   /* sf3_cfl: a cold load hit the renderer data (renderer off) while the level clock was sf3_cfl_clk; present() restores the renderer when the level runs again */
#ifndef COLDGROUPS
#define COLDGROUPS 64
#endif
#ifdef CDSIM
/* The discovery translator's COLD_GAP must begin at the first reserved byte,
   including PPU/veneer scratch before the draw ring and guest RAM. */
static int sim_cold_overlap(u32 lo,u32 hi){ return hi>(u32)__ppu_start && lo<0x80200000u; }
#endif
static u8 cold_loaded[COLDGROUPS]; static u32 cold_loads, cold_calls, cold_conflicts; static u32 sf3_retry, last_cold_pres, sf3_clk0;   /* stage 12: renderer switched off by an overlay load (pause menu code) comes back once the level clock runs again (pause over) and no cold group was loaded for 6 presents */
static void flush_icache(void){ register u32 t1 __asm__("$9")=0x44;   /* kernel FlushCache A(44h): argument area and clobbers as dbgc() */
  __asm__ volatile("addiu $29,$29,-16\n li $8,0xA0\n jalr $8\n nop\n addiu $29,$29,16":"+r"(t1)::"$1","$2","$3","$4","$5","$6","$7","$8","$10","$11","$12","$13","$14","$15","$24","$25","$31","hi","lo","memory"); }
/* RT_MISS: a direct call/jump/function pointer reached a guest function that is not in the resident blob.  Overlay loader:
   find it in the cold table, read the 16 KiB groups of COLD.BIN that cover the function (and its out-of-line stubs) into their fixed
   home addresses, flush the I-cache, and return the host entry for RT_MISS to tail-jump to. */
/* cold_find: host entry of a function in the cold table (its groups are loaded from the disc), 0 if the address is not in the table */
static u32 cold_find(u32 addr){
  u32 g=addr&~1u; const u32*ct=(const u32*)coldtab; u32 n=ct[0]; const u32*r=ct+1; u32 lo=0,hi=n; cold_calls++;
  while(lo<hi){ u32 m=(lo+hi)>>1; u32 v=r[m*4]; if(v==g){ lo=m; goto found; } if(v<g) lo=m+1; else hi=m; }
  return 0;
found:;
  u32 host=r[lo*4+1], hs=r[lo*4+2], he=r[lo*4+3];
  u32 g0=(hs-COLD_HOST)>>14, g1=(he-1-COLD_HOST)>>14, loaded=0;
  /* stage 12: a tiny, position-independent cold function (the bx rN veneers, 12 bytes) whose group lies inside the renderer's data window used to switch the 3D renderer off when the HUD/text code reached it
     in a level (the group load would overwrite the world).  Its few words are read from the disc and kept in a small resident table instead; the group is not loaded. */
  if(sf3_ok && g0==g1 && he-hs<=16 && he>SF_WORLD_LO && hs<0x8011b200u && !cold_loaded[g0]){
    static u32 vene[24][4] __attribute__((aligned(16))); static u32 vene_g[24], nvene;
    u32*const vtmp=(u32*)__veneer_scratch;   /* dedicated linker-reserved 4 KiB, outside PPU CLUT/row buffers and renderer code */
    for(u32 q=0;q<nvene;q++) if(vene_g[q]==g) return (u32)vene[q]+(host-hs);
    if(nvene<24){ u32 dst=COLD_HOST+g0*16384, off=hs-dst, sec=off>>11, left=CD_COLD_PAGES*2-g0*8-sec; cd_read(CD_COLD_LBA+g0*8+sec,left<2?left:2,(u8*)vtmp);
      const u32*src=(const u32*)((u8*)vtmp+(off&2047)); u32 nw=(he-hs)>>2, ok=1; for(u32 q=0;q<nw;q++){ u32 op=src[q]>>26; if(op==1||(op>=4&&op<=7)) ok=0; }
      if(ok){ for(u32 q=0;q<4;q++) vene[nvene][q]=q<nw?src[q]:0; vene_g[nvene]=g; nvene++; flush_icache(); dbg("VENEER resident copy "); hex(g); dbg("\n"); return (u32)vene[nvene-1]+(host-hs); } } }
  for(u32 k=g0;k<=g1;k++) if(!cold_loaded[k]){ u32 lo=COLD_HOST+k*16384, hi=lo+16384;      /* only a group that would really be loaded can hit the renderer's data (stage 7: groups already in memory used to trigger this too) */
    if(sf3_ok && (hi>SF_WORLD_LO && lo<0x8011b200u)) {
#ifdef COLD_RECOVER     /* stage 12/13 alternative: load the group, renderer off, restored when the level clock runs again (present()) */
      dbg("SF3 CONFLICT cold load over renderer data, renderer off: "); hex(addr); dbg("\n"); sf3_ok=0; sf3_retry=1; sf3_cfl=1; sf3_cfl_clk=*(volatile u32*)(EW+0x1e00); } }
#else                   /* stage 13 cities: this group would be loaded over the renderer's world window: do not load it, the interpreter runs the function from the ROM image instead (h_miss, ip_lookup); the renderer stays on */
      static u32 nconf; cold_conflicts++; if(nconf<24){ nconf++; dbg("SF3 cold group over renderer data: interpreting "); hex(addr); dbg("\n"); } return 0; } }
#endif
  for(u32 k=g0;k<=g1;k++) if(!cold_loaded[k]){
    u32 left=CD_COLD_PAGES*2-k*8, dst=COLD_HOST+k*16384;
#ifdef CDSIM
    if(sim_cold_overlap(dst,dst+16384)){      /* sim-only COLD_GAP bytes are zeros; preserve linker-reserved scratch and guest RAM even when a CD group straddles the gap */
      static u8 gtmp[16384]; cd_read(CD_COLD_LBA+k*8,left<8?left:8,gtmp);
      for(u32 q=0;q<16384;q++){ u32 a=dst+q; if(!sim_cold_overlap(a,a+1)) ((volatile u8*)a)[0]=gtmp[q]; } }
    else
#endif
    cd_read(CD_COLD_LBA+k*8,left<8?left:8,(u8*)dst);
    cold_loaded[k]=1; cold_loads++; loaded=1; }
  if(loaded){ last_cold_pres=g_pres; flush_icache(); dbg("COLD load "); hex(addr); dec(g0); dec(g1); dbg("\n"); }
  return host;
}
#ifdef NO_INTERP
static const u32 ip_enters = 0;  /* diagnostic value for the full-cold simulator */
u32 h_miss(u32 addr){ u32 h=cold_find(addr); if(h) return h; gpu_panic("RT_MISS guest code not in cold set: ",addr); return 0; }
#else
#include "interp_glue.h"
/* RT_MISS: overlay loader, else the interpreter (stage 8: nothing halts) */
u32 h_miss(u32 addr){
  ov_sync();
  if(((addr&~1u)-OV_BASE)<OV1_SIZE){ if(!ov_res()) return film_miss(addr); u32 h=hot_lookup(addr&~1u); if(h) return h; }   /* intro fix: overlay area (interp_glue.h) */
  u32 h=cold_find(addr); if(h) return h; interp_target=addr&~1u; return (u32)interp_enter; }
#endif

/* ---------------------------------------------------------------- GPU
   GP0 handshake (psx-spx "GPU Status Register", "Ready Bits"): GPUSTAT bit 26 is set when the GPU wants a COMMAND word and stays clear while it
   waits for the parameters or the data of the command it has.  So bit 26 is waited for before command words only (gp0c); the parameters of a
   command (at most 8 here, the command FIFO holds 16 words) follow without a wait (gp0p).  VRAM data of GP0(A0h) goes through DMA2 in block
   mode ("DMA2 in Continuous Mode - VRAM transfers"; at most 10h words per block for the v0 GPU; DMA direction GP1(04h)=2 set up first: the
   request is "GP0 write FIFO empty").  GP0(E3h..E5h) bypass the FIFO ("use them only if you are sure that the FIFO is empty"): gp0e waits for
   bit 26 and bit 28 (write FIFO empty).  Reading VRAM (GP0(C0h)) polls bit 27 per word (ppu12.h). */
#define D2_MADR (*(volatile u32*)0x1F8010A0)
#define D2_BCR  (*(volatile u32*)0x1F8010A4)
#define D2_CHCR (*(volatile u32*)0x1F8010A8)
#define DPCR    (*(volatile u32*)0x1F8010F0)
static inline __attribute__((always_inline)) void gp0c(u32 w){ while(!(GP1&0x04000000)){} GP0=w; }                /* command word */
static inline __attribute__((always_inline)) void gp0p(u32 w){ GP0=w; }                                            /* parameter word */
static inline __attribute__((always_inline)) void gp0e(u32 w){ while((GP1&0x14000000)!=0x14000000){} GP0=w; }     /* E3h..E5h: FIFO empty */
/* every command with two parameters (fill 02h, rectangle 60h, VRAM load A0h, VRAM store C0h) goes through this one out-of-line sender: one wait,
   before the command word, then the parameters.  (It also keeps every caller free of a second wait between two such commands.) */
static __attribute__((noinline)) void gp0_2(u32 c,u32 p1,u32 p2){ gp0c(c); gp0p(p1); gp0p(p2); }
/* the GPU has everything and has drawn it: DMA2 finished, ready for a command and write FIFO empty */
static void gpu_idle(void){ while(D2_CHCR&0x01000000){} while((GP1&0x14000000)!=0x14000000){} }
/* nw data words from RAM to GP0 (after a GP0(A0h) and its two parameters): DMA2 blocks of 16 words, a remainder as one shorter block */
static void gpu_dma(const void*src,u32 nw){
  u32 a=(u32)src&0xffffff, big=nw&~15u, r=nw&15u;
  if(big){ D2_MADR=a; D2_BCR=((big>>4)<<16)|16; D2_CHCR=0x01000201; while(D2_CHCR&0x01000000){} }
  if(r){ D2_MADR=a+big*4; D2_BCR=(1u<<16)|r; D2_CHCR=0x01000201; while(D2_CHCR&0x01000000){} } }
#define XY(x,y) (((u32)(y)<<16)|((x)&0xffff))
static int cur_oy, disp_on;
static int buf;           /* present() draws into the buffer at y = buf?240:0 and toggles buf after flipping it in */
static void rect(int x,int y,int w,int h,u32 rgb){ if(w<=0||h<=0) return; gp0_2(0x60000000|rgb,XY(x,y+cur_oy),XY(w,h)); }
#include "font.h"
static int chidx(char c){ if(c>='0'&&c<='9') return c-'0'; if(c>='a'&&c<='z') c-=32; if(c>='A'&&c<='Z') return 10+c-'A'; return -1; }
static RTCOLD void text(int x,int y,const char*s,int sc,u32 rgb){     /* rc7 .rtcold: error screens only (and the PPU_DEBUG page) */
  for(;*s;s++,x+=4*sc){ int i=chidx(*s); if(i<0) continue; u16 g=F35[i];
    for(int r=0;r<5;r++) for(int c=0;c<3;c++) if(g&(1<<(14-(r*3+c)))) rect(x+c*sc,y+r*sc,sc,sc,rgb); }
}
static void num(int x,int y,u32 v,int sc,u32 rgb){ char b[12]; int n=0; if(!v) b[n++]='0'; while(v){b[n++]='0'+v%10; v/=10;} char t[12]; for(int i=0;i<n;i++) t[i]=b[n-1-i]; t[n]=0; text(x,y,t,sc,rgb); }
/* display set up but OFF until the first finished picture is flipped in (flip_to); both 320x240 buffers black meanwhile */
static RTCOLD void gpu_init(void){
  GP1=0x00000000;                                                 /* reset: display off, DMA off, drawing settings cleared */
  GP1=0x03000001;                                                 /* display off */
  GP1=0x06000000|(0x260|((0x260+320*8)<<12)); GP1=0x07000000|(0x10|((0x10+240)<<10)); GP1=0x08000001;   /* 320x240 NTSC, 15 bit */
  GP1=0x04000002; DPCR|=0x00000800;                               /* DMA direction CPU -> GP0, DMA2 on */
  GP1=0x05000000;
  gp0_2(0x02000000,XY(0,0),XY(320,480));                          /* fill both buffers black */
  gpu_idle(); disp_on=0;
}
static void vsync(void){ ISTAT=~1u; for(volatile int n=0;n<400000;n++){ if(ISTAT&1) break; } ISTAT=~1u; }
/* show the buffer at (0,o) once everything drawn into it is finished, at the next vertical blank; the display comes on with the first one */
static void flip_to(int o){ gpu_idle(); vsync(); GP1=0x05000000|((u32)o<<10); if(!disp_on){ disp_on=1; GP1=0x03000000; } }
/* rc7: a fault the runtime cannot go on from (a boot-time check of the intro fix, an interpreter limit): the message on the TTY and on the screen (both
   buffers, display on), then stop; never a silent hang on a black or frozen picture */
static RTCOLD void fatal_screen(const char*m,u32 a){
  dbg(m); hex(a); dbg("\n");
  char h[9]; for(int i=0;i<8;i++){ u32 d=(a>>(28-4*i))&15; h[i]=(char)(d<10?'0'+d:'A'+d-10); } h[8]=0;
  while(D2_CHCR&0x01000000){} GP1=0x01000000;                     /* let a running DMA end, then drop any half-sent GPU command */
  for(int b=0;b<2;b++){ cur_oy=b*240;
    gp0_2(0x02600000,XY(0,cur_oy),XY(320,240)); gpu_idle();
    gp0c(0xE1000000|(1<<10)); gp0e(0xE3000000|((u32)cur_oy<<10)); gp0e(0xE4000000|319u|((u32)(cur_oy+239)<<10)); gp0e(0xE5000000);
    text(64,72,"PORT ERROR",4,0xffffff); text(4,124,m,2,0xc0c0ff); text(128,152,h,2,0xffffff); }
  gpu_idle(); GP1=0x05000000; GP1=0x03000000; disp_on=1;
  for(;;){}
}
#ifndef CDSIM
/* a read that keeps failing: say so on the screen and go on retrying; the data is never taken as good.  The message goes into both buffers and
   the display shows the buffer present() is NOT about to draw into (y = buf?0:240), so the next picture is drawn out of view and flipped in as
   usual once the disc reads again.  Every failure episode shows it (cd_err_on is cleared when a read completes); cd_failed counts the episodes. */
static RTCOLD void cd_error_screen(u32 lba){
  if(cd_err_on) return; cd_err_on=1; cd_failed++;
  dbg("CD READ ERROR lba "); dec(lba); dbg("stat "); hex(cd_stat); dbg("retrying\n");
  while(D2_CHCR&0x01000000){} GP1=0x01000000;                     /* let a running DMA end, then drop any half-sent GPU command */
  for(int b=0;b<2;b++){ cur_oy=b*240;
    gp0_2(0x02000060,XY(0,cur_oy),XY(320,240)); gpu_idle();
    gp0c(0xE1000000|(1<<10)); gp0e(0xE3000000|((u32)cur_oy<<10)); gp0e(0xE4000000|319u|((u32)(cur_oy+239)<<10)); gp0e(0xE5000000);
    text(64,96,"CD READ ERROR",4,0xffffff); text(88,136,"CHECK THE DISC",2,0xc0c0ff); }
  gpu_idle(); GP1=0x05000000|((u32)(buf?0:240)<<10); GP1=0x03000000; disp_on=1; cur_oy=buf?240:0;
}
static void cd_error_gone(void){ cd_err_on=0; dbg("CD reads again\n"); }
#endif
static u32 last_dl, last_rc, logic_lines, max_lines, tot_lines, nfr_meas;
#ifndef PPU_SF3HUD
#define PPU_SF3HUD 0
#endif
#include "ppu12.h"
static u32 rd32g(u32 off){ return rom_read(0x08000000+off,4); }
/* ---------------------------------------------------------------- stage 3: the PS1 city renderer (sf3.c) driven from Payback's state */
#include "../include/sf_entity.h"
extern u8 sf3_plook, sf3_ppol; extern u32 sf3_mt; extern int sf3_sin(int);
extern int rd_spawn(s32 ux,s32 uy,s32 uz,int yaw,s32 vx,s32 vy,s32 vz,int id,u32 shirt); extern void rd_set_car(int on,s32 ux,s32 uy,s32 uz,int h16,s32 vx,s32 vy,s32 vz); extern void rd_step_all(const void*w,s32 cx,s32 cz); extern int rd_active(void); extern int rd_has(int id); extern void rd_drop(int id); extern void rd_clear(void); extern u32 rd_spawned, rd_steps, rd_hurt_max, rd_rejected; extern const char sf3_rpw[]; extern int sf3_hide_player;
extern int sf3_init(void); extern u32 sf3_first_map; extern int sf3_map_load(u32 n); extern u32 sf3_map_cur, sf3_map_x, sf3_map_y, sf3_map_z, sf3_map_loads; extern int sf3_frame(int oy,s32 px,s32 py,s32 pz,int heading,int pkind,const SfEnt*ents,int nents,int hud);
extern s32 sf3_score, sf3_hp, sf3_clock; extern u32 sf3_stat_eng, sf3_stat_prim, sf3_stat_ovf, sf3_stat_lod, sf3_frames; extern u32 sf3_ph[8], sf3_cnt[32], sf3_hash;
void sf3_cd_read(u32 lba,u32 nsec,u8*dst){ cd_read(lba,nsec,dst); }
#ifndef PRINT_EVERY_SF3
#define PRINT_EVERY_SF3 63
#endif
static u32 st3_render, st3_hud_only, st3_lines_sum, st3_lines_max, st3_gather_lines, st3_id5;
static SfEnt ents3[40]; static s32 map_dx,map_dz,map_dy;
static int s7_reset;        /* rc7: set when the guest leaves a level: the next level's first frame starts the ragdoll events afresh (stage7_pre) */
#ifndef HERO_DOLL_TICKS
#define HERO_DOLL_TICKS 90  /* rc7: the player's own doll (a bail-out) hides him for at most 3 s of game time (level clock ticks, 30 a second) */
#endif
#ifdef SF3_DEMO
static const s16 S4[18]={0,1608,3196,4756,6270,7723,9102,10394,11585,12665,13623,14449,15137,15679,16069,16305,16384,16384};   /* sin(k*pi/32) in 1.14 */
static int sin_t(int a){ a&=0xffff; int q=a>>14, x=a&16383; if(q&1) x=16384-x; int k=x>>10, r=x&1023; int v=S4[k]+(((S4[k+1]-S4[k])*r)>>10); return (q&2)?-v:v; }
static int cos_t(int a){ return sin_t(a+16384); }
#endif
/* the level's player: Payback's entity list (IWRAM 0x03000c60, last index 0x0300000c), controlled index (EWRAM 0x02001db8), map 0x02001d40, clock 0x02001e00 */
/* an entity pointer in the guest's IWRAM table: a raw GBA address (0x02xxxxxx, as in the mGBA snapshots) or, in the translated guest, the host address inside the EWRAM window (stage 4: the translated game stores host pointers) */
static const u8 *entp(u32 p){ if((p>>24)==2) return EW+(p&0x3ffff); if(p>=(u32)EW&&p<(u32)EW+0x40000) return (const u8*)p; return 0; }
static s32 g3_map=-1;      /* the guest's map id as gather3 last read it */
static int gather3(s32*px,s32*py,s32*pz,int*hd,int*pk,int*nents){
#ifdef SF3_DEMO
  /* renderer test without a level: a car drives a scripted route through Freedom City (heading 0 = +z) */
  { static s32 x=9728, z=2700; static int h=0; u32 f=st3_render; int ph=f%240; x+=(sin_t(h)*40)>>14; z+=(cos_t(h)*40)>>14;
    if(ph>=40&&ph<70) h+=300; if(ph>=110&&ph<150) h-=300; if(ph>=190&&ph<210) h+=300; h&=0xffff;
    *px=x; *pz=z; *py=0; *hd=h; *pk=1; *nents=0; return 1; }
#endif
  { s32 gm=*(volatile s16*)(EW+0x1e66); if(*(volatile u32*)(EW+0x1e00)==0 || gm<0 || gm>10) return 0; g3_map=gm; }      /* in a level, on one of Payback's 11 maps (the grid id the level loader 0x0803c580 was given, EWRAM 0x02001e66; rampage: = the setup's city/map 0x02001d40, 0 Freedom City, 1 Los Francos, 2 Corona, 3..10 the multiplayer maps; the story levels' own grid, 0x02001d40 stays 0 there) */
  s32 nl=*(volatile s16*)(IW+0xc), ci=*(volatile s16*)(EW+0x1db8); if(nl<0||nl>100||ci<0||ci>nl) return 0;
  const u32*tab=(const u32*)(IW+0xc60); const u8*e=entp(tab[ci]); if(!e) return 0;
  *px=*(const s32*)(e+4)>>1; *pz=*(const s32*)(e+8)>>1; *py=((19904-(s32)*(const u16*)(e+0xc))>>1);
  *hd=((s32)*(const s16*)(e+0x12)*11651>>10)&0xffff;
  sf3_score=*(const s32*)(e+0x90); sf3_hp=*(const s16*)(e+0x68); sf3_clock=*(volatile u32*)(EW+0x1e00)/30;
  u32 d=*(const u32*)(e+0x1c); *pk=0; if(d-0x08354af4u<128*0x3c) *pk=(rom_byte((d+0x26)&0x01ffffff)==0);
  sf3_plook=0; sf3_ppol=0; if(d-0x08354af4u<128*0x3c){ sf3_plook=(u8)(rom_byte((d+0x38)&0x01ffffff)-0x1a); sf3_ppol=rom_byte((d+0x27)&0x01ffffff)?1:0; }
  int n=0;
  for(s32 i=0;i<=nl&&n<40;i++){ if(i==ci) continue; const u8*o=entp(tab[i]); if(!o) continue;
    u32 dd=*(const u32*)(o+0x1c); if(dd-0x08354af4u>=128*0x3c) continue; u32 cl=rom_byte((dd+0x26)&0x01ffffff); if(cl>1) continue;
    s32 ox=*(const s32*)(o+4)>>1, oz=*(const s32*)(o+8)>>1; if(ox-*px>9000||*px-ox>9000||oz-*pz>9000||*pz-oz>9000) continue;
    ents3[n].x=ox; ents3[n].z=oz; ents3[n].y=(19904-(s32)*(const u16*)(o+0xc))>>1; ents3[n].yaw=((s32)*(const s16*)(o+0x12)*11651>>10)&0xffff; ents3[n].kind=cl?1:0; ents3[n].spare=(u8)i; ents3[n].look=(u8)(rom_byte((dd+0x38)&0x01ffffff)-0x1a); ents3[n].pol=rom_byte((dd+0x27)&0x01ffffff)?1:0; n++; }
  *nents=n; return 1;
}
static void stage7_pre(s32*pxp,s32*pyp,s32*pzp,int*hdp,int*pkq,int*nep){
  s32 px=*pxp,py=*pyp,pz=*pzp; int hd=*hdp,pk=*pkq,ne=*nep;
      { /* stage 13 map follow + stage 7 map switch: the world drawn is the guest's own map (EWRAM 0x02001d40, loaded from the CD when a level starts on another map);
           L2 / R2 = previous / next of the 11 maps as a viewer override (loaded from the CD (SF3M.BIN), the view moves to that map's start point, the guest keeps running its own map);
           a new level on another map (the guest's id changes) drops the override */
#ifdef TESTPOKE
        if(pad_new_extra&32){ int bq=-1; s32 bd=0x7fffffff; for(int q=0;q<ne;q++){ if(ents3[q].kind!=0) continue; s32 dx=ents3[q].x-px, dz=ents3[q].z-pz; if(dx<0) dx=-dx; if(dz<0) dz=-dz; if(dx+dz<bd){ bd=dx+dz; bq=q; } }
          if(bq>=0){ *(volatile u16*)(EW+0x1db8)=ents3[bq].spare; dbg("TEST-ONLY: Select -> controlled entity index set to "); dec(ents3[bq].spare); dbg("(nearest car, dist "); dec(bd); dbg(")\n"); } }
#endif
        static s32 ovr=-1, lastg=-1; u32 nw=pad_new_extra; int req=-1;
        if(g3_map!=lastg){ lastg=g3_map; ovr=-1; }
        int cur=sf3_map_loads?(int)sf3_map_cur:-1, base=ovr>=0?ovr:(int)g3_map, usr=0;
        if(nw&4){ req=(base+1)%11; usr=1; } else if(nw&2){ req=(base+10)%11; usr=1; }
#ifdef MAPTEST
        { static u32 mt; if(++mt==MAPTEST_AT){ req=MAPTEST_TO; usr=1; } }
#endif
        if(!usr&&cur!=base) req=base;       /* follow: the guest's map is not the one in the renderer */
        { static s32 chk=-2; if(g3_map!=chk){ chk=g3_map; u32 gp=*(volatile u32*)(EW+0x7124); int gi=-1; for(int q=0;q<11;q++) if(rom_read(0x081aa8b4+4*q,4)<=gp) gi=q;   /* the loader leaves its read pointer at the end of the grid's data: the last table entry at or below it is the grid it decoded */
            dbg("GRIDCHK id "); dec(g3_map); dbg("PB_MAP "); dec(*(volatile s16*)(EW+0x1d40)); dbg("decoded grid by pointer "); dec(gi); dbg(gi==g3_map?"match":"MISMATCH"); dbg("\n"); } }
        if(req>=0){ u32 c0=cd_sectors; u32 m0=RC1_VAL; int r=sf3_map_load(req); dbg(usr?"MAPCHANGE to ":"MAPFOLLOW to "); dec(req); dbg("rc "); dec(r); dbg("cd sectors "); dec(cd_sectors-c0); dbg("hlines "); dec((RC1_VAL-m0)&0xffff); dbg("start "); dec(sf3_map_x); dec(sf3_map_y); dec(sf3_map_z); dbg("guest map "); dec(g3_map); dbg("guest pos "); dec(px); dec(pz); dbg("\n");
          if(r==0){ if(usr){ ovr=(req==g3_map)?-1:req; } if(ovr>=0){ map_dx=sf3_map_x-px; map_dz=sf3_map_z-pz; map_dy=sf3_map_y; } else { map_dx=map_dz=map_dy=0; } } } }
      px+=map_dx; pz+=map_dz; py+=map_dy; for(int q=0;q<ne;q++){ ents3[q].x+=map_dx; ents3[q].z+=map_dz; ents3[q].y+=map_dy; }
      { extern int sf3_floor_at(int,int); int fl=sf3_floor_at(px,pz); if(fl<60000&&py<fl-1024) py=fl;      /* Little Chicago (guest map 4): the guest's start pose is 2048 units below this world's ground (camera under the floor); lift it to the floor */
        for(int q=0;q<ne;q++){ int f2=sf3_floor_at(ents3[q].x,ents3[q].z); if(f2<60000&&ents3[q].y<f2-1024) ents3[q].y=f2; } }
      { /* stage 7 ragdolls: events from the guest's state (bail-out = the driver leaves a moving car, or Triangle in a car; hit = a pedestrian within 3 m of the player's car doing > 4 m/s), the solver steps in renderer units */
        static int pkp=-1; static s32 ppx,ppy,ppz,pvx,pvy,pvz,pmap=-1; static u8 conv[128]; static u32 cdn[128], nfr, pclk, hero_clk;
        /* rc7: velocities (m/s Q20) over GAME time: the position change since the previous gathered frame divided by the level clock ticks between
           the two (30 a second; 491520 = one unit per tick).  The solver's events assumed one 3D frame per tick; at this port's 3D frame rate (one
           every 2 to 9 ticks) a car crawling against a tree read as a bail-out at 300 m/s, and the doll hid the man for some 300 frames (minutes).
           No movement at all across a jump of more than 4000 units or 90 ticks (respawn, rig pokes), a new map, or the first frame of a new level
           (s7_reset; the level clock starts again there, so dt is out of range too). */
        u32 clk=*(volatile u32*)(EW+0x1e00), dt=clk-pclk; pclk=clk;
        s32 ddx=px-ppx, ddy=py-ppy, ddz=pz-ppz;
        int jump=!nfr||pmap!=(s32)sf3_map_cur||s7_reset||dt>90||ddx>4000||ddx<-4000||ddy>4000||ddy<-4000||ddz>4000||ddz<-4000;
        if(!dt) dt=1;
        s32 vx=jump?0:ddx*491520/(s32)dt, vy=jump?0:ddy*491520/(s32)dt, vz=jump?0:ddz*491520/(s32)dt;
        if(jump){ pkp=-1; if(s7_reset){ s7_reset=0; for(int q=0;q<128;q++) cdn[q]=0; } }
        pmap=sf3_map_cur; nfr++;
        if(vy>8*1048576) vy=8*1048576; if(vy<-8*1048576) vy=-8*1048576;
        u32 tri=pad_new_extra&1; s32 sp=(vx<0?-vx:vx)+(vz<0?-vz:vz);
        if((pkp==1&&pk==0&&(((pvx<0?-pvx:pvx)+(pvz<0?-pvz:pvz))>2621440)) || (pk==1&&tri&&sp>1048576)){
          s32 bx=pk==1?vx:pvx, bz=pk==1?vz:pvz; int k=rd_spawn(px,py,pz,hd,bx,3*1048576,bz,200,0x2040D0); if(k>=0) hero_clk=clk; dbg("DOLL bail-out slot "); dec(k); dbg("speed "); dec(((bx<0?-bx:bx)+(bz<0?-bz:bz))>>20); dbg("\n"); }
        if(pk==1&&sp>4*1048576){ for(int q=0;q<ne;q++){ if(ents3[q].kind!=1) continue; int id=ents3[q].spare&127; if(cdn[id]) continue;
            s32 dx=ents3[q].x-px, dz=ents3[q].z-pz; if(dx<0) dx=-dx; if(dz<0) dz=-dz; if(dx+dz>270) continue;
            int k=rd_spawn(ents3[q].x,ents3[q].y,ents3[q].z,ents3[q].yaw,vx*9/10,vy+2*1048576+(sp>>3),vz*9/10,id,0x30A0E0+(id*0x13A7C1&0x7f7f7f)); if(k>=0){ cdn[id]=420; dbg("DOLL hit ped "); dec(id); dbg("slot "); dec(k); dbg("speed "); dec(sp>>20); dbg("\n"); } } }
#ifdef DOLLTEST
        if(nfr==DOLLTEST_AT){ int k=rd_spawn(px,py,pz,hd,3*1048576,3*1048576,2*1048576,200,0x2040D0); if(k>=0) hero_clk=clk; dbg("TEST-ONLY forced doll slot "); dec(k); dbg("\n"); }
#endif
        for(int q=0;q<128;q++) if(cdn[q]) cdn[q]--;
        { int m=0; for(int q=0;q<ne;q++){ if(ents3[q].kind==1&&cdn[ents3[q].spare&127]) continue; ents3[m++]=ents3[q]; } ne=m; }
        if(rd_has(200)&&clk-hero_clk>HERO_DOLL_TICKS){ rd_drop(200); dbg("DOLL player released, ticks "); dec(clk-hero_clk); dbg("\n"); }   /* rc7: the solver steps once a 3D frame: at this port's frame rate its own release (asleep 10 s of solver time) took minutes */
        sf3_hide_player=rd_has(200);
        rd_set_car(pk==1,px,py,pz,hd,vx,vy,vz);
        if(rd_active()){ u32 d0=RC1_VAL; rd_step_all(sf3_rpw,px,pz); u32 dl=(RC1_VAL-d0)&0xffff; static u32 dmax,dsum,dn; dn++; dsum+=dl; if(dl>dmax) dmax=dl; if((dn&15)==1){ dbg("RD lines "); dec(dl); dbg("max "); dec(dmax); dbg("avg "); dec(dsum/dn); dbg("active "); dec(rd_active()); dbg("steps "); dec(rd_steps); dbg("hurtmax "); dec(rd_hurt_max); dbg("\n"); } }
        pkp=pk; ppx=px; ppy=py; ppz=pz; pvx=vx; pvy=vy; pvz=vz; }
  *pxp=px;*pyp=py;*pzp=pz;*hdp=hd;*pkq=pk;*nep=ne; }
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
      if(ok){ stage7_pre(&px,&py,&pz,&hd,&pk,&ne);
      u32 r0=RC1_VAL; sf3_frame(oy,px,py,pz,hd,pk,ents3,ne,1); u32 dl=(RC1_VAL-r0)&0xffff; st3_render++; st3_lines_sum+=dl; if(dl>st3_lines_max) st3_lines_max=dl;
        if(f==23){ dbg("SNAP "); dec(k); dbg(names[k]); dbg(" pos "); dec(px); dec(py); dec(pz); dbg("hd "); dec(hd); dbg("veh "); dec(pk); dbg("ents "); dec(ne); dbg("eng "); dec(sf3_stat_eng); dbg("prim "); dec(sf3_stat_prim); dbg("ovf "); dec(sf3_stat_ovf); dbg("lod "); dec(sf3_stat_lod); dbg("\n"); } }
      else if(f==0){ dbg("SNAP "); dec(k); dbg("gather failed\n"); }
      flip_to(oy);
    }
  }
}
#endif
void h_vbl(void){
#ifdef KPLAN
  { static u32 poked; if(TESTTOURCAR&&!poked&&CAR_T&&lvl_f0&&io_cyc/280896-lvl_f0>=CAR_T){ poked=1; *(volatile u16*)(EW+0x1db8)=6; dbg("TEST-ONLY: controlled entity index set to 6 (car)\n"); } }
#endif
  { u32 n=(160+228-io_vc)%228; if(!n) n=228; IO_ADV(n*1232); } io_vc=160; io16w(0x202,io16(0x202)|1); tick(); g_nvbl++; g_gframes++; ppu_flush();
  present();
}
#ifdef PADDBG
/* test log (stage 13): the controlled entity as Payback holds it, once per present while a level runs.  GS gframe clock controlled-index entities x z heading hp score defindex raw-pad guest-keyinput */
static void gs_dump(void){
  if(!*(volatile u32*)(EW+0x1e00)) return;
  s32 nl=*(volatile s16*)(IW+0xc), ci=*(volatile s16*)(EW+0x1db8); if(nl<0||nl>100||ci<0||ci>nl) return;
  const u8*e=entp(((const u32*)(IW+0xc60))[ci]); if(!e) return;
  u32 dp=*(const u32*)(e+0x1c); s32 di=(dp-0x08354af4u)/0x3c;
  dbg("GS gf "); dec(g_gframes); dbg("clk "); dec(*(volatile u32*)(EW+0x1e00)); dbg("ci "); dec(ci); dbg("nl "); dec(nl);
  dbg("x "); dec(*(const s32*)(e+4)); dbg("z "); dec(*(const s32*)(e+8)); dbg("hd "); dec(*(const s16*)(e+0x12)&0xffff); dbg("hp "); dec(*(const s16*)(e+0x68)); dbg("sc "); dec(*(const s32*)(e+0x90));
  dbg("def "); dec(di); dbg("cls "); dec(rom_byte((dp+0x26)&0x01ffffff)); dbg("pad "); hex(pad_raw); dbg("key "); hex(io_keys); dbg("\n");
  { const u32*tab=(const u32*)(IW+0xc60); s32 px=*(const s32*)(e+4), pz=*(const s32*)(e+8); s32 bc=0x7fffffff,bi=-1,bp=0x7fffffff,pi=-1; const u8*bce=0,*bpe=0; int nc=0,np=0;
    for(s32 i=0;i<=nl;i++){ if(i==ci) continue; const u8*o=entp(tab[i]); if(!o) continue; u32 d2=*(const u32*)(o+0x1c); if(d2-0x08354af4u>=128*0x3c) continue; u32 cl=rom_byte((d2+0x26)&0x01ffffff);
      s32 dx=*(const s32*)(o+4)-px, dz=*(const s32*)(o+8)-pz; if(dx<0) dx=-dx; if(dz<0) dz=-dz; s32 d=dx+dz;
      if(cl==0){ nc++; if(d<bc){ bc=d; bi=i; bce=o; } } else if(cl==1){ np++; if(d<bp){ bp=d; pi=i; bpe=o; } } }
    dbg("GN cars "); dec(nc); dbg("peds "); dec(np);
    if(bce){ dbg("car "); dec(bi); dec(*(const s32*)(bce+4)); dec(*(const s32*)(bce+8)); dec(*(const s16*)(bce+0x12)&0xffff); dec((*(const u32*)(bce+0x1c)-0x08354af4u)/0x3c); }
    if(bpe){ dbg("ped "); dec(pi); dec(*(const s32*)(bpe+4)); dec(*(const s32*)(bpe+8)); }
    dbg("\n"); } }
#endif
static void present(void){
  cd_idle();             /* a data read left running since the last picture is paused now (reads that follow each other need no Pause) */
  sv_service(); cdda_service();
#ifdef SF3_DEFER
  /* title-boot disc: the renderer's data window is shared with menu-only overlay code (cold tier 1), so the renderer starts when the level does */
  /* rc7: after the guest left a level (present() below turns the renderer off) the start is armed again: a new level is running once its clock
     differs from the one left behind and its entity table is there again */
  { if(!sf3_tried && !sf3_ok && *(volatile u32*)(EW+0x1e00) && (u32)*(volatile s16*)(EW+0x1e66)<=10u
       && (!sf3_left || (*(volatile u32*)(EW+0x1e00)!=sf3_left_clk && *(volatile s16*)(IW+0xc)>=0))){ sf3_tried=1; sf3_left=0; sf3_first_map=*(volatile s16*)(EW+0x1e66); dbg("guest map "); dec(sf3_first_map); dbg("\n"); dbg("deferred sf3_init at level start, gba frame "); dec(io_cyc/280896); dbg("\n");
      sf3_ok=(sf3_init()==0); for(u32 k=0;k<COLDGROUPS;k++){ u32 lo=COLD_HOST+k*16384, hi=lo+16384; if(hi>SF_WORLD_LO && lo<0x8011b200u) cold_loaded[k]=0; } dbg("sf3_ok "); dec(sf3_ok); dbg("\n"); } }
  if(sf3_retry && !sf3_ok && g_pres-last_cold_pres>=6 && *(volatile u32*)(EW+0x1e00)!=sf3_clk0){ sf3_retry=0; dbg("sf3 re-init after overlay load\n");
    sf3_ok=(sf3_init()==0); for(u32 k=0;k<COLDGROUPS;k++){ u32 lo=COLD_HOST+k*16384, hi=lo+16384; if(hi>SF_WORLD_LO && lo<0x8011b200u) cold_loaded[k]=0; } dbg("sf3_ok "); dec(sf3_ok); dbg("\n"); }
#endif
  g_pres++;
#ifndef PRES_DBG_EVERY
#define PRES_DBG_EVERY 50
#endif
#ifdef SF3_DEFER
  /* stage 13: Pause (and Quit to title, then a new level) runs menu-only cold code over the renderer's data window (SF3 CONFLICT: renderer off).  When the guest is back in a running level on map 0 (clock advanced by 8 ticks since it was
     seen running) the renderer data is read back from the disc and the cold groups that overlap the window are dropped again (the next Pause loads them again). */
  { static u32 rclk; if(sf3_cfl&&!sf3_ok){ u32 c=*(volatile u32*)(EW+0x1e00);
      if(c&&*(volatile s16*)(EW+0x1d40)==0){ if(!rclk||c<rclk) rclk=c; if(c-rclk>=8&&c!=sf3_cfl_clk){ rclk=0; sf3_cfl=0;
          /* cold groups that were loaded over the window: the part of a group that lies in the world file (read-only, linear from sf3_w_lba) is re-read sector by sector; a group that reaches the stamp/side tables
             (0x80111000..) needs the whole map read again */
          int full=0, nrest=0; extern u32 sf3_w_lba, sf3_w_len; u32 we=SF_WORLD_LO+sf3_w_len;
          for(u32 k=0;k<COLDGROUPS;k++){ u32 lo=COLD_HOST+k*16384, hi=lo+16384; if(cold_loaded[k]&&hi>SF_WORLD_LO&&lo<0x8011b200u){ dbg("CFL group "); dec(k); hex(lo); hex(hi); hex(we); dbg("\n"); if(hi>0x80111000u) full=1; } }
          if(!full){ for(u32 k=0;k<COLDGROUPS;k++){ u32 lo=COLD_HOST+k*16384, hi=lo+16384; if(cold_loaded[k]&&hi>SF_WORLD_LO&&lo<0x8011b200u){
                u32 a=lo<SF_WORLD_LO?SF_WORLD_LO:lo, b=hi>we?we:hi;
                if(a<b){ u32 s0=(a-SF_WORLD_LO)>>11, s1=(b-1-SF_WORLD_LO)>>11; cd_read(sf3_w_lba+s0,s1-s0+1,(u8*)(SF_WORLD_LO+s0*2048)); }
                cold_loaded[k]=0; nrest++; } }
            sf3_ok=1; dbg("SF3 renderer data restored from the world file, groups "); dec(nrest); dbg("level clock "); dec(c); dbg("\n"); }
          else { dbg("SF3 re-init after cold-code conflict, level clock "); dec(c); dbg("\n");
            sf3_ok=(sf3_init()==0); for(u32 k=0;k<COLDGROUPS;k++){ u32 lo=COLD_HOST+k*16384, hi=lo+16384; if(hi>SF_WORLD_LO && lo<0x8011b200u) cold_loaded[k]=0; } dbg("sf3_ok "); dec(sf3_ok); dbg("\n"); } } }
      else rclk=0; } }
#endif
  if((g_pres%PRES_DBG_EVERY)==1){ dbg("present "); dec(g_pres); dbg(" tick "); dec(io_nd); dbg("gf "); dec(g_gframes); dbg("clk "); dec(*(volatile u32*)(EW+0x1e00)); dbg("map "); dec(*(volatile u16*)(EW+0x1d40)); dbg("nent "); dec(*(volatile u16*)(IW+0xc)); dbg("dsp "); hex(io16(0)); dbg("keys "); hex(io_keys); dbg("PPU n2 "); dec(pp_n2); dbg("n4 "); dec(pp_n4); dbg("up "); dec(pp_nup); dbg("rb "); dec(pp_nrb); dbg("rst "); dec(pp_nreset); dbg("lost "); dec(pp_lost); dbg("fade "); dec(pp_nfade); dbg("w "); dec(pp_fade_w); dbg("fb "); dec(pp_nfb); dbg("obj "); dec(pp_nobj); dbg("disp "); hex(pp_disp); dbg("\n"); }
  u32 rc=RC1_VAL; u32 lines=(rc-last_rc)&0xffff;   /* scanlines of CPU time since the previous present = guest logic time */
  /* ----- game-state tick (same clock as the lockstep proof): vblank = io_vc 160, IF bit0 */
  u32 n=DL[0]; u32 from=last_dl; if(n-from>256) from=n-256; last_dl=n;
  logic_lines=lines; if(lines>max_lines) max_lines=lines; tot_lines+=lines; nfr_meas++;
  int oy=buf?240:0; cur_oy=oy;
#ifndef AUTOKEYS
  if(pad_gf!=g_gframes){ pad_gf=g_gframes; pad_frame_poll(); }
  io_keys=pad_gba;
  { u32 lat=pad_latch|pad_raw, np=lat&~pad_lastp; pad_latch=0; pad_lastp=pad_raw;
    pad_new_extra=((np>>12)&1)|(((np>>8)&3)<<1)|(((np>>1)&3)<<3);
#ifdef TESTPOKE
    pad_new_extra|=(np&1)<<5;     /* TEST-ONLY: a fresh Select press pokes the controlled entity index to the nearest traffic car (see stage7_pre) */
#endif
    radio_poll(lat,np); }
#ifdef PADDBG
  { static u32 lp=0xffffffff; if(pad_raw!=lp){ lp=pad_raw; dbg("PADRAW "); hex(pad_raw); dbg("\n"); } }
  gs_dump();
#endif
#endif
  if(sf3_ok){ s32 px,py,pz; int hd,pk,ne; static s32 hpx,hpy,hpz; static int hhd,hpk,hne,hvalid;   /* stage 16: last gathered pose, drawn again while the guest's level state is not readable (Pause) */
#ifdef PCACHE1
    rom_pool=1;                       /* stage 20: a level runs: resident pages and slots become one CLOCK pool (cd_fetch) */
#endif
#ifdef SF3_DEFER
    /* rc7: the guest left the level (Quit to title, game over): its entity count at IWRAM 0x0300000c is -1 and the level clock stands still, three
       pictures in a row after a good one.  The renderer goes off: the menus present every PRESENT_MENU guest frames again, and the menu code and the
       next level's loader (0x0803c4cc.., cold groups 42/43 over the renderer's world window) are loaded and run natively again.  With the renderer on
       they were refused and interpreted: 3.4 M interpreter steps and about 3000 frames of the menu picture before a second level showed its city.
       The next level start runs the deferred sf3_init again, as the first one did (the world is read from the disc again). */
    { static u32 nl, lc; u32 c=*(volatile u32*)(EW+0x1e00);
      if(hvalid && *(volatile s16*)(IW+0xc)==-1 && c==lc){ if(++nl>=3){ nl=0; hvalid=0; sf3_ok=0; sf3_tried=0; sf3_left=1; sf3_left_clk=c; rd_clear(); s7_reset=1;   /* no doll or bail-out carried into the next level */
          dbg("SF3 off: the guest left the level, level clock "); dec(c); dbg("\n"); goto no3d; } }
      else nl=0;
      lc=c; }
#endif
#ifdef TG_LOADS
    /* TEST-ONLY: after TG_LOADS map loads, the guest's grid id is overwritten with TG_TO (as if a new level had loaded another grid): the renderer must follow it and drop the L2/R2 override */
    { static u32 tgd; if(!tgd && sf3_map_loads>=TG_LOADS && st3_render>2){ tgd=1; *(volatile s16*)(EW+0x1e66)=TG_TO; dbg("TEST-ONLY: guest grid id set to "); dec(TG_TO); dbg("\n"); } }
#endif
    u32 g0=RC1_VAL; int ok=gather3(&px,&py,&pz,&hd,&pk,&ne); st3_gather_lines=(RC1_VAL-g0)&0xffff;
    if(ok){ stage7_pre(&px,&py,&pz,&hd,&pk,&ne); hpx=px; hpy=py; hpz=pz; hhd=hd; hpk=pk; hne=ne; hvalid=1; u32 r0=RC1_VAL; sf3_frame(oy,px,py,pz,hd,pk,ents3,ne,PPU_SF3HUD); while(*(volatile u32*)0x1F8010A8&0x01000000){} pp_draw(oy,1); u32 dl=(RC1_VAL-r0)&0xffff; st3_render++; st3_lines_sum+=dl; if(dl>st3_lines_max) st3_lines_max=dl;
      if((st3_render&PRINT_EVERY_SF3)==1||st3_render<4){ dbg("SF3 frame "); dec(st3_render); dbg("map "); dec(sf3_map_cur); dbg("gmap "); dec(g3_map); dbg("pos "); dec(px); dec(py); dec(pz); dbg("hd "); dec(hd); dbg("veh "); dec(pk); dbg("ents "); dec(ne); dbg("eng "); dec(sf3_stat_eng); dbg("host "); dec(dl); dbg("lines prim "); dec(sf3_stat_prim); dbg("ovf "); dec(sf3_stat_ovf); dbg("lod "); dec(sf3_stat_lod); dbg("logic "); dec(lines); dbg("gat "); dec(st3_gather_lines); dbg("romld "); dec(rom_miss_count); dbg("cnf "); dec(cold_conflicts); dbg("interp "); dec(ip_enters); dbg("cdsec "); dec(cd_sectors); dbg("ph "); for(int q=0;q<8;q++) dec(sf3_ph[q]); dbg("cnt "); for(int q=0;q<32;q++) dec(sf3_cnt[q]); dbg("\n"); }
#ifdef SPINTEST
      /* TEST-ONLY (stage 13): once, after SPINTEST renders: 12 headings (1/12 turn apart), 6 renders each (the camera and the LOD governor settle), the guest frozen in this call; prints the 6th render of each heading and the summary, then goes on normally */
      { static int spun; if(!spun&&st3_render>=SPINTEST){ spun=1; u32 sum=0,mx=0,over=0; for(int it=0;it<12;it++){ int h2=(hd+it*5461)&0xffff; u32 d2=0;
            for(int r6=0;r6<6;r6++){ int o2=buf?240:0; u32 q0=RC1_VAL; sf3_frame(o2,px,py,pz,h2,pk,ents3,ne,PPU_SF3HUD); d2=(RC1_VAL-q0)&0xffff; flip_to(o2); buf^=1; }
            dbg("SPIN "); dec(it); dbg("hd "); dec(h2); dbg("map "); dec(sf3_map_cur); dbg("host "); dec(d2); dbg("prim "); dec(sf3_stat_prim); dbg("ovf "); dec(sf3_stat_ovf); dbg("lod "); dec(sf3_stat_lod); dbg("\n"); sum+=d2; if(d2>mx) mx=d2; if(d2>456) over++; }
          dbg("SPIN done map "); dec(sf3_map_cur); dbg("mean "); dec(sum/12); dbg("max "); dec(mx); dbg("over456 "); dec(over); dbg("\n"); } }
#endif
#ifdef MODELTOUR
#ifndef MT_HOLD
#define MT_HOLD 40
#endif
#ifndef MT_R
#define MT_R 1000
#endif
#if MT_HOLD < 1
#error "MT_HOLD must be positive"
#endif
      /* TEST-ONLY (stage 17): after MODELTOUR renders the guest is frozen and model scenes are shown, each held MT_HOLD renders (HUD "MT n"):
         0..7 the line-up (10 vehicle classes, 6 walkers) from 8 angles round it; 8, 9 the player walks / runs on a circle; 10..19 one vehicle class each on a turntable with the player beside it;
         20 walkers toward the camera, 21 walkers across the view.  Prints the mean lines of the last 16 renders of each scene.  Not part of the game. */
      { static int tour; if(!tour&&st3_render>=MODELTOUR){ tour=1; int pk2=0;
          static const u8 cl[10]={0,8,15,7,3,11,13,9,2,20};
          s32 cx=px, cz=pz, cy=py;
          for(int sc=0;;sc++){ int scn=sc%24; sf3_mt=scn; u32 sum=0,cnt=0,mxl=0;
            for(int r=0;r<MT_HOLD;r++){ static u32 frame; frame++; int ne2=0; s32 qx=cx, qz=cz-1200; int qh=0; pk2=0;
              if(scn<8){ int ang=scn*8192;
                for(int i=0;i<10;i++){ int col=i%5,row=i/5; ents3[ne2].x=cx+(col-2)*430; ents3[ne2].z=cz+(row?330:-330); ents3[ne2].y=cy; ents3[ne2].yaw=row?0x8000+col*0x0800:0x0000+col*0x0800; ents3[ne2].kind=0; ents3[ne2].spare=i; ents3[ne2].look=cl[i]; ents3[ne2].pol=(cl[i]==9||cl[i]==20); ne2++; }
                for(int i=0;i<6;i++){ int a2=(frame*(i==5?3000:1100)/50+i*10923)&0xffff; int rr=(i==5?110:60+i*8); ents3[ne2].x=cx+(sf3_sin(a2)*rr>>14); ents3[ne2].z=cz+(sf3_sin(a2+16384)*rr>>14); ents3[ne2].y=cy; ents3[ne2].yaw=(a2+16384)&0xffff; ents3[ne2].kind=1; ents3[ne2].spare=20+i; ents3[ne2].look=(i==0)?0xFE:0; ents3[ne2].pol=(i==1); ne2++; }
                qx=cx-(sf3_sin(ang)*(MT_R)>>14); qz=cz-(sf3_sin(ang+16384)*(MT_R)>>14); qh=ang; }
              else if(scn<10){ int a3=(frame*(scn==8?560:1500))&0xffff; qx=cx+(sf3_sin(a3)*1300>>14); qz=cz+(sf3_sin(a3+16384)*1300>>14); qh=(a3+16384)&0xffff; }
              else if(scn<20){ int k=scn-10; ents3[ne2].x=cx; ents3[ne2].z=cz; ents3[ne2].y=cy; ents3[ne2].yaw=(frame*350)&0xffff; ents3[ne2].kind=0; ents3[ne2].spare=1; ents3[ne2].look=cl[k]; ents3[ne2].pol=(cl[k]==9||cl[k]==20); ne2++; qx=cx-250; qz=cz-330; qh=0; }
              else if(scn>=22){ static const u8 lk[7]={0,13,15,9,7,3,5}; static const s16 lx[7]={-230,-230,-230,230,230,230,560}, bz[7]={600,1700,3000,1000,2300,3500,350};
                for(int i=0;i<7;i++){ int zz=(i==6)?bz[i]:(i<3?(bz[i]-(int)(frame*7))%3800:(bz[i]+(int)(frame*5))%3800); if(zz<-300) zz+=3800; ents3[ne2].x=cx+lx[i]; ents3[ne2].z=cz+zz-300; ents3[ne2].y=cy; ents3[ne2].yaw=(i<3)?0x8000:0; ents3[ne2].kind=0; ents3[ne2].spare=i; ents3[ne2].look=lk[i]; ents3[ne2].pol=(lk[i]==9); ne2++; }
                for(int i=0;i<4;i++){ int zz=(300+i*560+frame*4)%2600; ents3[ne2].x=cx-520; ents3[ne2].z=cz+zz-300; ents3[ne2].y=cy; ents3[ne2].yaw=0; ents3[ne2].kind=1; ents3[ne2].spare=40+i; ents3[ne2].look=0; ents3[ne2].pol=(i==2); ne2++; }
                qx=cx; qz=cz-200; qh=0; if(scn==23){ pk2=1; sf3_plook=13; sf3_ppol=0; } }
              else { for(int i=0;i<4;i++){ int along=(frame*(i==3?9:4)+i*130)%1000-500; int lat=(i-2)*130+(i==3?200:0); ents3[ne2].y=cy; ents3[ne2].kind=1; ents3[ne2].spare=30+i; ents3[ne2].look=(i==0)?0xFE:0; ents3[ne2].pol=(i==1);
                  if(scn==20){ ents3[ne2].x=cx+lat; ents3[ne2].z=cz+400-along; ents3[ne2].yaw=0x8000; } else { ents3[ne2].x=cx+along; ents3[ne2].z=cz+i*110+300; ents3[ne2].yaw=0x4000; } ne2++; }
                qx=cx; qz=cz-200; qh=0; }
              int o2=buf?240:0; u32 q0=RC1_VAL; sf3_frame(o2,qx,cy,qz,qh,pk2,ents3,ne2,1); u32 d2=(RC1_VAL-q0)&0xffff;
              if(r>=MT_HOLD-16){ sum+=d2; cnt++; if(d2>mxl) mxl=d2; }
              flip_to(o2); buf^=1; }
            dbg("MT scene "); dec(scn); dbg("mean "); dec(sum/cnt); dbg("max "); dec(mxl); dbg("prim "); dec(sf3_stat_prim); dbg("ovf "); dec(sf3_stat_ovf); dbg("lod "); dec(sf3_stat_lod); dbg("veh lines "); dec(sf3_cnt[28]); dbg("ped lines "); dec(sf3_cnt[29]); dbg("nveh "); dec(sf3_cnt[30]); dbg("nped "); dec(sf3_cnt[31]); dbg("\n"); } } }
#endif
#ifdef PROFSPIN
      /* TEST-ONLY profiling: freeze the guest at this state and spin the player's heading in 1/32 turns, 6 renders per heading (camera settles), print the last */
      if(st3_render>=PROFSPIN){ for(u32 it=0;;it++){ int h2=(hd+(it/6)*2048)&0xffff; int o2=buf?240:0; u32 q0=RC1_VAL; sf3_frame(o2,px,py,pz,h2,pk,ents3,ne,1); u32 d2=(RC1_VAL-q0)&0xffff;
          if(it%6==5){ dbg("SPIN "); dec(it/6); dbg("hd "); dec(h2); dbg("host "); dec(d2); dbg("prim "); dec(sf3_stat_prim); dbg("lod "); dec(sf3_stat_lod); dbg("hash "); hex(sf3_hash); dbg("ph "); for(int q=0;q<8;q++) dec(sf3_ph[q]); dbg("cnt "); for(int q=0;q<32;q++) dec(sf3_cnt[q]); dbg("\n"); }
          flip_to(o2); buf^=1; } }
#endif
      goto flip; }
    else if(hvalid && *(volatile u32*)(EW+0x1e00) && (u32)*(volatile s16*)(IW+0xc)<=100u){   /* stage 16: the guest's level is paused / its state is being rewritten by overlay code: hold the last 3D view (same pose, entities of the last good gather) under the PPU layers instead of the dark debug page.
      stage 20: only while the guest still has its level's entity table (count 0..100 at IWRAM 0x0300000c, as gather3 reads it): Quit to title leaves the level clock at its last value
      and sets the count to -1, and the held view then showed through every index-0 pixel of the game menu (pp_draw(oy,1) draws no backdrop) */
      static u32 nh; if(nh<3||(nh&63)==0){ dbg("SF3 hold last frame, hold count "); dec(nh); dbg("\n"); } nh++;
      sf3_frame(oy,hpx,hpy,hpz,hhd,hpk,ents3,hne,PPU_SF3HUD); while(*(volatile u32*)0x1F8010A8&0x01000000){} pp_draw(oy,1); goto flip; } }
#ifdef SF3_DEFER
 no3d:
#endif
  if(sf3_cfl&&*(volatile u32*)(EW+0x1e00)){ last_rc=RC1_VAL; return; }   /* stage 13: renderer data is being restored after a cold-code overlay hit it: keep showing the last 3D frame (no switch to the debug page, no luminance flash) */
  pp_draw(oy,0);          /* the 2D layer: black borders, backdrop, page, sprites (ppu12.h sets its own drawing environment) */
#ifndef PPU_DEBUG
  goto flip;
#else
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
    if((id==2||id==4)&&rom_read(r0,2)>=100){ static u32 lastimg; if(!img_f0) img_f0=io_cyc/280896+1; if(r0!=lastimg){ lastimg=r0; static u32 nimg; if(nimg<400){ nimg++; dbg("IMG gf "); dec(g_gframes); dbg("nd "); dec(io_nd); hex(r0); dbg("\n"); } } }
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
  text(4,4,"PAYBACK  ORIGINAL GAME  RC",2,0xffffff); text(4,92,"MENU 2D LAYER NOT DRAWN: SEE README",1,0xc0c0c0);
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
#endif
  /* ----- present */
 flip:
  flip_to(oy); buf^=1;
  cd_resume();           /* CD audio held for data reads comes back when no data read was made for a while (after this picture's own reads) */
  last_rc=RC1_VAL;
}
#ifdef SNAPRESUME
/* TEST-ONLY resume from a guest-state snapshot taken in the unicorn sim at the entry of present() (called from h_vbl and from the VCOUNT poll in io_read) during the level: SNAPST.BIN on the disc (sector-aligned):
   sec 0 header: [0]=magic [1..32]=MIPS regs $0..$31 at h_vbl entry, [0x24..]=statics (see snap order below), 0x200..0x2ff = RT_CC stack 0x801fff00..;
   1: EWRAM 128 sec, 129: IWRAM 16, 145: VRAM shadow 48, 193: PAL+OAM, 194: io[], 195: ee[] 4 sec.  The guest code and the helpers are the same translation. */
extern void snap_resume(const u32*regs,u32 target);
static u32 snap_regs[32], snap_target;
#ifdef COLD_SECS
#define COLD_SECS_N COLD_SECS      /* stage 7: exactly the sectors of the cold file (the page-rounded count ran up to 2 KiB over the renderer window) */
#else
#define COLD_SECS_N (CD_COLD_PAGES*2)
#endif
static RTCOLD void snap_restore(void){
  u8*h=PCACHE; cd_read(CD_SNAPST_LBA,1,h); const u32*w=(const u32*)h;
  for(int i=0;i<32;i++) snap_regs[i]=w[1+i];
  snap_target=w[0x88/4];
  const u32*st=w+40;
  io_vc=st[0]; io_nread=st[1]; io_nd=st[2]; io_cyc=st[3]; io_acc=st[4]; g_gframes=st[5]; g_nvbl=st[6];
  for(int k=0;k<4;k++){ tm_t0[k]=st[7+k]; tm_rl[k]=st[11+k]; tm_ovb[k]=st[15+k]; tm_en[k]=st[19+k]; }
  io_hi=0; for(int k=0;k<4;k++) tm_t0h[k]=io_cyc<tm_t0[k]?0xffffffffu:0u;   /* the snapshot's 32-bit base: every timer started less than 2^32 cycles ago */
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
    u32 ng=(COLD_SECS_N+7)/8; if(ng>COLDGROUPS) ng=COLDGROUPS;
    cd_read(CD_COLD_LBA,COLD_SECS_N,(u8*)COLD_HOST); for(u32 k=0;k<ng;k++) cold_loaded[k]=1; flush_icache(); dbg("cold prefix preloaded, groups "); dec(ng); { u32 sm=0; const u32*p=(const u32*)COLD_HOST; for(u32 q=0;q<136000;q++) sm=sm*31+p[q]; dbg("checksum "); hex(sm); } dbg("\n"); }
  dbg("snapshot restored: gba frame "); dec(io_cyc/280896); dbg("tick "); dec(io_nd); dbg("\n");
}
#endif
/* ---------------------------------------------------------------- start */
extern u32 GUEST_MAIN_HOST;       /* from payback_syms.c */
RTCOLD int main(void){      /* rc7: in .rtcold (it runs once) */
  /* stage 19: take the machine over before any device is used.  crt0.s has set SR (GTE on, interrupts and every interrupt mask bit off), so no
     interrupt can reach a kernel handler; here I_MASK = 0, every pending I_STAT bit and every CD-ROM controller interrupt is acknowledged. */
  IMASK=0; ISTAT=0;
  RC1_MODE=0x0100;       /* root counter 1 counts hblank: the time base of every bounded wait of the CD driver */
#ifndef CDSIM
  cd_drain();
#endif
  ISTAT=0;
  dbg("PAYBACK PS1 stage2: start\n");
  gpu_init(); cdda_init();
  memset((void*)DL,0,0x2100);
  HELP[0]=(u32)h_memrd; HELP[1]=(u32)h_memwr; HELP[2]=(u32)h_miss; HELP[3]=(u32)h_vbl;
  const u32 *b=(const u32*)bootimg; const u8 *p=bootimg+160;
  memcpy(EW,p,0x40000); p+=0x40000; memcpy(IW,p,0x8000); p+=0x8000; memcpy(PAL,p,0x400); p+=0x400; memcpy(VRAM,p,0x18000); p+=0x18000; memcpy(OAM,p,0x400); p+=0x400; memcpy(io,p,0x400);
  io_vc=b[32]; io_nread=b[33]; for(int i=0;i<4;i++) io_tm[i]=b[34+i]; io_nd=b[38]; io_keys=PAD[(io_nd/30)%6];
  const u32 *rp=(const u32*)rompack; rp_n=rp[0]; rp_idx=rp+1; rp_data=(const u8*)(rp+1+rp_n);
  for(u32 i=0;i<rp_n;i++) rom_pg[rp_idx[i]&2047]=rp_data+i*4096;     /* optional pre-seeded pages (never evicted before the first level, see cd_fetch) */
#ifdef PCACHE1
  pool_rp=rp_n<RP_MAX?rp_n:RP_MAX; for(u32 i=0;i<pool_rp;i++) fr_pg[i]=(rp_idx[i]&2047)+1;
#endif
  dbg("boot image loaded, rom pages "); dec(rp_n); dbg("\n");
#ifndef NO_INTERP
  intro_fix_init();     /* overlay guard + the ZOO-logo join point (interp_glue.h) */
#endif
  last_rc=RC1_VAL;
  static u32 regs[32]; for(int i=0;i<32;i++) regs[i]=b[i];
  { extern u8 __sfbss_start[],__sfbss_end[]; for(u8*q=__sfbss_start;q<__sfbss_end;q++) *q=0; }
  { extern u8 __dlbss_start[],__dlbss_end[]; for(u8*q=__dlbss_start;q<__dlbss_end;q++) *q=0; }
  #ifdef NOSF3
  sf3_ok=0;    /* unicorn sim has no GTE */
#else
#ifdef SF3_DEFER
  sf3_ok=0;
#else
  sf3_ok=(sf3_init()==0);
#endif
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
