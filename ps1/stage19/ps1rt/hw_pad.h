/* PS1 pad driver (SIO0, polled, no IRQ handler): digital pad and DualShock.  Included by rt.c / hwtest.c after u8/u16/u32, ISTAT, dbg/hex/dec.
   Public: pad_poll() -> GBA KEYINPUT value (active low, bits 0..9), plus pad_raw (active HIGH, PS1 bit layout), pad_ax[4], pad_id, pad_extra.
   PS1 button word (after inversion): b0 Select, b1 L3, b2 R3, b3 Start, b4 Up, b5 Right, b6 Down, b7 Left, b8 L2, b9 R2, b10 L1, b11 R1, b12 Triangle, b13 Circle, b14 Cross, b15 Square.
   GBA KEYINPUT bits: 0 A, 1 B, 2 Select, 3 Start, 4 Right, 5 Left, 6 Up, 7 Down, 8 R, 9 L. */
#ifndef HW_PAD_H
#define HW_PAD_H
#define JOY_DATA (*(volatile u8*)0x1F801040)
#define JOY_STAT (*(volatile u16*)0x1F801044)
#define JOY_MODE (*(volatile u16*)0x1F801048)
#define JOY_CTRL (*(volatile u16*)0x1F80104A)
#define JOY_BAUD (*(volatile u16*)0x1F80104E)
static int sio_inited;
static void sio_init(void){ if(sio_inited) return; JOY_CTRL=0x40; JOY_BAUD=0x88; JOY_MODE=0x000D; JOY_CTRL=0; sio_inited=1; }
/* full-duplex transfer of n bytes with the device selected on 'port' (0 = slot 1).  The device acks every byte but the last (IRQ7 / JOY_STAT bit 9).
   returns number of bytes exchanged (n on success), or the count reached when an ack did not come (no device / aborted) */
static int sio_xfer(int port,const u8*tx,u8*rx,int n){
  sio_init(); JOY_CTRL=0x1003|(port<<13); ISTAT=~0x80u; for(volatile int d=0;d<300;d++){}
  int i;
  for(i=0;i<n;i++){
    JOY_DATA=tx[i];
    u32 s; for(s=0;s<20000;s++) if(JOY_STAT&2) break;
    rx[i]=JOY_DATA; if(s==20000){ i++; break; }
    if(i<n-1){ for(s=0;s<40000;s++) if((ISTAT&0x80)||(JOY_STAT&0x200)) break; JOY_CTRL|=0x10; ISTAT=~0x80u; if(s==40000){ i++; break; } }
  }
  JOY_CTRL=0; for(volatile int d=0;d<100;d++){}
  return i;
}
u16 pad_raw, pad_prev; u8 pad_ax[4]={128,128,128,128}; u8 pad_id=0xff; u32 pad_extra, pad_polls, pad_fails, pad_cfg_tries; int pad_analog; u32 pad_cfg_log[3];
/* stage 19: the driver never changes the controller's mode.  A digital pad (ID 41h) and a DualShock in either mode (41h digital, 73h analog) are read
   as they are; the game needs no sticks.  A pad found in configuration mode (ID F3h: "While in config mode, the ID bytes are always F3h 5Ah",
   psx-spx) was left there by someone else: it gets Exit config (43h with 00h) and is read again at the next poll.
   pad_cfg_tries counts these Exit config transfers, pad_cfg_log[2] records the last one (bytes exchanged | reply ID << 8 | reply byte 2 << 16). */
static const u8 CFG_EXIT[9]={1,0x43,0,0,0x5a,0x5a,0x5a,0x5a,0x5a};
static void pad_exit_config(void){ u8 rx[9]; pad_cfg_tries++;
  int n=sio_xfer(0,CFG_EXIT,rx,9); pad_cfg_log[2]=n|(rx[1]<<8)|(rx[2]<<16); for(volatile int d=0;d<3000;d++){} }
/* GBA key mapping (documented in HW.md): Cross=A, Circle/Square=B, Select, Start, D-pad (and left stick when analog), L1=L, R1=R.  Triangle/L2/R2/L3/R3 and the right stick are not GBA keys: pad_extra */
static u32 pad_to_gba(u32 p){ u32 k=0;
  if(p&(1u<<14)) k|=0x001; if(p&((1u<<13)|(1u<<15))) k|=0x002; if(p&1) k|=0x004; if(p&(1u<<3)) k|=0x008;
  if(p&(1u<<5)) k|=0x010; if(p&(1u<<7)) k|=0x020; if(p&(1u<<4)) k|=0x040; if(p&(1u<<6)) k|=0x080;
  if(p&(1u<<11)) k|=0x100; if(p&(1u<<10)) k|=0x200; return k; }
/* one 0x42 poll as a single transaction whose length follows the id byte (stage 13): digital 0x41 = 5 bytes, DualShock analog 0x73 = 9 (buttons + sticks in the same transfer: the old code did two). */
static int sio_pad_xfer(u8*rx){
  static const u8 tx[9]={1,0x42,0,0,0,0,0,0,0}; sio_init(); JOY_CTRL=0x1003; ISTAT=~0x80u; for(volatile int d=0;d<300;d++){}
  int n=9,i;
  for(i=0;i<n;i++){
    JOY_DATA=tx[i]; u32 s; for(s=0;s<20000;s++) if(JOY_STAT&2) break;
    rx[i]=JOY_DATA; if(s==20000){ i++; break; }
    if(i==1){ u32 id=rx[1]&0xff; n=3+2*(id&15); if(n>9) n=9; if(n<5) n=5; }
    if(i<n-1){ for(s=0;s<40000;s++) if((ISTAT&0x80)||(JOY_STAT&0x200)) break; JOY_CTRL|=0x10; ISTAT=~0x80u; if(s==40000){ i++; break; } }
  }
  JOY_CTRL=0; for(volatile int d=0;d<100;d++){}
  return i; }
u32 pad_poll(void){
  u8 rx[9]={0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff}; pad_polls++;
  int n=sio_pad_xfer(rx);
  u32 id=rx[1]&0xff; pad_id=id;
  if(n<5||rx[2]!=0x5a||((id&0xf0)!=0x40&&(id&0xf0)!=0x70&&(id&0xf0)!=0x50&&(id&0xf0)!=0xf0)){ pad_fails++; pad_raw=0; pad_extra=0; pad_analog=0; return 0x3ff; }
  if((id&0xf0)==0xf0){ pad_exit_config(); pad_raw=0; pad_extra=0; return 0x3ff; }   /* configuration mode: leave it, read at the next poll */
  pad_prev=pad_raw; pad_raw=(~(rx[3]|(rx[4]<<8)))&0xffff;
  if((id&0xf0)==0x70||(id&0xf0)==0x50){
    if(n==9){ for(int i=0;i<4;i++) pad_ax[i]=rx[5+i]; pad_analog=1;
      /* left stick -> d-pad (threshold 64 of 128 around 0x80) */
      u32 lx=pad_ax[2], ly=pad_ax[3]; if(lx>=0xc0) pad_raw|=1u<<5; if(lx<=0x40) pad_raw|=1u<<7; if(ly<=0x40) pad_raw|=1u<<4; if(ly>=0xc0) pad_raw|=1u<<6; } }
  else { pad_analog=0; pad_ax[0]=pad_ax[1]=pad_ax[2]=pad_ax[3]=128; }
  pad_extra=((pad_raw>>12)&1)|(((pad_raw>>8)&3)<<1)|(((pad_raw>>1)&3)<<3);   /* b0 Triangle, b1 L2, b2 R2, b3 L3, b4 R3 */
  return 0x3ff&~pad_to_gba(pad_raw); }
#endif
