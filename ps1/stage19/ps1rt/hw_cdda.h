/* CD-DA playback (CD-ROM controller + SPU CD input), polled, no IRQ handler.  Needs cd_cmd/cd_done/cd_pause/cd_setmode/cd_mode/cd_reading/cd_stat/
   cdda_ended/cd_rd_gf/g_gframes/bcd/unbcd and CD0..CD3 from the includer (rt.c: every command drains pending interrupts first and waits for its own
   answer, bounded in time).
   Public: cdda_init() (SPU + CD volume, reads TOC: cdda_last), cdda_play(track), cdda_stop() (pause), cdda_off() (motor stop), cdda_service() (once
   per present: end-of-track -> next track), cdda_hold() before every data read, cdda_idle() once per present (resumes the music), cdda_dmode() (the
   Setmode value for data reads).  Track numbers are disc track numbers: track 1 = the data track, audio from 2.
   A data read seeks the laser away from the music, so the music is held (paused) for data and resumed later:
   - The resume position is only ever a place where the drive was really PLAYING this track: Getstat must show Play without Seek, then GetlocP must
     report the same track, index 1 or more, and an absolute address inside the track's TOC range.  Anything else keeps the position saved before:
     right after a Play the drive is still seeking and GetlocP reports the last DATA sector it read (psx-spx: Getloc while the Play seek runs can even
     stop the drive).  Until a position has been taken, a resume starts the track again with Play(track).
   - Data reads never resume the music themselves: a burst of page misses costs one Pause, not a Pause and a Play per read.  The music comes back
     at a present once the disc has had no data read for cdda_quiet guest frames (CDDA_QUIET, doubled up to CDDA_QMAX each time the music is held
     again soon after it came back, back to CDDA_QUIET after it played for CDDA_QMAX guest frames).  rc8: once the music has been held for
     CDDA_HMAX guest frames, CDDA_QUIET frames without a data read are enough again, and that resume starts the back-off from CDDA_QUIET
     (with the doubled interval alone a level's steady page reads kept the radio silent 11-17 s after every hold; reads are never delayed).
     rc8 review: that early resume backs off too.  Each one costs a seek to the music and, at the next page read, a seek back, which the
     game waits for; under steady reads (fast driving, teleports) resumes every 4 s took 12-20 % of the level's speed on SwanStation.  When
     music that came back through the early resume is held again before it has played CDDA_HMAX guest frames, the hold needed for the next
     early resume (cdda_hmax) doubles, up to CDDA_HMAXX; music that plays CDDA_QMAX guest frames sets it back to CDDA_HMAX.  In normal play
     the early resume rarely happens and nothing changes.
   - Data is read at double speed (Setmode A0h) while the radio is on too (CDDA_DMODE_PLAY): the spindle changes speed only when the disc goes
     from music to data or back, which the quiet interval keeps rare.  Measured on SwanStation from the same level state: a walk with the radio on
     runs as fast as without it (1.33 guest frames/s) and the music sounds 13 frames after a resume; with single-speed data reads (20h, no speed
     change) the walk ran at 1.17 and the way back from the pause menu took 2.8 s longer.
   - A resume the drive did not take (Setloc or Play not answered INT3) leaves the music held, so the next present tries again; every CDDA_WD
     guest frames cdda_service() asks Getstat whether the drive still plays (or seeks to play), and music found stopped twice in a row without
     reaching the end of its track (an error) is resumed the same way. */
#ifndef HW_CDDA_H
#define HW_CDDA_H
#define SPU16(a) (*(volatile u16*)(a))
#ifndef CDDA_QUIET
#define CDDA_QUIET 8u
#endif
#ifndef CDDA_QMAX
#define CDDA_QMAX 64u
#endif
#ifndef CDDA_HMAX
#define CDDA_HMAX (CDDA_QMAX/2u)  /* guest frames of held music after which the short quiet interval applies again */
#endif
#ifndef CDDA_HMAXX
#define CDDA_HMAXX (CDDA_QMAX*4u) /* the most the early-resume hold backs off to (32 s with the real-frame values) */
#endif
#ifndef CDDA_DMODE_PLAY
#define CDDA_DMODE_PLAY 0xa0u      /* Setmode for data reads while the radio is on: 924h-byte sectors, double speed (20h: single speed) */
#endif
#ifndef CDDA_WD
#define CDDA_WD 30u                /* guest frames between two Getstat checks of music that should be playing */
#endif
#ifdef CDDA_DATARADIO
/* TEST ONLY, for the data-track test discs (no audio track): the radio's track 2 is the data track itself, played, paused, located and
   resumed like music (Play, Pause, GetlocP, Setloc + Play) with the SPU's CD input muted, so the hold / resume cycle, its spindle speed
   changes and its seeks run on a disc that has no music.  cdda_init then reports 2 tracks.  Never in a release build. */
#define CDDA_PT(t) ((t)==2u?1u:(t))
#else
#define CDDA_PT(t) (t)
#endif
u32 (*cdda_nextfn)(u32 cur); u32 cdda_last, cdda_cur, cdda_playing, cdda_held, cdda_loop, cdda_cmds, cdda_resumes, cdda_holds, cdda_pos_ok,
    cdda_pos_rej, cdda_pos_trk, cdda_pos_idx, cdda_rel_s, cdda_rel_f, cdda_abs[3], cdda_t0, cdda_t1, cdda_quiet=CDDA_QUIET, cdda_gf, cdda_rfail,
    cdda_lost, cdda_wd_gf, cdda_wd_n, cdda_hgf, cdda_hmax=CDDA_HMAX, cdda_hrel, cdda_hback; u8 cdda_stat;
/* send a command and take its first answer (the response bytes in resp): returns the INT number (3 = ok, 5 = error, 0 = no answer) */
static u32 cdc(u8 c,const u8*p,int np,u8*resp){ u8 r[8]; u32 f=cd_cmd(c,p,np,resp?resp:r); cdda_stat=cd_stat; cdda_cmds++; return f; }
static void cdc2(u8 c,const u8*p,int np){ u8 r[8]; if(cdc(c,p,np,r)==3) cd_done(r); cd_reading=0; }   /* commands that answer INT3 then INT2 (Pause, Stop) */
static void cdda_setmode(u8 m){ if(cd_reading&&cd_mode!=m) cd_pause(); cd_setmode(m); }   /* never change the mode under a running data read */
static u32 cdda_dmode(void){ return cdda_playing?CDDA_DMODE_PLAY:0xa0u; }   /* data reads: 924h-byte sectors, double speed (see above) */
static u32 cdda_msf(u32 m,u32 s,u32 f){ return unbcd(m)*4500+unbcd(s)*75+unbcd(f); }   /* BCD MM:SS:FF -> sectors from 00:00:00 */
void cdda_init(void){
  SPU16(0x1F801DAA)=0xC001; SPU16(0x1F801D80)=0x3fff; SPU16(0x1F801D82)=0x3fff; SPU16(0x1F801DB0)=0x7fff; SPU16(0x1F801DB2)=0x7fff;   /* SPU on, unmuted, CD input on */
  CD0=2; CD2=0x80; CD3=0x00; CD0=3; CD1=0x80; CD2=0x00; CD3=0x20;                                                         /* CD L->L, R->R full, apply */
  u8 r[8]; if(cdc(0x13,0,0,r)==3) cdda_last=unbcd(r[2]); else cdda_last=1;
#ifdef CDDA_DATARADIO
  if(cdda_last<2){ cdda_last=2; SPU16(0x1F801DB0)=0; SPU16(0x1F801DB2)=0; }
#endif
}
/* start a track from its beginning.  GetTD gives the track's range for the GetlocP check (start of index 1 rounded down to the second, so the range
   begins inside the track's own 2-second pregap; the next track's start, or the end of the disc).  The saved position is the track start. */
void cdda_play(u32 trk){ if(trk<2||trk>cdda_last) return; u8 p=bcd(CDDA_PT(trk)), q=bcd(trk<cdda_last?trk+1:0), r[8];
  u32 t0=0, t1=0xffffffffu; if(cdc(0x14,&p,1,r)==3){ u32 a=cdda_msf(r[1],r[2],0); if(cdc(0x14,&q,1,r)==3){ t0=a; t1=cdda_msf(r[1],r[2],0); } }
  cdda_setmode(0x03); u32 rc=cdc(0x03,&p,1,0); dbg("CDDA play cmd 0x03 track "); dec(trk); dbg("int "); dec(rc); dbg("\n");
  if(rc==3){ cdda_cur=trk; cdda_playing=1; cdda_held=0; cdda_ended=0; cdda_t0=t0; cdda_t1=t1; cdda_pos_ok=0; cdda_pos_trk=trk; cdda_pos_idx=1;
    cdda_abs[0]=bcd(t0/4500); cdda_abs[1]=bcd((t0/75)%60); cdda_abs[2]=bcd(t0%75); cdda_gf=cdda_wd_gf=g_gframes; cdda_wd_n=0; } }
void cdda_stop(void){ if(!cdda_playing) return; cdc2(0x09,0,0); cdda_playing=0; cdda_held=0; }
void cdda_off(void){ cdc2(0x08,0,0); cdda_playing=0; cdda_held=0; cdda_cur=0; }
/* before a data read: take the position (only while the drive really plays this track) and pause the music */
void cdda_hold(void){ if(!cdda_playing||cdda_held) return;
  { u32 played=g_gframes-cdda_gf; cdda_quiet=played>=CDDA_QMAX?CDDA_QUIET:(cdda_quiet*2>CDDA_QMAX?CDDA_QMAX:cdda_quiet*2);
    if(played>=CDDA_QMAX) cdda_hmax=CDDA_HMAX;
    else if(cdda_hrel&&played<CDDA_HMAX&&cdda_hmax<CDDA_HMAXX){ cdda_hmax*=2u; cdda_hback++; }   /* an early resume cut short: back off */
    cdda_hrel=0; }
  cdda_held=1; cdda_holds++; cdda_hgf=g_gframes;
  u8 r[8]; if(cdc(0x01,0,0,r)!=3) return;                               /* Getstat: bit 7 Play, bit 6 Seek */
  u8 st=r[0];
#ifdef CDDA_DBG
  dbg("CDDA hold stat "); hex(st); dbg("gf "); dec(g_gframes); dbg("\n");
#endif
  if((st&0xc0)!=0x80) return;                                           /* still seeking (Pause could fail with INT5), or not playing (AutoPause) */
  if(cdc(0x11,0,0,r)==3){ u32 a=cdda_msf(r[5],r[6],r[7]);
    if(unbcd(r[0])==CDDA_PT(cdda_cur)&&r[1]>=1&&r[1]<=0x99&&a>=cdda_t0&&a<cdda_t1){ cdda_pos_ok=1; cdda_pos_trk=cdda_cur; cdda_pos_idx=unbcd(r[1]);
      cdda_rel_s=unbcd(r[2])*60+unbcd(r[3]); cdda_rel_f=unbcd(r[4]); cdda_abs[0]=r[5]; cdda_abs[1]=r[6]; cdda_abs[2]=r[7]; }
    else cdda_pos_rej++; }
  cdc2(0x09,0,0); }                                                     /* Pause: INT3, INT2 */
/* resume the held music where it was (or the track from its start), unless the track ended meanwhile: cdda_service then starts the next one.
   A resume the drive does not take leaves the music held: the next present tries again. */
static void cdda_release(void){ if(!cdda_held) return; cdda_hrel=(g_gframes-cdda_hgf>=cdda_hmax); if(cdda_hrel) cdda_quiet=CDDA_QUIET; cdda_gf=g_gframes; cdda_wd_gf=g_gframes; cdda_wd_n=0; if(cdda_ended){ cdda_held=0; return; }
  cdda_setmode(0x03); cdda_resumes++;
  u32 rc;
  if(cdda_pos_ok){ u8 p[3]={cdda_abs[0],cdda_abs[1],cdda_abs[2]}; rc=cdc(0x02,p,3,0); if(rc==3) rc=cdc(0x03,0,0,0); }   /* Setloc + Play from there */
  else { u8 p=bcd(CDDA_PT(cdda_cur)); rc=cdc(0x03,&p,1,0); }                                                                    /* Play(track): its start */
#ifdef CDDA_DBG
  dbg("CDDA resume pos "); dec(cdda_pos_ok); hex((u32)cdda_abs[0]<<16|cdda_abs[1]<<8|cdda_abs[2]); dbg("int "); dec(rc); dbg("stat "); hex(cdda_stat); dbg("gf "); dec(g_gframes); dbg("\n");
#endif
  if(rc==3) cdda_held=0; else cdda_rfail++; }
/* once per present, after the left-running data read was paused: the music comes back after cdda_quiet guest frames without a data read */
static void cdda_idle(void){ if(!cdda_held) return; u32 q=g_gframes-cd_rd_gf; if(q>=cdda_quiet||(q>=CDDA_QUIET&&g_gframes-cdda_hgf>=cdda_hmax)) cdda_release(); }
/* once per present: INT4 = end of track (auto-pause): play the next one (wraps to the first audio track), or repeat when cdda_loop.
   INT5, or (every CDDA_WD guest frames) two Getstat answers in a row with neither Play nor Seek set before the end of the track: the music
   stopped, resume it. */
void cdda_service(void){
  if(!cdda_playing||cdda_held) return; u32 f=cd_flags(); if(f){ cd_result(0); cd_ack(); }
  if(f==4||cdda_ended){ cdda_ended=0; u32 n=cdda_loop?cdda_cur:cdda_nextfn?cdda_nextfn(cdda_cur):(cdda_cur+1>cdda_last?2:cdda_cur+1); cdda_playing=0; cdda_play(n); return; }
  u32 lost=(f==5);
  if(!lost&&g_gframes-cdda_wd_gf>=CDDA_WD){ u8 r[8]; cdda_wd_gf=g_gframes;
    if(cdc(0x01,0,0,r)==3&&!(r[0]&0xc0)&&!cdda_ended){ if(++cdda_wd_n>=2) lost=1; } else cdda_wd_n=0; }
  if(cdda_ended) return;                                              /* INT4 came with the Getstat: the next present plays the next track */
  if(lost){ cdda_lost++; cdda_held=1; cdda_hgf=g_gframes; cdda_wd_n=0;
#ifdef CDDA_DBG
    dbg("CDDA stopped stat "); hex(cdda_stat); dbg("int "); dec(f); dbg("gf "); dec(g_gframes); dbg("\n");
#endif
  } }
#endif
