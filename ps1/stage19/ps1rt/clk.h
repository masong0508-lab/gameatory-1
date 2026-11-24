/* clk.h: guest time on the PS1 (PS1 speed plan, Stage 1) and the test-only speed stamps (Stage 0, -DSPEEDPROF).
   rt.c includes this file twice: the first time (near the top, after RC1_VAL) gives the clock and the stamp counters, which the CD
   driver's waits need; the second time (after the IO model state, before io_read) gives the timer registers and the present triggers.
   Every part is behind its own flag; with none of them set nothing here is compiled and the runtime keeps its virtual clock
   (io_cyc: VCOUNT/DISPSTAT polls, SWI 5 and 96 cycles per timer/KEYINPUT poll), which the simulator, lockstep and CDSIM builds need.
     RTC64        (1a, C1) root counter 1 (hblank, 15734 Hz) extended to 64 bits; polled in io_read, hl_past, vsync and present;
                           sf/ps1.h's timers_init no longer resets it.
     RTC_TIMERS   (1b, C2) TM0..TM3 counted from that clock in 64 bits (TM3:TM2 = G>>10), race-free TM3 -> TM2 pair; timer and
                           KEYINPUT reads no longer advance the virtual clock.  Needs RTC64, RTC_PRESENT and RTC_GFRAMES.
     RTC_PRESENT  (1c, C3) in the level, present once per iteration at the limiter's elapsed read (get_time called from 0x0802471c),
                           identified by the return address the runtime's C-call stub saved; no virtual-vblank presents in the level;
                           the draw ring is flushed when it is more than 192 entries behind.
     RTC_PMAX=ms  (1d)     fallback: a picture older than this many ms at a timer read (or at a VCOUNT/DISPSTAT read in the level, with no
                           world frame begun since the last picture) is presented then.  Needs RTC_PRESENT.
     RTC_GFRAMES  (1e, C7) g_gframes = real GBA frames (clock / 280896): the pad is read once per real frame; the menu present
                           cadence keeps the virtual frame count (g_vf).  Needs RTC64.
     RTC_QUANT    (1f, C8) at the elapsed read only, when the real elapsed e is 6 units (of 8.362 ms) or more, the game is shown
                           t_last + 4*ceil(e/4).  Needs RTC_TIMERS and RTC_PRESENT.
     RTC_DT       (1g, C4) the ragdolls step by the level clock's change since the last picture (1..5 ticks).  Needs RTC_PRESENT.
     SPEEDPROF    test builds only: RC1 line stamps of the present and the limiter phases, per-iteration counters (u32 sp_acc[],
                           read by the rig), an "SP" TTY line per level picture, and the forced step period of the profile (sp_acc[SP_FORCE]). */
#ifndef CLK_H_1
#define CLK_H_1
typedef unsigned long long u64;
#if defined(RTC_TIMERS)&&!(defined(RTC64)&&defined(RTC_PRESENT)&&defined(RTC_GFRAMES))
#error "RTC_TIMERS needs RTC64, RTC_PRESENT and RTC_GFRAMES"
#endif
#if (defined(RTC_GFRAMES)||defined(RTC_PRESENT))&&!defined(RTC64)
#error "RTC_GFRAMES and RTC_PRESENT need RTC64"
#endif
#if defined(RTC_PMAX)&&!defined(RTC_PRESENT)
#error "RTC_PMAX needs RTC_PRESENT"
#endif
#if defined(RTC_QUANT)&&!(defined(RTC_TIMERS)&&defined(RTC_PRESENT))
#error "RTC_QUANT needs RTC_TIMERS and RTC_PRESENT"
#endif
#if defined(RTC_DT)&&!defined(RTC_PRESENT)
#error "RTC_DT needs RTC_PRESENT"
#endif
#ifdef RTC_GFRAMES
static u32 g_gframes;
#endif
#ifdef RTC64
/* C1: PS1 lines since boot, 64 bits: clk_lines is the low word (it wraps after 75.8 hours), clk_hi counts its wraps.  rc8 review: with
   the low word alone G stepped back by 2^32 lines at that wrap (TM3:TM2 about 3 h back, the level clock stood still), a jump the GBA's
   own clock never makes.  Two agreeing reads (an hblank-clocked counter can be read mid-change); at most one wrap (4.17 s) between two
   polls, which the poll points guarantee.  clk_now32() and the differences taken from it stay 32-bit (they are wrap-safe).
   G = GBA cycles since boot, 64-bit: 1066.285 GBA cycles per PS1 line = 69880080 / 65536. */
static u32 clk_raw, clk_lines, clk_hi;
static __attribute__((noinline)) void clk_poll(void){ u32 a=RC1_VAL&0xffff, b=RC1_VAL&0xffff; if(a!=b) a=RC1_VAL&0xffff;
  u32 o=clk_lines; clk_lines+=(a-clk_raw)&0xffff; clk_raw=a; if(clk_lines<o) clk_hi++; }
#ifdef RTC_GFRAMES
static u32 gf_last, gf_rem;         /* low word of G at the last call, GBA cycles since the last frame boundary (32-bit: calls < 256 s apart) */
#endif
static __attribute__((noinline)) u64 clk_gba(void){ clk_poll();
  u64 g=(((u64)clk_lines*69880080u)>>16)+(((u64)clk_hi*69880080u)<<16);   /* (hi*2^32+lo)*K>>16 exactly: two 32x32 multiplies */
#ifdef RTC_GFRAMES
  { u32 g32=(u32)g; gf_rem+=g32-gf_last; gf_last=g32; if(gf_rem>=280896u){ u32 n=gf_rem/280896u; g_gframes+=n; gf_rem-=n*280896u; } }
#endif
  return g; }
#define CLK_POLL() clk_poll()
#else
#define CLK_POLL() ((void)0)
#endif
#ifdef SPEEDPROF
/* cumulative counters for the rig (symbol sp_acc); lines are RC1 (hblank) lines, 15734 per second */
enum { SP_NPRES, SP_SVC, SP_GATHER, SP_PRE, SP_ENG, SP_DMA, SP_PPD, SP_GIDLE, SP_VS, SP_FLUSH, SP_NFLUSH, SP_PRESL, SP_NLVL, SP_IT, SP_WAITRD, SP_TLRD,
       SP_TMOTHER, SP_ROMRD, SP_MISS, SP_LOGIC, SP_WAITL, SP_ITL, SP_ITMAX, SP_AGEMAX, SP_OLD, SP_TRIG_C3, SP_TRIG_PMAX, SP_TRIG_VBL, SP_TRIG_ADV, SP_AUTOFL,
       SP_NOLD_CD, SP_MULT_H, SP_PER_H=SP_MULT_H+8, SP_FORCE=SP_PER_H+20, SP_QUANT, SP_LASTRA, SP_C3MISS, SP_FLIPS, SP_TLBAD, SP_AGEMAXCD,
       SP_TM2FRESH, SP_NLINE, SP_CDL, SP_CDX, SP_N };
u32 sp_acc[80];
_Static_assert(SP_N<=80, "sp_acc");
static u32 sp_raw, sp_lines;       /* a private 32-bit line clock for the stamps (accumulated 16-bit deltas) */
static u32 sp_now(void){ u32 a=RC1_VAL&0xffff; sp_lines+=(a-sp_raw)&0xffff; sp_raw=a; return sp_lines; }
#define SP_T0(v) u32 v=RC1_VAL
#define SP_ADD(i,v) (sp_acc[i]+=(RC1_VAL-(v))&0xffff)
#define SP_INC(i) (sp_acc[i]++)
static int sp_inpres;              /* inside present() or ppu_flush(): CD reads there are part of that time already */
#define SP_IN() (sp_inpres++)
#define SP_OUT() (sp_inpres--)
#else
#define SP_IN() ((void)0)
#define SP_OUT() ((void)0)
#define SP_T0(v) do{}while(0)
#define SP_ADD(i,v) ((void)0)
#define SP_INC(i) ((void)0)
#endif
#elif !defined(CLK_H_2)
#define CLK_H_2
/* ---------------------------------------------------------------- second part: after the IO model state, before io_read */
#if defined(RTC_PRESENT)||defined(SPEEDPROF)
/* host return addresses of the limiter's get_time calls (build.sh appends them to syms.c from the translation map) */
extern const u32 LIM_RA_ENTRY, LIM_RA_ELAPSED, LIM_RA_WAIT, LIM_RA_TLAST;
#define RT_CC_RA (*(volatile u32*)0x801fffc8)   /* RT_CC: $sp = 0x801fff90, the guest's $31 saved at 56($sp) */
#endif
#if defined(RTC64)||defined(SPEEDPROF)
static u32 pp_from;                            /* ppu12.h: ring entries replayed so far */
static int disp_on;
static u32 pic_t, pic_try;                     /* line clock of the last flip, and of the last fallback attempt */
static u32 c3_scan, c3_seen6;                  /* ring scanned up to c3_scan; an id-6 entry (world frame begun) since the last picture */
#endif
#ifdef RTC64
static u32 clk_now32(void){ clk_poll(); return clk_lines; }
#endif
#if defined(RTC_PRESENT)||defined(SPEEDPROF)
static int c3_have6(void){
  u32 n=DL[0]; if(n-c3_scan>256) c3_scan=n-256;
  for(;c3_scan<n&&!c3_seen6;c3_scan++) if(DL[8+(c3_scan&255)*8]==6) c3_seen6=1;
  c3_scan=n; return c3_seen6; }
#endif
#ifdef RTC_QUANT
/* rc10: from this many units of real elapsed time on, the game is shown t_last + 4*ceil(e/4).  The PLAN's 6 left e = 5 as on the GBA (one tick
   for 5 units: the game at 80 % speed); with the faster rc10 present the car and the man on foot often take 5 units, so 5 is rounded up too
   (two ticks, the game at full speed) */
#ifndef RTC_QUANT_MIN
#define RTC_QUANT_MIN 6
#endif
static u32 q_tlast, q_valid;       /* the game's t_last (get_time units) as the runtime returned it */
#endif
#ifdef SPEEDPROF
static u32 sp_it_t, sp_tl_t, sp_tl_x, sp_el_t, sp_el_x, sp_pic_t, sp_cdk;
static u32 sp_x(void){ return sp_acc[SP_PRESL]+sp_acc[SP_FLUSH]+sp_acc[SP_CDX]; }   /* time that is not guest logic: pictures, ring replay, CD reads */
static u32 sp_cd(void){ return cd_sectors; }   /* every CD data read (ROM pages, cold code, world data) */
/* a timer read: which call of the limiter it is (by the saved return address), the phase times and the step histograms */
static void sp_timer(u32 ra){
  u32 t=sp_now();
  if(ra==LIM_RA_ELAPSED){ SP_INC(SP_IT);
    if(sp_tl_t){ u32 l=(t-sp_tl_t)-(sp_x()-sp_tl_x); sp_acc[SP_LOGIC]+=l; }
    if(sp_it_t){ u32 l=t-sp_it_t; sp_acc[SP_ITL]+=l; if(l>sp_acc[SP_ITMAX]) sp_acc[SP_ITMAX]=l; }
    sp_it_t=t; sp_el_t=t; sp_el_x=sp_x();
    { u32 m=*(volatile u32*)(IW+0x1c), p=*(volatile u32*)(IW+0x10); sp_acc[SP_MULT_H+(m>7?7:m)]++; sp_acc[SP_PER_H+(p>19?19:p)]++; }
#ifdef RTC_QUANT
    if(q_valid&&*(volatile u32*)(IW+0x7ecc)!=q_tlast) SP_INC(SP_TLBAD);   /* the game's t_last ([sp+0x30]) against the runtime's copy */
#endif
  }
  else if(ra==LIM_RA_WAIT) SP_INC(SP_WAITRD);
  else if(ra==LIM_RA_TLAST){ SP_INC(SP_TLRD);
    if(sp_el_t){ u32 l=(t-sp_el_t)-(sp_x()-sp_el_x); sp_acc[SP_WAITL]+=l; }
    sp_tl_t=t; sp_tl_x=sp_x();
    { u32 P=sp_acc[SP_FORCE]; if(P>=4&&P<=19){ *(volatile u32*)(IW+0x10)=P; *(volatile u32*)(IW+0x20)=P; *(volatile u32*)(IW+0x1c)=(P+2)>>2; } } }   /* 0c: forced period */
  else { SP_INC(SP_TMOTHER); sp_acc[SP_LASTRA]=ra; } }
/* a picture was flipped in: its age (since the previous flip), with and without CD reads in between */
static void sp_flip(void){
  u32 t=sp_now(), age=t-sp_pic_t, cd=sp_cd(); sp_pic_t=t;
  if(cd!=sp_cdk){ if(age>sp_acc[SP_AGEMAXCD]) sp_acc[SP_AGEMAXCD]=age; if(age>2360) SP_INC(SP_NOLD_CD); }
  else { if(age>sp_acc[SP_AGEMAX]) sp_acc[SP_AGEMAX]=age; if(age>2360) SP_INC(SP_OLD); }
  sp_cdk=cd; }
#endif
#ifdef RTC_TIMERS
/* C2: the timers from the 64-bit clock.  counts = (G - start) >> prescaler, cascade = overflows of the timer below; the reload 0
   (period 0x10000, the only one Payback uses for TM2/TM3) is a shift.  A TM3 read keeps the TM2 value of the same instant, and the
   TM2 read that follows it at once (get_time and the raw timer read TM3, then TM2) returns that value: no wrap race. */
static u64 tm_t0q[4]; static u32 tm_snap_n=0xffffffffu, tm_snap_lo;
/* counts are 32-bit: TM2 at /1024 wraps its count after 72.8 h, like the GBA's TM3:TM2 pair */
static u32 tm_val64(u32 k,u64 G,u32*ov){
  u32 ctrl=io[0x102+4*k]|(io[0x103+4*k]<<8), c;
  if(!(ctrl&0x80)){ *ov=0; return tm_rl[k]&0xffff; }
  if(k>0&&(ctrl&4)){ u32 o; tm_val64(k-1,G,&o); c=o-tm_ovb[k]; }
  else { u64 d=G-tm_t0q[k]; u32 ps=ctrl&3; c=ps==3?(u32)(d>>10):(u32)d>>(ps==0?0:ps==1?6:8); }   /* TM0/TM1 (faster prescalers, never read by Payback) wrap after 256 s */
  u32 rl=tm_rl[k]&0xffff;
  if(!rl){ *ov=c>>16; return c&0xffff; }
  { u32 per=0x10000-rl; *ov=c/per; return (rl+c%per)&0xffff; } }   /* other reloads: not used by Payback */
static void tm_write_check_rt(void){
  for(u32 k=0;k<4;k++){ u32 ctrl=io[0x102+4*k]|(io[0x103+4*k]<<8); u32 en=(ctrl>>7)&1;
    if(en&&!tm_en[k]){ u64 G=clk_gba(); tm_rl[k]=io[0x100+4*k]|(io[0x101+4*k]<<8); tm_t0q[k]=G; if(k>0){ u32 o; tm_val64(k-1,G,&o); tm_ovb[k]=o; } }
    tm_en[k]=en; } }
static u32 tm_read_rt(u32 k,u32 ra){
  if(k==2){ if(io_nread==tm_snap_n+1) return tm_snap_lo; SP_INC(SP_TM2FRESH); }
  u64 G=clk_gba(); u32 o, v=tm_val64(k,G,&o);
  if(k==3){ tm_snap_lo=tm_val64(2,G,&o); tm_snap_n=io_nread;
#ifdef RTC_QUANT
    /* C8: the pair is get_time's dividend; one unit = 137 TM2 ticks */
    u32 pair=(v<<16)|tm_snap_lo, now=pair/137;
    if(ra==LIM_RA_TLAST){ q_tlast=now; q_valid=1; }
    else if(ra==LIM_RA_ENTRY){ q_tlast=now-1; q_valid=1; }       /* 0x08023d54: t_last = get_time()-1 */
    else if(ra==LIM_RA_ELAPSED&&q_valid){ u32 e=now-q_tlast;
      if(e>=RTC_QUANT_MIN&&e<0x40000000u){ u32 shown=q_tlast+((e+3)&~3u), pq=shown*137+68; v=pq>>16; tm_snap_lo=pq&0xffff; SP_INC(SP_QUANT); } }
#endif
  }
  (void)ra; return v; }
#endif
/* ---- presents driven by the guest's timer reads (C3, the fallback) */
#ifdef RTC_PMAX
#define PMAX_LINES ((u32)(RTC_PMAX)*15734u/1000u)
#endif
static void on_timer_read(u32 ra,u32 k){
  if(k!=3) return;                 /* every timer reader of Payback reads TM3 first (get_time, the raw timer) */
#ifdef SPEEDPROF
  sp_timer(ra);
#endif
#ifdef RTC_PRESENT
  if(LVL_ON&&ra==LIM_RA_ELAPSED){
    if(PIC_READY()){ SP_INC(SP_TRIG_C3); ppu_flush(); present(); return; }   /* the iteration's world frame is drawn: show it, and charge it to elapsed */
    SP_INC(SP_C3MISS); }
#endif
#ifdef RTC_PMAX
  { u32 t=clk_now32(); if(disp_on&&t-pic_t>PMAX_LINES&&t-pic_try>PMAX_LINES&&!PMAX_HOLD()){ pic_try=t; SP_INC(SP_TRIG_PMAX); ppu_flush(); present(); } }
#endif
  (void)ra; (void)k; }
/* a VCOUNT or DISPSTAT read in the level: no virtual-vblank presents there any more, so a level screen that only polls VCOUNT (pause)
   or a long effect wait would keep its picture without this */
static void on_vcount_read(void){
#ifdef RTC_PMAX
  if(!LVL_ON) return;
  { u32 t=clk_now32(); if(disp_on&&t-pic_t>PMAX_LINES&&t-pic_try>PMAX_LINES&&!PMAX_VHOLD()){ pic_try=t; SP_INC(SP_TRIG_PMAX); ppu_flush(); present(); } }
#endif
}
/* any IO read: the draw ring must be replayed before it laps (256 entries); C3 flushes once per iteration only */
static inline void ring_guard(void){
#ifdef RTC_PRESENT
  if(DL[0]-pp_from>192){ SP_INC(SP_AUTOFL); if(sf3_ok) c3_have6(); ppu_flush(); }
#endif
}
/* a picture has just been flipped in */
static void pic_flipped(void){
#ifdef RTC64
  pic_t=clk_now32();
#endif
#ifdef SPEEDPROF
  sp_flip();
#endif
}
#ifdef SPEEDPROF
/* one TTY line per level picture (every 64th other picture): presents, real/virtual frames, iterations, and per-picture deltas of
   the C calls (RT_MISS, ROM reads), CD page fetches and the present split in RC1 lines */
static u32 sp_prev[SP_N], sp_pmiss, sp_pres_prev;
static void sp_line(int level){
  if(!level&&(g_pres&63)) return;
  SP_INC(SP_NLINE);
  static const u8 IX[]={SP_IT,SP_MISS,SP_ROMRD,SP_SVC,SP_GATHER,SP_PRE,SP_ENG,SP_DMA,SP_PPD,SP_GIDLE,SP_VS,SP_FLUSH,SP_LOGIC,SP_TRIG_C3,SP_TRIG_PMAX};
  static const char NM[]="ITMIROSVGAPRENDMPDGIVSFLLGC3PM";
  dbg(level?"SP L ":"SP M "); dec(g_pres); dec(g_gframes); dbg("cf "); dec(rom_miss_count-sp_pmiss); sp_pmiss=rom_miss_count;
  for(u32 i=0;i<sizeof IX;i++){ dbgc(NM[2*i]); dbgc(NM[2*i+1]); dbgc(' '); dec(sp_acc[IX[i]]-sp_prev[IX[i]]); sp_prev[IX[i]]=sp_acc[IX[i]]; }
  dbgc('\n'); }
#endif
#endif
