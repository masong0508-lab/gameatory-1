/* ps1.h: home-grown PS1 runtime bits for the stage2b tests (no SDK, clang mips1). */
#ifndef PS1_H
#define PS1_H
typedef unsigned char u8; typedef signed char s8; typedef unsigned short u16; typedef short s16;
typedef unsigned int u32; typedef int s32;
#define R32(a) (*(volatile u32*)(a))
#define R16(a) (*(volatile u16*)(a))
#define R8(a)  (*(volatile u8*)(a))
#define GP0 R32(0x1F801810)
#define GP1 R32(0x1F801814)          /* write: GP1 commands, read: GPUSTAT */
#define I_STAT R32(0x1F801070)
#define I_MASK R32(0x1F801074)
#define DPCR R32(0x1F8010F0)
#define DICR R32(0x1F8010F4)
#define D2_MADR R32(0x1F8010A0)
#define D2_BCR  R32(0x1F8010A4)
#define D2_CHCR R32(0x1F8010A8)
#define D6_MADR R32(0x1F8010E0)
#define D6_BCR  R32(0x1F8010E4)
#define D6_CHCR R32(0x1F8010E8)
#define T_CNT(n)  R32(0x1F801100+16*(n))
#define T_MODE(n) R32(0x1F801104+16*(n))
#define T_TGT(n)  R32(0x1F801108+16*(n))
#define JOY_DATA R8(0x1F801040)
#define JOY_STAT R16(0x1F801044)
#define JOY_MODE R16(0x1F801048)
#define JOY_CTRL R16(0x1F80104A)
#define JOY_BAUD R16(0x1F80104E)

/* ---- debug text through BIOS A(3Ch) putchar (PCSXR HLE: -psxout; real BIOS: TTY).  stage 19: the call reserves the 16-byte argument area the
   kernel may use ([SP+0..15]) and declares every caller-saved register, HI and LO destroyed. */
static void dbg(const char*p){ while(*p){ register u32 a0 __asm__("$4")=*p++; register u32 t1 __asm__("$9")=0x3c;
  __asm__ volatile("addiu $29,$29,-16\n li $8,0xA0\n jalr $8\n nop\n addiu $29,$29,16":"+r"(a0),"+r"(t1)::"$1","$2","$3","$5","$6","$7","$8","$10","$11","$12","$13","$14","$15","$24","$25","$31","hi","lo","memory"); } }
static void dhex(u32 v){ char b[10]; for(int i=0;i<8;i++){int d=(v>>(28-4*i))&15; b[i]=d<10?48+d:87+d;} b[8]=32;b[9]=0; dbg(b);}
static void ddec(s32 v){ char b[14]; int i=13; b[i]=0; b[--i]=' '; u32 u=v<0?-v:v; do{ b[--i]=48+u%10; u/=10; }while(u); if(v<0) b[--i]='-'; dbg(b+i); }

/* ---- GTE.  mtc2/mfc2/lwc2/swc2 assemble with clang mips1; ctc2/cfc2/commands need .word.
   Rules on hardware: one instruction must sit between a GTE register write and a command that uses it (2 nops here,
   as Sony's macros); a value read with mfc2/cfc2 is not usable in the next instruction (load delay: nop here). */
#define MTC2(n,v) __asm__ volatile("mtc2 %0,$" #n :: "r"((u32)(v)))
#define MFC2(n) ({u32 r_; __asm__ volatile("mfc2 %0,$" #n "\n nop" : "=r"(r_)); r_;})
#define CTC2(n,v) do{ register u32 t_ __asm__("$8")=(u32)(v); __asm__ volatile(".word 0x48C80000|(" #n "<<11)" :: "r"(t_)); }while(0)
#define CFC2(n) ({ register u32 t_ __asm__("$8"); __asm__ volatile(".word 0x48480000|(" #n "<<11)\n nop" : "=r"(t_)); t_; })
#define LWC2(n,p,off) __asm__ volatile("lwc2 $" #n "," #off "(%0)" :: "r"(p), "m"(*(const u32*)((const char*)(p)+(off))))
#define SWC2(n,p,off) __asm__ volatile("swc2 $" #n "," #off "(%1)" : "=m"(*(u32*)((char*)(p)+(off))) : "r"(p))
#define GTE_(cmd) __asm__ volatile("nop\n nop\n .word " #cmd)
#define GTE(cmd) GTE_(cmd)
#define GTE0_(cmd) __asm__ volatile(".word " #cmd)
#define GTE0(cmd) GTE0_(cmd)        /* command straight after another command: no nops needed */
#define RTPS  0x4A180001   /* 1 vertex: V0 -> SXY2,SZ3,IR0 */
#define RTPT  0x4A280030   /* 3 vertices: V0,V1,V2 -> SXY0..2, SZ1..3 */
#define NCLIP 0x4B400006   /* MAC0 = cross product of SXY0,1,2 (sign = facing) */
#define AVSZ3 0x4B58002D   /* OTZ = ZSF3*(SZ1+SZ2+SZ3)>>12 */
#define AVSZ4 0x4B68002E   /* OTZ = ZSF4*(SZ0+SZ1+SZ2+SZ3)>>12 */
#define DPCS  0x4A780010   /* RGB2 = RGBC + IR0*(FC-RGBC) */
typedef struct { s16 x,y,z,pad; } SV;
/* rotation matrix (4096 = 1.0), rows m[0..2], m[3..5], m[6..8] */
static void gte_set_rot(const s32*m){
  CTC2(0,((u32)(m[1]&0xffff)<<16)|(u32)(m[0]&0xffff)); CTC2(1,((u32)(m[3]&0xffff)<<16)|(u32)(m[2]&0xffff));
  CTC2(2,((u32)(m[5]&0xffff)<<16)|(u32)(m[4]&0xffff)); CTC2(3,((u32)(m[7]&0xffff)<<16)|(u32)(m[6]&0xffff));
  CTC2(4,(u32)(m[8]&0xffff)); }
static void gte_set_trans(s32 x,s32 y,s32 z){ CTC2(5,x); CTC2(6,y); CTC2(7,z); }
static void gte_set_screen(int cx,int cy,int h){ CTC2(24,cx<<16); CTC2(25,cy<<16); CTC2(26,h); }

/* ---- GPU */
#define XY(x,y) (((u32)(u16)(y)<<16)|((u32)(u16)(x)))
#define TPAGE(x,y,bpp,abr) (((x)>>6)|(((y)>>8)<<4)|((abr)<<5)|((bpp)<<7))   /* bpp 0=4bit 1=8bit 2=15bit */
#define CLUT(x,y) (((y)<<6)|((x)>>4))
/* stage 19 GP0 handshake (psx-spx "Ready Bits"): GPUSTAT bit 26 = ready for a COMMAND word; it stays clear while the GPU waits for parameters or
   data, so it is waited for before command words only.  gp0e: GP0(E3h..E5h) bypass the FIFO, sent only with the FIFO empty (bit 28). */
static inline __attribute__((always_inline)) void gp0c(u32 w){ while(!(GP1&0x04000000)){} GP0=w; }
static inline __attribute__((always_inline)) void gp0p(u32 w){ GP0=w; }
static inline __attribute__((always_inline)) void gp0e(u32 w){ while((GP1&0x14000000)!=0x14000000){} GP0=w; }
/* nw data words from RAM to GP0 (after GP0(A0h) and its two parameters): DMA2 blocks of 16 words, a remainder as one shorter block */
static void gpu_dma(const void*src,u32 nw){
  u32 a=(u32)src&0xFFFFFF, big=nw&~15u, r=nw&15u;
  if(big){ D2_MADR=a; D2_BCR=((big>>4)<<16)|16; D2_CHCR=0x01000201; while(D2_CHCR&0x01000000){} }
  if(r){ D2_MADR=a+big*4; D2_BCR=(1u<<16)|r; D2_CHCR=0x01000201; while(D2_CHCR&0x01000000){} } }
static void gpu_init(void){
  I_MASK=0;                                  /* we poll I_STAT; no BIOS handler may eat the flags */
  GP1=0x00000000;                            /* reset */
  GP1=0x06000000|(0x260|((0x260+320*8)<<12));/* horizontal display range */
  GP1=0x07000000|(0x10|((0x10+240)<<10));    /* vertical range (NTSC) */
  GP1=0x08000001;                            /* 320x240, NTSC, 15 bit, non-interlaced */
  GP1=0x04000002;                            /* DMA direction: CPU -> GP0 */
  DPCR|=0x08000800;                          /* enable DMA2 (GPU) and DMA6 (OT clear) */
  GP1=0x05000000;                            /* display start 0,0 */
  GP1=0x03000000;                            /* display on */
}
/* RAM -> VRAM by DMA2 (d word aligned) */
static void vram_load(int x,int y,int w,int h,const u16*d){
  gp0c(0xA0000000); gp0p(XY(x,y)); gp0p(XY(w,h)); gpu_dma(d,((u32)(w*h)+1)>>1); }
static void vsync_wait(void){ I_STAT=~1u; for(volatile int n=0;n<2000000;n++){ if(I_STAT&1) break; } }
/* set draw area and offset for the buffer at (0,oy) and clear it (direct writes, GPU must be idle) */
static void draw_target(int oy,u32 rgb){
  gp0e(0xE3000000|(oy<<10)); gp0e(0xE4000000|319|((oy+239)<<10)); gp0e(0xE5000000|(oy<<11));
  gp0c(0x02000000|rgb); gp0p(XY(0,oy)); gp0p(XY(320,240)); }

/* ---- ordering table + primitive buffer, sent with a DMA2 linked list */
#define OTN 1024
static u32 ot[OTN];
static u32 *pb;                               /* bump pointer into the primitive buffer */
static void ot_clear(void){                   /* DMA6 writes ot[OTN-1] -> ot[OTN-2] -> ... -> ot[0] = end */
  D6_MADR=(u32)&ot[OTN-1]&0xFFFFFF; D6_BCR=OTN; D6_CHCR=0x11000002; while(D6_CHCR&0x01000000){} }
static inline void addprim(int z,u32*p,int words){ p[0]=((u32)words<<24)|ot[z]; ot[z]=(u32)p&0xFFFFFF; }
static void ot_send(void){                    /* draw from ot[OTN-1] (far) down to ot[0] (near) */
  while(!(GP1&0x04000000)){} D2_MADR=(u32)&ot[OTN-1]&0xFFFFFF; D2_BCR=0; D2_CHCR=0x01000401; }
static void gpu_idle(void){ while(D2_CHCR&0x01000000){} while((GP1&0x14000000)!=0x14000000){} }   /* DMA2 done, command-ready, write FIFO empty */
/* packets: word 0 is the tag, then the GP0 words */
static inline void pF4(int z,u32 rgb,u32 a,u32 b,u32 c,u32 d){ u32*p=pb; p[1]=0x28000000|rgb; p[2]=a;p[3]=b;p[4]=c;p[5]=d; addprim(z,p,5); pb=p+6; }
static inline void pG4(int z,u32 a,u32 ca,u32 b,u32 cb,u32 c,u32 cc,u32 d,u32 cd){ u32*p=pb;
  p[1]=0x38000000|ca;p[2]=a;p[3]=cb;p[4]=b;p[5]=cc;p[6]=c;p[7]=cd;p[8]=d; addprim(z,p,8); pb=p+9; }
static inline void pG3(int z,u32 a,u32 ca,u32 b,u32 cb,u32 c,u32 cc){ u32*p=pb;
  p[1]=0x30000000|ca;p[2]=a;p[3]=cb;p[4]=b;p[5]=cc;p[6]=c; addprim(z,p,6); pb=p+7; }
/* uv words: u | v<<8 ; clut and tpage ride in the top halves of the first and second uv word */
static inline void pFT3(int z,u32 rgb,u32 a,u32 ua,u32 b,u32 ub,u32 c,u32 uc,u32 clut,u32 tp){ u32*p=pb;
  p[1]=0x24000000|rgb;p[2]=a;p[3]=ua|(clut<<16);p[4]=b;p[5]=ub|(tp<<16);p[6]=c;p[7]=uc; addprim(z,p,7); pb=p+8; }
static inline void pFT4(int z,u32 rgb,u32 a,u32 ua,u32 b,u32 ub,u32 c,u32 uc,u32 d,u32 ud,u32 clut,u32 tp){ u32*p=pb;
  p[1]=0x2C000000|rgb;p[2]=a;p[3]=ua|(clut<<16);p[4]=b;p[5]=ub|(tp<<16);p[6]=c;p[7]=uc;p[8]=d;p[9]=ud; addprim(z,p,9); pb=p+10; }
static inline void pGT4(int z,u32 a,u32 ca,u32 ua,u32 b,u32 cb,u32 ub,u32 c,u32 cc,u32 uc,u32 d,u32 cd,u32 ud,u32 clut,u32 tp){ u32*p=pb;
  p[1]=0x3C000000|ca;p[2]=a;p[3]=ua|(clut<<16);p[4]=cb;p[5]=b;p[6]=ub|(tp<<16);p[7]=cc;p[8]=c;p[9]=uc;p[10]=cd;p[11]=d;p[12]=ud; addprim(z,p,12); pb=p+13; }
static inline void pCMD(int z,u32 w){ u32*p=pb; p[1]=w; addprim(z,p,1); pb=p+2; }   /* E1 tpage, E2 texture window ... in the list */

/* ---- root counters */
#ifdef RTC64
static void timers_init(void){ T_MODE(2)=0x200; }   /* 2: sysclk/8 (free run).  1 is the runtime's 64-bit guest clock (rt.c sets hblank mode once at boot): a mode write would reset it */
#else
static void timers_init(void){ T_MODE(1)=0x100; T_MODE(2)=0x200; }   /* 1: hblank clock (free run), 2: sysclk/8 (free run) */
#endif
#define HLINES() (T_CNT(1)&0xffff)
#define TICKS8() (T_CNT(2)&0xffff)
/* show the buffer at (0,oy) at the first vblank that is at least `fields` fields after the previous flip (2 = 30 fps NTSC) */
static u32 flip_line;
static void frame_flip(int oy,int fields){
  gpu_idle();
  do vsync_wait(); while(((HLINES()-flip_line)&0xffff)<(u32)(fields*263-131));
  flip_line=HLINES(); GP1=0x05000000|(oy<<10); }

/* ---- pad on SIO0, polled.  returns buttons active-high (bit: 0 SEL 3 START 4 UP 5 RIGHT 6 DOWN 7 LEFT 8 L2 9 R2 10 L1 11 R1
   12 TRI 13 CIRCLE 14 CROSS 15 SQUARE), or 0xFFFF0000|id problem when no pad answers */
static int pad_id;
static int pad_byte(int out,int last){ int r;
  JOY_DATA=out; for(volatile int n=0;n<400;n++){ if(JOY_STAT&2) break; } r=JOY_DATA;      /* RX ready */
  if(!last) for(volatile int n=0;n<400;n++){ if(I_STAT&0x80) break; }                   /* /ACK from the pad = IRQ7 flag */
  JOY_CTRL|=0x10; I_STAT=~0x80u; return r; }
static void pad_init(void){ JOY_CTRL=0x40; JOY_BAUD=0x88; JOY_MODE=0x000D; JOY_CTRL=0; }
static u32 pad_read(int port){ int lo,hi;
  JOY_CTRL=0x1003|(port<<13); I_STAT=~0x80u; for(volatile int n=0;n<60;n++){}
  pad_byte(0x01,0); pad_id=pad_byte(0x42,0); pad_byte(0x00,0); lo=pad_byte(0x00,0); hi=pad_byte(0x00,1);
  JOY_CTRL=0;
  if((pad_id&0xf0)!=0x40 && (pad_id&0xf0)!=0x70 && (pad_id&0xf0)!=0x50) return 0xFFFF0000u|pad_id;
  return (~(lo|(hi<<8)))&0xffff; }

#ifndef SF_NOLIBC
void *memset(void*d,int c,unsigned n){ char*p=d; while(n--) *p++=c; return d; }
void *memcpy(void*d,const void*s,unsigned n){ char*p=d; const char*q=s; while(n--) *p++=*q++; return d; }
#endif
#endif
