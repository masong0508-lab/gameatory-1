/* Execute the production PPU cache/blit code with synthetic pixels and a
 * minimal GPU transfer model. No guest program, ROM or emulator is involved. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint32_t u32; typedef int32_t s32;
typedef uint16_t u16; typedef int16_t s16; typedef uint8_t u8;
static u8 ew[0x40000], vram[0x18000], palette[1024], oam[1024], rom[0x100000];
static u32 ring[4096]; static u8 scratch[4096];
static u16 gpu[512][1024];
#define EW ew
#define VRAM vram
#define PAL palette
#define OAM oam
#define DL ring
#define PP_MEM ((uintptr_t)scratch)
#define GP1 0x0c000000u
#define XY(x,y) ((u32)(u16)(x) | ((u32)(u16)(y)<<16))
static u32 read_gpu(void);
#define PP_GPUREAD read_gpu()
static int command, phase, gx, gy, gw, gh, transferred;
static void gp0(u32 word){
  if(phase==1){ gx=word&0xffff; gy=word>>16; phase=2; return; }
  if(phase==2){ gw=word&0xffff; gh=word>>16; transferred=0; phase=command==0xa0?3:0; return; }
  if(phase==3){
    for(int k=0;k<2;k++){
      int x=gx+transferred%gw, y=gy+transferred/gw;
      if(x>=1024||y>=512){ fprintf(stderr,"GPU transfer outside VRAM\n"); return; }
      gpu[y][x]=(u16)(word>>(16*k)); transferred++;
    }
    if(transferred==gw*gh) phase=0;
    return;
  }
  command=word>>24;
  if(command==0xa0||command==0xc0) phase=1;
}
/* the runtime's command / parameter / FIFO-empty writes and its DMA2 data transfer, all into the same model */
#define gp0c gp0
#define gp0p gp0
#define gp0e gp0
static void gpu_dma(const void *src,u32 words){ const u32 *p=src; for(u32 i=0;i<words;i++) gp0(p[i]); }
static void gp0_2(u32 c,u32 p1,u32 p2){ gp0(c); gp0(p1); gp0(p2); }
static u32 read_gpu(void){
  u32 word=0;
  for(int k=0;k<2;k++){
    word|=(u32)gpu[gy+transferred/gw][gx+transferred%gw]<<(16*k);
    transferred++;
  }
  return word;
}
static const u8 *rom_page(u32 page){ return rom+(page&255)*4096; }
static u32 rom_read(u32 address,int size){
  u32 value=0; address&=0x000fffff;
  for(int k=0;k<size;k++) value|=(u32)rom[address+k]<<(8*k);
  return value;
}
static u32 io16(u32 offset){ (void)offset; return 0; }
static void dbg(const char*s){ (void)s; }
static void dec(u32 value){ (void)value; }
#include "ppu12.h"

static void put16(u8 *p,u16 value){ p[0]=value; p[1]=value>>8; }
static void put32(u8 *p,u32 value){ for(int k=0;k<4;k++)p[k]=value>>(8*k); }
static u8 pixel(int image,int x,int y){ return (u8)(1+(image*17+x*3+y*5)%250); }
static void make_image(int index,int width,int height,u32 offset){
  u8 *header=rom+0x100+index*8;
  put16(header,width); header[2]=height;
  put32(header+4,offset-(PP_IMG_BASE&0x01ffffff));
  for(int y=0;y<height;y++)for(int x=0;x<width;x++)rom[offset+y*width+x]=pixel(index,x,y);
}
static int verify_page(int page,int image){
  for(int y=0;y<160;y++)for(int x=0;x<240;x++)
    if(vram[page*0xa000+y*240+x]!=pixel(image,x,y)) return 0;
  return 1;
}
#define REQUIRE(test) do { if(!(test)){ fprintf(stderr,"failed line %d: %s\n",__LINE__,#test); return 1; } } while(0)
int main(void){
  put16(ew+0x1cea,240); put16(ew+0x1cec,160); put16(ew+0x1d00,240);
  make_image(0,512,255,0x20000);  /* maximal image consumes both cache pages */
  make_image(1,300,180,0x50000);  /* forces eviction of the previous image */
  make_image(2,513,160,0x70000);  /* too wide for the atlas; direct-copy fallback */
  for(int y=0;y<512;y++)for(int x=0;x<1024;x++)gpu[y][x]=0x5a5a;
  pp_blit4(0x08000100,0,0,0x10);
  REQUIRE(verify_page(0,0)); REQUIRE(pp_nup==1);
  pp_blit4(0x08000108,0,0,0);
  REQUIRE(verify_page(1,1)); REQUIRE(verify_page(0,0)); REQUIRE(pp_nreset==1);
  pp_blit4(0x08000100,0,0,0x10);
  REQUIRE(verify_page(0,0)); REQUIRE(verify_page(1,1)); REQUIRE(pp_nreset==2);
  u32 uploads=pp_nup;
  pp_blit4(0x08000110,0,0,0);
  REQUIRE(verify_page(1,2)); REQUIRE(pp_nup==uploads);
  /* Cache transfers cannot touch the world page, model texture or HUD page. */
  REQUIRE(gpu[256][448]==0x5a5a);
  REQUIRE(gpu[PS1_VRAM_MODEL_Y][PS1_VRAM_MODEL_X]==0x5a5a);
  REQUIRE(gpu[PS1_VRAM_PPU_L1_Y][PS1_VRAM_PPU_L1_X]==0x5a5a);
  puts("PPU two-page cache: eviction, preserved pages and ROM-copy fallback passed");
  return 0;
}
