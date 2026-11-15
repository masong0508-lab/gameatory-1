/* CD-DA playback (CD-ROM controller + SPU CD input), polled, no IRQ handler.  Needs cd_cmd/cd_wait/cd_ack/bcd and CD0..CD3 from the includer.
   Public: cdda_init() (SPU + CD volume, reads TOC: cdda_last), cdda_play(track), cdda_stop() (pause), cdda_off() (motor stop), cdda_pos(), cdda_service() (once per vblank:
   end-of-track -> next track), cdda_hold()/cdda_release() around data reads (a data seek ends audio playback: position is saved and resumed).
   Track numbers are disc track numbers: track 1 = the data track, audio from 2. */
#ifndef HW_CDDA_H
#define HW_CDDA_H
#define SPU16(a) (*(volatile u16*)(a))
u32 (*cdda_nextfn)(u32 cur); u32 cdda_last, cdda_cur, cdda_playing, cdda_held, cdda_loop, cdda_ended, cdda_cmds, cdda_resumes, cdda_pos_trk, cdda_pos_idx, cdda_rel_s, cdda_rel_f, cdda_abs[3]; u8 cdda_stat;
static u8 cdda_mode_cur;
static u32 unbcd(u32 v){ return (v>>4)*10+(v&15); }
/* send a command, wait for its INT, read the response (up to 8 bytes) and ack.  returns the INT number (3 = ok, 5 = error) */
static u32 cdc(u8 c,const u8*p,int np,u8*resp){
  CD0=1; u32 pend=CD3&7; if(pend){ if(pend==4) cdda_ended=1; cd_ack(); }
  cd_cmd(c,p,np); u32 f=cd_wait(); int n=0; CD0=1; while((CD0&0x20)&&n<8){ u8 b=CD1; if(resp) resp[n]=b; n++; } cdda_stat=resp?resp[0]:cdda_stat;
  cd_ack(); cdda_cmds++; return f; }
static void cdc2(u8 c,const u8*p,int np){ u8 r[8]; cdc(c,p,np,r); cd_wait(); cd_ack(); }   /* commands that answer INT3 then INT2 (Pause, Stop) */
static void cdda_setmode(u8 m){ if(cdda_mode_cur==m) return; cdc(0x0e,&m,1,0); cdda_mode_cur=m; }
void cdda_init(void){
  SPU16(0x1F801DAA)=0xC001; SPU16(0x1F801D80)=0x3fff; SPU16(0x1F801D82)=0x3fff; SPU16(0x1F801DB0)=0x7fff; SPU16(0x1F801DB2)=0x7fff;   /* SPU on, unmuted, CD input on */
  CD0=2; CD2=0x80; CD3=0x00; CD0=3; CD1=0x80; CD2=0x00; CD3=0x20;                                                         /* CD L->L, R->R full, apply */
  u8 r[8]; if(cdc(0x13,0,0,r)==3) cdda_last=unbcd(r[2]); else cdda_last=1; }
void cdda_play(u32 trk){ if(trk<2||trk>cdda_last) return; u8 p=bcd(trk); cdda_setmode(0x03); u32 rc=cdc(0x03,&p,1,0); dbg("CDDA play cmd 0x03 track "); dec(trk); dbg("int "); dec(rc); dbg("\n"); if(rc==3){ cdda_cur=trk; cdda_playing=1; cdda_held=0; } }
void cdda_stop(void){ if(!cdda_playing) return; cdc2(0x09,0,0); cdda_playing=0; cdda_held=0; }
void cdda_off(void){ cdc2(0x08,0,0); cdda_playing=0; cdda_held=0; cdda_cur=0; }
void cdda_pos(void){ u8 r[8]; if(cdc(0x11,0,0,r)==3){ cdda_pos_trk=unbcd(r[0]); cdda_pos_idx=unbcd(r[1]); cdda_rel_s=unbcd(r[2])*60+unbcd(r[3]); cdda_rel_f=unbcd(r[4]); cdda_abs[0]=r[5]; cdda_abs[1]=r[6]; cdda_abs[2]=r[7]; } }
/* a data read will seek the laser away: remember where audio was, pause, go to the data speed */
void cdda_hold(void){ if(!cdda_playing||cdda_held) return; cdda_pos(); cdc2(0x09,0,0); cdda_held=1; cdda_setmode(0x80); }
void cdda_release(void){ if(!cdda_held) return; cdda_held=0; u8 p[3]={cdda_abs[0],cdda_abs[1],cdda_abs[2]}; cdda_setmode(0x03); cdc(0x02,p,3,0); u8 r[8]; cdc(0x03,0,0,r); cdda_resumes++; }
/* once per vblank: INT4 = end of track (auto-pause): play the next one (wraps to the first audio track), or repeat when cdda_loop */
void cdda_service(void){
  if(!cdda_playing||cdda_held) return; CD0=1; u32 f=CD3&7; if(!f) return; cd_ack();
  if(f==4||cdda_ended){ cdda_ended=0; u32 n=cdda_loop?cdda_cur:cdda_nextfn?cdda_nextfn(cdda_cur):(cdda_cur+1>cdda_last?2:cdda_cur+1); cdda_playing=0; cdda_play(n); } }
#endif
