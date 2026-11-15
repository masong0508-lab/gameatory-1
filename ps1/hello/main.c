/* Star-FlyBack PS1 hello: textured spinning cube, GTE-projected, no SDK, no BIOS calls. */
typedef unsigned int u32; typedef int s32; typedef unsigned short u16; typedef short s16;
#include "sintab.h"
#define GP0 (*(volatile u32*)0x1F801810)
#define GP1 (*(volatile u32*)0x1F801814)
#define ISTAT (*(volatile u32*)0x1F801070)
#define gte_cmd(c) __asm__ volatile(".word " #c "\n nop\n nop\n nop\n nop\n nop\n nop\n nop\n nop\n" ::: "memory")
#define CTC2(n,v) __asm__ volatile("move $8,%0\n nop\n .word 0x48C00000|(8<<16)|(" #n "<<11)\n nop\n nop" :: "r"(v):"$8")
#define MTC2(n,v) __asm__ volatile("move $8,%0\n nop\n .word 0x48800000|(8<<16)|(" #n "<<11)\n nop\n nop" :: "r"(v):"$8")
static inline u32 mfc2_12(void){u32 r;__asm__ volatile(".word 0x48000000|(8<<16)|(12<<11)\n nop\n nop\n move %0,$8":"=r"(r)::"$8");return r;}
static inline u32 mfc2_13(void){u32 r;__asm__ volatile(".word 0x48000000|(8<<16)|(13<<11)\n nop\n nop\n move %0,$8":"=r"(r)::"$8");return r;}
static inline u32 mfc2_14(void){u32 r;__asm__ volatile(".word 0x48000000|(8<<16)|(14<<11)\n nop\n nop\n move %0,$8":"=r"(r)::"$8");return r;}
static inline s32 mfc2_24(void){s32 r;__asm__ volatile(".word 0x48000000|(8<<16)|(24<<11)\n nop\n nop\n move %0,$8":"=r"(r)::"$8");return r;}
static inline s32 mfc2_7(void){s32 r;__asm__ volatile(".word 0x48000000|(8<<16)|(7<<11)\n nop\n nop\n move %0,$8":"=r"(r)::"$8");return r;}
static void gp0(u32 w){ while(!(GP1&0x04000000)){} GP0=w; }   /* wait ready for cmd */
static void vsync(void){ /* VBlank flag in I_STAT; fall back to a timeout so a missing flag never hangs */
  ISTAT=~1u; for(volatile int n=0;n<400000;n++){ if(ISTAT&1) break; } ISTAT=~1u; }
#define XY(x,y) (((u32)(y)<<16)|((x)&0xffff))
static const s16 V[8][3]={{-100,-100,-100},{100,-100,-100},{-100,100,-100},{100,100,-100},
                          {-100,-100,100},{100,-100,100},{-100,100,100},{100,100,100}};
/* faces as quads TL,TR,BL,BR; winding checked on screen */
static const unsigned char F[6][4]={{1,0,3,2},{4,5,6,7},{0,4,2,6},{5,1,7,3},{0,1,4,5},{6,7,2,3}};
static void upload_tex(void){
  gp0(0xA0000000); gp0(XY(320,0)); gp0(XY(32,32));
  for(int y=0;y<32;y+=1) for(int x=0;x<32;x+=2){
    u32 w=0;
    for(int k=0;k<2;k++){ int xx=x+k; int c=((xx>>3)+(y>>3))&1;
      int r=c?31:4, g=c?18:10, b=c?4:26;
      if(xx==0||y==0||xx==31||y==31){r=31;g=31;b=31;}
      if(xx==y||xx+y==31){r=31;g=4;b=4;}
      u16 p=(u16)(r|(g<<5)|(b<<10)|0x8000); w|=(u32)p<<(16*k);}
    gp0(w);
  }
}
static void dbg(const char*p);
static void hex(u32 v){ char b[10]; for(int i=0;i<8;i++){int d=(v>>(28-4*i))&15; b[i]=d<10?48+d:87+d;} b[8]=32;b[9]=0; dbg(b);}
static void dbg(const char*p){ while(*p){ register u32 a0 __asm__("$4")=*p++; register u32 t1 __asm__("$9")=0x3c;
  __asm__ volatile("li $8,0xA0\n jalr $8\n nop":"+r"(a0),"+r"(t1)::"$1","$2","$3","$5","$6","$7","$8","$10","$11","$12","$13","$14","$15","$24","$25","$31","memory"); } }
int main(void){
  dbg("PS1 hello: start\n");
  GP1=0x00000000; GP1=0x03000000;
  GP1=0x06000000|(0x260|((0x260+320*8)<<12));
  GP1=0x07000000|(0x10|((0x10+240)<<10));
  GP1=0x08000001;                       /* 320x240 NTSC 15bpp */
  dbg("gpu init done\n"); upload_tex(); dbg("tex uploaded\n");
  CTC2(24,(160<<16)); CTC2(25,(120<<16)); CTC2(26,320);
  CTC2(5,0); CTC2(6,0); CTC2(7,520);
  int ang=0, buf=0;
  for(;;){
    int sa=sintab[ang&1023], ca=sintab[(ang+256)&1023];
    int sb=sintab[(ang*2/3)&1023], cb=sintab[((ang*2/3)+256)&1023];
    /* R = Rx(a)*Ry(b), 4096=1.0 */
    s32 m[9]={cb, 0, sb,
              (sa*sb)>>12, ca, -((sa*cb)>>12),
              -((ca*sb)>>12), sa, (ca*cb)>>12};
    CTC2(0,((u32)(m[1]&0xffff)<<16)|(u32)(m[0]&0xffff));
    CTC2(1,((u32)(m[3]&0xffff)<<16)|(u32)(m[2]&0xffff));
    CTC2(2,((u32)(m[5]&0xffff)<<16)|(u32)(m[4]&0xffff));
    CTC2(3,((u32)(m[7]&0xffff)<<16)|(u32)(m[6]&0xffff));
    CTC2(4,(u32)(m[8]&0xffff));
    int oy=buf?240:0; 
    gp0(0xE1000000|(5)|(2<<7)|(0<<4));   /* tpage x=320 (5), 15bpp */
    gp0(0xE3000000|XY(0,oy)); gp0(0xE4000000|XY(319,oy+239)); gp0(0xE5000000|XY(0,oy));
    gp0(0x02201830); gp0(XY(0,oy)); gp0(XY(320,240));  /* clear, dark blue */
     u32 sxy[8]; 
    for(int i=0;i<8;i+=1){
      MTC2(0,((u32)(V[i][1]&0xffff)<<16)|(u32)(V[i][0]&0xffff)); MTC2(1,(s32)V[i][2]);
      gte_cmd(0x4A180001);
      sxy[i]=mfc2_14();
    }
    /* sort faces by depth (average of rotated z): recompute with AVSZ via per-vertex z not kept; use simple z from matrix */
     int order[6]={0,1,2,3,4,5}; s32 zf[6];
    for(int f=0;f<6;f++){ s32 z=0; for(int k=0;k<4;k++){ int i=F[f][k]; z+=(m[6]*V[i][0]+m[7]*V[i][1]+m[8]*V[i][2])>>12; } zf[f]=z; }
    for(int i=0;i<6;i++)for(int j=i+1;j<6;j++) if(zf[order[j]]>zf[order[i]]){int t=order[i];order[i]=order[j];order[j]=t;}
    for(int n=0;n<6;n++){ int f=order[n];
      u32 a=sxy[F[f][0]],b=sxy[F[f][1]],c=sxy[F[f][2]],d=sxy[F[f][3]];
      /* back-face cull with GTE NCLIP */
      MTC2(12,a); MTC2(13,b); MTC2(14,c); gte_cmd(0x4A400006);
      s32 nc=mfc2_24();
      if(nc<=0) continue;
      gp0(0x2D808080); gp0(a); gp0(0x0000); gp0(b); gp0(((5|(2<<7))<<16)|31);
      gp0(c); gp0(31<<8); gp0(d); gp0((31<<8)|31);
    }
     while(!(GP1&0x04000000)){}
    vsync();
    GP1=0x05000000|(oy<<10);
    buf^=1; ang+=6; if(ang==6*3) dbg("frame 3\n");
  }
}
