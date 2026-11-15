/* PS1 memory card driver (SIO0, same port as the pad, byte protocol 0x81 'R'/'W') and the EEPROM save layer for the Payback port.
   Needs hw_pad.h (sio_xfer).  Card = 1024 frames of 128 bytes = 16 blocks of 64 frames; block 0 = header+directory, blocks 1..15 files.
   Save file "BESLES-99901SFBACK" = 2 blocks (16 KiB): image frame 0 title+CLUT, frame 1 icon, frame 3 meta (magic, seq, crc32), payload (the 8 KiB EEPROM) at image offset 0x200.
   Public: sv_load(ee,n) -> 1 loaded / 0 none / -1 no card, sv_dirty(off,len), sv_service() (one frame write per call, call once per vblank). */
#ifndef HW_CARD_H
#define HW_CARD_H
#define A4 __attribute__((aligned(4)))
#ifndef SV_IDLE
#define SV_IDLE 20      /* present() calls without a new EEPROM write before the flush starts */
#endif
static int mc_slot=-1; static u32 mc_reads, mc_writes, mc_err, mc_fail_last;
static int mc_frame_rd(u32 f,u8*d){
  u8 tx[140],rx[140]; for(int i=0;i<140;i++) tx[i]=0; tx[0]=0x81; tx[1]=0x52; tx[4]=f>>8; tx[5]=f&255;
  for(int t=0;t<3;t++){
    int n=sio_xfer(mc_slot,tx,rx,140);
    if(n==140&&rx[2]==0x5a&&rx[3]==0x5d&&rx[8]==(f>>8)&&rx[9]==(f&255)){
      u8 c=(f>>8)^(f&255); for(int i=0;i<128;i++) c^=rx[10+i];
      if(c==rx[138]&&rx[139]==0x47){ for(int i=0;i<128;i++) d[i]=rx[10+i]; mc_reads++; return 0; } }
    mc_err++; mc_fail_last=n|(rx[1]<<8)|(rx[2]<<16);
  } return -1; }
static int mc_frame_wr(u32 f,const u8*d){
  u8 tx[138],rx[138]; tx[0]=0x81; tx[1]=0x57; tx[2]=0; tx[3]=0; tx[4]=f>>8; tx[5]=f&255; u8 c=tx[4]^tx[5];
  for(int i=0;i<128;i++){ tx[6+i]=d[i]; c^=d[i]; } tx[134]=c; tx[135]=0; tx[136]=0; tx[137]=0;
  for(int t=0;t<3;t++){
    int n=sio_xfer(mc_slot,tx,rx,138);
    if(n==138&&rx[137]==0x47){ mc_writes++; return 0; }
    mc_err++; mc_fail_last=n|(rx[1]<<8)|(rx[137]<<16);
  } return -1; }
/* find a formatted card in slot 1 then slot 2 */
static int mc_probe(void){ u8 b[128];
  for(int s=0;s<2;s++){ mc_slot=s; if(mc_frame_rd(0,b)==0&&b[0]=='M'&&b[1]=='C'){ return 1; } }   /* first read also clears the "new card" flag */
  mc_slot=-1; return 0; }
static u32 crc32b(const u8*p,u32 n){ u32 c=~0u; while(n--){ c^=*p++; for(int k=0;k<8;k++) c=(c>>1)^(0xedb88320u&-(c&1)); } return ~c; }
static const char SV_NAME[20]="BESLES-99901SFBACK";
#define SV_PAYLOAD_OFF 0x200
static u8 *sv_ee; static u32 sv_n, sv_blk[2], sv_have, sv_seq, sv_idle, sv_pend_dir, sv_state, sv_ok_writes;
static u32 sv_pend[3];                    /* bitmap over image frames 0..95 */
static u8 sv_dirf[2][128];
static int sv_ready;
static void sv_setp(u32 j){ sv_pend[j>>5]|=1u<<(j&31); }
static u32 sv_cardframe(u32 j){ return sv_blk[j>>6]*64+(j&63); }
static void sv_dirent(u8*e,int first){ for(int i=0;i<128;i++) e[i]=0;
  if(first){ e[0]=0x51; e[4]=0x00; e[5]=0x40; e[6]=0; e[7]=0; e[8]=(sv_blk[1]-1)&255; e[9]=(sv_blk[1]-1)>>8; for(int i=0;i<20;i++) e[10+i]=SV_NAME[i]; }
  else { e[0]=0x53; e[8]=0xff; e[9]=0xff; }
  u8 c=0; for(int i=0;i<127;i++) c^=e[i]; e[127]=c; }
/* title (Shift-JIS full width "STAR FLYBACK EEPROM"), CLUT, 16x16 4bpp star icon, meta */
static void sv_image_frame(u32 j,u8*d){
  for(int i=0;i<128;i++) d[i]=0;
  if(j==0){ d[0]='S'; d[1]='C'; d[2]=0x11; d[3]=2;
    const char*t="STAR FLYBACK SAVE"; u8*o=d+4; for(;*t&&o<d+4+62;t++){ u32 c=*t; u32 sj; if(c>='A'&&c<='Z') sj=0x8260+(c-'A'); else if(c>='0'&&c<='9') sj=0x824f+(c-'0'); else sj=0x8140; *o++=sj>>8; *o++=sj&255; }
    u16*pal=(u16*)(d+96); pal[0]=0; pal[1]=0x03ff|0x8000; pal[2]=0x001f|0x8000; pal[3]=0x7fff; }          /* 1 = yellow, 2 = red, 3 = white */
  else if(j==1){ static const u16 S[16]={0x0100,0x0100,0x0380,0x0380,0x07c0,0xfffe,0x7ffc,0x3ff8,0x1ff0,0x0fe0,0x1ff0,0x1c70,0x3838,0x7018,0x6008,0x0000};
    for(int y=0;y<16;y++) for(int x=0;x<16;x++){ int on=(S[y]>>(15-x))&1; int v=on?1:0; if(on&&y>4&&y<7) v=3; d[y*8+(x>>1)]|=v<<((x&1)*4); } }
  else if(j==3){ u32*m=(u32*)d; m[0]=0x42465346u; m[1]=1; m[2]=sv_seq; m[3]=sv_n; m[4]=crc32b(sv_ee,sv_n); }
  else if(j>=4){ u32 off=(j-4)*128; if(off<sv_n) for(int i=0;i<128&&off+i<sv_n;i++) d[i]=sv_ee[off+i]; }
}
static u32 sv_image_frames(void){ return 4+(sv_n+127)/128; }
/* directory scan: find our file (returns 1) or two free blocks (returns 0 and fills sv_blk, sv_have=0) ; -1 on card error / full */
static int sv_scan(void){ u8 e[128]; int found=-1, fr[2]={-1,-1}, nfree=0;
  for(u32 k=1;k<=15;k++){ if(mc_frame_rd(k,e)) return -1;
    u32 st=e[0]; int match=1; for(int i=0;i<18;i++) if(e[10+i]!=SV_NAME[i]) match=0;
    if(st==0x51&&match) found=k; else if(((st&0xf0)==0xa0)&&nfree<2) fr[nfree++]=k; }
  if(found>0){ if(mc_frame_rd(found,e)) return -1; u32 nx=e[8]|(e[9]<<8); sv_blk[0]=found; sv_blk[1]=nx<15?nx+1:0; if(!sv_blk[1]) return -1; sv_have=1; return 1; }
  if(nfree<2) return -1; sv_blk[0]=fr[0]; sv_blk[1]=fr[1]; sv_have=0; return 0; }
int sv_load(u8*ee,u32 n){ sv_ee=ee; sv_n=n; sv_ready=0;
  if(!mc_probe()){ dbg("MC no card\n"); return -1; }
  int r=sv_scan(); if(r<0){ dbg("MC dir error/full\n"); return -1; } sv_ready=1;
  if(r==0){ dbg("MC no save yet\n"); return 0; }
  u8 d[128] A4, m[128] A4; if(mc_frame_rd(sv_cardframe(3),m)) return -1; u32*mm=(u32*)m;
  if(mm[0]!=0x42465346u||mm[3]!=n){ dbg("MC bad meta\n"); sv_have=0; return 0; }
  for(u32 q=0;q<(n+127)/128;q++){ if(mc_frame_rd(sv_cardframe(q+4),d)) return -1; for(u32 i=0;i<128&&q*128+i<n;i++) ee[q*128+i]=d[i]; }
  if(crc32b(ee,n)!=mm[4]){ dbg("MC crc mismatch, save ignored\n"); for(u32 i=0;i<n;i++) ee[i]=0xff; sv_have=0; return 0; }
  sv_seq=mm[2]; dbg("MC loaded seq "); dec(sv_seq); dbg("blk "); dec(sv_blk[0]); dec(sv_blk[1]); dbg("\n"); return 1; }
void sv_dirty(u32 off,u32 len){ if(!sv_ready) return; sv_idle=0; if(!sv_have){ for(u32 j=0;j<sv_image_frames();j++) sv_setp(j); sv_pend_dir=1; }
  for(u32 q=off/128;q<=(off+len-1)/128&&q*128<sv_n;q++) sv_setp(q+4); sv_setp(3); }
/* one card frame write per call, after SV_IDLE quiet presents.  Directory entries go last, so a torn first save leaves no half file. */
void sv_service(void){
  if(!sv_ready) return; u32 nf=sv_image_frames(); int any=0; for(int i=0;i<3;i++) if(sv_pend[i]) any=1;
  if(!any&&!sv_pend_dir) return; if(++sv_idle<SV_IDLE) return;
  for(u32 j=0;j<nf;j++){ if(j==3) continue; if(sv_pend[j>>5]&(1u<<(j&31))){ u8 d[128] A4; sv_image_frame(j,d); if(mc_frame_wr(sv_cardframe(j),d)){ dbg("MC write fail\n"); return; }
      sv_pend[j>>5]&=~(1u<<(j&31)); sv_ok_writes++; return; } }
  if(sv_pend[0]&8){ u8 d[128] A4; sv_seq++; sv_image_frame(3,d); if(mc_frame_wr(sv_cardframe(3),d)){ dbg("MC write fail\n"); return; } sv_pend[0]&=~8u; sv_ok_writes++; return; }
  if(sv_pend_dir){ u8 e[128]; sv_dirent(e,0); if(mc_frame_wr(sv_blk[1],e)) return; sv_dirent(e,1); if(mc_frame_wr(sv_blk[0],e)) return; sv_pend_dir=0; sv_have=1; sv_ok_writes+=2; dbg("MC file created blk "); dec(sv_blk[0]); dec(sv_blk[1]); dbg("\n"); }
}
#endif
