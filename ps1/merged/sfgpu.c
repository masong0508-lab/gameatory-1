/* Native PS1 indexed GPU raster experiment. The scene surface contains
 * 0x0100|palette_index in each VRAM halfword. The actual CLUT is applied
 * at presentation, including palette changes and fade. Two surfaces
 * correspond to the two guest mode-4 pages. Normal rendering never reads
 * the scene back; pause/unsupported raster operations materialize it.
 * Geometry is the existing game geometry, with integer GPU subpixel
 * rounding and affine interpolation within the existing subdivided spans.
 */
#include "sfgpu_api.h"
#define REG(a) (*(volatile u32*)(a))
#define GP0 REG(0x1f801810u)
#define GP1 REG(0x1f801814u)
#define D2_MADR REG(0x1f8010a0u)
#define D2_BCR REG(0x1f8010a4u)
#define D2_CHCR REG(0x1f8010a8u)
#define XY(x,y) (((u32)(x)&65535u)|((u32)(y)<<16))
#define SX 320
#define TX 576
#define CX 704
#define CY 160
#define L1X 832
#define L1Y 256
#define NODES 252
extern void *sf_resolve(u32,u32*);
extern void sf_fast_poll(void);
static u32 packet[NODES+1] __attribute__((aligned(16)));
static unsigned count, active, valid[2], gpu_page, env_dirty=1, epoch, hand;
static int last_tile=-1;
static u32 tile_addr[64]; static u16 tile_epoch[64];static u8 tile_log[64];
static u32 lut_addr[3];static u16 lut_epoch[3];static unsigned lut_hand,identity_ready,win=~0u;
volatile u32 sf_gpu_wait_state;
u32 sf_gpu_frames,sf_gpu_fallbacks,sf_gpu_materializes,sf_gpu_flat_count,sf_gpu_span_count,sf_gpu_texture_uploads,sf_gpu_texture_hits,sf_gpu_present_count,sf_gpu_bad_index,sf_gpu_wall_groups;
static inline void idle(void){sf_gpu_wait_state=1;while(D2_CHCR&0x01000000u){}sf_gpu_wait_state=2;while((GP1&0x14000000u)!=0x14000000u){}sf_gpu_wait_state=0;}
static inline void cmd(u32 v){sf_gpu_wait_state=3;while(!(GP1&0x04000000u)){} GP0=v;sf_gpu_wait_state=0;}
/* Submit complete commands, respecting FIFO boundaries. In particular
 * wait for the empty FIFO before drawing-area/texture-window changes. */
static void flush(void){if(!count)return;idle();unsigned i=1;
 while(i<=count){u32 w=packet[i];unsigned op=w>>24,n=1;
  if(op==0x02||op==0x60)n=3;else if(op==0x20)n=4;else if(op==0x28)n=5;else if(op==0x2d)n=9;
  if(op==0xe2)idle();cmd(w);for(unsigned k=1;k<n;k++)GP0=packet[i+k];i+=n;
 }count=0;
}
static u32 *reserve(unsigned n){if(count+n>NODES)flush();u32*p=packet+1+count;count+=n;return p;}
static void setenv(int x,int y,int w,int h){flush();idle();cmd(0xe1000400u);cmd(0xe2000000u);idle();GP0=0xe3000000u|x|((u32)y<<10);idle();GP0=0xe4000000u|(x+w-1)|((u32)(y+h-1)<<10);idle();GP0=0xe5000000u|x|((u32)y<<11);cmd(0xe6000000u);win=~0u;}
static void environment(void){if(env_dirty){setenv(SX,gpu_page*256,240,160);env_dirty=0;}}
static void dma(const void*p,u32 n,u32 mode){u32 a=(u32)p&0x1fffffu,big=n&~15u,rem=n&15u;if(big){D2_MADR=a;D2_BCR=(big/16u<<16)|16u;D2_CHCR=mode;sf_gpu_wait_state=4;while(D2_CHCR&0x01000000u){}sf_gpu_wait_state=0;}if(rem){D2_MADR=a+big*4;D2_BCR=(1u<<16)|rem;D2_CHCR=mode;sf_gpu_wait_state=4;while(D2_CHCR&0x01000000u){}sf_gpu_wait_state=0;}}
static void upload(const void*p,int x,int y,int w,int h){flush();idle();cmd(0x01000000u);cmd(0xa0000000u);GP0=XY(x,y);GP0=XY(w,h);dma(p,(u32)w*h/2,0x01000201u);}
static u32 rgb(unsigned i){u32 v=0x100u|(i&255u);return ((v&31)<<3)|((v&0x3e0)<<6)|((v&0x7c00)<<9);}
static u8 *pageptr(unsigned p){return (u8*)(0x80181000u+p*0xa000u);}
static int pageoff(const void*d){u32 a=(u32)d,o=a-0x06000000u;if(o>=0x14000u)o=a-0x80181000u;if(o>=0x14000u)return -1;if(o>=0xa000u)o-=0xa000u;if(o>=38400u)return -1;return (int)o;}
static int pageof(const void*d){u32 a=(u32)d,o=a-0x06000000u;if(o>=0x14000u)o=a-0x80181000u;return o>=0x14000u?-1:o>=0xa000u;}
static int copyin(void*dest,const void*src,unsigned n){u8*d=dest;u32 a=(u32)src;while(n){u32 avail=0;const u8*p;if(a>=0x80010000u&&a<0x80200000u){p=(const u8*)a;avail=0x80200000u-a;}else p=sf_resolve(a,&avail);if(!p||!avail)return 0;u32 k=n<avail?n:avail;n-=k;a+=k;while(k>=4&&!(((u32)p|(u32)d)&3u)){*(u32*)d=*(const u32*)p;d+=4;p+=4;k-=4;}while(k--)*d++=*p++;}return 1;}
static void materialize(unsigned pg,int merge){
 /* Rows are read in small blocks, so no extra full RAM framebuffer. */
 flush();idle();env_dirty=1;u16 tmp[240*2] __attribute__((aligned(4)));u8*d=pageptr(pg);
 for(int y=0;y<160;y+=2){cmd(0xc0000000u);GP0=XY(SX,y+pg*256);GP0=XY(240,2);while(!(GP1&0x08000000u)){}GP1=0x04000003u;dma(tmp,240,0x01000200u);GP1=0x04000002u;
  for(int i=0;i<480;i++){u32 v=tmp[i];if((v&0x7f00u)!=0x100u)sf_gpu_bad_index++;if(!merge||!d[i])d[i]=(u8)v;}d+=480;
 }
 valid[pg]=0;sf_gpu_materializes++;
}
void sf_gpu_materialize_all(void){if(active){materialize(gpu_page,0);active=0;sf_gpu_fallbacks++;}for(int i=0;i<2;i++)if(valid[i])materialize(i,1);}
static int fail(void){if(active){materialize(gpu_page,0);active=0;sf_gpu_fallbacks++;}return 0;}
int sf_gpu_begin(u8*back,int eligible){if(active)fail();int p=pageof(back);if(!eligible||p<0||pageoff(back)!=0){sf_gpu_materialize_all();return 0;}
 gpu_page=p;valid[p]=0;active=1;epoch++;if(!(epoch&65535u)){for(int i=0;i<64;i++)tile_epoch[i]=0;for(int i=0;i<3;i++)lut_epoch[i]=0;epoch++;}env_dirty=1;environment();
 /* fill uses absolute VRAM coordinates, exact 240-pixel aligned width */
 u32 *q=reserve(3);q[0]=0x02000000u|rgb(0);q[1]=XY(SX,p*256);q[2]=XY(240,160);
 if(!identity_ready){u16 values[256] __attribute__((aligned(4)));for(int i=0;i<256;i++)values[i]=0x100u|i;upload(values,SX,CY,256,1);identity_ready=1;}
 return 1;
}
void sf_gpu_end(void){if(!active)return;flush();idle();u32*d=(u32*)pageptr(gpu_page);for(int i=0;i<9600;i++)d[i]=0;valid[gpu_page]=1;active=0;sf_gpu_frames++;}
static void rect(int x,int y,int w,int h,int color){if(w<=0||h<=0)return;environment();u32*p=reserve(3);p[0]=0x60000000u|rgb(color);p[1]=XY(x,y);p[2]=XY(w,h);}
int sf_gpu_rectspan(u8*dst,int width,int height,int color){if(!active)return 0;int off=pageoff(dst);if(pageof(dst)!=(int)gpu_page||off<0||width<0||height<0)return fail();int x=off%240,y=off/240;if(x+width>240||y+height>160)return fail();rect(x,y,width,height,color);return 1;}
int sf_gpu_flat(const s16*xy,int n,int color){if(!active)return 0;if(n<3||n>32)return fail();s16 pts[64];if(!copyin(pts,xy,4*n))return fail();xy=pts;u32 v[32];for(int i=0;i<n;i++){int x=xy[2*i],y=xy[2*i+1];if(x<0||x>3840||y<0||y>2560)return fail();v[i]=XY((x+7)>>4,(y+7)>>4);}environment();u32 c=rgb(color);if(n==4){u32*p=reserve(5);p[0]=0x28000000u|c;p[1]=v[0];p[2]=v[1];p[3]=v[3];p[4]=v[2];}else for(int i=1;i+1<n;i++){u32*p=reserve(4);p[0]=0x20000000u|c;p[1]=v[0];p[2]=v[i];p[3]=v[i+1];}sf_gpu_flat_count++;return 1;}
int sf_gpu_fill(u8*row,int rows,s32 xl,s32 sl,s32 xr,s32 sr,u32 color){if(!active)return 0;if(rows<=0)return 1;int off=pageoff(row);if(pageof(row)!=(int)gpu_page||off<0||off%240||rows>160||off/240+rows>160)return fail();int y=off/240;/* Validate before any drawing. */
 for(int i=0;i<rows;i++){int l=(s32)((u32)xl+(u32)i*sl+0x7fffu)>>16,r=(s32)((u32)xr+(u32)i*sr+0x7fffu)>>16;if(l<0||l>240||r<0||r>240)return fail();}
 /* GPU trapezoid when noncrossing. Existing exact span edges for unusual shapes. */
 int l0=(xl+0x7fff)>>16,r0=(xr+0x7fff)>>16,l1=(s32)((u32)xl+(u32)rows*sl+0x7fffu)>>16,r1=(s32)((u32)xr+(u32)rows*sr+0x7fffu)>>16;
 if(l0<=r0&&l1<=r1&&l1>=0&&r1<=240){environment();u32*p=reserve(5);p[0]=0x28000000u|rgb(color);p[1]=XY(l0,y);p[2]=XY(r0,y);p[3]=XY(l1,y+rows);p[4]=XY(r1,y+rows);}
 else for(int i=0;i<rows;i++,xl+=sl,xr+=sr){int l=(xl+0x7fff)>>16,r=(xr+0x7fff)>>16;rect(l,y+i,r-l,1,color);}return 1;
}
static int texture(const u8*src,int log){u32 ad=(u32)src;int persistent=(ad>=0x08000000u&&ad<=0x08fffc00u);int cacheable=persistent||(ad>=0x02000000u&&ad<0x08000000u)||(ad>=0x80180000u&&ad<0x801f8000u);
 if(cacheable&&last_tile>=0&&tile_addr[last_tile]==ad&&tile_log[last_tile]==log&&(persistent||tile_epoch[last_tile]==(u16)epoch)){sf_gpu_texture_hits++;return last_tile;}
 if(cacheable)for(int k=0;k<64;k++)if(tile_addr[k]==ad&&tile_log[k]==log&&(persistent||tile_epoch[k]==(u16)epoch)){sf_gpu_texture_hits++;last_tile=k;return k;}
 u8 data[1024] __attribute__((aligned(4))),small[256] __attribute__((aligned(4)));int size=1<<log;if(log==5){if(!copyin(data,src,1024))return -1;}else{if(!copyin(small,src,size*size))return -1;for(int y=0;y<32;y++)for(int x=0;x<32;x++)data[y*32+x]=small[(y&(size-1))*size+(x&(size-1))];}
 int k=hand++&63;upload(data,TX+(k&7)*16,(k>>3)*32,16,32);tile_addr[k]=cacheable?ad:0;tile_epoch[k]=(u16)epoch;tile_log[k]=log;sf_gpu_texture_uploads++;last_tile=k;return k;
}
static int palette(const u8*lut){if(!lut)return 0;u32 ad=(u32)lut;for(int i=0;i<3;i++)if(lut_addr[i]==ad&&lut_epoch[i]==(u16)epoch)return i+1;u8 bytes[256];u16 values[256] __attribute__((aligned(4)));if(!copyin(bytes,lut,256))return -1;for(int i=0;i<256;i++)values[i]=0x100u|bytes[i];int k=lut_hand++%3;upload(values,SX,CY+1+k,256,1);lut_addr[k]=ad;lut_epoch[k]=(u16)epoch;return k+1;}
static void window(int slot){u32 w=28u|(28u<<5)|((u32)((slot&7)*4)<<10)|((u32)((slot>>3)*4)<<15);if(win!=w){*reserve(1)=0xe2000000u|w;win=w;}}
static void tquad(int x,int y,int w,int h,int u0,int v0,int u1,int v1,int vertical,int cl){u32 a=(u32)(u0&255)|((u32)(v0&255)<<8),b=(u32)(u1&255)|((u32)(v1&255)<<8);u32*p=reserve(9);p[0]=0x2d000000u;p[1]=XY(x,y);p[2]=a|((u32)((SX>>4)|((CY+cl)<<6))<<16);p[3]=XY(x+w,y);p[4]=(vertical?a:b)|((u32)((TX>>6)|128u)<<16);p[5]=XY(x,y+h);p[6]=vertical?b:a;p[7]=XY(x+w,y+h);p[8]=b;}
/* Coalesce adjacent wall columns into one quad only when the CPU
 * has checked coverage, tile identity and perspective interpolation. */
int sf_gpu_wallquad(const s16 *pts,const s32 *uv,const u8 *tile,const u8 *lut){
 if(!active)return 0;
 int slot=texture(tile,5),cl=palette(lut);if(slot<0||cl<0)return 0;
 environment();window(slot);u32*p=reserve(9);p[0]=0x2d000000u;
 int u0=(uv[0]>>16),v0=(uv[1]>>16);
 for(int i=0;i<4;i++){int u=96+(u0&31)+((uv[2*i]>>16)-u0),v=96+(v0&31)+((uv[2*i+1]>>16)-v0);
  p[1+2*i]=XY(pts[2*i],pts[2*i+1]);p[2+2*i]=(u&255)|((v&255)<<8);
 }
 p[2]|=((u32)((SX>>4)|((CY+cl)<<6))<<16);p[4]|=((u32)((TX>>6)|128u)<<16);sf_gpu_wall_groups++;return 1;
}
/* GPU span uses the same packed UV and original mip level; split at safe
 * interpolator ranges. GPU integer UV quantization can differ by a texel
 * from the software pixel-pair sampling. Small runs use exact texels. */
int sf_gpu_texspan(u8*dst,int n,u32 uv,u32 duv,const u8*tile,const u8*lut,int step,int cross,int log){if(!active)return 0;if(n<=0)return 1;int off=pageoff(dst),vert=step>=240,unit=vert?step/240:step,x=off%240,y=off/240;if(off<0||pageof(dst)!=(int)gpu_page||log<2||log>5||unit<1||unit>4||cross<1||cross>4||n>160||x+(vert?cross:n*unit)>240||y+(vert?n*unit:cross)>160)return fail();
 int slot=texture(tile,log),cl=palette(lut);if(slot<0||cl<0)return fail();environment();window(slot);
 int frac=16-log,mask=(1<<log)-1;int du=(s16)(duv>>16),dv=(s16)duv;
 while(n){int k=n>16?16:n;while(k>1&&(((du<0?-du:du)*k>>frac)>64||((dv<0?-dv:dv)*k>>frac)>64))k>>=1;int u0=96+((uv>>16>>frac)&mask),v0=96+((uv&65535u)>>frac);
  int u1=u0+(((int)((uv>>16)&((1u<<frac)-1))+du*k)>>frac),v1=v0+(((int)(uv&((1u<<frac)-1))+dv*k)>>frac);
  if(k==1){u1=u0;v1=v0;}
  tquad(x,y,vert?cross:k*unit,vert?k*unit:cross,u0,v0,u1,v1,vert,cl);
  if(vert)y+=k*unit;else x+=k*unit;uv+=duv*k;n-=k;
 }
 sf_gpu_span_count++;return 1;
}
/* Apply the real opaque palette to one index per pixel via three
 * 2:1 quads, then scale the resulting 16bpp image to the display.
 * The middle eight-pixel strip avoids the 8-bit U=256 wrap. */
static void decode_quad(int x0,int x1,int u0,int u1,int tp){u32*p=reserve(9);p[0]=0x2d000000u;p[1]=XY(x0,0);p[2]=u0|((496u<<6)<<16);p[3]=XY(x1,0);p[4]=u1|((u32)tp<<16);p[5]=XY(x0,160);p[6]=u0|(160u<<8);p[7]=XY(x1,160);p[8]=u1|(160u<<8);}
void sf_gpu_before_ppu(void){flush();env_dirty=1;}
int sf_gpu_present(int pg,int oy){flush();env_dirty=1;if(pg<0||pg>1||!valid[pg])return 0;setenv(CX,0,240,160);cmd(0x01000000u);int py=pg?16:0;decode_quad(0,120,0,240,5|128|py);decode_quad(120,128,112,128,6|128|py);decode_quad(128,240,0,224,7|128|py);flush();setenv(0,oy+8,320,224);cmd(0x01000000u);
 /* setenv uses y offset 8 here, so write local y 0..224. */
 u32*p=reserve(9);p[0]=0x2d000000u;p[1]=0;p[2]=0;p[3]=XY(320,0);p[4]=240u|((11u|256u)<<16);p[5]=XY(0,224);p[6]=160u<<8;p[7]=XY(320,224);p[8]=240u|(160u<<8);flush();idle();
 /* Restore exactly the PPU's expected draw area and y offset. */
 setenv(0,oy+8,320,224);GP0=0xe5000000u|((u32)oy<<11);env_dirty=1;sf_gpu_present_count++;return 1;
}
