/* radio keys on the pad, edge triggered once per poll: SELECT+R1 next track, SELECT+L1 previous, SELECT+Triangle stop / start again.  Needs pad_raw/pad_prev and cdda_*. */
#ifndef HW_RADIO_H
#define HW_RADIO_H
static u32 radio_trk, radio_on;
static void radio_log(const char*m){ dbg("RADIO "); dbg(m); dec(radio_trk); dbg("playing "); dec(cdda_playing); dbg("\n"); }
static void radio_poll(void){
  if(cdda_last<2) return; u32 p=pad_raw, n=p&~(u32)pad_prev; if(!(p&1)) return;       /* SELECT held */
  if(!radio_trk) radio_trk=2;
  if(n&(1u<<11)){ radio_trk=radio_trk+1>cdda_last?2:radio_trk+1; cdda_play(radio_trk); radio_on=1; radio_log("next "); }
  else if(n&(1u<<10)){ radio_trk=radio_trk<=2?cdda_last:radio_trk-1; cdda_play(radio_trk); radio_on=1; radio_log("prev "); }
  else if(n&(1u<<12)){ if(cdda_playing){ cdda_stop(); radio_on=0; radio_log("stop "); } else { cdda_play(radio_trk); radio_on=1; radio_log("start "); } } }
#endif
