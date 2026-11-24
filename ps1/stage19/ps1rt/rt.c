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
#include "clk.h"       /* PS1 speed plan: the 64-bit clock (RTC64) and the test-only speed stamps (SPEEDPROF); first part */
#ifdef PRES_ASYNC
int fl_req=-1;                 /* rc10: y of the buffer waiting to be shown (flip asked for), -1 none (see pres_finish) */
static int pend_oy=-1;         /* rc10: y of a 3D picture sent (DMA2 maybe still drawing it), its 2D layer not yet drawn */
void fl_poll(void);
#define FL_POLL() do{ if(fl_req>=0) fl_poll(); }while(0)
#else
#define FL_POLL() ((void)0)
#endif
/* stage 20 D3: the page table is the translator's reserved ROMPG (t2m.py Cfg.ROMPG, 2048 x u32), so the blob's own RT_MEMRD fast path reads
   the same table as rom_page(): non-zero = resident, cleared on every eviction (cd_fetch).  Zeroed in main(); the absolute symbol keeps the
   name for the test rig (misses.csv). */
/* rc8: the table lives in ROMPG in every build (without D3 the blob's fast path that reads it is off and nothing else uses the area), which
   keeps 8 KB out of the runtime's BSS */
#define rom_pg ((const u8**)0x8002a000)
/* Milestone B (-DMERGED, tools12/build_msb.sh): the merged Star-FlyBack ROM is 16 MiB, 4096 pages; the table then fills 0x8002a000..0x8002e000
   (t2m T2M_ROMPG_N=4096) and the interpreter keeps 8 stacks (interp_glue.h IP_MAXD) in 0x8002e000..0x80030000.  A read of a page past the image
   (a guest address 0x09000000 and up) stops with an error screen instead of wrapping onto another page. */
#ifdef MERGED
#define ROM_NPG 4096u
#else
#define ROM_NPG 2048u
#endif
__asm__(".globl rom_pg\n.set rom_pg, 0x8002a000\n");
static u32 g_pres, g_gframes;   /* presented pictures, guest (GBA) frames */
u32 g_flips;                    /* display-start changes (flip_to, the CD error and fatal screens): g_pres counts present() STARTS, so a picture
                                   can reach the screen with no g_pres step between two looks (issue #15); count pictures with this one */
static u32 cd_rd_gf;            /* the guest frame in which the last data read ended (hw_cdda.h resumes the music after a quiet interval) */
#ifdef CDSTAT
static u32 cd_nreq, cd_npass;   /* test counters (speed stage 3): data requests (one Setloc+ReadN each, retries not counted), passes (retries counted) */
#define CDSTAT_INC(v) ((v)++)
#else
#define CDSTAT_INC(v) ((void)0)
#endif
#if defined(CDPADPOLL) && !defined(CDSIM)
/* speed item P6: the pad is also polled inside the CD driver's waits, at most once per PS1 field (263 hblank lines: the CPU only waits there),
   and on cold calls, at most once per 2 fields (cold_find: the level load runs one guest frame of several seconds that calls cold code
   thousands of times a second and reads no disc for up to 4 s; a poll costs about 0.4 ms of CPU there; 2 fields, 33 ms, still fall inside
   the shortest press tested, 3 frames = 50 ms: 3 fields did not), and every 1024th guest store on the slow raw-address path (h_memwr:
   right after 'Play game' the guest fills guest memory that way for about 0.2 s with no cold call and no I/O read), so a press made while
   the guest stands still for a read or a long load is not lost: pad_cdlat keeps the buttons seen there (GBA KEYINPUT bits, 1 = pressed)
   until the guest's next KEYINPUT read, which sees them pressed once; pad_latch (defined with the pad path below) gets them too (radio,
   map keys).
   Coverage with the dispatch items on (wave 1 review): DISP_D1 / DISP_D2 send repeated cold calls past cold_find (rt_mcache hit or a
   linked jal), and DISP_D4's wr_front stores to EWRAM / IWRAM without h_memwr, so the cold-call and raw-store polls fire only on a D1
   miss and on raw stores to regions 5-7.  What still covers a long stall is the poll in the CD waits (the level is CD-bound: most of an
   iteration is CD wait) and the real-frame pad read at every KEYINPUT read and present (RTC_GFRAMES); the level-start taps of 3, 6 and 12
   frames lose none on the combined build (taps_level_vf). */
/* pad_cddn: the buttons down at the last look (the guest's last KEYINPUT read, or the last poll here).  Only a button that goes down after
   that is latched: a press the guest has already seen (a cursor key still held at a CD wait right after the read that moved the cursor)
   is not delivered again at the next read.  Without this edge rule the title menu got that stale DOWN together with the next Cross, many
   frames after DOWN was released (Down+A in one read), and did not open the entry (wave 1 fixup: boot_to_title, title_trace 8/8). */
static u32 pad_cdt, pad_cdlat, pad_cddn, pad_rawn; static u32 pad_latch;
#ifdef CDSTAT
static u32 pad_cdpolls, pad_cddeliv;   /* test counters: polls made here; KEYINPUT reads that a latched press changed */
#endif
static void cd_padpoll(u32 lines);
#ifdef CDPADPOLL_AB
u32 pad_cd_off;   /* TEST ONLY: P6 on and off from one level state.  The session writes a mask here: 1 no polls in the CD waits, 2 none on cold calls,
                     4 none on raw stores (7: P6 off) */
#define CD_PADPOLL(lines) do{ if(!(pad_cd_off&((lines)==263u?1u:2u))) cd_padpoll(lines); }while(0)
#define RAW_PADPOLL() do{ if(!(++pad_rawn&1023u)&&!(pad_cd_off&4u)) cd_padpoll(526u); }while(0)
#else
#define CD_PADPOLL(lines) cd_padpoll(lines)
#define RAW_PADPOLL() do{ if(!(++pad_rawn&1023u)) cd_padpoll(526u); }while(0)
#endif
#else
#define CD_PADPOLL(lines) ((void)0)
#define RAW_PADPOLL() ((void)0)
#endif
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
static u32 hl_past(void){ u32 t=RC1_VAL&0xffff; hl_acc+=(t-hl_t)&0xffff; hl_t=t; CLK_POLL(); return hl_acc; }
#define HL_RESP 16000u      /* about 1 s: the first response of a command, a further sector of a running read */
#define HL_LONG 80000u      /* about 5 s: a second response (Pause, Init), the first sector after a seek or a spin-up */
static void cd_ack(void){ CD0=1; CD3=0x1f; }
static u32 cd_flags(void){ CD0=1; u32 f=CD3&7; if(f) f=CD3&7; return f; }        /* psx-spx: the first non-zero read may be unstable: read again */
static void cd_result(u8*r){ for(u32 n=0;(CD0&0x20)&&n<16;n++){ u8 b=CD1; if(!n) cd_stat=b; if(r&&n<8) r[n]=b; } }
static u32 cd_waitint(u32 lim){
  hl_start(); for(;;){ u32 f=cd_flags(); if(f) return f; if(hl_past()>lim) break; CD_PADPOLL(263u); }
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
#if defined(CDPADPOLL) && !defined(CDSIM)
__attribute__((noinline)) static void cd_padpoll(u32 lines){ u32 t=RC1_VAL&0xffff; if(((t-pad_cdt)&0xffff)<lines) return; pad_cdt=t;
  u32 dn=0x3ffu&~pad_poll(); pad_cdlat|=dn&~pad_cddn; pad_cddn=dn; pad_latch|=pad_raw; CDSTAT_INC(pad_cdpolls); }
#endif
#ifndef CDSIM
void cdda_init(void) RTCOLD;              /* rc7: once, at boot */
#ifdef RTC_GFRAMES
/* PS1 speed Stage 1, item 1e (PLAN.md; critique K6): with the real-time clock g_gframes counts real GBA frames, 59.7 a second.  The radio's
   quiet interval, its back-off limit and its play check were set in virtual frames, which ran at 1.5-7 a second in rc6: in real frames they
   become 60 / 480 / 240 (1 s, 8 s, 4 s), the same real time as before.  A build may still set its own values. */
#ifndef CDDA_QUIET
#define CDDA_QUIET 60u
#endif
#ifndef CDDA_QMAX
#define CDDA_QMAX 480u
#endif
#ifndef CDDA_WD
#define CDDA_WD 240u
#endif
#endif
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
#ifdef PZBLOCK
static u8 *const *cd_scat;          /* rc9 pause block: when set, sector s of the request goes to cd_scat[s/2] + (s&1)*2048 (one pool frame per page) */
#endif
/* One Setloc + ReadN pass from the first sector of the request that is still missing.  Every sector the drive delivers is identified by the
   MM:SS:FF address in its own header and stored if it belongs to the request and is still missing, so a sector that the drive skipped (buffer
   overrun with a read speed-up), delivered late or delivered twice can never be taken for another one.
   Returns 0 when the request is complete, -1 on an error answer or a timeout, -2 when the drive went past the request with sectors missing. */
static int cd_pass(u32 lba,u32 n,u8*dst,u32*left){
  CDSTAT_INC(cd_npass);
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
#ifdef PZBLOCK
      u8*d=cd_scat?cd_scat[s>>1]+((s&1)<<11):dst+s*2048;
#else
      u8*d=dst+s*2048;
#endif
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
#ifdef SPEEDPROF
/* stamps: CD read time, and the part of it outside present() (map loads in present are already in the present's time) */
static void cd_read0(u32 lba,u32 nsec,u8*dst);
static void cd_read(u32 lba,u32 nsec,u8*dst){ u32 t=sp_now(); cd_read0(lba,nsec,dst); u32 l=sp_now()-t; sp_acc[SP_CDL]+=l; if(!sp_inpres) sp_acc[SP_CDX]+=l; }
#define cd_read cd_read0
#endif
/* read nsec consecutive 2048-byte sectors starting at disc LBA into dst.  The drive is left reading: cd_idle() (once per presented picture)
   pauses it, so a read that follows at once costs no Pause and no seek back.  CD audio stays held until cd_resume() finds the disc quiet. */
static void cd_read(u32 lba,u32 nsec,u8*dst){
  while(nsec>CD_RUN){ cd_read(lba,CD_RUN,dst); lba+=CD_RUN; nsec-=CD_RUN; dst+=CD_RUN*2048; }
  cdda_hold();                                                    /* a data seek ends CD-DA playback: remember the position, pause */
  CDSTAT_INC(cd_nreq);
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
#ifdef RTC_GFRAMES
  clk_gba();             /* g_gframes counts real frames now (it is brought up to date at clock reads): the quiet interval starts at the end of this read */
#endif
  cd_sectors+=nsec; cd_rd_gf=g_gframes;
  if(cd_err_on) cd_error_gone();                                  /* the disc reads again: the next picture replaces the message */
}
#ifdef SPEEDPROF
#undef cd_read
#endif
/* at the start of present(): pause a data read left running since the last picture */
static void cd_idle(void){ if(cd_reading) cd_pause(); }
/* at the end of present(): CD audio held for data reads comes back once the disc has been quiet for a while (hw_cdda.h) */
static void cd_resume(void){ cdda_idle(); }
#endif
#ifdef DISP_PROF
/* TEST-ONLY (stage 20 dispatch measurements): where the time of a level-loop iteration goes, in hblank lines (RC1, 15734 per second).  RC1 is
   extended to 32 bits by dsp_rc(), which runs at every timer read, CD page fetch and present (each well within its 4.1-s wrap).  The phases are
   cut at the limiter's two timer reads, told apart by the caller's return address that RT_CC saved at 0x801fffc8 (get_time 0x08077c84 is a leaf
   up to its TM3 read): game logic = t_last read (guest 0x08024758) -> the next elapsed read (0x0802471c); limiter spin = the rest.  Lines spent
   in CD page fetches (dsp_cdl) and in present() (dsp_prl, without its own fetches) are taken out of both phases. */
#ifndef PROF_RA_E
#define PROF_RA_E 0x800a1424u     /* host return address of the elapsed read (guest 0x08024720) in this blob (payback_P.map) */
#endif
#ifndef PROF_RA_T
#define PROF_RA_T 0x800a14d8u     /* host return address of the t_last read (guest 0x0802475c) */
#endif
static u32 dsp_rch, dsp_rcl;
static u32 dsp_rc(void){ u32 t=RC1_VAL&0xffff; if(t<dsp_rcl) dsp_rch+=0x10000; dsp_rcl=t; return dsp_rch|t; }
u32 dsp_cdl, dsp_prl, dsp_lgl, dsp_spl, dsp_lgn, dsp_spn;
static u32 dsp_ph, dsp_ph0, dsp_cd0, dsp_pr0;
static void dsp_phase(u32 ra){
  u32 t=dsp_rc(), ph=ra==PROF_RA_T?1u:(ra==PROF_RA_E?2u:0u);
  if(!ph||ph==dsp_ph) return;
  u32 net=(t-dsp_ph0)-(dsp_cdl-dsp_cd0)-(dsp_prl-dsp_pr0);
  if(dsp_ph==1){ dsp_lgl+=net; dsp_lgn++; } else if(dsp_ph==2){ dsp_spl+=net; dsp_spn++; }
  dsp_ph=ph; dsp_ph0=t; dsp_cd0=dsp_cdl; dsp_pr0=dsp_prl; }
#endif
#ifdef PCACHE1
/* stage 19: one 4 KiB page (2 sectors) per fetch into the next of NSLOT single-page slots (FIFO replacement).  With the measured resident set
   (t/resident62.txt) the rest of the working set is small, and a single page per seek reads 4 times less than a 16 KiB cluster.
   stage 20 (rc7): from the first level on (rom_pool, set by present() once the 3D renderer is up) the resident pages and the slots are one pool of
   pool_rp+NSLOT frames with CLOCK replacement.  In a vehicle the level reads 17 pages beyond the resident set in a cycle: with 8 FIFO slots each of
   them came from the CD again about every second guest frame (5.5 fetches per second, 0.6 guest frames/s on SwanStation).
   rc8: the reference bit is the page-table entry itself.  With -DDISP_D3 the blob's own RT_MEMRD fast path (and D4's rd_front) read resident ROM
   pages straight from ROMPG without any C code, so a reference mark set in rom_page() never saw them: hot pages read only by translated code
   looked unused and were evicted first.  So when the hand passes a frame whose page is mapped (read since the last pass, or never looked at
   since it came in), it unmaps the page (rom_pg[pg] = 0) and keeps its data in the frame (pg_fr[pg] = frame+1); the next read of that page, by
   any path (blob fast path, rd_front, rom_page, ip_rd, DMA), finds the entry 0, reaches cd_fetch through the slow path, and maps the frame
   again without a disc read (rom_soft counts these).  The victim is the first frame under the hand whose page is unmapped: not read since the
   hand last passed.  Boot and the menus before the first level keep the stage 19 behaviour (FIFO over the slots, resident pages kept, M3 page
   pairs).  Nothing holds a page pointer across a fetch: rom_read resolves every byte, rom_copy and the DMA path one page at a time, ip_rd every
   access. */
#define RP_MAX 64
static u16 fr_pg[RP_MAX+NSLOT];         /* page+1 held by each frame, 0 = empty: frames 0..pool_rp-1 are resident pages (rompack), then the slots */
#ifdef MERGED
static u8 pg_fr[ROM_NPG] __attribute__((section(".dl.bss.pg_fr")));       /* (B1: 4 KiB, in the ragdoll region: the renderer region has 208 bytes free) */
#else
static u8 pg_fr[2048] __attribute__((section(".sf.bss.pg_fr")));
#endif                  /* frame+1 that holds each page (mapped or unmapped by the hand), 0 = not in RAM */
_Static_assert(RP_MAX+NSLOT<255, "pg_fr holds frame+1 in a byte");
static u32 rom_pool, pool_rp, pool_hand, rom_soft;
static u8 *pool_frame(u32 f){ return f<pool_rp?(u8*)rp_data+f*4096:PCACHE+(f-pool_rp)*4096; }
#ifdef COLD1PASS
static u32 cold_m5; static void cold_all(void); static int pal_bg_zero(void);
#endif
#ifdef PCPAIR
static u32 rom_pairs;   /* speed item M3: fetches that read the aligned page pair */
#endif
/* frame f gets page pg (data already in it): the maps both ways */
static void pool_set(u32 f,u32 pg){ fr_pg[f]=pg+1; pg_fr[pg]=f+1; rom_pg[pg]=pool_frame(f); if(f>=pool_rp) slot_owner[f-pool_rp]=pg+1; }
/* frame f is reused: its page (if any) leaves RAM */
#ifdef POOL_THRASH
/* rc9: the CLOCK pool also before the first level once the menus thrash the slots (the Credits: about 4 page fetches per guest frame over the
   8 FIFO slots, 1.8 guest frames/s at stock on SwanStation and no end in 10 minutes).  The last 16 pages that left a slot are remembered;
   a fetch of one of them is a refetch.  rc9 review: pool_refetch is a level, not a total: +1 for a refetch, -1 for any other fetch (-4 while
   the menu pool is on: a new screen that reads new pages turns it off soon), so only a
   stretch in which most fetches are refetches reaches POOL_THRASH (the Credits: every fetch of the thrash is a refetch); boot, the title, a tour
   of the menus and the route to the level (13 to 15 refetches among 40 to 250 fetches) stay below it.  The menu pool (pool_menu) goes off
   again before the first level when the fetches are no longer refetches (the level back at 0) or no page was fetched for POOL_QUIET pictures
   (the title menu after the Credits): the FIFO over the slots and the page pairs come back, and a resident page that the CLOCK hand gave away
   comes back into its own frame at its next miss (pool_back), so the route to the level runs as in rc8. */
#ifndef POOL_QUIET
#define POOL_QUIET 60u
#endif
static u16 ev_ring[16]; static u32 ev_i; u32 pool_refetch, pool_menu, pool_ons, pool_offs; static u32 pool_lmiss, pool_quiet;
static void pool_menu_off(void){ rom_pool=0; pool_menu=0; pool_refetch=0; pool_offs++; dbg("ROM pool off before a level\n"); }
#endif
static void pool_drop(u32 f){ u32 o=fr_pg[f];
#ifdef POOL_THRASH
  if(o && (!rom_pool || pool_menu)){ ev_ring[ev_i&15]=o; ev_i++; }
#endif
  if(o){ rom_pg[o-1]=0; pg_fr[o-1]=0; } fr_pg[f]=0; if(f>=pool_rp) slot_owner[f-pool_rp]=0; }
#ifdef PZBLOCK
/* rc9 pause block.  After Start in a level and after Return to game the game reads about 40 ROM pages that the level itself does not use (the
   pause menu's code and pictures; the resume code, which runs in the interpreter, and the graphics it unpacks again).  One by one from ROM.BIN
   they cost a seek each: on SwanStation at 1x CD the pause menu took 1.6 s to come up and the level clock restarted 2.0-3.2 s after Cross,
   with the paused picture on the screen all that time.  PAUSE.BIN holds copies of those pages (t/pause_pages.txt, sorted) in consecutive
   sectors; once the level clock has stood still for PZ_STILL pictures and no page was missed for PZ_QUIET (or a page of the block is missed
   after such a quiet stretch: Return to game before the block came in) all of them are
   read in one request, each sector straight into a pool frame (cd_scat), and mapped.  The frames are taken by the same CLOCK hand as a miss
   would take them, never one that holds a page of the block; pages of the block already in RAM keep their frame.  The block is read at most
   once per stop of the clock (pz_done = the clock value it was read at), and not at all while every page of it is in RAM.  The pause menu
   itself reads about 25 pages for as long as it is up (its code and the pictures of the pause effect): those of them that are in the block
   stay referenced; the block plus that set plus the level's own pages are more than the 70 frames of the pool, so the list is a measured
   compromise (TEST-ONLY variants: pz_start, and protecting every block page while paused, which made the menu thrash its other pages). */
#include "pz_pages.h"     /* PZ_N, pz_pg[]: the sorted page list, written by build.sh from t/pause_pages.txt */
#ifndef PZ_STILL
#define PZ_STILL 2u
#endif
#ifndef PZ_QUIET
#define PZ_QUIET 2u     /* ... and no page miss for this many pictures: the pause menu's own pages are in, the hand sees them referenced */
#endif
_Static_assert(PZ_N<=60u && PZ_N+8u<RP_MAX+NSLOT, "the pause block leaves frames for everything else");
extern const u32 CD_PZ_LBA;
static u32 pz_lclk, pz_still, pz_done=0xffffffffu, pz_loads, pz_lmiss, pz_quiet;
/* rc9 review: the block is read only after Start was pressed in a running level (the pause menu; pz_arm, set in present()), never for a clock
   that stands still for another reason (a heavy frame, a respawn, the menus with the menu pool on): on Beetle at 400 % a stand in play read the
   block and gave 59 frames of the pool away to it (a 100-frame freeze and the level's pages read again).  Disarmed by the read, and when the
   clock has run on PZ_ARM_TICKS since the press (Start without a pause) */
#ifndef PZ_ARM_TICKS
#define PZ_ARM_TICKS 30u
#endif
static u32 pz_arm, pz_arm_clk;
static int pz_ok(u32 c){ return pz_arm && rom_pool && c && c==pz_lclk && c!=pz_done && pz_quiet>=PZ_QUIET && *(volatile s16*)(IW+0xc)>=0; }
static __attribute__((noinline)) int pz_has(u32 pg){ u32 lo=0,hi=PZ_N; while(lo<hi){ u32 m=(lo+hi)>>1; if(pz_pg[m]<pg) lo=m+1; else if(pz_pg[m]>pg) hi=m; else return 1; } return 0; }
static void cd_read(u32 lba,u32 nsec,u8*dst);
static __attribute__((noinline)) void pz_load(void){
  static u8 *dst[PZ_N];
  u32 n=pool_rp+NSLOT;
  pz_done=pz_lclk; pz_arm=0;
  for(u32 i=0;i<PZ_N;i++){ u32 pg=pz_pg[i], f1=pg_fr[pg], f;
    if(f1) f=f1-1;
    else { for(;;){ f=pool_hand; pool_hand=f+1<n?f+1:0; u32 o=fr_pg[f]; if(!o) break; if(pz_has(o-1)) continue; if(!rom_pg[o-1]) break; rom_pg[o-1]=0; }
      pool_drop(f); }
    pool_set(f,pg); dst[i]=pool_frame(f); }
#ifdef CDSIM
  for(u32 i=0;i<PZ_N;i++) cd_read(CD_PZ_LBA+2*i,2,dst[i]);
#else
  cd_scat=dst; cd_read(CD_PZ_LBA,2*PZ_N,0); cd_scat=0;
#endif
  pz_loads++;
}
#ifdef PZ_START
/* TEST-ONLY (measured, not in the release): Start was pressed (raw pad bit 3) in a running level: read the block at once, before the pause
   menu's own misses.  On SwanStation at 1x CD the menu then came up 160 frames after Start instead of 102: with 51 pages of the block coming in
   while the level runs the hand takes level pages that the pause menu reads too (10 misses after the block); the resume was 43 frames either way. */
static void pz_start(void){
  u32 c=*(volatile u32*)(EW+0x1e00);
  if(!rom_pool || !c || *(volatile s16*)(IW+0xc)<0) return;
  for(u32 i=0;i<PZ_N;i++) if(!pg_fr[pz_pg[i]]){ pz_lclk=c; pz_still=0; pz_load(); return; }
}
#endif
/* present(): count the pictures the level clock has stood still for; read the block once it stood still for PZ_STILL of them (in a level) */
static void pz_present(void){
  u32 c=*(volatile u32*)(EW+0x1e00);
  if(rom_miss_count!=pz_lmiss){ pz_lmiss=rom_miss_count; pz_quiet=0; } else if(pz_quiet<PZ_QUIET) pz_quiet++;
  if(pz_arm && c-pz_arm_clk>PZ_ARM_TICKS) pz_arm=0;
  if(c!=pz_lclk){ pz_lclk=c; pz_still=0; return; }
  if(pz_still<PZ_STILL) pz_still++;
  if(pz_still>=PZ_STILL && pz_ok(c)){
    for(u32 i=0;i<PZ_N;i++) if(!pg_fr[pz_pg[i]]){ pz_load(); return; }
    pz_done=c; }
}
#endif
/* out of line: the miss path grew (M3, M5, the pool), and clang would otherwise stop inlining rom_page's resident test into h_memrd, resolve,
   gread ... (or inline the whole miss path into them) */
#ifdef PGPROF
u8 pg_prof[4096];       /* TEST-ONLY (B2 page lists): disc fetches by ROM page, saturating */
#endif
static __attribute__((noinline)) const u8 *cd_fetch(u32 pg){
#ifdef PGPROF
  if(pg<4096&&pg_prof[pg]<255) pg_prof[pg]++;
#endif
  { u32 f1=pg_fr[pg]; if(f1){ rom_pg[pg]=pool_frame(f1-1); rom_soft++; return rom_pg[pg]; } }   /* read again after the hand unmapped it: no disc read */
#ifdef POOL_THRASH
  if(!rom_pool || pool_menu){ u32 k=0; while(k<16 && ev_ring[k]!=pg+1) k++;
    if(k<16){ if(pool_refetch<POOL_THRASH) pool_refetch++; } else { u32 d=rom_pool?4u:1u; pool_refetch=pool_refetch>d?pool_refetch-d:0; }
    if(!rom_pool){ if(pool_refetch>=POOL_THRASH){ rom_pool=1; pool_menu=1; pool_ons++; dbg("ROM pool on before a level\n"); } }
    else if(!pool_refetch) pool_menu_off(); }
#endif
  u32 f;
#ifdef POOL_THRASH
  /* pool_back: in the FIFO again after a menu pool, a resident page that is not in RAM is read into its own frame */
  if(pool_offs && !rom_pool) for(f=0;f<pool_rp;f++) if((rp_idx[f]&(ROM_NPG-1u))==pg) goto rd;
#endif
#ifdef PZBLOCK
  if(pz_still && pz_ok(*(volatile u32*)(EW+0x1e00)) && pz_has(pg)){ pz_load(); return rom_pg[pg]; }
#endif
#ifdef COLD1PASS
  /* speed item M5: the game's first data read comes in the boot's black screen (BG palette all zero, no OBJ shown): COLD.BIN first */
  if(!cold_m5 && !rom_miss_count && pal_bg_zero()) cold_all();
#endif
#ifdef PCPAIR
  /* speed item M3: the aligned 8 KiB pair (4 sectors, one seek) into two adjacent slots, unless the other page of the pair is already in
     memory (resident or in a slot).  A pair never wraps round the slot ring: when only the last slot is left, the pair starts again at
     slot 0 and the last slot keeps its page for one more round.  Only while no level clock runs (boot, menus, the level load) and before the
     first level (rc8: the CLOCK pool owns the slots from then on): in a running level the misses are scattered and a pair halves the pages the
     8 slots hold (measured from the same level state, both cores: misses per guest frame -10 to -20 %, sectors +5 to +39 %, ticks/s 0 to -5 %).
     PCPAIR_LEVEL pairs in levels too (measurement only). */
#ifdef PCPAIR_LEVEL
  if(NSLOT>=2 && !rom_pool && !rom_pg[pg^1u] && !pg_fr[pg^1u]){
#else
  if(NSLOT>=2 && !rom_pool && !rom_pg[pg^1u] && !pg_fr[pg^1u] && !*(volatile u32*)(EW+0x1e00)){
#endif
    if(slot_next>=NSLOT-1) slot_next=0;
    u32 s=slot_next, lo=pg&~1u; slot_next=(slot_next+2)%NSLOT;
    for(u32 k=0;k<2;k++) pool_drop(pool_rp+s+k);
    cd_read(CD_ROM_LBA+lo*2,4,PCACHE+s*4096);
    for(u32 k=0;k<2;k++) pool_set(pool_rp+s+k,lo+k);
    rom_miss_count++; rom_pairs++; rom_miss_last=pg<<12;
    return rom_pg[pg];
  }
#endif
  if(!rom_pool){ f=pool_rp+slot_next; slot_next=(slot_next+1)%NSLOT; }
  else { u32 n=pool_rp+NSLOT; for(;;){ f=pool_hand; pool_hand=f+1<n?f+1:0; u32 o=fr_pg[f]; if(!o||!rom_pg[o-1]) break; rom_pg[o-1]=0; } }   /* second chance: unmap, keep the data */
#ifdef POOL_THRASH
rd:
#endif
  pool_drop(f);
  u8 *d=pool_frame(f);
#ifdef DISP_PROF
  { u32 t0=dsp_rc(); cd_read(CD_ROM_LBA+pg*2,2,d); dsp_cdl+=dsp_rc()-t0; }
#else
  cd_read(CD_ROM_LBA+pg*2,2,d);
#endif
  pool_set(f,pg);
  rom_miss_count++; rom_miss_last=pg<<12;
  return d;
}
#else
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
#ifdef MERGED
u32 rom_past_n, rom_obus_n;
static void fatal_screen(const char*m,u32 a) __attribute__((noreturn));
static __attribute__((noinline,noreturn)) void rom_past(u32 pg){ rom_past_n++; fatal_screen("ROM PAGE PAST THE IMAGE: ",pg); }
static inline const u8 *rom_page(u32 pg){ if(pg>=ROM_NPG) rom_past(pg); const u8*p=rom_pg[pg]; return p?p:cd_fetch(pg); }
#else
static inline const u8 *rom_page(u32 pg){ pg&=2047; const u8*p=rom_pg[pg]; return p?p:cd_fetch(pg); }
#endif
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
#ifdef MERGED_NATIVE
  if(a-0x80000000u<0x200000u) return (u8*)a;     /* B2: a host address from native Stunt Fox (its data, its stack) handed to a DMA */
#endif
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
   game reads went back to 0 (its 1-s waits never ended).  TM0/TM1 at /1 still wrap their counts after 256 s (32-bit counts; Payback reads only TM2/TM3).
   rc8: with the real-time clock (RTC_TIMERS, clk.h) the timers come from clk_gba(), the one 64-bit guest time base of that build (RC1 lines since
   boot, 32 bits = 75.8 h, times 1066.285 GBA cycles in 64 bits); the virtual 64-bit timer state below is then not compiled, and io_cyc only counts
   the virtual VCOUNT cycles that the debug lines and the test-only menu assist print. */
#ifdef RTC_TIMERS
static u32 io_cyc, io_acc, tm_rl[4], tm_ovb[4], tm_en[4];
#define IO_ADV(c) (io_cyc+=(c))
#else
static u32 io_cyc, io_hi, io_acc, tm_t0[4], tm_t0h[4], tm_rl[4], tm_ovb[4], tm_en[4];
#define IO_ADV(c) do{ u32 c_=(c); io_cyc+=c_; if(io_cyc<c_) io_hi++; }while(0)
#endif
#include "clk.h"       /* second part: timers from the clock (RTC_TIMERS), presents at the limiter (RTC_PRESENT, RTC_PMAX) */
#ifdef RTC_GFRAMES
static u32 g_vf;       /* virtual frames (VCOUNT line 160, SWI 5): the menu present cadence; g_gframes counts real frames */
#define VF g_vf
#else
#define VF g_gframes
#endif
#ifdef RTC_PRESENT
#define VF_PRESENT() (!sf3_ok&&(VF&(PRESENT_MENU-1))==0)      /* the level presents at its limiter (C3) */
#else
#define VF_PRESENT() ((VF&(sf3_ok?(PRESENT_EVERY-1):(PRESENT_MENU-1)))==0)
#endif
static void adv_lines(u32 n){ IO_ADV(n*1232); while(n--){ io_vc=io_vc>=227?0:io_vc+1; if(io_vc==160){ VF++; ppu_flush(); if(VF_PRESENT()){ SP_INC(SP_TRIG_ADV); present(); } } } }
static void adv_poll(void){ io_acc+=96; if(io_acc>=1232){ io_acc-=1232; adv_lines(1); } }
#ifndef RTC_TIMERS
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
#endif
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
  }
#ifdef MERGED_NATIVE
  if(a-0x80000000u<0x200000u){ *avail=0x80200000u-a; return (u8*)a; }     /* B2: native Stunt Fox's own memory */
#endif
  return 0;
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
#ifdef DISP_FREEZE_GF
/* TEST-ONLY (dispatch equivalence check, never a release): the guest stops for good at its first IO read of GBA frame DISP_FREEZE_GF.  Under the
   virtual clock and the menu assist (KPLAN, no pad input) every build reaches that read through the same guest instructions, so the rig can
   compare guest RAM (EWRAM, IWRAM, palette, OAM, VRAM shadow, io[]) between a build with the dispatch patches and one without. */
u32 dsp_frozen;
static void dsp_freeze(void){ dsp_frozen=1; dbg("DISP FREEZE at guest frame "); dec(g_gframes); dbg("\n"); for(;;){} }
#endif
u32 io_read(u32 off,u32 size){
  FL_POLL();
#ifdef DISP_FREEZE_GF
  if(g_gframes>=DISP_FREEZE_GF) dsp_freeze();
#endif
#ifdef DISP_PROF
  if(off==0x10c) dsp_phase(*(volatile u32*)0x801fffc8);   /* TEST-ONLY: a TM3 read (the limiter's get_time); 0x801fffc8 = the RT_CC-saved $31 of this read */
#endif
  io_nread++;
#ifdef SPEEDPROF
  sp_now();
#endif
  ring_guard();
  if(off==0x130||off==0x131){
#ifdef RTC_GFRAMES
  clk_gba();            /* real frames: the pad is read at most once per GBA frame of real time */
#endif
#ifndef RTC_TIMERS
  adv_poll();
#endif
#ifdef SIMKEYS
 io_keys=sim_keys;          /* TEST-ONLY (unicorn sim): the host script writes sim_keys */
#elif !defined(AUTOKEYS)
 if(pad_gf!=g_gframes){ pad_gf=g_gframes; pad_frame_poll(); io_keys=pad_gba; }
#if defined(CDPADPOLL) && !defined(CDSIM)
 if(pad_cdlat){
#ifdef CDSTAT
   if(io_keys&pad_cdlat) pad_cddeliv++;
#endif
   io_keys&=~pad_cdlat; pad_cdlat=0; }   /* P6: presses seen during a CD wait or a long load read as pressed once */
#endif
#ifdef PADSPLIT
 /* wave 1 fixup, PADSPLIT: one pad change per guest frame.  The guest reads KEYINPUT once per frame of its own, and in the menus a
    frame can now take 30-40 real frames when it waits for ROM pages; a player who lets go of DOWN and presses Cross within that time
    gave the guest both changes in one read (DOWN up and A down together), and Payback's title menu then takes no A: the entry did
    not open however long A was held (rig boot_to_title, title_trace 8/8).  When a read sees a button go up and another go down,
    this read reports only the release; the new press is reported from the next guest frame on (kept in pad_split even if it was let
    go meanwhile, so it reads as pressed once).  Only while the level clock stands still (menus, pause): in a running level a guest
    frame is a whole level iteration and a held-back press would come one iteration late. */
 { static u32 pad_seen, pad_split, pad_split_vf, pad_lvclk; u32 lc=*(volatile u32*)(EW+0x1e00), menu=(lc==pad_lvclk); pad_lvclk=lc;
   if(pad_split){ if(VF!=pad_split_vf||!menu){ io_keys&=~pad_split; pad_split=0; } else io_keys|=pad_split; }
   u32 dn=0x3ffu&~io_keys, rel=pad_seen&~dn, nw=dn&~pad_seen;
   if(menu&&rel&&nw&&!pad_split){ io_keys|=nw; pad_split=nw; pad_split_vf=VF; }
   pad_seen=0x3ffu&~io_keys; }
#endif
#if defined(CDPADPOLL) && !defined(CDSIM)
 pad_cddn=0x3ffu&~io_keys;               /* what the guest has now seen down (the edge rule of cd_padpoll) */
#endif
#endif
#ifdef KPLAN
 io_keys=pad_gba&kplan_keys(io_cyc/280896);   /* MENU ASSIST: the stock game's title -> rampage menu path (frames from power-on) OR-ed with the real pad (active low: AND); the in-level plan is TESTTOUR (test only) */
#endif
#ifdef AUTOKEYS
 io_keys=auto_keys(io_nd);
#endif
 u32 v=io_keys; return size==2?v:(size==1?(v>>(8*(off-0x130)))&0xff:v); }
  if(off==6||off==7){ on_vcount_read(); adv_lines(vc_n(io_vc)); u32 v=io_vc; return size!=1?v:(v>>(8*(off-6)))&0xff; }
  if(off==4||off==5){ on_vcount_read(); adv_lines(vc_n(io_vc)); u32 ds=io16(4);
    u32 v=((io_vc>=160&&io_vc<227)?1:0)|(((io_nread&3)==0)?2:0)|((io_vc==((ds>>8)&0xff))?4:0)|(ds&0xff38);
    return size==2?(v&0xffff):(size==1?(v>>(8*(off-4)))&0xff:v); }
  if(off==0x100||off==0x104||off==0x108||off==0x10c){ u32 k=(off-0x100)/4,o;
#if defined(SPEEDPROF)||defined(RTC_PRESENT)
    on_timer_read(RT_CC_RA,k);
#endif
#ifdef RTC_TIMERS
    (void)o; return tm_read_rt(k,RT_CC_RA);
#else
    adv_poll(); return tm_cnt(k,&o);
#endif
  }
  u32 v=0; for(u32 k=0;k<size;k++) v|=io[off+k]<<(8*k); return v;
}
void io_write(u32 off,u32 size,u32 val){
  if(size<4) val&=(1u<<(8*size))-1;
  if(size==4&&off>=0xb0&&off<0xe0&&((off-0xb0)%12==0||(off-0xb0)%12==4)) val=unmap_host(val);
  if(off==0x202&&size==2){ io16w(0x202,io16(0x202)&~val); return; }
  for(u32 k=0;k<size;k++) io[off+k]=val>>(8*k);
  for(u32 ch=0;ch<4;ch++){ u32 cnt=0xb0+12*ch+8; if(off<=cnt+2&&off+size>=cnt+4) dma_check(ch); }
#ifdef RTC_TIMERS
  if(off>=0x100&&off<0x110) tm_write_check_rt();
#else
  if(off>=0x100&&off<0x110) tm_write_check();
#endif
  if(off==0&&size>=2){ g_dispcnt_writes++; pp_dispcnt(io16(0)); tick();
#ifdef SPEEDPROF
    { static u32 d0; u32 d=io16(0); if((d^d0)&0x10) SP_INC(SP_FLIPS); d0=d; }   /* page flips: the GBA reference counts menu iterations this way */
#endif
  }
}
/* ---------------------------------------------------------------- C helpers called from RT_CC */
/* stage 20: a host-form VRAM pointer that runs past the 96 KiB VRAM shadow (0x80199000..: the 3D renderer's code and data) is folded back the way GBA VRAM
   mirrors (128 KiB period, 0x06018000..0x0601FFFF = 0x06010000..0x06017FFF), as a guest-form address would be by g2h(); nothing outside the guest windows is touched */
static u32 vram_over_n;      /* the first fold is reported on the TTY ('overflow' is one of the rig's fault words): the guard hides the damage, not the bug */
static inline u32 vram_over(u32 ea){ if(ea-((u32)VRAM+0x18000u)<0x801b0000u-((u32)VRAM+0x18000u)){ if(!vram_over_n++){ dbg("VRAM shadow overflow folded back "); hex(ea); dbg("\n"); } u32 o=(ea-(u32)VRAM)&0x1ffffu; if(o>=0x18000u) o-=0x8000u; ea=(u32)VRAM+o; } return ea; }
#ifdef DISP_PROF
/* TEST-ONLY counters of the C calls the dispatch work removes (PLAN.md Stage 2): RT_MISS C calls, h_memrd calls (and of them ROM reads),
   h_memwr calls, D1 cache fills.  The test rig reads them by symbol and divides by the level clock (one tick per level-loop iteration). */
u32 dsp_nmiss, dsp_nmrd, dsp_nrom, dsp_nmwr, dsp_nfill;
#define DSP_PROF(x) (x)
#else
#define DSP_PROF(x) ((void)0)
#endif
u32 h_memrd(u32 ea,u32 kind){
  DSP_PROF((dsp_nmrd++, dsp_nrom+=((ea>>24)==8||(ea>>24)==10||(ea>>24)==12)));    /* TEST-ONLY: every call, and the ROM reads among them */
  static const u8 SZ[5]={1,1,2,2,4}; u32 size=SZ[kind]; u32 v; ea=vram_over(ea);
  if((ea>>24)==8||(ea>>24)==10||(ea>>24)==12){ SP_INC(SP_ROMRD);
#ifdef SPEEDPROF
    sp_now();           /* keep the stamp clock's 16-bit deltas short in logic that reads no IO */
#endif
    v=rom_read(ea,size); }
  else if((ea>>24)==13) v=1;
  else if(ea-0x8017f000u<0x400) v=io_read(ea-0x8017f000u,size);
#ifdef MERGED_NATIVE
  else if(ea>=0x80000000u&&ea<0x80200000u){ v=0; for(u32 k=0;k<size;k++) v|=((u32)((volatile u8*)ea)[k])<<(8*k); }    /* B2: native Stunt Fox's data and stack too */
#else
  else if(ea>=0x80180000u&&ea<0x80200000u){ v=0; for(u32 k=0;k<size;k++) v|=((u32)((volatile u8*)ea)[k])<<(8*k); }
#endif
  else if((ea>>24)==4&&(ea&0xfffffc00u)==0x04000000u) v=io_read(ea&0x3ff,size);
  else if((ea>>24)>=2&&(ea>>24)<=7&&g2h(ea)){ const volatile u8*p=g2h(ea); v=0; for(u32 k=0;k<size;k++) v|=((u32)p[k])<<(8*k); }   /* raw guest RAM address that reached the slow path (runtime-built pointer, e.g. lsl #19 constants) */
#ifdef MERGED
  /* Milestone B: 0x09000000.. is past the 16 MiB image.  Star-FlyBack's radio looks for its tables there (title songs 0x09500000, streams, edits: only
     in a 32 MiB cartridge with the remixes); a GBA cartridge bus answers an address past the chip with the address itself (open bus: halfword =
     address/2), which is no table magic.  Served here without a disc read (rom_obus_n counts them). */
  else if((ea>>24)==9){ u32 h0=(ea>>1)&0xffffu, h1=((ea+2)>>1)&0xffffu; rom_obus_n++; v=size==4?(h0|h1<<16):size==2?h0:((ea&1)?(h0>>8):(h0&0xff)); }
#endif
  else { dbg("BADRD "); hex(ea); v=0; }
  if(kind==1&&(v&0x80)) v|=0xffffff00; if(kind==3&&(v&0x8000)) v|=0xffff0000;
  return v;
}
u32 h_memwr(u32 ea,u32 size,u32 val){
  ea=vram_over(ea); DSP_PROF(dsp_nmwr++);
  if(ea-0x8017f000u<0x400) io_write(ea-0x8017f000u,size,val);
#ifdef MERGED_NATIVE
  else if(ea>=0x80000000u&&ea<0x80200000u){ for(u32 k=0;k<size;k++) ((volatile u8*)ea)[k]=val>>(8*k); }
#else
  else if(ea>=0x80180000u&&ea<0x80200000u){ for(u32 k=0;k<size;k++) ((volatile u8*)ea)[k]=val>>(8*k); }
#endif
  else if((ea>>24)==13) {}
  else if((ea>>24)==4&&(ea&0xfffffc00u)==0x04000000u) io_write(ea&0x3ff,size,val);
  else if((ea>>24)>=2&&(ea>>24)<=7&&g2h(ea)){ volatile u8*p=g2h(ea); for(u32 k=0;k<size;k++) p[k]=val>>(8*k); RAW_PADPOLL(); }   /* raw guest RAM address on the slow path (see h_memrd) */
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
#ifdef MERGED_NATIVE
#include "sfnat_place.h"
static u32 cold_nat_n;
#endif
static u8 cold_loaded[COLDGROUPS]; static u32 cold_loads, cold_calls, cold_conflicts; static u32 sf3_retry, last_cold_pres, sf3_clk0;   /* stage 12: renderer switched off by an overlay load (pause menu code) comes back once the level clock runs again (pause over) and no cold group was loaded for 6 presents */
static void flush_icache(void){ register u32 t1 __asm__("$9")=0x44;   /* kernel FlushCache A(44h): argument area and clobbers as dbgc() */
  __asm__ volatile("addiu $29,$29,-16\n li $8,0xA0\n jalr $8\n nop\n addiu $29,$29,16":"+r"(t1)::"$1","$2","$3","$4","$5","$6","$7","$8","$10","$11","$12","$13","$14","$15","$24","$25","$31","hi","lo","memory"); }
#ifdef COLD_SECS
#define COLD_SECS_N COLD_SECS
#else
#define COLD_SECS_N (CD_COLD_PAGES*2)
#endif
#ifdef COLD1PASS
#ifndef COLD1_QUIET
#ifdef RTC_GFRAMES
#define COLD1_QUIET 30u        /* g_gframes counts REAL frames here (Stage 1): 0.5 s without a data read before present() starts the one pass
                                  (the value 4 was tuned in virtual frames, 0.25-1 s in the menus; 4 real frames would be 67 ms) */
#else
#define COLD1_QUIET 4u         /* guest frames without a data read before present() starts the one pass */
#endif
#endif
/* speed item M5: COLD.BIN in one pass.  The whole file is read into the homes of all groups (two requests of at most CD_RUN sectors, through
   cd_read's retries), every group is marked loaded only after the read, and the I-cache is flushed once.  Only in the menus before the
   first level start: the renderer is off and its world window, which the last groups overlap, is not loaded yet; main() copied the boot
   image out of the cold homes long before.  At the level start sf3_init() drops the groups over the world window as before, and later
   loads go through the per-group path below.  It starts at the game's first page miss when that comes in the boot's black screen (the
   BG palette all zero; the white flash has faded out, the guest builds the language screen and presents nothing), so the 2.6 s read
   freezes no animation (at the first quiet picture after the first data read, the language screen, it stopped the panning backdrop and
   the sliding list for the whole read); else present() starts it at the first quiet picture after the first data read (P6 latches
   presses made meanwhile); the first cold call starts it if that comes earlier. */
static u32 cold_m5;   /* 0 not yet, 1 read, 2 never (a level had started first: the level clock ran or the renderer was on) */
/* every BG palette entry is black (the backdrop too): M5's test for the boot's black screen in cd_fetch */
static int pal_bg_zero(void){ const volatile u32*p=(const volatile u32*)PAL; u32 o=0; for(u32 i=0;i<128;i++) o|=p[i]; return !(o&0x7fff7fffu); }
#ifdef MERGED_NATIVE
/* B2: Payback's CUBE_BeginModify (0x0803c3bc) copies a level cell into one of 200 slots of 64 bytes at 0x02003f24 before changing it, unless the
   cell's pointer already is a copy: "pointer <= 0x07ffffff" on the GBA (RAM below the ROM).  Translated with model P that pointer is the host
   address 0x801b.., above the constant: every call made a new copy and the slots were never given back (rc10 too: all 199 taken a few seconds
   into a level).  Stunt Fox's polygon pool lies over those slots (render.c pool_floor), so in a car or the Arwing it had no room and the 3D
   picture stopped.  The translated test (cold group, COLD.BIN offset 0x6c764) becomes "not a ROM pointer (0x08000000..0x09ffffff)": the same
   answer for every GBA pointer, and right for host pointers.  Patched only when the five words are the ones expected; b2_cellfix counts it. */
static u32 b2_cellfix;
static void b2_coldfix(void){
  volatile u32*w=(volatile u32*)(COLD_HOST+0x6c764u);
  if((u32)w+20>SF_NAT_LO) return;
  if(w[0]==0x3c1007ffu&&w[1]==0x3610ffffu&&w[2]==0x02405821u&&w[3]==0x0212082bu&&w[4]==0x1020014bu){
    w[0]=0x3c10f800u;      /* lui  $16,0xf800        r0 = -0x08000000 */
    w[1]=0x02128021u;      /* addu $16,$16,$18       r0 = r2 - 0x08000000 */
    w[3]=0x00108642u;      /* srl  $16,$16,25        0 for a ROM pointer */
    w[4]=0x1600014bu;      /* bnez $16,(the same skip): not ROM: already a copy */
    b2_cellfix++; }
}
#endif
__attribute__((noinline)) static void cold_all(void){
  if(cold_m5) return;
  cold_m5=2; if(*(volatile u32*)(EW+0x1e00) || sf3_ok) return;
  cold_m5=1;
#ifdef MERGED_NATIVE
  { u32 ng=(SF_NAT_LO-COLD_HOST)>>14, ns=ng*8<COLD_SECS_N?ng*8:COLD_SECS_N;      /* B2: only the groups below native Stunt Fox */
    cd_read(CD_COLD_LBA,ns,(u8*)COLD_HOST);
    for(u32 k=0;k<(ns+7)/8 && k<COLDGROUPS;k++) cold_loaded[k]=1;
    b2_coldfix(); }
#else
  cd_read(CD_COLD_LBA,COLD_SECS_N,(u8*)COLD_HOST);
  for(u32 k=0;k<(COLD_SECS_N+7)/8 && k<COLDGROUPS;k++) cold_loaded[k]=1;
#endif
  last_cold_pres=g_pres; flush_icache();
}
#endif
/* RT_MISS: a direct call/jump/function pointer reached a guest function that is not in the resident blob.  Overlay loader:
   find it in the cold table, read the 16 KiB groups of COLD.BIN that cover the function (and its out-of-line stubs) into their fixed
   home addresses, flush the I-cache, and return the host entry for RT_MISS to tail-jump to. */
/* cold_find: host entry of a function in the cold table (its groups are loaded from the disc), 0 if the address is not in the table */
static u32 vene[24][4] __attribute__((aligned(16))); static u32 vene_g[24], nvene;   /* resident veneer copies (stage 12, below): never recycled */
#ifdef DISP_D2
static u32 cf_perm;      /* stage 20 D2: the host entry cold_find returned last can never go away (a veneer copy, or a span whose groups all lie below the renderer's world window) */
#define CF_PERM(x) (cf_perm=(x))
#else
#define CF_PERM(x) ((void)0)
#endif
static u32 cold_find(u32 addr){
  u32 g=addr&~1u; const u32*ct=(const u32*)coldtab; u32 n=ct[0]; const u32*r=ct+1; u32 lo=0,hi=n; cold_calls++;
  CD_PADPOLL(526u);      /* P6: a long load runs here for seconds without a disc read or a KEYINPUT read */
  while(lo<hi){ u32 m=(lo+hi)>>1; u32 v=r[m*4]; if(v==g){ lo=m; goto found; } if(v<g) lo=m+1; else hi=m; }
  return 0;
found:;
  u32 host=r[lo*4+1], hs=r[lo*4+2], he=r[lo*4+3];
  u32 g0=(hs-COLD_HOST)>>14, g1=(he-1-COLD_HOST)>>14, loaded=0;
#ifdef MERGED_NATIVE
  /* B2: native Stunt Fox lives from SF_NAT_LO up (ps1/merged/place.py): a group that reaches it is never loaded, its functions are interpreted */
  if(COLD_HOST+(g1+1)*16384u>SF_NAT_LO){ static u32 nnat; cold_nat_n++; if(nnat<24){ nnat++; dbg("COLD group over native SF: interpreting "); hex(addr); dbg("\n"); } return 0; }
#endif
  /* stage 12: a tiny, position-independent cold function (the bx rN veneers, 12 bytes) whose group lies inside the renderer's data window used to switch the 3D renderer off when the HUD/text code reached it
     in a level (the group load would overwrite the world).  Its few words are read from the disc and kept in a small resident table instead; the group is not loaded. */
  if(sf3_ok && g0==g1 && he-hs<=16 && he>SF_WORLD_LO && hs<0x8011b200u && !cold_loaded[g0]){
    u32*const vtmp=(u32*)__veneer_scratch;   /* dedicated linker-reserved 4 KiB, outside PPU CLUT/row buffers and renderer code */
    for(u32 q=0;q<nvene;q++) if(vene_g[q]==g){ CF_PERM(1); return (u32)vene[q]+(host-hs); }
    if(nvene<24){ u32 dst=COLD_HOST+g0*16384, off=hs-dst, sec=off>>11, left=CD_COLD_PAGES*2-g0*8-sec; cd_read(CD_COLD_LBA+g0*8+sec,left<2?left:2,(u8*)vtmp);
      const u32*src=(const u32*)((u8*)vtmp+(off&2047)); u32 nw=(he-hs)>>2, ok=1; for(u32 q=0;q<nw;q++){ u32 op=src[q]>>26; if(op==1||(op>=4&&op<=7)) ok=0; }
      if(ok){ for(u32 q=0;q<4;q++) vene[nvene][q]=q<nw?src[q]:0; vene_g[nvene]=g; nvene++; flush_icache(); dbg("VENEER resident copy "); hex(g); dbg("\n"); CF_PERM(1); return (u32)vene[nvene-1]+(host-hs); } } }
#ifdef COLD1PASS
  if(!cold_loaded[g0]||!cold_loaded[g1]) cold_all();      /* a cold call before the one pass: do the pass now (later: returns at once) */
#endif
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
#ifdef MERGED_NATIVE
  if(loaded) b2_coldfix();
#endif
  if(loaded){ last_cold_pres=g_pres; flush_icache(); dbg("COLD load "); hex(addr); dec(g0); dec(g1); dbg("\n"); }
  CF_PERM(COLD_HOST+(g1+1)*16384u<=SF_WORLD_LO);     /* every group of the span ends below the world window: never dropped (present()) */
  return host;
}
/* ---------------------------------------------------------------- stage 20 dispatch phase 1 (PLAN.md Stage 2), each item behind its own flag:
   D3 -DDISP_D3  RT_MEMRD's first word `j RT_MEMRD_SLOW` -> nop: the blob's own fast path serves aligned lb/lbu/lh/lhu/lw from resident ROM pages
   D1 -DDISP_D1  RT_MISS words 0-1 -> `j rt_mcache; addu $24,$25,$0`: a 512 x 8 B cache of cold_find results (dsp_mcache, BSS) in front of the C call
   D4 -DDISP_D4  RT_MEMRD -> `j rd_front`, RT_MEMWR -> `j wr_front`: EWRAM/IWRAM by GBA address without the C call (ROM reads to D3's fast path first; IO still goes to C)
   D2 -DDISP_D2  h_miss links a `jal RT_MISS` call site to its permanent host entry: queued in dsp_lq (BSS), written at the next present, one FlushCache
   test only: -DDISP_D1CHK checks every D1 hit against the cold table (dsp_mchk_bad = 0 expected), -DDISP_PROF counts the C calls.
   The blob addresses are the stubs of t2m.py runtime() (cfg 'P'): RT_MISS 0x80030008, rt_miss_ret 0x80030028, RT_MEMRD 0x80030044, its ROM fast path
   0x8003004c, kind dispatch 0x8003009c, RT_MEMRD_SLOW 0x80030128, RT_MEMWR 0x8003013c, RT_CC 0x80030150.  dsp_boot() compares every word the new code
   relies on before it patches anything; on a mismatch it patches nothing and says so on the TTY. */
#if defined(DISP_D1)||defined(DISP_D2)||defined(DISP_D3)||defined(DISP_D4)
#define DISP_ANY 1
#endif
#if defined(DISP_D1CHK)&&!defined(DISP_D1)
#error "DISP_D1CHK checks the D1 cache: it needs -DDISP_D1"
#endif
#ifdef DISP_ANY
u32 dsp_ok;             /* the boot patches are in (read by the test rig) */
#endif
#ifdef DISP_D1
/* 512 x {key = guest target >> 1 (0xffffffff = empty), host entry}.  rc8: in the runtime's BSS (rt_mcache addresses it by symbol): wave 1 had it at
   0x80028400 in the reserved area below ROMPG, which rc7's .rtcold code fills (ps1.ld) */
u32 dsp_mcache[1024] __attribute__((aligned(8)));
#define MCACHE ((volatile u32*)dsp_mcache)
static void dsp_mclear(void){ for(u32 i=0;i<1024;i+=2) MCACHE[i]=0xffffffffu; }   /* at boot and wherever a cold group is dropped */
static inline u32 dsp_mslot(u32 addr){ return ((addr>>1)^(addr>>12))&511; }       /* = rt_mcache */
#else
#define dsp_mclear() ((void)0)
#endif
#ifdef DISP_D2
/* D2: rules of dispatch.md D2 for the call site at ra-8 and the target addr (as RT_MISS got it): ra word-aligned in the hot blob or in a loaded cold group;
   the site is `jal RT_MISS` (0x0c00c002); the `li $25` before it encodes addr exactly (lui+ori at ra-16/ra-12, or lui alone at ra-12 when the low half is 0) */
static u32 dsp_lq[256] __attribute__((section(".sf.bss.dsp_lq")));                     /* 64 x {site, target, host, 0}; rc8: BSS (wave 1: 0x80029400, now .rtcold) */
#define LQ ((volatile u32*)dsp_lq)
#define LQ_N 64u
u32 lq_n, d2_linked, d2_queued, d2_full, d2_stale, d2_batches;     /* read by the test rig: keep them external */
static int d2_site_ok(u32 addr,u32 ra){
  if(ra&3) return 0;
  u32 s=ra-8;
  if(!(s>=0x80030310u&&s<0x80044288u)){ u32 k=(s-COLD_HOST)>>14; if(s<COLD_HOST||k>=COLDGROUPS||!cold_loaded[k]) return 0; }
  const volatile u32*w=(const volatile u32*)s;
  if(w[0]!=0x0c00c002u) return 0;
  u32 hi=0x3c190000u|(addr>>16), lo=0x37390000u|(addr&0xffff);
  return (w[-1]==lo&&w[-2]==hi)||((addr&0xffff)==0&&w[-1]==hi);
}
/* 1 = the site is linked or queued (do not cache: the next calls from it must reach h_miss until the queue is written).  A full queue
   returns 0, so h_miss caches the target in D1 instead: else every call from a site that did not fit went through h_miss and cold_find
   until the next present drained the queue, about once a second in a level (review of wave 1: 204 full in a 10 min soak). */
static int d2_link(u32 addr,u32 ra,u32 host){
  if(!cf_perm||!d2_site_ok(addr,ra)) return 0;
  u32 s=ra-8;
  for(u32 q=0;q<lq_n;q++) if(LQ[4*q]==s) return 1;
  if(lq_n>=LQ_N){ d2_full++; return 0; }
  LQ[4*lq_n]=s; LQ[4*lq_n+1]=addr; LQ[4*lq_n+2]=host; lq_n++; d2_queued++; return 1;
}
/* at a present: write the queued sites (each checked again: its group may have been dropped since), then one FlushCache */
static void d2_apply(void){
  if(!lq_n) return;
  u32 n=0;
  for(u32 q=0;q<lq_n;q++){ u32 s=LQ[4*q], addr=LQ[4*q+1], host=LQ[4*q+2];
    if(d2_site_ok(addr,s+8)){ *(volatile u32*)s=0x0c000000u|((host>>2)&0x03ffffffu); n++; } else d2_stale++; }
  lq_n=0; d2_linked+=n; d2_batches++;
  if(n) flush_icache();
  if(d2_batches<=8||(d2_batches&63)==0){ dbg("DISP D2 linked "); dec(n); dbg("total "); dec(d2_linked); dbg("stale "); dec(d2_stale); dbg("full "); dec(d2_full); dbg("\n"); }
}
#endif
#ifdef DISP_D1CHK
/* TEST-ONLY: every D1 hit comes here (RT_CC from rt_mcache, a2 = the cached host) and is checked against the cold table without side effects: the same host
   (or the function's resident veneer copy) and every group of its span loaded.  A mismatch is counted and printed; the call then takes the normal path. */
u32 dsp_mchk_hits, dsp_mchk_bad;
static u32 h_miss2(u32 addr,u32 ra);
u32 h_mchk(u32 addr,u32 ra,u32 cached){
  u32 g=addr&~1u, ok=0; const u32*ct=(const u32*)coldtab; u32 n=ct[0]; const u32*r=ct+1; u32 lo=0,hi=n; dsp_mchk_hits++;
  while(lo<hi){ u32 m=(lo+hi)>>1; u32 v=r[m*4]; if(v==g){ lo=m; goto found; } if(v<g) lo=m+1; else hi=m; }
  goto out;
found:;
  { u32 host=r[lo*4+1], hs=r[lo*4+2], he=r[lo*4+3]; int vq=-1;
    for(u32 q=0;q<nvene;q++) if(vene_g[q]==g) vq=(int)q;
    if(vq>=0) ok=(cached==(u32)vene[vq]+(host-hs));
    else if(cached==host){ ok=1; for(u32 k=(hs-COLD_HOST)>>14;k<=(he-1-COLD_HOST)>>14;k++) if(!cold_loaded[k]) ok=0; } }
out:
  if(ok) return cached;
  dsp_mchk_bad++; if(dsp_mchk_bad<=16){ dbg("DISP D1 CHECK MISMATCH target "); hex(addr); dbg("cached "); hex(cached); dbg("\n"); }
  MCACHE[2*dsp_mslot(addr)]=0xffffffffu;
  return h_miss2(addr,ra);
}
#endif
#ifdef DISP_D1
/* D1 fill: only a cold_find result (never the interpreter), and not when D2 has linked or queued the call site */
#define MC_FILL(a,h) do{ if(dsp_ok){ u32 s_=dsp_mslot(a); MCACHE[2*s_+1]=(h); MCACHE[2*s_]=(a)>>1; DSP_PROF(dsp_nfill++); } }while(0)
#else
#define MC_FILL(a,h) ((void)0)
#endif
#ifdef DISP_D2
#define D2_LINK(a,ra,h) (dsp_ok&&d2_link((a),(ra),(h)))
#else
#define D2_LINK(a,ra,h) 0
#endif
#ifdef NO_INTERP
static const u32 ip_enters = 0;  /* diagnostic value for the full-cold simulator */
u32 h_miss(u32 addr,u32 ra){ (void)ra; SP_INC(SP_MISS); DSP_PROF(dsp_nmiss++); u32 h=cold_find(addr); if(h){ if(!D2_LINK(addr,ra,h)) MC_FILL(addr,h); return h; } gpu_panic("RT_MISS guest code not in cold set: ",addr); return 0; }
#else
#include "interp_glue.h"
/* RT_MISS: overlay loader, else the interpreter (stage 8: nothing halts).  a1 = the caller's $31 when the stage 20 RT_MISS patch is in (rt_mcache).
   rc8: the overlay-area targets of the intro fix (rc7) are decided first.  rc8 review: an overlay-0 target with a cold-table entry
   (0x03000da8, OV1_INIT) fell through to the D2 link and the D1 fill, so a later call there while the film overlay is resident could have
   taken the stale overlay-0 code before this test.  Such a target is never linked (D2: a call site cannot be unlinked); it may go into D1,
   which is filled here only while overlay 0 is resident, and ov_slots(1) (the film overlay comes in) empties D1.  Not caching it at all
   cost the menus 4-7 % (pad route to the level 66 frames later on SwanStation, 114 on Beetle). */
u32 h_miss(u32 addr,u32 ra){
  (void)ra; SP_INC(SP_MISS); DSP_PROF(dsp_nmiss++);
  ov_sync();
  if(((addr&~1u)-OV_BASE)<OV1_SIZE){ if(!ov_res()) return film_miss(addr); u32 h=hot_lookup(addr&~1u); if(h) return h;   /* intro fix: overlay area (interp_glue.h) */
    h=cold_find(addr); if(h){ MC_FILL(addr,h); return h; } interp_target=addr&~1u; return (u32)interp_enter; }
  u32 h=cold_find(addr); if(h){ if(!D2_LINK(addr,ra,h)) MC_FILL(addr,h); return h; } interp_target=addr&~1u; return (u32)interp_enter; }
#endif
#ifdef DISP_D1CHK
static u32 h_miss2(u32 addr,u32 ra){ return h_miss(addr,ra); }
#endif
#ifdef DISP_ANY
/* The new code.  rt_mcache: RT_MISS jumps here with $24 = $25 = the guest target and $31 = the caller's return address; it uses only $1, $2, $3, $24, $25
   and $28, which the C call it replaces clobbers too ($2 carries its result), so flags ($4-$7), guest registers and $31 are untouched. */
__asm__(
  ".pushsection .text,\"ax\",@progbits\n.set push\n.set noreorder\n.set noat\n.align 2\n"
#if defined(DISP_D1)||defined(DISP_D2)
  ".globl rt_mcache\n.type rt_mcache,@function\n"
  "rt_mcache:\n"
#ifdef DISP_D1
  " srl $1,$24,1\n"                 /* key = target >> 1: the Thumb bit does not matter */
  " srl $2,$24,12\n"
  " xor $2,$2,$1\n"
  " andi $2,$2,511\n"               /* slot = ((t >> 1) ^ (t >> 12)) & 511 */
  " sll $2,$2,3\n"
  " lui $25,%hi(dsp_mcache)\n"
  " addu $2,$2,$25\n"
  " lw $25,%lo(dsp_mcache)($2)\n"   /* key[slot], dsp_mcache + 8 * slot (8-aligned: %lo(+4) has the same %hi) */
  " lw $2,%lo(dsp_mcache+4)($2)\n"  /* host[slot] (load delay of the key) */
  " bne $25,$1,rt_mslow\n"
  " lui $25,0x8002\n"               /* delay slot: first word of the slow path */
#ifdef DISP_D1CHK
  " addu $3,$2,$0\n"                /* TEST-ONLY: a2 = the cached host, checked by h_mchk through RT_CC */
  " lui $25,%hi(h_mchk)\n"
  " j rt_mcc\n"
  " addiu $25,$25,%lo(h_mchk)\n"
#else
  " jr $2\n"                        /* hit: straight to the host entry */
  " nop\n"
#endif
#else
  " lui $25,0x8002\n"
#endif
  "rt_mslow:\n"                     /* RT_MISS's own body: h_miss = HELP+8 through RT_CC, back through rt_miss_ret (jr $2) */
  " ori $25,$25,0x8008\n"
  " lw $25,0($25)\n"
  "rt_mcc:\n"
  " addu $2,$31,$0\n"               /* a1 = the caller's return address (D2) */
  " lui $28,0x8003\n"
  " j 0x80030150\n"
  " ori $28,$28,0x0028\n"
  ".size rt_mcache,.-rt_mcache\n"
#endif
#ifdef DISP_D4
  /* rd_front, from RT_MEMRD: $24 = address, $2 = kind (0 lbu, 1 lb, 2 lhu, 3 lh, 4 lw), $28 = return.  By the region byte a >> 24: ROM first (about
     four of five reads here are ROM reads): the fast path's own region test (regions 8, 10, 12, 14), then the fast path past it, 0x80030060, which takes
     $25 = the region byte (D3); then EWRAM 0x801b0000 + (a & 0x3ffff) and IWRAM 0x801f0000 + (a & 0x7fff), = g2h(), into the blob's kind dispatch
     (alignment checks, the load, jr $28).  Everything else goes to C (RT_MEMRD_SLOW): GBA IO and the IO page 0x8017f000 (io_read and the clock;
     region byte 0x80), raw host addresses, a ROM page that is not resident, a misaligned read */
  ".globl rd_front\n.type rd_front,@function\n"
  "rd_front:\n"
  " srl $25,$24,24\n"
  " andi $1,$25,0xf9\n"
  " xori $1,$1,8\n"
  " beq $1,$0,rd_rom\n"
  " addiu $1,$25,-2\n"              /* (on the ROM path 0x80030060 sets $1 again) */
  " beq $1,$0,rd_ew\n"
  " addiu $1,$25,-3\n"
  " bne $1,$0,rd_slow\n"
  " andi $25,$24,0x7fff\n"
  " lui $1,0x801f\n"
  " j 0x8003009c\n"
  " addu $25,$25,$1\n"
  "rd_ew:\n"
  " sll $25,$24,14\n"
  " srl $25,$25,14\n"
  " lui $1,0x801b\n"
  " j 0x8003009c\n"
  " addu $25,$25,$1\n"
  "rd_rom:\n"
#ifdef DISP_D3
  " j 0x80030060\n"                 /* the ROM fast path past its region test: sltiu $1,$25,0xe; ROMPG[(a >> 12) & 0x7ff]; the kind dispatch */
  " nop\n"
#endif
  "rd_slow:\n"
  " j 0x80030128\n"
  " nop\n"
  ".size rd_front,.-rd_front\n"
  /* wr_front, from RT_MEMWR (its delay slot `ori $25,$25,0x8004` has run, so $25 is not used): $24 = address, $2 = size 1/2/4, $3 = value.  The same windows
     by the region byte; aligned sb/sh/sw; everything else (GBA IO and the IO page, a misaligned store, any other address) takes RT_MEMWR's own body,
     rebuilt here (h_memwr = HELP+4 through RT_CC) */
  ".globl wr_front\n.type wr_front,@function\n"
  "wr_front:\n"
  " srl $25,$24,24\n"
  " addiu $1,$25,-2\n"
  " beq $1,$0,wr_ew\n"
  " addiu $1,$25,-3\n"
  " bne $1,$0,wr_slow\n"
  " andi $25,$24,0x7fff\n"
  " lui $1,0x801f\n"
  " b wr_st\n"
  " addu $25,$25,$1\n"
  "wr_ew:\n"
  " sll $25,$24,14\n"
  " srl $25,$25,14\n"
  " lui $1,0x801b\n"
  " addu $25,$25,$1\n"
  "wr_st:\n"
  " addiu $1,$2,-4\n"
  " beq $1,$0,wr_w\n"
  " addiu $1,$2,-2\n"
  " beq $1,$0,wr_h\n"
  " addiu $1,$2,-1\n"
  " bne $1,$0,wr_slow\n"
  " nop\n"
  " jr $28\n"
  " sb $3,0($25)\n"
  "wr_w:\n"
  " andi $1,$24,3\n"
  " bne $1,$0,wr_slow\n"
  " nop\n"
  " jr $28\n"
  " sw $3,0($25)\n"
  "wr_h:\n"
  " andi $1,$24,1\n"
  " bne $1,$0,wr_slow\n"
  " nop\n"
  " jr $28\n"
  " sh $3,0($25)\n"
  "wr_slow:\n"
  " lui $25,0x8002\n"
  " ori $25,$25,0x8004\n"
  " lw $25,0($25)\n"
  " j 0x80030150\n"
  " nop\n"
  ".size wr_front,.-wr_front\n"
#endif
  /* the new words of the boot patches, in the order of dsp_at[] below.  Assembled (never executed here) so that the linker resolves the jumps and
     mips1_lint checks them with the rest of the code; ps1/tools/disp_patch_check.py decodes them in the linked ELF. */
  ".globl dsp_new\n.type dsp_new,@function\n"
  "dsp_new:\n"
#if defined(DISP_D1)||defined(DISP_D2)
  " j rt_mcache\n"                  /* 0x80030008 */
  " addu $24,$25,$0\n"              /* 0x8003000c: RT_MISS's first word, now in the delay slot */
#endif
#ifdef DISP_D4
  " j rd_front\n"                   /* 0x80030044 */
  " j wr_front\n"                   /* 0x8003013c */
#elif defined(DISP_D3)
  " nop\n"                          /* 0x80030044: falls through into the ROM fast path (its delay slot 0x80030048 is a nop) */
#endif
  ".size dsp_new,.-dsp_new\n"
  ".globl dsp_new_end\ndsp_new_end:\n"
  ".set pop\n.popsection\n");
extern const u32 dsp_new[], dsp_new_end[];
/* patched words: address and the original word (t2m.py runtime()), in the order of dsp_new */
static const u32 dsp_at[][2]={
#if defined(DISP_D1)||defined(DISP_D2)
  {0x80030008u,0x0320c021u},       /* RT_MISS: addu $24,$25,$0 */
  {0x8003000cu,0x3c198002u},       /*          lui $25,0x8002 */
#endif
#ifdef DISP_D4
  {0x80030044u,0x0800c04au},       /* RT_MEMRD: j RT_MEMRD_SLOW */
  {0x8003013cu,0x3c198002u},       /* RT_MEMWR: lui $25,0x8002 */
#elif defined(DISP_D3)
  {0x80030044u,0x0800c04au},
#endif
};
/* words the new code relies on, checked and left as they are */
static const u32 dsp_keep[][2]={
  {0x80030010u,0x37398008u},{0x80030014u,0x8f390000u},     /* RT_MISS: ori $25,$25,0x8008 (HELP+8); lw $25,0($25) */
  {0x80030018u,0x3c1c8003u},{0x8003001cu,0x379c0028u},     /*          la $28,rt_miss_ret */
  {0x80030020u,0x0800c054u},{0x80030024u,0x00000000u},     /*          j RT_CC; nop */
  {0x80030028u,0x00400008u},{0x8003002cu,0x00000000u},     /* rt_miss_ret: jr $2; nop */
  {0x80030048u,0x00000000u},                               /* RT_MEMRD delay slot: nop */
  {0x8003004cu,0x0018ce02u},{0x80030050u,0x332100f9u},     /* ROM fast path: srl $25,$24,24; andi $1,$25,0xf9 (region test) */
  {0x80030054u,0x38210008u},{0x80030060u,0x2f21000eu},     /*                xori $1,$1,8; past the test (D4's rd_front enters here): sltiu $1,$25,0xe */
  {0x80030078u,0x3c198002u},{0x8003007cu,0x3739a000u},     /*                la $25,ROMPG (0x8002a000) */
  {0x8003008cu,0x13200026u},{0x80030094u,0x33010fffu},     /*                beqz $25,RT_MEMRD_SLOW; andi $1,$24,0xfff */
  {0x8003009cu,0x2441fffcu},{0x800300a0u,0x1020000fu},     /* kind dispatch: addiu $1,$2,-4; beqz $1,lw */
  {0x800300ecu,0x8f220000u},{0x800300f0u,0x03800008u},     /*                lw $2,0($25); jr $28 */
  {0x80030128u,0x3c198002u},{0x8003012cu,0x37398000u},     /* RT_MEMRD_SLOW: la $25,HELP+0 */
  {0x80030130u,0x8f390000u},{0x80030134u,0x0800c054u},     /*                lw $25,0($25); j RT_CC */
  {0x80030140u,0x37398004u},{0x80030148u,0x0800c054u},     /* RT_MEMWR: ori $25,$25,0x8004 (the patched word's delay slot); j RT_CC */
  {0x80030150u,0x3c1d801fu},{0x80030154u,0x37bdff90u},     /* RT_CC: la $29,0x801fff90 */
  {0x80030184u,0x03002021u},{0x80030188u,0x00402821u},     /*        a0 = $24; a1 = $2 */
  {0x8003018cu,0x00603021u},{0x80030190u,0x0320f809u},     /*        a2 = $3; jalr $25 */
  {0x800301c4u,0x03800008u},                               /*        jr $28 */
};
/* a hash of the rest of the ROM fast path and the kind dispatch (0x8003004c..0x80030128, which D3 and D4 run): ((h << 5) | (h >> 27)) ^ word */
#ifdef MERGED
#define DSP_FAST_HASH 0x5b2dd86du   /* the fast path masks the page number with 0xfff (t2m T2M_ROMPG_N=4096): one bit more than below */
#else
#define DSP_FAST_HASH 0x5b2dc86du
#endif
static void dsp_boot(void){
  u32 n=sizeof dsp_at/sizeof dsp_at[0], bad=0, h=0;
  if((u32)(dsp_new_end-dsp_new)!=n) bad=1;
  for(u32 i=0;i<n&&!bad;i++) if(*(volatile u32*)dsp_at[i][0]!=dsp_at[i][1]) bad=dsp_at[i][0];
  for(u32 i=0;i<sizeof dsp_keep/sizeof dsp_keep[0]&&!bad;i++) if(*(volatile u32*)dsp_keep[i][0]!=dsp_keep[i][1]) bad=dsp_keep[i][0];
  for(u32 a=0x8003004cu;a<0x80030128u;a+=4) h=((h<<5)|(h>>27))^*(volatile u32*)a;
  if(!bad&&h!=DSP_FAST_HASH) bad=0x8003004cu;
  if(bad){ dbg("DISP boot patches NOT applied: the blob word at "); hex(bad); dbg("is not the expected one (fast path hash "); hex(h); dbg(")\n"); return; }
  for(u32 i=0;i<n;i++) *(volatile u32*)dsp_at[i][0]=dsp_new[i];
  dsp_ok=1; flush_icache();
  dbg("DISP boot patches applied:");
#ifdef DISP_D3
  dbg(" D3");
#endif
#ifdef DISP_D1
  dbg(" D1");
#endif
#ifdef DISP_D4
  dbg(" D4");
#endif
#ifdef DISP_D2
  dbg(" D2");
#endif
#ifdef DISP_D1CHK
  dbg(" D1CHK");
#endif
  dbg(", words "); dec(n); dbg("\n");
}
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
#ifdef PRES_ASYNC
/* rc10: the level's 3D list may still be running through DMA2 (linked list) after present() returned: a command word written to GP0 meanwhile
   would land inside that list, so every command waits for DMA2 first (one register read when it is idle) */
#define GP0_DMAWAIT() while(D2_CHCR&0x01000000){}
#else
#define GP0_DMAWAIT() ((void)0)
#endif
static inline __attribute__((always_inline)) void gp0c(u32 w){ GP0_DMAWAIT(); while(!(GP1&0x04000000)){} GP0=w; }                /* command word */
static inline __attribute__((always_inline)) void gp0p(u32 w){ GP0=w; }                                            /* parameter word */
static inline __attribute__((always_inline)) void gp0e(u32 w){ GP0_DMAWAIT(); while((GP1&0x14000000)!=0x14000000){} GP0=w; }     /* E3h..E5h: FIFO empty */
/* the same without the DMA2 wait, for the two fault screens (they let a running DMA end first, and .rtcold has no room for the waits) */
static inline __attribute__((always_inline)) void gp0c0(u32 w){ while(!(GP1&0x04000000)){} GP0=w; }
static inline __attribute__((always_inline)) void gp0e0(u32 w){ while((GP1&0x14000000)!=0x14000000){} GP0=w; }
/* every command with two parameters (fill 02h, rectangle 60h, VRAM load A0h, VRAM store C0h) goes through this one out-of-line sender: one wait,
   before the command word, then the parameters.  (It also keeps every caller free of a second wait between two such commands.) */
static __attribute__((noinline)) void gp0_2(u32 c,u32 p1,u32 p2){ gp0c(c); gp0p(p1); gp0p(p2); }
/* the GPU has everything and has drawn it: DMA2 finished, ready for a command and write FIFO empty */
static void gpu_idle(void){ while(D2_CHCR&0x01000000){} while((GP1&0x14000000)!=0x14000000){} }
/* nw data words by DMA2 in request mode: blocks of 16 words, a remainder as one shorter block.  chcr 0x01000201: RAM to GP0 (after a GP0(A0h) and
   its two parameters); 0x01000200: GPUREAD to RAM (after a GP0(C0h), ppu12.h pp_vread_rows; rc10 review: the same 16-word blocks both ways) */
static void gpu_dma_x(const void*src,u32 nw,u32 chcr){
  u32 a=(u32)src&0xffffff, big=nw&~15u, r=nw&15u;
  if(big){ D2_MADR=a; D2_BCR=((big>>4)<<16)|16; D2_CHCR=chcr; while(D2_CHCR&0x01000000){} }
  if(r){ D2_MADR=a+big*4; D2_BCR=(1u<<16)|r; D2_CHCR=chcr; while(D2_CHCR&0x01000000){} } }
#define gpu_dma(src,nw) gpu_dma_x((src),(nw),0x01000201u)
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
#ifndef CDSIM
/* rc8: a PAL disc shows a PAL picture.  The licence sector (LBA 4, written by tools7/mkdisc2.py) names the disc's region, and the emulators make
   the console PAL from it.  Beetle/Mednafen shows nothing while a PAL console's GPU is left in NTSC mode, so the Europe disc programs PAL
   (GP1(08h) bit 3) and the 240 lines centred in PAL's 256-line range (23h..123h of psx-spx): Y 2Bh..11Bh.  Display still off; one read at boot. */
static u32 pal_disp;
static RTCOLD void gpu_region(void){
  u8 b[2048]; cd_read(4,1,b);
  static const char E[8]="Euro pe "; int eu=1; for(int i=0;i<8;i++) if(b[0x3c+i]!=(u8)E[i]) eu=0;
  if(!eu) return;
  pal_disp=1; GP1=0x07000000|(0x2b|((0x2b+240)<<10)); GP1=0x08000009;
  dbg("disc region E: PAL display\n");
}
#endif
static void vsync(void){ ISTAT=~1u; for(volatile int n=0;n<400000;n++){ if(ISTAT&1) break; } ISTAT=~1u; CLK_POLL(); }
/* show the buffer at (0,o) once everything drawn into it is finished, at the next vertical blank; the display comes on with the first one */
#ifdef PRES_ASYNC
static u32 fl_tl;              /* rc10 review: clk_lines at the last display-start change of the level (fl_do, flip_to) */
#define FL_TL() (fl_tl=clk_lines)
#else
#define FL_TL() ((void)0)
#endif
static void flip_to(int o){ SP_T0(t0); gpu_idle(); SP_ADD(SP_GIDLE,t0); SP_T0(t1); vsync(); SP_ADD(SP_VS,t1); GP1=0x05000000|((u32)o<<10); g_flips++; FL_TL(); if(!disp_on){ disp_on=1; GP1=0x03000000; }
#if defined(RTC64)||defined(SPEEDPROF)
  pic_flipped();
#endif
}
/* rc7: a fault the runtime cannot go on from (a boot-time check of the intro fix, an interpreter limit): the message on the TTY and on the screen (both
   buffers, display on), then stop; never a silent hang on a black or frozen picture */
static RTCOLD void fatal_screen(const char*m,u32 a){
  dbg(m); hex(a); dbg("\n");
  char h[9]; for(int i=0;i<8;i++){ u32 d=(a>>(28-4*i))&15; h[i]=(char)(d<10?'0'+d:'A'+d-10); } h[8]=0;
  while(D2_CHCR&0x01000000){} GP1=0x01000000;                     /* let a running DMA end, then drop any half-sent GPU command */
  for(int b=0;b<2;b++){ cur_oy=b*240;
    gp0_2(0x02600000,XY(0,cur_oy),XY(320,240)); gpu_idle();
    gp0c0(0xE1000000|(1<<10)); gp0e0(0xE3000000|((u32)cur_oy<<10)); gp0e0(0xE4000000|319u|((u32)(cur_oy+239)<<10)); gp0e0(0xE5000000);
    text(64,72,"PORT ERROR",4,0xffffff); text(4,124,m,2,0xc0c0ff); text(128,152,h,2,0xffffff); }
  gpu_idle(); GP1=0x05000000; GP1=0x03000000; disp_on=1; g_flips++;
  for(;;){}
}
#ifndef CDSIM
/* a read that keeps failing: say so on the screen and go on retrying; the data is never taken as good.  The message goes into both buffers and
   the display shows the buffer present() is NOT about to draw into (y = buf?0:240), so the next picture is drawn out of view and flipped in as
   usual once the disc reads again.  Every failure episode shows it (cd_err_on is cleared when a read completes); cd_failed counts the episodes. */
static RTCOLD void cd_error_screen(u32 lba){
  if(cd_err_on) return; cd_err_on=1; cd_failed++;
#ifdef PRES_ASYNC
  if(fl_req>=0){ buf^=1; fl_req=-1; } pend_oy=-1;   /* a picture waiting for its flip counts as shown: buf is the buffer to draw next */
#endif
  dbg("CD READ ERROR lba "); dec(lba); dbg("stat "); hex(cd_stat); dbg("retrying\n");
  while(D2_CHCR&0x01000000){} GP1=0x01000000;                     /* let a running DMA end, then drop any half-sent GPU command */
  for(int b=0;b<2;b++){ cur_oy=b*240;
    gp0_2(0x02000060,XY(0,cur_oy),XY(320,240)); gpu_idle();
    gp0c0(0xE1000000|(1<<10)); gp0e0(0xE3000000|((u32)cur_oy<<10)); gp0e0(0xE4000000|319u|((u32)(cur_oy+239)<<10)); gp0e0(0xE5000000);
    text(64,96,"CD READ ERROR",4,0xffffff); text(88,136,"CHECK THE DISC",2,0xc0c0ff); }
  gpu_idle(); GP1=0x05000000|((u32)(buf?0:240)<<10); GP1=0x03000000; disp_on=1; cur_oy=buf?240:0; g_flips++;
}
static void cd_error_gone(void){ cd_err_on=0; dbg("CD reads again\n"); }
#endif
static u32 last_dl, last_rc, logic_lines, max_lines, tot_lines, nfr_meas;
#ifndef PPU_SF3HUD
#define PPU_SF3HUD 0
#endif
#include "ppu12.h"
#ifdef PRES_ASYNC
/* rc10 (PROFILE.md): the level picture without the CPU standing still.  present() sends the 3D list (sf3_frame) and returns: the GPU draws it while
   the guest runs its next iteration.  The next present() first finishes that picture (pres_finish: the 2D layer over it, pp_draw, with the 2D
   state of that moment) and asks for the flip (fl_req); the flip itself is done at a poll point that falls in the first lines of a vertical
   blank (fl_poll: the vblank flag of ISTAT, cleared when the flip is asked for, is seen set and the previous poll was at most FL_WIN lines before,
   so the blank began less than FL_WIN lines ago; FL_WIN 16 lines) once the GPU is idle; fl_sync() waits for it the old way (gpu_idle + vsync) before anything is
   drawn into the buffer that is still shown.  buf (the buffer to draw next) changes when the flip is done.
   Poll points: the renderer (city items, phases), io_read, the ring replay. */
#ifndef FL_WIN
#define FL_WIN 16      /* the blank is 23 lines (NTSC: 263 - 240 shown) or more (PAL); the display start is taken at the start of the shown lines */
#endif
/* rc10 review (frame pacing): a picture stays on screen for at least two vertical blanks, the game's own step (its limiter runs in 2-frame units),
   as rc9's flip at the end of present() effectively did.  Without it a late flip followed by an early one showed a picture for one 60 Hz frame
   (4-13 % of the pictures with an overclock).  Flips land within FL_WIN lines after a blank begins, so two flips one blank apart are 247..279
   lines apart (PAL 297..329) and two blanks apart 510..542 (PAL 610..642): FL_MINL separates them on both. */
#ifndef FL_MINL
#define FL_MINL 400
#endif
#if !defined(RTC64)
#error "PRES_ASYNC needs RTC64 (clk_lines)"
#endif
static u32 fl_pt;              /* RC1 low word at the previous poll */
u32 fl_npoll, fl_nsync, fl_nlate, fl_nhold;   /* flips done at a poll point / by waiting; blanks seen too late at a poll; blanks passed up to hold the picture */
static void fl_do(int o){ GP1=0x05000000|((u32)o<<10); g_flips++; FL_TL(); if(!disp_on){ disp_on=1; GP1=0x03000000; } buf^=1; fl_req=-1;
#if defined(RTC64)||defined(SPEEDPROF)
  pic_flipped();
#endif
}
void fl_poll(void){ u32 t=RC1_VAL&0xffff, dt=(t-fl_pt)&0xffff; fl_pt=t;
  if(ISTAT&1){ if(dt<=FL_WIN&&!(D2_CHCR&0x01000000)&&(GP1&0x14000000)==0x14000000){ clk_poll(); if(clk_lines-fl_tl>=FL_MINL){ fl_do(fl_req); fl_npoll++; return; } fl_nhold++; }
    else fl_nlate++;
    ISTAT=~1u; } }
void fl_sync(void){ if(fl_req>=0){ SP_T0(t0); gpu_idle(); SP_ADD(SP_GIDLE,t0); SP_T0(t1); do vsync(); while(clk_lines-fl_tl<FL_MINL); SP_ADD(SP_VS,t1); fl_do(fl_req); fl_nsync++; } }
static void pres_finish(void){
  if(pend_oy<0) return;
  SP_T0(td); while(D2_CHCR&0x01000000){} SP_ADD(SP_DMA,td);
  SP_T0(tp); pp_draw(pend_oy,1); SP_ADD(SP_PPD,tp);
  fl_req=pend_oy; pend_oy=-1; ISTAT=~1u; fl_pt=RC1_VAL&0xffff; }
#endif
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
#ifdef RTC_DT
        /* C4 (wave 1) with the rc7 velocities above: one picture per level iteration stands for dt ticks of game time; the cooldowns count ticks
           (at most 90 at once) and the solver steps once per tick, at most 5 times per picture */
        u32 cdt=dt>90?90:dt, sdt=dt>5?5:dt;
#endif
        if(vy>8*1048576) vy=8*1048576; if(vy<-8*1048576) vy=-8*1048576;
        u32 tri=pad_new_extra&1; s32 sp=(vx<0?-vx:vx)+(vz<0?-vz:vz);
        if((pkp==1&&pk==0&&(((pvx<0?-pvx:pvx)+(pvz<0?-pvz:pvz))>2621440)) || (pk==1&&tri&&sp>1048576)){
          s32 bx=pk==1?vx:pvx, bz=pk==1?vz:pvz;
          /* rc8 review: a vehicle swap or crash can still move the man up to 4000 units in a tick, read as a launch of up to 1875 m/s (191 seen
             after a Beetle helicopter crash; driving bail-outs reach 95).  The launch is halved until it is 64 m/s or less (|x|+|z|). */
          while((u32)(bx<0?-bx:bx)+(u32)(bz<0?-bz:bz)>(64u<<20)){ bx/=2; bz/=2; }   /* unsigned sum: two axes near 1875 m/s overflow s32 */
          int k=rd_spawn(px,py,pz,hd,bx,3*1048576,bz,200,0x2040D0); if(k>=0) hero_clk=clk; dbg("DOLL bail-out slot "); dec(k); dbg("speed "); dec(((bx<0?-bx:bx)+(bz<0?-bz:bz))>>20); dbg("\n"); }
        if(pk==1&&sp>4*1048576){ for(int q=0;q<ne;q++){ if(ents3[q].kind!=1) continue; int id=ents3[q].spare&127; if(cdn[id]) continue;
            s32 dx=ents3[q].x-px, dz=ents3[q].z-pz; if(dx<0) dx=-dx; if(dz<0) dz=-dz; if(dx+dz>270) continue;
            int k=rd_spawn(ents3[q].x,ents3[q].y,ents3[q].z,ents3[q].yaw,vx*9/10,vy+2*1048576+(sp>>3),vz*9/10,id,0x30A0E0+(id*0x13A7C1&0x7f7f7f)); if(k>=0){ cdn[id]=420; dbg("DOLL hit ped "); dec(id); dbg("slot "); dec(k); dbg("speed "); dec(sp>>20); dbg("\n"); } } }
#ifdef DOLLTEST
        if(nfr==DOLLTEST_AT){ int k=rd_spawn(px,py,pz,hd,3*1048576,3*1048576,2*1048576,200,0x2040D0); if(k>=0) hero_clk=clk; dbg("TEST-ONLY forced doll slot "); dec(k); dbg("\n"); }
#endif
#ifdef RTC_DT
        for(int q=0;q<128;q++) if(cdn[q]) cdn[q]=cdn[q]>cdt?cdn[q]-cdt:0;
#else
        for(int q=0;q<128;q++) if(cdn[q]) cdn[q]--;
#endif
        { int m=0; for(int q=0;q<ne;q++){ if(ents3[q].kind==1&&cdn[ents3[q].spare&127]) continue; ents3[m++]=ents3[q]; } ne=m; }
        if(rd_has(200)&&clk-hero_clk>HERO_DOLL_TICKS){ rd_drop(200); dbg("DOLL player released, ticks "); dec(clk-hero_clk); dbg("\n"); }   /* rc7: the solver steps once a 3D frame: at this port's frame rate its own release (asleep 10 s of solver time) took minutes */
        sf3_hide_player=rd_has(200);
        rd_set_car(pk==1,px,py,pz,hd,vx,vy,vz);
#ifdef RTC_DT
        if(rd_active()){ u32 d0=RC1_VAL; for(u32 st=0;st<sdt&&rd_active();st++) rd_step_all(sf3_rpw,px,pz); u32 dl=(RC1_VAL-d0)&0xffff;
#else
        if(rd_active()){ u32 d0=RC1_VAL; rd_step_all(sf3_rpw,px,pz); u32 dl=(RC1_VAL-d0)&0xffff;
#endif
          static u32 dmax,dsum,dn; dn++; dsum+=dl; if(dl>dmax) dmax=dl; if((dn&15)==1){ dbg("RD lines "); dec(dl); dbg("max "); dec(dmax); dbg("avg "); dec(dsum/dn); dbg("active "); dec(rd_active()); dbg("steps "); dec(rd_steps); dbg("hurtmax "); dec(rd_hurt_max); dbg("\n"); } }
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
  { u32 n=(160+228-io_vc)%228; if(!n) n=228; IO_ADV(n*1232); } io_vc=160; io16w(0x202,io16(0x202)|1); tick(); g_nvbl++; VF++; ppu_flush();
  SP_INC(SP_TRIG_VBL); present();
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
#ifdef DISP_PROF
static void present_(void);
static void present(void){ u32 t0=dsp_rc(), c0=dsp_cdl; present_(); dsp_prl+=(dsp_rc()-t0)-(dsp_cdl-c0); }   /* TEST-ONLY timing wrapper */
#define present present_
#endif
static void present(void){
#ifdef SPEEDPROF
  u32 sp_t=sp_now(); int sp_lvl=0; SP_T0(ts); sp_inpres++;
#endif
  int pr_async=0;        /* rc10 PRES_ASYNC: this picture's 3D list is left running (its 2D layer and flip come with the next present) */
#ifdef PRES_ASYNC
  pres_finish();
#endif
  cd_idle();             /* a data read left running since the last picture is paused now (reads that follow each other need no Pause) */
  sv_service(); cdda_service();
  SP_ADD(SP_SVC,ts); CLK_POLL();
#if defined(RTC_PRESENT)||defined(SPEEDPROF)
  c3_seen6=0; c3_scan=DL[0];   /* a world frame begun from here on belongs to the next picture */
#endif
#if defined(SF3_DEFER) && !defined(MERGED_NATIVE)     /* (B2: no sf3; Stunt Fox draws its own picture into the page) */
  /* title-boot disc: the renderer's data window is shared with menu-only overlay code (cold tier 1), so the renderer starts when the level does */
  /* rc7: after the guest left a level (present() below turns the renderer off) the start is armed again: a new level is running once its clock
     differs from the one left behind and its entity table is there again */
  { if(!sf3_tried && !sf3_ok && *(volatile u32*)(EW+0x1e00) && (u32)*(volatile s16*)(EW+0x1e66)<=10u
       && (!sf3_left || (*(volatile u32*)(EW+0x1e00)!=sf3_left_clk && *(volatile s16*)(IW+0xc)>=0))){ sf3_tried=1; sf3_left=0; sf3_first_map=*(volatile s16*)(EW+0x1e66); dbg("guest map "); dec(sf3_first_map); dbg("\n"); dbg("deferred sf3_init at level start, gba frame "); dec(io_cyc/280896); dbg("\n");
      sf3_ok=(sf3_init()==0); for(u32 k=0;k<COLDGROUPS;k++){ u32 lo=COLD_HOST+k*16384, hi=lo+16384; if(hi>SF_WORLD_LO && lo<0x8011b200u) cold_loaded[k]=0; } dsp_mclear(); dbg("sf3_ok "); dec(sf3_ok); dbg("\n"); } }
  if(sf3_retry && !sf3_ok && g_pres-last_cold_pres>=6 && *(volatile u32*)(EW+0x1e00)!=sf3_clk0){ sf3_retry=0; dbg("sf3 re-init after overlay load\n");
    sf3_ok=(sf3_init()==0); for(u32 k=0;k<COLDGROUPS;k++){ u32 lo=COLD_HOST+k*16384, hi=lo+16384; if(hi>SF_WORLD_LO && lo<0x8011b200u) cold_loaded[k]=0; } dsp_mclear(); dbg("sf3_ok "); dec(sf3_ok); dbg("\n"); }
#endif
  g_pres++; SP_INC(SP_NPRES);
#ifdef PZBLOCK
  pz_present();
#endif
#ifdef POOL_THRASH
  if(pool_menu){ if(rom_miss_count!=pool_lmiss){ pool_lmiss=rom_miss_count; pool_quiet=0; } else if(++pool_quiet>=POOL_QUIET) pool_menu_off(); }
#endif
#ifdef COLD1PASS
  if(!cold_m5 && disp_on && (rom_miss_count|cold_loads) && g_gframes-cd_rd_gf>=COLD1_QUIET && !pp_fade_w) cold_all();
#endif
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
            dsp_mclear();
            sf3_ok=1; dbg("SF3 renderer data restored from the world file, groups "); dec(nrest); dbg("level clock "); dec(c); dbg("\n"); }
          else { dbg("SF3 re-init after cold-code conflict, level clock "); dec(c); dbg("\n");
            sf3_ok=(sf3_init()==0); for(u32 k=0;k<COLDGROUPS;k++){ u32 lo=COLD_HOST+k*16384, hi=lo+16384; if(hi>SF_WORLD_LO && lo<0x8011b200u) cold_loaded[k]=0; } dsp_mclear(); dbg("sf3_ok "); dec(sf3_ok); dbg("\n"); } } }
      else rclk=0; } }
#endif
#ifdef DISP_D2
  d2_apply();             /* stage 20 D2: the call sites queued since the last picture, after this present's group drops */
#endif
  if((g_pres%PRES_DBG_EVERY)==1){ dbg("present "); dec(g_pres); dbg(" tick "); dec(io_nd); dbg("gf "); dec(g_gframes); dbg("clk "); dec(*(volatile u32*)(EW+0x1e00)); dbg("map "); dec(*(volatile u16*)(EW+0x1d40)); dbg("nent "); dec(*(volatile u16*)(IW+0xc)); dbg("dsp "); hex(io16(0)); dbg("keys "); hex(io_keys); dbg("PPU n2 "); dec(pp_n2); dbg("n4 "); dec(pp_n4); dbg("up "); dec(pp_nup); dbg("rb "); dec(pp_nrb); dbg("rst "); dec(pp_nreset); dbg("lost "); dec(pp_lost); dbg("fade "); dec(pp_nfade); dbg("w "); dec(pp_fade_w); dbg("fb "); dec(pp_nfb); dbg("obj "); dec(pp_nobj); dbg("disp "); hex(pp_disp); dbg("\n"); }
  u32 rc=RC1_VAL; u32 lines=(rc-last_rc)&0xffff;   /* scanlines of CPU time since the previous present = guest logic time */
  /* ----- game-state tick (same clock as the lockstep proof): vblank = io_vc 160, IF bit0 */
  u32 n=DL[0]; u32 from=last_dl; if(n-from>256) from=n-256; last_dl=n;
  logic_lines=lines; if(lines>max_lines) max_lines=lines; tot_lines+=lines; nfr_meas++;
#ifdef PRES_ASYNC
  int oy=fl_req>=0?(fl_req?0:240):(buf?240:0); cur_oy=oy;   /* the buffer not shown and not waiting to be shown */
#else
  int oy=buf?240:0; cur_oy=oy;
#endif
#ifndef AUTOKEYS
#ifdef RTC_GFRAMES
  clk_gba();
#endif
  if(pad_gf!=g_gframes){ pad_gf=g_gframes; pad_frame_poll(); }
  io_keys=pad_gba;
  { u32 lat=pad_latch|pad_raw, np=lat&~pad_lastp; pad_latch=0; pad_lastp=pad_raw;
    pad_new_extra=((np>>12)&1)|(((np>>8)&3)<<1)|(((np>>1)&3)<<3);
#ifdef TESTPOKE
    pad_new_extra|=(np&1)<<5;     /* TEST-ONLY: a fresh Select press pokes the controlled entity index to the nearest traffic car (see stage7_pre) */
#endif
    radio_poll(lat,np);
#ifdef PZBLOCK
    if((np&8u) && sf3_ok){ u32 c=*(volatile u32*)(EW+0x1e00); if(c && *(volatile s16*)(IW+0xc)>=0){ pz_arm=1; pz_arm_clk=c; } }   /* Start in a running level */
#endif
#if defined(PZBLOCK)&&defined(PZ_START)
    if((np&8u) && sf3_ok) pz_start();   /* TEST: Start in a level reads the block at once */
#endif
    }
#ifdef PADDBG
  { static u32 lp=0xffffffff; if(pad_raw!=lp){ lp=pad_raw; dbg("PADRAW "); hex(pad_raw); dbg("\n"); } }
  gs_dump();
#endif
#endif
  if(sf3_ok){ s32 px,py,pz; int hd,pk,ne; static s32 hpx,hpy,hpz; static int hhd,hpk,hne,hvalid;   /* stage 16: last gathered pose, drawn again while the guest's level state is not readable (Pause) */
#ifdef PCACHE1
    rom_pool=1;                       /* stage 20: a level runs: resident pages and slots become one CLOCK pool (cd_fetch) */
#ifdef POOL_THRASH
    pool_menu=0;                      /* ... for good, also when the menus had turned it on */
#endif
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
#ifdef SPEEDPROF
    sp_acc[SP_GATHER]+=st3_gather_lines; sp_lvl=1;
#endif
    if(ok){ SP_T0(tq); stage7_pre(&px,&py,&pz,&hd,&pk,&ne); SP_ADD(SP_PRE,tq); hpx=px; hpy=py; hpz=pz; hhd=hd; hpk=pk; hne=ne; hvalid=1; u32 r0=RC1_VAL; sf3_frame(oy,px,py,pz,hd,pk,ents3,ne,PPU_SF3HUD);
#ifdef PRES_ASYNC
      SP_ADD(SP_ENG,r0); pr_async=1; u32 dl=(RC1_VAL-r0)&0xffff; st3_render++;
#else
      SP_ADD(SP_ENG,r0); SP_T0(td); while(*(volatile u32*)0x1F8010A8&0x01000000){} SP_ADD(SP_DMA,td); SP_T0(tp); pp_draw(oy,1); SP_ADD(SP_PPD,tp); u32 dl=(RC1_VAL-r0)&0xffff; st3_render++;
#endif
      st3_lines_sum+=dl; if(dl>st3_lines_max) st3_lines_max=dl;
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
      { SP_T0(r0); sf3_frame(oy,hpx,hpy,hpz,hhd,hpk,ents3,hne,PPU_SF3HUD); SP_ADD(SP_ENG,r0); SP_T0(td); while(*(volatile u32*)0x1F8010A8&0x01000000){} SP_ADD(SP_DMA,td); SP_T0(tp); pp_draw(oy,1); SP_ADD(SP_PPD,tp); } goto flip; } }
#ifdef SF3_DEFER
 no3d:
#endif
  if(sf3_cfl&&*(volatile u32*)(EW+0x1e00)){ last_rc=RC1_VAL;
#ifdef SPEEDPROF
    sp_acc[SP_PRESL]+=sp_now()-sp_t; sp_inpres--;
#endif
    return; }   /* stage 13: renderer data is being restored after a cold-code overlay hit it: keep showing the last 3D frame (no switch to the debug page, no luminance flash) */
#ifdef PRES_ASYNC
  fl_sync();             /* the buffer drawn now may still be the one shown */
#endif
  { SP_T0(tp); pp_draw(oy,0); SP_ADD(SP_PPD,tp); }          /* the 2D layer: black borders, backdrop, page, sprites (ppu12.h sets its own drawing environment) */
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
#ifdef PRES_ASYNC
  if(pr_async) pend_oy=oy; else
#endif
  { flip_to(oy); buf^=1; }
  (void)pr_async;
  cd_resume();           /* CD audio held for data reads comes back when no data read was made for a while (after this picture's own reads) */
  last_rc=RC1_VAL;
#ifdef SPEEDPROF
  sp_acc[SP_PRESL]+=sp_now()-sp_t; sp_inpres--; if(sp_lvl) SP_INC(SP_NLVL); sp_line(sp_lvl);
#endif
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
#ifndef RTC_TIMERS
  for(int k=0;k<4;k++){ tm_t0[k]=st[7+k]; tm_rl[k]=st[11+k]; tm_ovb[k]=st[15+k]; tm_en[k]=st[19+k]; }
  io_hi=0; for(int k=0;k<4;k++) tm_t0h[k]=io_cyc<tm_t0[k]?0xffffffffu:0u;   /* the snapshot's 32-bit base: every timer started less than 2^32 cycles ago */
#endif
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
  /* the renderer's and the ragdoll's BSS: cleared first, the runtime keeps pg_fr and dsp_lq in .sfbss (rc8, room in the runtime) */
  { extern u8 __sfbss_start[],__sfbss_end[]; for(u8*q=__sfbss_start;q<__sfbss_end;q++) *q=0; }
  { extern u8 __dlbss_start[],__dlbss_end[]; for(u8*q=__dlbss_start;q<__dlbss_end;q++) *q=0; }
  RC1_MODE=0x0100;       /* root counter 1 counts hblank: the time base of every bounded wait of the CD driver */
#ifdef RTC64
  clk_raw=RC1_VAL&0xffff; /* and of the guest's clock (clk.h): set once here, never reset */
#endif
#ifndef CDSIM
  cd_drain();
#endif
  ISTAT=0;
  dbg("PAYBACK PS1 stage2: start\n");
  gpu_init(); cdda_init();
#ifndef CDSIM
  gpu_region();
#endif
  memset((void*)DL,0,0x2100);
  HELP[0]=(u32)h_memrd; HELP[1]=(u32)h_memwr; HELP[2]=(u32)h_miss; HELP[3]=(u32)h_vbl;
  const u32 *b=(const u32*)bootimg; const u8 *p=bootimg+160;
  memcpy(EW,p,0x40000); p+=0x40000; memcpy(IW,p,0x8000); p+=0x8000; memcpy(PAL,p,0x400); p+=0x400; memcpy(VRAM,p,0x18000); p+=0x18000; memcpy(OAM,p,0x400); p+=0x400; memcpy(io,p,0x400);
  io_vc=b[32]; io_nread=b[33]; for(int i=0;i<4;i++) io_tm[i]=b[34+i]; io_nd=b[38]; io_keys=PAD[(io_nd/30)%6];
  const u32 *rp=(const u32*)rompack; rp_n=rp[0]; rp_idx=rp+1; rp_data=(const u8*)(rp+1+rp_n);
  for(u32 i=0;i<ROM_NPG;i++) rom_pg[i]=0;          /* ROMPG is outside the BSS: a real BIOS (and a packed EXE) leaves it undefined */
  for(u32 i=0;i<rp_n;i++) rom_pg[rp_idx[i]&(ROM_NPG-1u)]=rp_data+i*4096;     /* optional pre-seeded pages (never evicted before the first level, see cd_fetch) */
#ifdef PCACHE1
  pool_rp=rp_n<RP_MAX?rp_n:RP_MAX; for(u32 i=0;i<pool_rp;i++){ u32 pg=rp_idx[i]&(ROM_NPG-1u); fr_pg[i]=pg+1; pg_fr[pg]=i+1; }
#endif
  dbg("boot image loaded, rom pages "); dec(rp_n); dbg("\n");
#ifndef NO_INTERP
  intro_fix_init();     /* overlay guard + the ZOO-logo join point (interp_glue.h) */
#endif
#ifdef DISP_ANY
  dsp_mclear();             /* the D1 cache is empty before RT_MISS can reach it */
  dsp_boot();
#endif
  last_rc=RC1_VAL;
  static u32 regs[32]; for(int i=0;i<32;i++) regs[i]=b[i];
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
