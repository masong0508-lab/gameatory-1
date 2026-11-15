/* Star-FlyBack radio on the pad (edge triggered once per poll), needs pad_raw/pad_prev and cdda_*.
   SELECT+R1 next track in the mode, SELECT+L1 previous, SELECT+Triangle stop / start, SELECT+Square next mode (REMIXES -> ALL SONGS -> ORIGINALS).
   Disc track numbers (stage5 bin/cue, mkdisc2 --default-tracks): 2..12 the 11 tracker-module "PS1 remix final" renders, 13..15 Star-FlyBack PS1 remix songs 1, 2, 4.
   Payback song 3 is never on the disc.  Modes: REMIXES = 2..12, ALL SONGS = 2..15, ORIGINALS = 13..15 (the Star-FlyBack songs; the tracker "originals" renders are not on this disc: 51 min do not fit).
   -DRADIO_AUTOPLAY starts the first track of the mode; -DRADIO_TEST runs a scripted key sequence (test builds only). */
#ifndef HW_RADIO_H
#define HW_RADIO_H
static u32 radio_trk, radio_on, radio_mode;
static const u8 radio_lo[3]={2,2,13}, radio_hi[3]={12,15,15};
static const char*const radio_name[3]={"REMIXES","ALL SONGS","ORIGINALS"};
static u32 radio_hi_(void){ u32 h=radio_hi[radio_mode]; return h>cdda_last?cdda_last:h; }
static u32 radio_next(u32 cur){ u32 lo=radio_lo[radio_mode],hi=radio_hi_(); return (cur<lo||cur+1>hi)?lo:cur+1; }
static u32 radio_prev(u32 cur){ u32 lo=radio_lo[radio_mode],hi=radio_hi_(); return (cur<=lo||cur>hi)?hi:cur-1; }
static void radio_log(const char*m){ dbg("RADIO "); dbg(m); dbg(radio_name[radio_mode]); dbg(" track "); dec(radio_trk); dbg("playing "); dec(cdda_playing); dbg("\n"); }
static void radio_go(u32 t,const char*m){ radio_trk=t; cdda_play(t); radio_on=1; radio_log(m); }
static void radio_poll1(u32 p,u32 n){
  if(!(p&1)) return; if(!radio_trk) radio_trk=radio_lo[radio_mode];                  /* SELECT held */
  if(n&(1u<<11)) radio_go(radio_next(radio_trk),"next ");
  else if(n&(1u<<10)) radio_go(radio_prev(radio_trk),"prev ");
  else if(n&(1u<<15)){ radio_mode=(radio_mode+1)%3; radio_go(radio_lo[radio_mode],"mode "); }
  else if(n&(1u<<12)){ if(cdda_playing){ cdda_stop(); radio_on=0; radio_log("stop "); } else radio_go(radio_trk,"start "); } }
static void radio_poll(u32 lat,u32 newp){
  static u32 fr, inited;
  if(cdda_last<2) return;
  if(!inited){ inited=1; cdda_nextfn=radio_next; }
#if defined(RADIO_AUTOPLAY)||defined(RADIO_TEST)
  if(++fr==10){ dbg("RADIO TOC last track "); dec(cdda_last); dbg("\n"); radio_go(radio_lo[radio_mode],"autoplay "); }
#endif
#ifdef RADIO_TEST
  { /* scripted keys (test only): frame -> SELECT + key bit; each press is one edge */
    static const u16 sf[]={20,30,40,50,60,70,80,90,100,110,120,130}; static const u8 sk[]={11,11,15,11,11,10,15,11,12,12,0,0};
    for(u32 i=0;i<10;i++) if(fr==sf[i]){ dbg("RADIO TEST key "); dec(sk[i]); dbg("\n"); radio_poll1(1|(1u<<sk[i]),1u<<sk[i]); } }
#endif
  radio_poll1(lat,newp); }
#endif
