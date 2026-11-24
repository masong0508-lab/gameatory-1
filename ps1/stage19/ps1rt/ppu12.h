/* ppu12.h: PS1 "PPU-lite" for the plain-Payback disc (stage 12).  EMULATOR-ONLY results.  Code only: no Payback code or data in this file.
   What it draws: the 2D layer of Payback (menus, text, HUD, phone, fades) from
     - the stage 2 draw ring (the five pruned routines record (id,r0..r3)); replayed in order once per guest frame (and at every present),
     - plus DISPCNT writes that the IO model appends to the same ring as synthetic entries (id 0x20), so a replayed blit sees the DISPCNT of its time,
     - plus the GBA PAL / OAM / VRAM shadow (OBJ tiles, guest page writes).
   Layers (GBA mode 4 + OBJ):
     L1  the page the game draws into (2 pages of 240x160 indices, the VRAM shadow itself): transparent blits (id 2) are done here by the CPU, guest
         page writes land here too.  Uploaded as an 8 bpp texture, drawn with a CLUT in which index 0 is transparent.
     L0  opaque image blits (id 4: the big backdrops) use a two-page VRAM cache (8 bpp strips), then copy the requested pixels back into the guest's page.
         Evicting a cached image cannot erase a previously drawn backdrop; a full cache can also fall back to a direct ROM copy.
     OBJ OAM sprites: the OBJ tile VRAM (4 bpp) is repacked to a 256x128 4 bpp texture, one CLUT per palette bank, one textured quad per 8x8 tile.
   Fades: id 1 (gfx_fade_flip) rewrites the BG palette like the original (ROM table, swapped channels, whiten by (P-256)>>3); id 3 (gfx_effect) is a fade
   to black: modelled as a brightness ramp (approximation, see README).  Composition order: backdrop colour, L0, L1, OBJ; in the level the sf3 3D view is
   drawn first and L1 (index 0 transparent) + OBJ over it. */
#ifndef PPU12_H
#define PPU12_H
#include "../include/ps1_vram.h"
#define PP_PAL_ROM   0x086367a8u      /* the 256 colour source palette of gfx_fade_flip (guest ROM address) */
#define PP_IMG_BASE  0x0809d694u      /* image data base of the blit routines */
#ifndef PP_MEM
#define PP_MEM       ((u32)__ppu_start)  /* linker-reserved 4 KiB, independent of renderer growth */
#endif
#define PP_CLUT      ((u16*)(PP_MEM))              /* 4 x 256 halfwords: opaque BG, transparent BG, OBJ 4 bpp banks, OBJ 8 bpp (2 KB) */
#define PP_ROW       ((u8*)(PP_MEM+0x800))         /* 512 B row buffer */
#define PP_STG       ((u32*)(PP_MEM+0x800))        /* 2 KiB staging buffer for DMA uploads (the row buffer's space; never used at the same time) */
/* stage 19 picture area: the GBA's 160 lines go to PS1 lines 8..231 of the 240-line buffer, the 224-line area every TV and DuckStation's default
   crop ("Only Overscan Area") show; lines 0..7 and 232..239 are black.  Horizontally unchanged: 240 GBA pixels over 320. */
#define PP_Y0 8
#define PP_H  224
/* floor division by a positive constant for values > -2^20 */
#define PP_FDIV(v,d) ((((v)+(d)*65536)/(d))-65536)
/* GBA line -> PS1 line of a sprite tile's top edge: 160 -> 224, rounded: round(7y/5) = floor((14y+5)/10).  The GPU samples a textured polygon
   with a half-texel bias (measured on SwanStation and Beetle with a probe disc: the page quad shows GBA line L from PS1 line 8+floor((7L+1)/5)).
   One quad per 8x8 tile cannot follow the page's 5/7 step inside the tile; the rounded edge is the best a per-tile edge can do: 14% of the
   rows one line off, either way, against 28% always one line high with floor(7y/5) and 28% always one line low with ceil(7y/5). */
#define PP_SY(y) (PP_Y0+PP_FDIV((y)*14+5,10))
#define AT_X0 PS1_VRAM_PPU_ATLAS_X     /* two cached backdrop pages; a cache miss falls back to the ROM */
#define AT_NPG PS1_VRAM_PPU_ATLAS_PAGES
#define L1_X PS1_VRAM_PPU_L1_X         /* separate from world atlas page 6 at (448,256) */
#define L1_Y PS1_VRAM_PPU_L1_Y
#define OT_X PS1_VRAM_PPU_OBJ_X
#define CLUT_Y PS1_VRAM_PPU_CLUT_Y
#define PP_NIMG 40
#ifndef PP_DBG
#define PP_DBG 0
#endif
typedef struct { u32 key; u16 w,h; u8 ns; u8 pg[2]; u16 py[2]; u16 sw[2]; } PpImg;
typedef struct { s16 x,y,w,h,cx,cy; u16 img; } PpL0;
static PpImg pp_img[PP_NIMG]; static u32 pp_nimg; static u16 pp_pgy[AT_NPG];
static PpL0 pp_l0[2][20]; static u8 pp_nl0[2];
static u32 pp_from, pp_disp, pp_lost, pp_n2, pp_n4, pp_nup, pp_nreset, pp_nfade, pp_ndisp, pp_bright=32, pp_nobj, pp_nl0max, pp_n6, pp_nfb;
static u32 pp_nrb;
static u32 pp_fade_w;                 /* last gfx_fade_flip whiten amount */
#define PPR(k) (DL[8+((k)&255)*8+(k)])
#ifdef PPSTAMP
u32 pp_tl[8];   /* TEST-ONLY (rc10 profile): RC1 lines in blit2, blit4, fade_flip, cluts, page upload+quad, obj */
#define PT0(v) u32 v=RC1_VAL
#define PTA(i,v) (pp_tl[i]+=(RC1_VAL-(v))&0xffff)
#else
#define PT0(v) do{}while(0)
#define PTA(i,v) ((void)0)
#endif
/* ---- ring helpers */
static void pp_push(u32 id,u32 a){ u32 n=DL[0]; volatile u32*e=&DL[8+(n&255)*8]; e[0]=id; e[1]=a; e[2]=0; e[3]=0; e[4]=0; DL[0]=n+1; }
static void pp_dispcnt(u32 v){ pp_push(0x20,v); }
/* ---- ROM access */
static void rom_copy(u8*dst,u32 off,u32 n){ while(n){ const u8*p=rom_page(off>>12); u32 o=off&4095,k=4096-o; if(k>n) k=n; for(u32 i=0;i<k;i++) dst[i]=p[o+i]; dst+=k; off+=k; n-=k; } }
/* ---- GPU */
#ifndef PP_GPUREAD
#define PP_GPUREAD (*(volatile u32*)0x1F801810)
#endif
/* VRAM -> CPU: one row of hw halfwords (even) at (x,y) into dst (hw/2 words) */
static void pp_vread_row(int x,int y,int hw,u32*dst){ gp0_2(0xC0000000,XY(x,y),XY(hw,1)); for(int i=0;i<hw/2;i++){ while(!(GP1&0x08000000)){} dst[i]=PP_GPUREAD; } }   /* bit 27: a word is ready */
#ifdef PP_RBDMA
/* rc10: VRAM -> CPU for nr rows of hw halfwords (even) by DMA2 (direction GP1(04h)=3, request mode to RAM, 16-word blocks), after GPUSTAT bit 27 says
   the GPU has the data ready (psx-spx "DMA2 VRAM to CPU"); the direction is set back to CPU -> GP0 (2) for every other GPU user.  The polled word
   loop above cost about 15 cycles a word: the menus re-blit their full-screen backdrop every frame and spent most of a present reading it back. */
static void pp_vread_rows(int x,int y,int hw,int nr,u32*dst){
  u32 nw=(u32)(hw/2)*(u32)nr;
  gp0_2(0xC0000000,XY(x,y),XY(hw,nr)); while(!(GP1&0x08000000)){}
  GP1=0x04000003; gpu_dma_x(dst,nw,0x01000200u);   /* rc10 review: 16-word blocks as for CPU -> VRAM (psx-spx: the DMA2 block size), not one block of nw */
  GP1=0x04000002; }
#endif
/* RAM -> VRAM: texture cache flushed, GP0(A0h) + position + size, then the nw data words by DMA2 (rt.c gpu_dma) */
static void pp_vload(int x,int y,int w,int h,const u32*src,u32 nw){ gp0c(0x01000000); gp0_2(0xA0000000,XY(x,y),XY(w,h)); gpu_dma(src,nw); }
/* textured quad: command + 8 parameters (fits the 16-word command FIFO); out of line like gp0_2, one wait per command */
static __attribute__((noinline)) void pp_q(int x0,int y0,int x1,int y1,int u0,int v0,int u1,int v1,u32 clut,u32 tp,u32 cmd){
  gp0c(cmd); gp0p(XY(x0,y0)); gp0p(u0|(v0<<8)|(clut<<16)); gp0p(XY(x1,y0)); gp0p(u1|(v0<<8)|(tp<<16)); gp0p(XY(x0,y1)); gp0p(u0|(v1<<8)); gp0p(XY(x1,y1)); gp0p(u1|(v1<<8)); }
#define PP_TP8(x,y) (((x)>>6)|(((y)>>8)<<4)|(1<<7))
#define PP_TP4(x,y) (((x)>>6)|(((y)>>8)<<4))
#define PP_CL(x,y) (((x)>>4)|((y)<<6))
/* ---- L0 atlas */
static int pp_atlas_get(u32 hdr){
  for(u32 i=0;i<pp_nimg;i++) if(pp_img[i].key==hdr) return i;
  u32 w=rom_read(hdr,2), h=rom_read(hdr+2,1), src=(rom_read(hdr+4,4)+PP_IMG_BASE)&0x01ffffff;
  if(!w||!h||w>512) return -1;
  u32 ns=(w+255)/256;
  for(int attempt=0;attempt<2;attempt++){
    int pg[2],py[2]; int ok=pp_nimg<PP_NIMG;
    u16 tmp[AT_NPG]; for(int k=0;k<AT_NPG;k++) tmp[k]=pp_pgy[k];
    for(u32 s=0;s<ns&&ok;s++){ int f=-1; for(int k=0;k<AT_NPG;k++) if(tmp[k]+h<=PS1_VRAM_PPU_ATLAS_PAGE_H){ f=k; break; } if(f<0){ ok=0; break; } pg[s]=f; py[s]=tmp[f]; tmp[f]+=h; }
    if(!ok){ if(attempt==0){ pp_nimg=0; for(int k=0;k<AT_NPG;k++) pp_pgy[k]=0; pp_nl0[0]=pp_nl0[1]=0; pp_nreset++; continue; } return -1; }
    for(int k=0;k<AT_NPG;k++) pp_pgy[k]=tmp[k];
    PpImg*I=&pp_img[pp_nimg]; I->key=hdr; I->w=w; I->h=h; I->ns=ns;
    for(u32 s=0;s<ns;s++){
      u32 sw=w-256*s; if(sw>256) sw=256; u32 swe=(sw+3)&~3u; I->pg[s]=pg[s]; I->py[s]=py[s]; I->sw[s]=sw;
      int X=AT_X0+PS1_VRAM_PPU_ATLAS_PAGE_W*pg[s], Y=PS1_VRAM_PPU_ATLAS_Y+py[s]; u32 nw=(swe/2)*h; u32 nwe=(nw+1)&~1u;
      /* one GP0(A0h) per row: the row is read from the ROM (possibly from the CD) before its transfer starts, so no GPU command is ever left half sent */
      gp0c(0x01000000);
      for(u32 r=0;r<h;r++){ rom_copy(PP_ROW,src+r*w+256*s,sw); for(u32 i=sw;i<swe;i++) PP_ROW[i]=0;
        gp0_2(0xA0000000,XY(X,Y+r),XY(swe/2,1)); gpu_dma(PP_ROW,swe/4); }
      (void)nwe;
    }
    pp_nimg++; pp_nup++; return pp_nimg-1;
  }
  return -1;
}
/* ---- blits */
static void pp_blit2(u32 img,int x,int y,u32 disp){
  int w=rom_read(img,2), h=rom_read(img+2,1); u32 src=(rom_read(img+4,4)+PP_IMG_BASE)&0x01ffffff; int ow=w;
  if(y<0){ src+=(u32)(-y)*w; h+=y; y=0; }
  if(y+h>160) h=160-y; if(h<=0) return;
  if(x<0){ src+=(u32)(-x); w+=x; x=0; }
  if(x+w>240) w=240-x; if(w<=0) return;
  u8*dst=VRAM+((disp&0x10)?0:0xa000)+y*240+x;
#ifdef PP_ROMDIRECT
  /* rc10: a row that lies in one ROM page is read straight from the page (no copy into the row buffer first) */
  for(int r=0;r<h;r++){ u32 off=src+(u32)r*ow, o=off&4095;
    if(o+(u32)w<=4096u){ const u8*q=rom_page(off>>12)+o; for(int i=0;i<w;i++){ u8 b=q[i]; if(b) dst[i]=b; } }
    else { rom_copy(PP_ROW,off,w); for(int i=0;i<w;i++){ u8 b=PP_ROW[i]; if(b) dst[i]=b; } }
    dst+=240; }
#else
  for(int r=0;r<h;r++){ rom_copy(PP_ROW,src+(u32)r*ow,w); for(int i=0;i<w;i++){ u8 b=PP_ROW[i]; if(b) dst[i]=b; } dst+=240; }
#endif
}
#ifdef PP_ROMDIRECT
static u32 pp_nromb4;   /* rc10: opaque blits copied from ROM pages already in RAM (no VRAM read-back) */
/* every ROM page of bytes [a, a+n) is in RAM now (mapped, or kept in a pool frame): reading them costs no disc access */
#ifdef MERGED
static int pp_rom_has(u32 a,u32 n){ for(u32 pg=a>>12;pg<=(a+n-1)>>12;pg++){ if(pg>=ROM_NPG) return 0; if(!rom_pg[pg]&&!pg_fr[pg]) return 0; } return 1; }
#else
static int pp_rom_has(u32 a,u32 n){ for(u32 pg=a>>12;pg<=(a+n-1)>>12;pg++){ u32 q=pg&2047; if(!rom_pg[q]&&!pg_fr[q]) return 0; } return 1; }
#endif
#endif
static void pp_blit4(u32 img,int x,int y,u32 disp){
  int limw=*(volatile s16*)(EW+0x1cea), limh=*(volatile s16*)(EW+0x1cec), stride=*(volatile s16*)(EW+0x1d00);
  int w=rom_read(img,2), h=rom_read(img+2,1); int cx=0,cy=0; int px=x,py=y;
  if(y<0){ cy=-y; h+=y; y=0; }
  if(y+h>limh) h=limh-y; if(h<=0) return;
  if(x<0){ cx=-x; w+=x; x=0; }
  if(x+w>limw) w=limw-x; if(w<=0) return;
  (void)px; (void)py;
  if(x+w>240||y+h>160) return;
  u32 p=(disp&0x10)?0:1;
  if(stride!=240){ static u32 once; if(!once){ once=1; dbg("PPU stride "); dec(stride); dbg("\n"); } }
  u8*pg=VRAM+(p?0xa000:0);
#ifdef PP_ROMDIRECT
  /* rc10: when the image's ROM pages are all in RAM the window is copied from them (the bytes the atlas was made from); a page that would have
     to come from the disc is never fetched for this: the VRAM atlas and its read-back stay the way for those */
  { u32 src=(rom_read(img+4,4)+PP_IMG_BASE)&0x01ffffff; int ow=rom_read(img,2); u32 s0=src+(u32)cy*ow+cx;
    if(pp_rom_has(s0,(u32)(h-1)*ow+w)){ u8*d=pg+y*240+x;
      for(int r=0;r<h;r++){ u32 off=s0+(u32)r*ow; int i=0;
        while(i<w){ u32 o=(off+i)&4095, k=4096-o; if(k>(u32)(w-i)) k=w-i; const u8*q=rom_page((off+i)>>12)+o; u8*dd=d+i; u32 j=0;
          if(!(((u32)q^(u32)dd)&3)){ for(;j<k&&((u32)(dd+j)&3);j++) dd[j]=q[j]; for(;j+4<=k;j+=4) *(u32*)(dd+j)=*(const u32*)(q+j); }
          for(;j<k;j++) dd[j]=q[j];
          i+=k; }
        d+=240; }
      pp_nromb4++; return; } }
#endif
  int id=pp_atlas_get(img);
  if(id<0){ /* no atlas room: copy opaque from the ROM into the page */
    u32 src=(rom_read(img+4,4)+PP_IMG_BASE)&0x01ffffff; int ow=rom_read(img,2); u8*d=pg+y*240+x;
    for(int r=0;r<h;r++){ rom_copy(PP_ROW,src+(u32)(cy+r)*ow+cx,w); for(int i=0;i<w;i++) d[i]=PP_ROW[i]; d+=240; } return; }
  /* the page (the guest's own VRAM shadow, which the guest reads back, e.g. to build the OBJ glow tiles) gets the image window exactly like the GBA blit: read it back from the atlas */
  PpImg*I=&pp_img[id];
  for(u32 s=0;s<I->ns;s++){
    int c0=256*s, c1=c0+I->sw[s]; int a=cx>c0?cx:c0, b=(cx+w)<c1?(cx+w):c1; if(b<=a) continue;
    int hw0=((a-c0)>>2)<<1, hw1=((b-c0+3)>>2)<<1; int hw=hw1-hw0; if(hw>128) hw=128;
    int X=AT_X0+PS1_VRAM_PPU_ATLAS_PAGE_W*I->pg[s]+hw0;
#ifdef PP_RBDMA
#ifdef PPSTAMP
    pp_tl[7]=(u32)w|((u32)x<<8)|((u32)hw<<16)|((u32)(a-c0)<<24);
#endif
    PT0(t_dir);
    if(2*hw==240&&b-a==240&&(a-c0)==2*hw0&&x+(a-cx)==0){   /* a full-width window (the backdrops): the rows land in the page as they are, one DMA */
      pp_vread_rows(X,PS1_VRAM_PPU_ATLAS_Y+I->py[s]+cy,hw,h,(u32*)(pg+y*240)); PTA(6,t_dir); continue; }
    { int rpb=1024/hw; if(rpb<1) rpb=1;   /* rows per read: the 2 KiB staging buffer (PP_STG, the row buffer's space) holds 1024 halfwords */
      for(int r=0;r<h;r+=rpb){ int nr=h-r<rpb?h-r:rpb;
        pp_vread_rows(X,PS1_VRAM_PPU_ATLAS_Y+I->py[s]+cy+r,hw,nr,PP_STG);
        for(int k=0;k<nr;k++){ const u8*sr=(const u8*)PP_STG+2*hw*k+((a-c0)-2*hw0); u8*d=pg+(y+r+k)*240+x+(a-cx); int n=b-a, i=0;
          if(!(((u32)sr^(u32)d)&3)){ for(;i<n&&((u32)(d+i)&3);i++) d[i]=sr[i]; for(;i+4<=n;i+=4) *(u32*)(d+i)=*(const u32*)(sr+i); }   /* same alignment: words */
          for(;i<n;i++) d[i]=sr[i]; } } } }
#else
    for(int r=0;r<h;r++){
      pp_vread_row(X,PS1_VRAM_PPU_ATLAS_Y+I->py[s]+cy+r,hw,(u32*)PP_ROW);
      const u8*sr=PP_ROW+((a-c0)-2*hw0); u8*d=pg+(y+r)*240+x+(a-cx);
      for(int i=0;i<b-a;i++) d[i]=sr[i]; } }
#endif
  pp_nrb++;
}
/* gfx_fade_flip palette: PAL[i] = whiten(swap(ROM[i]), (P-256)>>3) */
static void pp_fade_flip(u32 P){
  int r6=((int)P-256)>>3; if(r6<0) r6=0; pp_fade_w=r6;
  static u8 tab[512]; rom_copy(tab,PP_PAL_ROM&0x01ffffff,512);
  for(int i=0;i<256;i++){ u32 v=tab[2*i]|(tab[2*i+1]<<8); int a=v>>10, b=(v>>5)&31, d=v&31; a+=r6; if(a>31)a=31; b+=r6; if(b>31)b=31; d+=r6; if(d>31)d=31;
    *(volatile u16*)(PAL+2*i)=a|(b<<5)|(d<<10); }
  pp_nfade++;
}
/* ---- ring replay: once per guest frame (adv_lines at vcount 160) and at every present */
#ifndef FL_POLL
#define FL_POLL() ((void)0)
#endif
#ifndef SP_IN   /* the speed stamps come from rt.c's clk.h; no-ops where this file is compiled without it (native tests) */
#define SP_IN() ((void)0)
#define SP_OUT() ((void)0)
#define SP_T0(v) do{}while(0)
#define SP_ADD(i,v) ((void)0)
#define SP_INC(i) ((void)0)
#endif
#ifdef PP_INSF
/* rc10: the ring replay (with the blits inlined in it, about 4.5 KiB) is placed in the renderer's region (.sf, 0x80199000..0x801b0000, loaded with
   the EXE and never overwritten), so that the C runtime below 0x80028000 has room for the speed work */
#define PP_SECT __attribute__((section(".sf.text.ppu"),noinline))
#else
#define PP_SECT
#endif
static PP_SECT void ppu_flush(void){
  SP_T0(sp_t0); SP_IN();  /* SPEEDPROF (rt.c clk.h): replay time */
  u32 n=DL[0]; if(n-pp_from>256){ pp_lost+=n-pp_from-256; pp_from=n-256; }
  for(;pp_from<n;pp_from++){
    FL_POLL();
    volatile u32*e=&DL[8+(pp_from&255)*8]; u32 id=e[0];
    if(id==0x20){ pp_disp=e[1]; pp_ndisp++; }
    else if(id==2){ PT0(t_); pp_blit2(e[1],(s32)e[2],(s32)e[3],pp_disp); pp_n2++; PTA(0,t_); }
    else if(id==4){ PT0(t_); pp_blit4(e[1],(s32)e[2],(s32)e[3],pp_disp); pp_n4++; PTA(1,t_); }
    else if(id==1){ PT0(t_); pp_fade_flip(e[1]); PTA(2,t_); }
    else if(id==3){ for(int i=0;i<256;i++) *(volatile u16*)(PAL+2*i)=0; pp_nfb++; }   /* gfx_effect: 32 vblank steps scaling the BG palette to zero (the guest is not slowed down here: the BG palette is black from the call on) */
    else if(id==6){ u32 p=(pp_disp&0x10)?0:1; u32*d=(u32*)(VRAM+(p?0xa000:0)); for(u32 i=0;i<9600;i++) d[i]=0; pp_nl0[p]=0; pp_n6++; }
  }
  /* fade ramp: gfx_effect fades the screen to black over 32 steps, the next gfx_fade_flip brings it back (one step = one guest frame here) */
  if(pp_bright<32){ pp_bright+=4; if(pp_bright>32) pp_bright=32; }
  SP_ADD(SP_FLUSH,sp_t0); SP_INC(SP_NFLUSH); SP_OUT();
}
/* ---- display */
static u32 pp_col(u32 v,u32 br){ if(br>=32) return v; u32 r=(v&31)*br/32, g=((v>>5)&31)*br/32, b=((v>>10)&31)*br/32; return r|(g<<5)|(b<<10); }
#ifdef PP_DIRTY
static u32 pp_clut_br, pp_nclut, pp_nobjup;   /* rc10: brightness of the CLUTs in VRAM (0 = none yet), CLUT and OBJ uploads (counters for the rig) */
#ifdef OBJH_PROF
u32 objh_n, objh_lines, objh_blk, objh_up_n, objh_up_lines;   /* TEST-ONLY: decisions and their RC1 lines, blocks checked, presents with uploads and their lines */
#endif
#endif
#define PP_OBJ_NB 8          /* the OBJ tiles in 8 blocks of 64 tile slots = 512 words = 16 rows of either texture (one upload) */
static void pp_cluts(void){
#ifdef PP_DIRTY
  /* rc10: the 2 KiB of CLUTs are only rebuilt and uploaded when the guest palette or the brightness changed: at full brightness every entry of
     PP_CLUT is the palette entry with bit 15 set (entry 0 of the transparent tables 0), so PAL is compared with the CLUT already in VRAM */
  if(pp_bright==32&&pp_clut_br==32){ const volatile u16*pa=(const volatile u16*)PAL; int same=1;
    for(int i=0;i<256&&same;i++) if((u16)(pa[i]|0x8000)!=PP_CLUT[i]) same=0;
    for(int i=1;i<256&&same;i++) if((u16)(pa[256+i]|0x8000)!=PP_CLUT[768+i]) same=0;
    if(same) return; }
  pp_clut_br=pp_bright; pp_nclut++;
#endif
  for(int i=0;i<256;i++){ u32 v=pp_col(*(volatile u16*)(PAL+2*i),pp_bright); u32 nz=(v&0x7fff)|0x8000;
    PP_CLUT[i]=nz; PP_CLUT[256+i]=i?nz:0; }
  for(int b=0;b<16;b++) for(int k=0;k<16;k++){ u32 v=pp_col(*(volatile u16*)(PAL+0x200+2*(b*16+k)),pp_bright); PP_CLUT[512+b*16+k]=k?((v&0x7fff)|0x8000):0; }
  for(int i=0;i<256;i++){ u32 v=pp_col(*(volatile u16*)(PAL+0x200+2*i),pp_bright); PP_CLUT[768+i]=i?((v&0x7fff)|0x8000):0; }
  pp_vload(PS1_VRAM_PPU_CLUT_X,CLUT_Y,PS1_VRAM_PPU_CLUT_W,PS1_VRAM_PPU_CLUT_H,(const u32*)PP_CLUT,PS1_VRAM_PPU_CLUT_W*PS1_VRAM_PPU_CLUT_H/2);
}
static const u8 PP_SZ[3][4][2]={{{8,8},{16,16},{32,32},{64,64}},{{16,8},{32,8},{32,16},{64,32}},{{8,16},{8,32},{16,32},{32,64}}};
/* general textured quad: 4 vertex positions (x,y pairs in PS1 pixels) in Z order (top-left, top-right, bottom-left, bottom-right of the texture rectangle) */
static __attribute__((noinline)) void pp_q4(const int*vx,const int*vy,int u0,int v0,int u1,int v1,u32 clut,u32 tp,u32 cmd){
  gp0c(cmd); gp0p(XY(vx[0],vy[0])); gp0p(u0|(v0<<8)|(clut<<16)); gp0p(XY(vx[1],vy[1])); gp0p(u1|(v0<<8)|(tp<<16)); gp0p(XY(vx[2],vy[2])); gp0p(u0|(v1<<8)); gp0p(XY(vx[3],vy[3])); gp0p(u1|(v1<<8)); }
#ifdef PP_DIRTY
/* PP_OBJCK BEGIN  rc10.2: the two checks of one block of 512 OBJ tile words (see pp_obj): out[0] = A, out[1] = B, compared as 64 bits.
     Two independent per-word mixers, each a multiply followed by a right xorshift (PP_OBJCK_STEP):
       A: a = (a + w) * KA;  a ^= a >> SA        KA = 0x85ebca6b, SA = 15
       B: b = (b ^ w) * KB;  b ^= b >> SB        KB = 0x27d4eb2f, SB = 13
     Both multipliers are 3 mod 4 (so neither is 1 modulo 4, 8, 16, ...): a difference confined to the top bits of a word is changed by the
     multiply (c*K mod 2^n is not c) and the xorshift then carries it down into the low bits, where the next word's add/xor and multiply spread
     it over the whole state.  A takes the word by add, B by xor; the constants and the shifts differ, so no additive or xor relation between
     words that cancels one mixer cancels the other (the rc10.1 checks failed on exactly that: B = djb2 ignored zero-sum changes in bits 27-31,
     A's 0x9e3779b1 = 1 mod 16 kept them, and the pair step a = G(a+w0); a = G((a+w1)*k) let a top-nibble difference through).
     Every step of A and of B is a bijection of its state for a fixed word, so a change of any ONE word always changes both, and two inputs
     give the same result only if the state after the last changed word is the same (ps1/tests/objck_search.c searches on exactly that).
     Not guaranteed: 64 bits can always be cancelled by a change built from the state itself; pp_obj's refresh bounds how long any miss stays.
   The C is the definition (host builds, ps1/tests).  On the PS1 the same steps are scheduled by hand (MIPS I): each chain's next multiply
   waits for its own MFLO, so the two chains alternate on the one multiplier, the xorshift, the next input and the loads sit between them;
   a loaded word is used two or more instructions later, no MULTU within two instructions after an MFLO; the loop reads two words past the
   block (the next block, or for the last one VRAM+0x18000, PS1 RAM, unused).  ps1/tests/test_objhash.py runs this loop under Unicorn against the C. */
#ifndef PP_OBJCK_KA
#define PP_OBJCK_KA 0x85ebca6bu
#define PP_OBJCK_SA 15
#define PP_OBJCK_KB 0x27d4eb2fu
#define PP_OBJCK_SB 13
#endif
#define PP_OBJCK_A0 0x811c9dc5u
#define PP_OBJCK_B0 0x2545f491u
#define PP_OBJCK_STEP(a,b,w) do{ u32 w_=(w); (a)=((a)+w_)*PP_OBJCK_KA; (a)^=(a)>>PP_OBJCK_SA; (b)=((b)^w_)*PP_OBJCK_KB; (b)^=(b)>>PP_OBJCK_SB; }while(0)
#define PP_OBJCK_S_(x) #x
#define PP_OBJCK_S(x) PP_OBJCK_S_(x)
static __attribute__((noinline)) void pp_objck(const u32*t,u32*out){
#if defined(__mips__)
  u32 a=PP_OBJCK_A0, b=PP_OBJCK_B0, w0, w1, x; const u32*e=t+512;
  __asm__ volatile(".set push\n.set noreorder\n"
    " lw %[w0],0(%[p])\n"
    " lw %[w1],4(%[p])\n"
    "1: addu %[a],%[a],%[w0]\n"                    /* A, word 0 */
    " multu %[ka],%[a]\n"
    " xor %[b],%[b],%[w0]\n"                       /* B input, word 0 */
    " addiu %[p],%[p],8\n"
    " lw %[w0],0(%[p])\n"                          /* next word 0 (used next pass) */
    " mflo %[a]\n"
    " srl %[x],%[a]," PP_OBJCK_S(PP_OBJCK_SA) "\n"
    " xor %[a],%[a],%[x]\n"
    " multu %[kb],%[b]\n"                          /* B, word 0 */
    " addu %[a],%[a],%[w1]\n"                      /* A input, word 1 */
    " mflo %[b]\n"
    " srl %[x],%[b]," PP_OBJCK_S(PP_OBJCK_SB) "\n"
    " xor %[b],%[b],%[x]\n"
    " multu %[ka],%[a]\n"                          /* A, word 1 */
    " xor %[b],%[b],%[w1]\n"                       /* B input, word 1 */
    " lw %[w1],4(%[p])\n"                          /* next word 1 */
    " mflo %[a]\n"
    " srl %[x],%[a]," PP_OBJCK_S(PP_OBJCK_SA) "\n"
    " xor %[a],%[a],%[x]\n"
    " multu %[kb],%[b]\n"                          /* B, word 1 */
    " mflo %[b]\n"
    " srl %[x],%[b]," PP_OBJCK_S(PP_OBJCK_SB) "\n"
    " bne %[p],%[e],1b\n"
    " xor %[b],%[b],%[x]\n"
    ".set pop\n"
    : [a]"+r"(a),[b]"+r"(b),[p]"+r"(t),[w0]"=&r"(w0),[w1]"=&r"(w1),[x]"=&r"(x) : [e]"r"(e),[ka]"r"(PP_OBJCK_KA),[kb]"r"(PP_OBJCK_KB) : "hi","lo","memory");
  out[0]=a; out[1]=b;
#else
  u32 a=PP_OBJCK_A0, b=PP_OBJCK_B0;
  for(u32 i=0;i<512;i++) PP_OBJCK_STEP(a,b,t[i]);
  out[0]=a; out[1]=b;
#endif
}
/* PP_OBJCK END */
/* PP_OBJDEC BEGIN  rc10.2: which blocks of which texture to upload.  m4 / m8: the blocks the sprites of the 4 bpp / 8 bpp texture can use
   (pp_obj, from OAM); now: the line clock.  For each texture the check (A,B) of every block as last uploaded and the time of that upload.
   A used block is uploaded when it was never uploaded, when its check differs, or when its upload is PP_OBJ_RF_HARD lines (2.0 s PAL,
   1.99 s NTSC) old; besides, the one oldest used block past PP_OBJ_RF_SOFT (1.5 s) per present, so the refreshes spread over the presents
   instead of coming all at once.  So a change the checks miss stays on the screen for less than 2 s.  Blocks no sprite uses are neither
   checked nor uploaded: what they show is checked when a sprite uses them again.  up[x]: blocks of texture x to upload. */
#if !defined(RTC64)
#error "PP_DIRTY needs RTC64 (clk_now32 for the OBJ refresh)"
#endif
#ifndef PP_OBJ_RF_HARD
#define PP_OBJ_RF_HARD 31250u
#endif
#ifndef PP_OBJ_RF_SOFT
#define PP_OBJ_RF_SOFT 23437u
#endif
static u32 pp_obj_h[2][PP_OBJ_NB][2], pp_obj_tl[2][PP_OBJ_NB], pp_obj_vm[2];
static u32 pp_nobjblk, pp_nobjrf;     /* blocks uploaded, of them refreshes (unchanged blocks uploaded for their age) */
static __attribute__((noinline,minsize)) void pp_objdec(const u32*t,u32 m4,u32 m8,u32 now,u32*up){
  u32 h[PP_OBJ_NB][2], mm=m4|m8; int so=-1; u32 sk=0, sage=0;
  for(u32 k=0;k<PP_OBJ_NB;k++) if((mm>>k)&1) pp_objck(t+512*k,h[k]);
  for(int x=0;x<2;x++){ u32 m=x?m8:m4, u=0;
    for(u32 k=0;k<PP_OBJ_NB;k++) if((m>>k)&1){ u32 age=now-pp_obj_tl[x][k];
      if(!((pp_obj_vm[x]>>k)&1)||h[k][0]!=pp_obj_h[x][k][0]||h[k][1]!=pp_obj_h[x][k][1]) u|=1u<<k;
      else if(age>=PP_OBJ_RF_HARD){ u|=1u<<k; pp_nobjrf++; }
      else if(age>=PP_OBJ_RF_SOFT&&age>=sage){ so=x; sk=k; sage=age; } }
    up[x]=u; }
  if(so>=0&&!((up[so]>>sk)&1)){ up[so]|=1u<<sk; pp_nobjrf++; }
  for(int x=0;x<2;x++) for(u32 k=0;k<PP_OBJ_NB;k++) if((up[x]>>k)&1){ pp_obj_h[x][k][0]=h[k][0]; pp_obj_h[x][k][1]=h[k][1]; pp_obj_tl[x][k]=now; pp_obj_vm[x]|=1u<<k; pp_nobjblk++; }
}
/* PP_OBJDEC END */
#endif
/* PP_OBJMASK BEGIN  rc10.2: the blocks each texture's sprites use: every OAM entry pp_obj draws (the same tests: not disabled, not an OBJ
   window, a valid shape, tile >= 512, priority not behind BG2, on the screen), from its first to its last tile slot (8 bpp: the even slot
   below and the odd one above), as a mask of 64-slot blocks: m[0] 4 bpp, m[1] 8 bpp. */
static __attribute__((noinline,minsize)) void pp_objmask(const volatile u16*oam,int map1d,u32 bg2pri,u32*m){
  u32 m4=0, m8=0;
  for(int i=0;i<128;i++){ u32 a0=oam[i*4], a1=oam[i*4+1], a2=oam[i*4+2]; if(((a0>>8)&3)==2) continue; if(((a0>>10)&3)==2) continue;
    u32 sh=a0>>14; if(sh==3) continue; u32 tn=a2&1023; if(tn<512) continue; if(((a2>>10)&3)>bg2pri) continue;
    u32 b8=(a0>>13)&1, sz=a1>>14, dbl=(a0>>9)&(a0>>8)&1; int pw=PP_SZ[sh][sz][0]<<dbl, ph=PP_SZ[sh][sz][1]<<dbl;
    int y=a0&255; if(y>=160) y-=256; int x=a1&511; if(x>=256) x-=512; if(x<=-pw||y<=-ph||x>=240) continue;
    u32 tw=(u32)PP_SZ[sh][sz][0]>>3, th=(u32)PP_SZ[sh][sz][1]>>3, lo=tn-512;
    u32 hi=lo+(map1d?((tw*th-1)<<b8):((th-1)*32+((tw-1)<<b8)))+b8; if(b8) lo&=~1u; if(hi>511) hi=511;
    u32 k=((2u<<(hi>>6))-1)&~((1u<<(lo>>6))-1); if(b8) m8|=k; else m4|=k; }
  m[0]=m4; m[1]=m8;
}
/* PP_OBJMASK END */
/* rc10.2: the tiles of each texture that were all index 0 (fully transparent) when their block was last uploaded: pp_obj draws no quad for
   them (a texel 0000h draws nothing, so the picture is the same).  The title and the menus show four 64x64 double-size affine sprites
   whose 256 tiles are all index 0: their quads took about 110 lines of every present, waiting on the GPU.  4 bpp: bit = tile slot (512);
   8 bpp: bit = tile n = slot/2 (256).  Kept with the upload, so it always describes what the texture in VRAM holds. */
static u32 pp_obj_z[24];          /* bits 0..511: 4 bpp slot; 512..767: 8 bpp tile n = slot/2 */
/* PP_OBJZERO BEGIN */
static inline __attribute__((always_inline)) void pp_objzero(const u32*s,int b8,u32 k){
  const u32*p=s+k*512; u32*zw=pp_obj_z+(b8?16+k:2*k), z=0;   /* the block's tiles are bits 64k.. (4 bpp) or 512+32k.. (8 bpp): whole words */
  for(u32 j=0;j<(64u>>b8);j++){ u32 o=0; for(u32 i=0;i<(8u<<b8);i++) o|=*p++; if(!o) z|=1u<<(j&31); if((j&31)==31){ *zw++=z; z=0; } }
}
/* PP_OBJZERO END */
/* one block (16 rows) of the 4 bpp (32 tile slots per row, one word per tile row) or the 8 bpp texture (16 tiles per row, two words per
   tile row), repacked into the staging buffer, one DMA.  Word i of texture row r: tile (r/8)*(32>>b8) + (i>>b8), its row r&7, word i&b8. */
static __attribute__((noinline,minsize)) void pp_objblk(int b8,u32 k){
  const u32*s=(const u32*)(VRAM+0x14000); u32 r0=k*16; u32*q=PP_STG;
  pp_objzero(s,b8,k);
  gp0c(0x01000000); gp0_2(0xA0000000,XY(OT_X,(b8?PS1_VRAM_PPU_OBJ8_Y:PS1_VRAM_PPU_OBJ4_Y)+r0),XY(PS1_VRAM_PPU_OBJ_W,16));
  for(u32 r=r0;r<r0+16;r++){ const u32*p=s+(r>>3)*256+((r&7)<<b8); for(u32 i=0;i<32;i++) *q++=p[((i>>b8)<<(3+b8))+(i&b8)]; }
  gpu_dma(PP_STG,512);
}
/* OBJ: sprites in OAM (regular and rotation/scaling, 4 bpp and 8 bpp, 1D and 2D tile mapping, normal and semi-transparent).
   The OBJ tile memory (GBA tiles 512..1023 = VRAM+0x14000, 16 KB) is repacked into two textures: a 4 bpp one (32 tile slots per row) at (OT_X,256) and an 8 bpp one
   (16 tiles per row) at (OT_X,384); only the texture(s) the visible sprites use are uploaded.  One textured quad per 8x8 tile (rotated parallelograms for affine sprites). */
static void pp_obj(void){
  u32 d=io16(0); if(!(d&0x1000)) return;
  const volatile u16*oam=(const volatile u16*)OAM; int map1d=(d&0x40)!=0;
  u32 bg2pri=(d&0x400)?(io16(0xc)&3):4;            /* OBJ with a lower priority than BG2 hide behind it (the page is opaque) */
  u32 bldcnt=io16(0x50), blda=io16(0x52); u32 eva=blda&31, evb=(blda>>8)&31; if(eva>16) eva=16; if(evb>16) evb=16;
  u32 bm=(evb<=10)?0:1;                              /* PS1 blend: 0 = B/2+F/2, 1 = B+F  (GBA alpha with 8/8 and 16/16 are the cases the game uses) */
  (void)bldcnt;
  u32 up[2];
#ifdef PP_DIRTY
  u32 mk[2]; pp_objmask(oam,map1d,bg2pri,mk); u32 m4=mk[0], m8=mk[1];
  if(!(m4|m8)) return;
  /* rc10: the OBJ tiles are uploaded only when they changed since the last upload (the texture areas in PS1 VRAM belong to the 2D layer
     alone).  The guest writes OBJ VRAM with plain stores (its VRAM pointers are host addresses), DMA3 and the BIOS copies, so nothing marks
     the tiles dirty: a check of the tile words decides.
     rc10.1 (review of PR #26): the rc10 checks djb2 and sdbm were linear (two bit-31 flips cancelled both); rc10.1's A (pair step with
     0x9e3779b1) + B (djb2) still missed edits confined to the top nibble (a 4 bpp pixel of column 7 moved by an even number of rows: about
     1 in 744 such edits), w0+d / w1-33d pairs (1 in 3000) and a built 4-word change, and a miss stayed on the screen for good.
     rc10.2: two per-word mixers (pp_objck above) per block of 64 tile slots; only the blocks the drawn sprites use are checked (the title and
     the menus use all eight: four 64x64 double-size affine sprites over the whole tile memory), changed blocks are uploaded alone, and every
     used block is uploaded again within 2 s (pp_objdec), which bounds any miss in time.  The stronger check costs about 6 lines more than
     rc10.1's per present at stock (SwanStation: 35 against 28.5); that alone made the title present miss its vertical blank (the title
     iteration ends a few lines before one: 15.1 -> 12.9 pictures/s), so the quads of fully transparent tiles are no longer sent (pp_obj_z:
     the title's four big sprites are all index 0, 110 lines of GPU-paced quads per present), which more than pays for it.
     Tests: ps1/tests/test_objhash.py (the C and the MIPS loop under Unicorn, the decision, the masks), ps1/tests/objck_search.py (the
     miss search). */
  { u32 now=clk_now32();
#ifdef OBJH_PROF
    u32 q0_=RC1_VAL;
#endif
    pp_objdec((const u32*)(VRAM+0x14000),m4,m8,now,up);
#ifdef OBJH_PROF
    objh_lines+=(RC1_VAL-q0_)&0xffff; objh_n++; for(u32 k=0;k<PP_OBJ_NB;k++) objh_blk+=((m4|m8)>>k)&1;
#endif
    if(up[0]|up[1]) pp_nobjup++; }
#else
  /* without PP_DIRTY every block of each texture a sprite uses is uploaded on every present (as before rc10) */
  up[0]=up[1]=0;
  for(int i=0;i<128;i++){ u32 a0=oam[i*4], a2=oam[i*4+2]; if(((a0>>8)&3)==2||((a0>>10)&3)==2||(a0>>14)==3||(a2&1023)<512) continue; up[(a0>>13)&1]=0xffu; }
  if(!(up[0]|up[1])) return;
#endif
#ifdef OBJH_PROF
  u32 qu_=RC1_VAL;
#endif
  for(int x=0;x<2;x++) for(u32 k=0;k<PP_OBJ_NB;k++) if((up[x]>>k)&1) pp_objblk(x,k);
#ifdef OBJH_PROF
  if(up[0]|up[1]){ objh_up_n++; objh_up_lines+=(RC1_VAL-qu_)&0xffff; }
#endif
  int nq=0;
  for(int pri=3;pri>=0;pri--) for(int i=127;i>=0;i--){
    u32 a0=oam[i*4], a1=oam[i*4+1], a2=oam[i*4+2];
    u32 aff=(a0>>8)&1, dbl=(a0>>9)&1; if(!aff&&dbl) continue;
    if(((a2>>10)&3)!=(u32)pri) continue; if((u32)pri>bg2pri) continue;
    u32 gm=(a0>>10)&3; if(gm==2) continue;
    u32 sh=a0>>14, sz=a1>>14; if(sh>2) continue; int w=PP_SZ[sh][sz][0], h=PP_SZ[sh][sz][1];
    int bw=dbl?2*w:w, bh=dbl?2*h:h;
    int y=a0&255; if(y>=160) y-=256; int x=a1&511; if(x>=256) x-=512; if(x<=-bw||y<=-bh||x>=240) continue;
    u32 tile=a2&1023; if(tile<512) continue; int tw=w/8, th=h/8; int b8=(a0>>13)&1; const u32*zp=pp_obj_z+(b8<<4);
    u32 cl=b8?PP_CL(PS1_VRAM_PPU_CLUT_X,CLUT_Y+3):PP_CL(PS1_VRAM_PPU_CLUT_X+16*(a2>>12),CLUT_Y+2);   /* 4 bpp: 16 banks side by side: x = 16*bank */
    u32 tpb=b8?PP_TP8(OT_X,PS1_VRAM_PPU_OBJ8_Y):PP_TP4(OT_X,PS1_VRAM_PPU_OBJ4_Y); if(gm==1) tpb|=(bm<<5);
    u32 cmd=(gm==1)?0x2f000000:0x2d000000;
    int hf=aff?0:(a1>>12)&1, vf=aff?0:(a1>>13)&1;
    int pa=256,pb=0,pc=0,pd=256; s32 det=65536;
    if(aff){ u32 g=(a1>>9)&31; pa=(s16)oam[g*16+3]; pb=(s16)oam[g*16+7]; pc=(s16)oam[g*16+11]; pd=(s16)oam[g*16+15]; det=pa*pd-pb*pc; if(!det) continue; }
    for(int ty=0;ty<th;ty++) for(int tx=0;tx<tw;tx++){
      /* texture slot of this tile */
      u32 slot; if(map1d) slot=tile+(u32)(ty*tw+tx)*(b8?2:1); else slot=tile+(u32)ty*32+(u32)tx*(b8?2:1);
      slot-=512; if(slot>=512) continue;
      { u32 zn=slot>>b8; if((zp[zn>>5]>>(zn&31))&1) continue; }   /* all index 0 in the texture: nothing to draw */
      int u,v; if(b8){ u32 n=slot>>1; u=(n&15)*8; v=(n>>4)*8+(PS1_VRAM_PPU_OBJ8_Y&255); } else { u=(slot&31)*8; v=(slot>>5)*8+(PS1_VRAM_PPU_OBJ4_Y&255); }   /* the 8 bpp texture sits at y=384 = texture page y 256 + 128 */
      int ue=u+8>255?255:u+8, ve=v+8>255?255:v+8;     /* exclusive edge: a tile of 8 texels spans 8 texel units */
      if(!aff){
        int dx=x+(hf?(tw-1-tx):tx)*8, dy=y+(vf?(th-1-ty):ty)*8; if(dx<=-8||dx>=240||dy<=-8||dy>=160) continue;
        int X0=dx*4/3, X1=(dx+8)*4/3, Y0=PP_SY(dy), Y1=PP_SY(dy+8);
        int u0=hf?ue:u, u1=hf?u:ue, v0=vf?ve:v, v1=vf?v:ve;
        pp_q(X0,Y0,X1,Y1,u0,v0,u1,v1,cl,tpb,cmd);
      } else {
        /* texture corner -> screen: S = M^-1 (T - c_t), c_t = (w/2,h/2); computed in 1/16 pixel, plus half a pixel (the GBA samples at integer positions) */
        int vx[4],vy[4]; int cx16=x*16+bw*8+8, cy16=y*16+bh*8+8;
        /* the PS1 GPU rounds an interpolated texture coordinate to the NEAREST texel, the GBA truncates: each texture corner is placed half a texel
           further on (du, dv in half texels, +1), so a pixel samples floor() of the GBA coordinate.  Without it a magnified sprite's last line or
           column showed the texel beyond its edge (the pause effect's 2x sprites put texture row 16 on the picture's last line, 231). */
        for(int k=0;k<4;k++){ int du=2*(tx*8+((k&1)?8:0)-w/2)+1, dv=2*(ty*8+((k&2)?8:0)-h/2)+1;
          s32 nx=pd*du-pb*dv, ny=-pc*du+pa*dv;       /* adj(P) * (du,dv), in half texels */
          s32 sx16=(s32)((nx*2048)/det), sy16=(s32)((ny*2048)/det);   /* (256*nx/det) px = nx*4096/det in 1/16 px; half texels: 2048 */
          int Vx=cx16+sx16, Vy=cy16+sy16;
          vx[k]=PP_FDIV(Vx*4,48); vy[k]=PP_Y0+PP_FDIV(Vy*7-16,80); }   /* 1/16 px -> PS1: x 4/3; y 7/5 rounded like PP_SY (identity: PP_SY(y)) */
        pp_q4(vx,vy,u,v,ue,ve,cl,tpb,cmd);
      }
      nq++; }
  }
  pp_nobj=nq;
}
static void pp_rect(int x,int y,int w,int h,u32 rgb){ gp0_2(0x60000000|rgb,XY(x,y),XY(w,h)); }
#ifdef MERGED
/* Milestone B: GBA mode 3 (240x160, 15-bit colour, BG2), which Star-FlyBack's title card (stuntfox src/title.c sf_intro_film) uses with the BLDY
   darkening fade (BLDCNT effect 3 on BG2).  The picture goes as a 15-bit texture into the two backdrop cache pages (576..832, 256..416; the cache
   is emptied, the backdrops come back from the ROM when the menus blit them again) and is drawn over 320 x 224 like the mode-4 page, modulated by
   (16 - EVY) / 16.  GBA and PS1 colours are both BGR555; bit 15 is unused on the GBA and inert in an opaque PS1 draw. */
u32 pp_nm3;
static void pp_mode3(void){
  if(pp_nimg||pp_pgy[0]||pp_pgy[1]){ pp_nimg=0; for(int k=0;k<AT_NPG;k++) pp_pgy[k]=0; pp_nl0[0]=pp_nl0[1]=0; pp_nreset++; }
  pp_vload(AT_X0,PS1_VRAM_PPU_ATLAS_Y,240,160,(const u32*)VRAM,240*160/2);
  u32 bc=io16(0x50), m=128;
  if(((bc>>6)&3)==3&&(bc&4)){ u32 evy=io16(0x54)&31; if(evy>16) evy=16; m=(16-evy)*8; }
  else if(((bc>>6)&3)==2&&(bc&4)){ u32 evy=io16(0x54)&31; if(evy>16) evy=16; m=128+evy*8; if(m>255) m=255; }   /* (brighten: approximated by modulation) */
  if(m) pp_q(0,PP_Y0,320,PP_Y0+PP_H,0,0,240,160,0,((AT_X0)>>6)|((PS1_VRAM_PPU_ATLAS_Y>>8)<<4)|(2<<7),0x2c000000u|m|(m<<8)|(m<<16));
  pp_nm3++;
}
#endif
static void pp_draw(int oy,int level){
  u32 d=io16(0);
  /* drawing environment of this frame buffer: area 320 x PP_H at (0,oy+PP_Y0), drawing offset (0,oy), texture window off.  GP0 E3/E4: x | y<<10, E5: x | y<<11 (NOT the vertex packing) */
  gp0c(0xE1000000|(1<<7)|(1<<10)); gp0c(0xE2000000); gp0e(0xE3000000|((u32)(oy+PP_Y0)<<10)); gp0e(0xE4000000|319u|((u32)(oy+PP_Y0+PP_H-1)<<10)); gp0e(0xE5000000|((u32)oy<<11)); gp0c(0xE6000000);
  /* the lines outside the picture area: black (fills are absolute VRAM rectangles, not clipped by the drawing area) */
  gp0_2(0x02000000,XY(0,oy),XY(320,PP_Y0)); gp0_2(0x02000000,XY(0,oy+PP_Y0+PP_H),XY(320,240-PP_Y0-PP_H));
#ifdef MERGED
  if(!level&&!(d&0x80)&&(d&7)==3&&(d&0x400)){ pp_rect(0,PP_Y0,320,PP_H,0); pp_mode3(); if(d&0x1000){ pp_cluts(); pp_obj(); } return; }
#endif
  if((d&0x80)||(d&7)!=4||!(d&0x400)){ if(!level) pp_rect(0,PP_Y0,320,PP_H,0); if(!level||!(d&0x1000)) return; pp_cluts(); pp_obj(); return; }
  { PT0(t_); pp_cluts(); PTA(3,t_); }
  u32 lp=(d&0x10)?1:0;                   /* displayed page: bit 4 set shows the page at VRAM+0xa000 (the game then draws into base 0) */
  u32 base=lp?0xa000:0;
  if(!level){ u32 c=pp_col(*(volatile u16*)(PAL),pp_bright); pp_rect(0,PP_Y0,320,PP_H,((c&31)<<3)|(((c>>5)&31)<<11)|(((c>>10)&31)<<19)); }
  /* the page (backdrops from blit 4 + transparent blits + guest writes): upload as 8 bpp (120 hw per row), draw with the transparent-0 CLUT (row 497) */
  PT0(t_);
  pp_vload(L1_X,L1_Y,PS1_VRAM_PPU_L1_W,PS1_VRAM_PPU_L1_H,(const u32*)(VRAM+base),PS1_VRAM_PPU_L1_W*PS1_VRAM_PPU_L1_H/2);
  pp_q(0,PP_Y0,320,PP_Y0+PP_H,0,0,240,160,PP_CL(PS1_VRAM_PPU_CLUT_X,CLUT_Y+1),PP_TP8(L1_X,L1_Y),0x2d000000);   /* u 0..240 over 320 px, v 0..160 over 224 lines (4:3, 7:5) */
  PTA(4,t_);
  if(d&0x1000){ PT0(t2_); pp_obj(); PTA(5,t2_); }
}
#endif
