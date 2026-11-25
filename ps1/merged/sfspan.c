/* Bounded exact mode-4 software raster spans. Linked WITHOUT guest
 * IR rewriting: validated addresses refer directly to host RAM.
 * Return zero before any write when the generic sfport fallback is needed. */
typedef unsigned int u32; typedef int s32; typedef unsigned char u8;
typedef unsigned short half __attribute__((may_alias));
typedef u32 word __attribute__((may_alias));
extern void *sf_resolve(u32,u32*);
extern void sf_fast_poll(void);
static u8 *screen(void *p,u32 len){
  u32 a=(u32)p,o;
  if(a-0x06000000u<0x14000u)o=a-0x06000000u;
  else if(a-0x80181000u<0x14000u)o=a-0x80181000u;
  else return 0;
  u32 k=o>=0xa000u?o-0xa000u:o;
  if(k>=38400u||len>38400u-k)return 0;
  return (u8*)(0x80181000u+o);
}
static const u8 *tilemap(const u8 *p,u32 n){
  u32 a=(u32)p;
  if(a>=0x80010000u&&a<0x80200000u&&n<=0x80200000u-a)return p;
  u32 av=0;const u8 *d=sf_resolve(a,&av);return av>=n?d:0;
}
int sf_fast_fill_trap(u8 *row,int rows,s32 xl,s32 sl,s32 xr,s32 sr,u32 color4){
  if(rows<=0)return 1;
  u8 *d=rows<=160?screen(row,(u32)rows*240u):0;
  if(!d)return 0;
  u32 l=(u32)xl,r=(u32)xr;
  for(int i=0;i<rows;i++,l+=(u32)sl,r+=(u32)sr){
    s32 a=(s32)(l+0x7fffu)>>16,e=(s32)(r+0x7fffu)>>16;
    if(a<0||a>240||e<0||e>240)return 0;
  }
  u32 c=(u8)color4;c|=c<<8;c|=c<<16;l=(u32)xl;r=(u32)xr;
  for(int i=0;i<rows;i++,d+=240,l+=(u32)sl,r+=(u32)sr){
    s32 a=(s32)(l+0x7fffu)>>16,e=(s32)(r+0x7fffu)>>16;
    u8 *p=d+a;int n=e-a;
    while(n>0&&((u32)p&3u)){*p++=(u8)c;n--;}
    while(n>=4){*(word*)p=c;p+=4;n-=4;}
    while(n>0){*p++=(u8)c;n--;}
  }
  sf_fast_poll();return 1;
}
/* The tile resolve can evict a ROM-backed LUT. Accept stable RAM LUTs
 * only, and resolve the tile last. No fetch while holding that tile. */
static const u8 *lutmap(const u8 *p){
  u32 a=(u32)p,b=a>>24;
  if(b==2||b==3||b==5||b==6||b==7)return tilemap(p,256);
  if(a>=0x80180000u&&a<=0x801f8000u-256)return p;
  return 0;
}
#define TEXEL(u) (((u)>>6&0x3e0)|(u)>>27)
static u8 *span(u8 *d,int n,u32 stride,u32 width,int tail){
  if(n<=0||n>160||tail<0||tail>720||((u32)d&(width-1u))||((u32)tail&(width-1u)))return 0;
  return screen(d,((u32)n-1u)*stride+width+(u32)tail);
}
int sf_fast_tex_hrun(u8 *dst,int n,u32 uv,u32 duv,const u8 *tile,int row2){
  if(n<=0)return 1;u8 *d=span(dst,n,2,2,row2);const u8*t=d?tilemap(tile,1024):0;
  if(!t)return 0;
  for(;n>0;n--,d+=2,uv+=duv){u32 v=t[TEXEL(uv)];v|=v<<8;*(half*)(d+row2)=v;*(half*)d=v;}
  sf_fast_poll();return 1;
}
int sf_fast_tex_hrun4(u32 *dst,int n,u32 uv,u32 duv,const u8 *tile,int row2){
  if(n<=0)return 1;u8*d=span((u8*)dst,n,4,4,row2);const u8*t=d?tilemap(tile,1024):0;
  if(!t)return 0;
  for(;n>0;n--,d+=4,uv+=duv){u32 v=t[TEXEL(uv)];v|=v<<8;v|=v<<16;*(word*)(d+row2)=v;*(word*)d=v;}
  sf_fast_poll();return 1;
}
int sf_fast_tex_mrun1(u8*dst,int n,u32 uv,u32 duv,const u8*mip,int row2){
  if(n<=0)return 1;u8*d=span(dst,n,2,2,row2);const u8*t=d?tilemap(mip,256):0;
  if(!t)return 0;
  for(;n>0;n--,d+=2,uv+=duv){u32 v=t[(uv>>8&0xf0)|uv>>28];v|=v<<8;*(half*)(d+row2)=v;*(half*)d=v;}
  sf_fast_poll();return 1;
}
int sf_fast_tex_mrun(u8*dst,int n,u32 uv,u32 duv,const u8*mip,int row2,u32 lv){
  if(n<=0)return 1;u32 size=lv==0x1b0603e0u?1024:lv==0x1c0800f0u?256:lv==0x1d0a0038u?64:lv==0x1e0c000cu?16:0;
  u8*d=size?span(dst,n,2,2,row2):0;const u8*t=d?tilemap(mip,size):0;
  if(!t)return 0;
  u32 mask=lv&255,cs=lv>>24,rs=lv>>16&255;
  for(;n>0;n--,d+=2,uv+=duv){u32 v=t[((uv>>rs)&mask)|uv>>cs];v|=v<<8;*(half*)(d+row2)=v;*(half*)d=v;}
  sf_fast_poll();return 1;
}
int sf_fast_tex_vrun(u8*dst,int n,u32 uv,u32 duv,const u8*tile,const u8*lut,int row2){
  if(n<=0)return 1;u8*d=span(dst,n,480,2,row2);const u8*l=lut&&d?lutmap(lut):0;const u8*t=d&&(!lut||l)?tilemap(tile,1024):0;
  if(!t)return 0;
  for(;n>0;n--,d+=480,uv+=duv){u32 v=t[TEXEL(uv)];if(l)v=l[v];v|=v<<8;*(half*)(d+row2)=v;*(half*)d=v;}
  sf_fast_poll();return 1;
}
int sf_fast_tex_vrun4(u8*dst,int n,u32 uv,u32 duv,const u8*tile,const u8*lut){
  if(n<=0)return 1;u8*d=span(dst,n,960,2,720);const u8*l=lut&&d?lutmap(lut):0;const u8*t=d&&(!lut||l)?tilemap(tile,1024):0;
  if(!t)return 0;
  for(;n>0;n--,d+=960,uv+=duv){u32 v=t[TEXEL(uv)];if(l)v=l[v];v|=v<<8;*(half*)(d+240)=v;*(half*)(d+480)=v;*(half*)(d+720)=v;*(half*)d=v;}
  sf_fast_poll();return 1;
}
