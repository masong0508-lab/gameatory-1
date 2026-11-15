/* hwtest: standalone PS1 test of the hardware replacements (pad, memory card save, CD-DA).  No Payback code or data.
   Build: ./build_hwtest.sh -> ../out/hwtest.exe + disc.  Output: screen (pad state, card, CD position) and the BIOS putchar log (pcsxr -psxout). */
typedef unsigned int u32; typedef int s32; typedef unsigned short u16; typedef short s16; typedef unsigned char u8; typedef signed char s8;
#define GP0 (*(volatile u32*)0x1F801810)
#define GP1 (*(volatile u32*)0x1F801814)
#define ISTAT (*(volatile u32*)0x1F801070)
#define IMASK (*(volatile u32*)0x1F801074)
#define CD0 (*(volatile u8*)0x1F801800)
#define CD1 (*(volatile u8*)0x1F801801)
#define CD2 (*(volatile u8*)0x1F801802)
#define CD3 (*(volatile u8*)0x1F801803)
void *memset(void*d,int c,unsigned n){u8*p=d;while(n--)*p++=c;return d;}
static void dbgc(char c){ register u32 a0 __asm__("$4")=c; register u32 t1 __asm__("$9")=0x3c;
  __asm__ volatile("li $8,0xA0\n jalr $8\n nop":"+r"(a0),"+r"(t1)::"$1","$2","$3","$5","$6","$7","$8","$10","$11","$12","$13","$14","$15","$24","$25","$31","memory"); }
static void dbg(const char*p){ while(*p) dbgc(*p++); }
static void hex(u32 v){ for(int i=0;i<8;i++){int d=(v>>(28-4*i))&15; dbgc(d<10?48+d:87+d);} dbgc(' '); }
static void dec(u32 v){ char b[12]; int n=0; if(!v) b[n++]='0'; while(v){b[n++]='0'+v%10; v/=10;} while(n) dbgc(b[--n]); dbgc(' '); }
/* --- CD primitives (same as rt.c) */
static u32 cd_ready, cd_sectors;
static void cd_ack(void){ CD0=1; CD3=0x1f; }
static u32 cd_wait(void){ for(u32 n=0;n<3000000;n++){ CD0=1; u32 f=CD3&7; if(f) return f; } dbg("CD timeout\n"); return 0; }
static void cd_cmd(u8 c,const u8*p,int n){ for(u32 w=0;(CD0&0x80);w++) if(w>2000000){ dbg("CD busy\n"); break; } CD0=0; for(int i=0;i<n;i++) CD2=p[i]; CD1=c; }
static u8 bcd(u32 v){ return (v/10)*16+v%10; }
#include "hw_pad.h"
#include "hw_card.h"
#include "hw_cdda.h"
static void cd_read(u32 lba,u32 nsec,u8*dst){
  cdda_hold();
  if(!cd_ready){ IMASK=0; cd_ready=1; u8 m=0x80; cd_cmd(0x0e,&m,1); cd_wait(); cd_ack(); }
  u32 a=lba+150; u8 p[3]={bcd(a/4500),bcd((a/75)%60),bcd(a%75)};
  cd_cmd(0x02,p,3); cd_wait(); cd_ack(); cd_cmd(0x06,0,0); cd_wait(); cd_ack();
  for(u32 s=0;s<nsec;s++){ cd_wait(); CD0=0; CD3=0x80; for(int i=0;i<2048;i++) dst[s*2048+i]=CD2; cd_ack(); }
  cd_cmd(0x09,0,0); cd_wait(); cd_ack(); cd_wait(); cd_ack(); cd_sectors+=nsec;
  cdda_release();
}
/* --- GPU text */
static void gp0(u32 w){ while(!(GP1&0x04000000)){} GP0=w; }
#define XY(x,y) (((u32)(y)<<16)|((x)&0xffff))
static int cur_oy;
static void rect(int x,int y,int w,int h,u32 rgb){ if(w<=0||h<=0) return; gp0(0x60000000|rgb); gp0(XY(x,y+cur_oy)); gp0(XY(w,h)); }
#include "font.h"
static int chidx(char c){ if(c>='0'&&c<='9') return c-'0'; if(c>='a'&&c<='z') c-=32; if(c>='A'&&c<='Z') return 10+c-'A'; return -1; }
static void text(int x,int y,const char*s,int sc,u32 rgb){ for(;*s;s++,x+=4*sc){ int i=chidx(*s); if(i<0) continue; u16 g=F35[i];
    for(int r=0;r<5;r++) for(int c=0;c<3;c++) if(g&(1<<(14-(r*3+c)))) rect(x+c*sc,y+r*sc,sc,sc,rgb); } }
static void num(int x,int y,u32 v,int sc,u32 rgb){ char b[12]; int n=0; if(!v) b[n++]='0'; while(v){b[n++]='0'+v%10; v/=10;} char t[12]; for(int i=0;i<n;i++) t[i]=b[n-1-i]; t[n]=0; text(x,y,t,sc,rgb); }
static void hexn(int x,int y,u32 v,int digits,int sc,u32 rgb){ char t[9]; for(int i=0;i<digits;i++){ int d=(v>>(4*(digits-1-i)))&15; t[i]=d<10?'0'+d:'A'+d-10; } t[digits]=0; text(x,y,t,sc,rgb); }
static void vsync(void){ ISTAT=~1u; for(volatile int n=0;n<400000;n++){ if(ISTAT&1) break; } ISTAT=~1u; }
static u8 ee[8192] A4;
static const char*const BN[16]={"SEL","L3","R3","STA","UP","RIG","DOW","LEF","L2","R2","L1","R1","TRI","CIR","CRO","SQU"};
int main(void){
  dbg("HWTEST start\n");
  GP1=0; GP1=0x03000000; GP1=0x06000000|(0x260|((0x260+320*8)<<12)); GP1=0x07000000|(0x10|((0x10+240)<<10)); GP1=0x08000001;
  for(u32 i=0;i<sizeof ee;i++) ee[i]=0xff;
  int lr=sv_load(ee,sizeof ee); u32 boots=0; if(lr==1) boots=*(u32*)ee; boots++; *(u32*)ee=boots; ee[100]=0x5a; ee[8191]=0xa5; sv_dirty(0,4); sv_dirty(8191,1);
  dbg("HWTEST card load="); dec(lr+1); dbg("boot count "); dec(boots); dbg("slot "); dec(mc_slot+1); dbg("reads "); dec(mc_reads); dbg("\n");
  cdda_init(); dbg("HWTEST cd last track "); dec(cdda_last); dbg("\n");
  u32 fc=0, buf=0, gba=0x3ff, lastgba=0xffffffff; u16 lastraw=0xffff;
  for(;;fc++){
    gba=pad_poll();
    if(pad_raw!=lastraw||gba!=lastgba){ lastraw=pad_raw; lastgba=gba; dbg("cfg "); hex(pad_cfg_log[0]); hex(pad_cfg_log[1]); hex(pad_cfg_log[2]); dbg("PAD id "); hex(pad_id); dbg("raw "); hex(pad_raw); dbg("gba "); hex(gba); dbg("ax "); dec(pad_ax[0]); dec(pad_ax[1]); dec(pad_ax[2]); dec(pad_ax[3]); dbg("fc "); dec(fc); dbg("\n"); }
    sv_service(); cdda_service();
    if(cdda_last>=2){
      if(fc==30){ cdda_play(2); dbg("CDDA play 2\n"); }
      if(fc==150||fc==210||fc==330){ cdda_pos(); dbg("CDDA pos fc "); dec(fc); dbg("trk "); dec(cdda_pos_trk); dbg("idx "); dec(cdda_pos_idx); dbg("rel "); dec(cdda_rel_s); dbg("."); dec(cdda_rel_f); dbg("stat "); hex(cdda_stat); dbg("\n"); }
      if(fc==160){ static u8 sec[2048*2]; cd_read(16,2,sec); cdda_pos(); dbg("CDDA after data read: trk "); dec(cdda_pos_trk); dbg("rel "); dec(cdda_rel_s); dbg("."); dec(cdda_rel_f); dbg("resumes "); dec(cdda_resumes); dbg("pvd "); dbgc(sec[1]); dbgc(sec[2]); dbgc(sec[3]); dbg("\n"); }
      if(fc==240){ cdda_stop(); dbg("CDDA stop\n"); }
      if(fc==270){ cdda_play(cdda_last>=3?3:2); dbg("CDDA play 3\n"); }
      if(fc==300){ cdda_off(); dbg("CDDA off\n"); }
    }
    if(fc%60==0){ dbg("HWTEST fc "); dec(fc); dbg("mc writes "); dec(mc_writes); dbg("err "); dec(mc_err); dbg("pend "); hex(sv_pend[0]); dbg("have "); dec(sv_have); dbg("\n"); }
    int oy=buf?240:0; cur_oy=oy;
    gp0(0xE1000000|(5)|(2<<7)); gp0(0xE3000000|XY(0,oy)); gp0(0xE4000000|XY(319,oy+239)); gp0(0xE5000000|XY(0,oy));
    gp0(0x02101018); gp0(XY(0,oy)); gp0(XY(320,240));
    text(4,4,"PS1 HW TEST",2,0xffffff);
    for(int i=0;i<16;i++){ int x=4+(i%8)*38, y=24+(i/8)*20; rect(x,y,34,16,(pad_raw>>i)&1?0x30c030:0x303030); text(x+2,y+5,BN[i],1,0xffffff); }
    text(4,70,"GBA KEYS",1,0x80c0ff); hexn(60,70,gba,3,1,0xffffff); text(100,70,"PAD ID",1,0x80c0ff); hexn(140,70,pad_id,2,1,0xffffff);
    text(4,80,"STICKS",1,0x80c0ff); for(int i=0;i<4;i++) num(50+i*24,80,pad_ax[i],1,0xffffff); text(4,90,"POLLS",1,0x80c0ff); num(40,90,pad_polls,1,0xffffff); text(90,90,"FAILS",1,0x80c0ff); num(125,90,pad_fails,1,0xffffff);
    text(4,106,"CARD SLOT",1,0x80c0ff); num(60,106,mc_slot+1,1,0xffffff); text(80,106,"LOAD",1,0x80c0ff); num(104,106,lr+1,1,0xffffff); text(120,106,"BOOT COUNT",1,0x80c0ff); num(175,106,boots,1,0xffffff);
    text(4,116,"WRITES",1,0x80c0ff); num(40,116,mc_writes,1,0xffffff); text(70,116,"ERRORS",1,0x80c0ff); num(106,116,mc_err,1,0xffffff); text(130,116,"READS",1,0x80c0ff); num(160,116,mc_reads,1,0xffffff);
    text(4,132,"CD TRACKS",1,0x80c0ff); num(55,132,cdda_last,1,0xffffff); text(80,132,"PLAYING",1,0x80c0ff); num(120,132,cdda_playing,1,0xffffff); text(135,132,"TRACK",1,0x80c0ff); num(165,132,cdda_cur,1,0xffffff);
    text(4,142,"REL SEC",1,0x80c0ff); num(45,142,cdda_rel_s,1,0xffffff); text(80,142,"RESUMES",1,0x80c0ff); num(120,142,cdda_resumes,1,0xffffff);
    text(4,158,"FRAME",1,0x80c0ff); num(40,158,fc,1,0xffffff);
    gp0(0x03000000); while(!(GP1&0x04000000)){} vsync(); GP1=0x05000000|(oy<<10); buf^=1;
  }
}
