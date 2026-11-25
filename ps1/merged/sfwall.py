"""Generate a direct PS1 wall kernel from existing public texture math.

Only the build copy is used; no ROM data enters the generated C. Keep the
original renderer as fallback and fail the build on changed source anchors.
"""
DECL = 'HOT void tex_wall(u8 *back, const s16 *xy, int n, const TexWall *t, int color)'


def section(s, start, stop):
    i = s.index(start)
    return s[i:s.index(stop, i+len(start))]


def generate(src):
    math = section(src, '#define SHR64', 'HOT8 static u32 inv30')
    divr = section(src, '#define DIVR', "/* a wall polygon's slanted edges")
    edge = section(src, 'HOT static int wall_edges', '/* ---- walls hidden')
    split = section(src, '__attribute__((noinline)) static int wall_split', '/* a wall polygon (screen 28.4) in columns')
    wall = section(src, DECL, '\n\n#endif')
    wrapper = '\n#if defined(PS1) && defined(SFNAT_FASTWALL)\n    if (sf_fast_wall(back, xy, n, t, color)) return;\n#endif'
    wall = wall.replace(wrapper, '')
    if wall.count('tex_vrun(') != 2 or wall.count('tex_vrun4(') != 1 or not wall.rstrip().endswith('}'):
        raise ValueError('wall raster loop changed')
    wall = wall.replace(DECL, 'static void wall_draw(u8 *back, const s16 *xy, int n, const TexWall *t, int color)')
    wall = wall.replace('tex_vrun4(', 'direct_vrun4(').replace('tex_vrun(', 'direct_vrun(')
    bound = '        if (rows <= 0)\n            continue;'
    if wall.count(bound) != 1:
        raise ValueError('wall row bounds changed')
    wall = wall.replace(bound, '        if (rows <= 0 || r0<0 || r1>160)\n            continue;')
    return HEAD + math + divr + edge.replace('__attribute__((target("arm"), always_inline))', '__attribute__((always_inline))') + split + wall + TAIL


HEAD = r'''
#include "tex.h"
#include "render.h"
#define PACK(s,t) ((((u32)(s)<<11)&0xffff0000u)|(((u32)(t)>>5)&0xffff))
#define PSTEP(ds,dt) ((((u32)(ds)<<11)&0xffff0000u)+(u32)((s32)(dt)>>5))
extern const u32 rtab[2048],erecip[2561];
extern void *sf_resolve(u32,u32*);
extern void sf_fast_poll(void);
static int copy_guest(void *dest,const void*src,u32 n){
 u8*d=dest;u32 a=(u32)src;
 while(n){u32 av=0;const u8*p;
  if(a>=0x80010000u&&a<0x80200000u){p=(const u8*)a;av=0x80200000u-a;}
  else p=sf_resolve(a,&av);
  if(!p||!av)return 0;
  u32 k=av<n?av:n;
  n-=k;a+=k;
  while(k>=4 && !(((u32)d|(u32)p)&3u)){*(u32*)d=*(const u32*)p;d+=4;p+=4;k-=4;}
  while(k--)*d++=*p++;
 }
 return 1;
}
#define TEXEL(u) (((u)>>6&0x3e0)|(u)>>27)
static inline void direct_vrun(u8 *dst,int n,u32 uv,u32 duv,const u8 *tile,const u8 *lut,int row2){
 if(lut)for(;n>0;n--,dst+=480,uv+=duv){u32 v=lut[tile[TEXEL(uv)]];v|=v<<8;*(u16*)(dst+row2)=v;*(u16*)dst=v;}
 else for(;n>0;n--,dst+=480,uv+=duv){u32 v=tile[TEXEL(uv)];v|=v<<8;*(u16*)(dst+row2)=v;*(u16*)dst=v;}
}
static inline void direct_vrun4(u8 *dst,int n,u32 uv,u32 duv,const u8 *tile,const u8 *lut){
 for(;n>0;n--,dst+=960,uv+=duv){u32 v=tile[TEXEL(uv)];if(lut)v=lut[v];v|=v<<8;*(u16*)dst=v;*(u16*)(dst+240)=v;*(u16*)(dst+480)=v;*(u16*)(dst+720)=v;}
}
'''
TAIL = r'''
/* Resolve/copy everything before the first framebuffer write, so an
 * unsupported address can use the untouched original renderer. A later
 * page-cache miss cannot invalidate a tile or palette lookup table. */
int sf_fast_wall(u8 *back,const s16*xy,int n,const TexWall*t,int color){
 u32 a=(u32)back,o=a-0x06000000u;
 if(o>=0x14000u)o=a-0x80181000u;
 if((o!=0&&o!=0xa000u)||n<3||n>MAXV)return 0;
 s16 points[2*MAXV] __attribute__((aligned(4))); TexWall w;
 if(!copy_guest(points,xy,4*n)||!copy_guest(&w,t,sizeof(w)))return 0;
 for(int i=0;i<n;i++)if(points[2*i]<0||points[2*i]>3840||points[2*i+1]<0||points[2*i+1]>2560)return 0;
 u8 tiles[4][1024] __attribute__((aligned(4))),lut[256] __attribute__((aligned(4)));
 const u8 *raw[4];for(int i=0;i<4;i++)raw[i]=w.tile[i];
 for(int i=0;i<4;i++)if(raw[i]){
  int j=0;while(j<i&&raw[j]!=raw[i])j++;
  if(j<i)w.tile[i]=w.tile[j];
  else{if(!copy_guest(tiles[i],raw[i],1024))return 0;w.tile[i]=tiles[i];}
 }
 if(w.lut){if(!copy_guest(lut,w.lut,256))return 0;w.lut=lut;}
 wall_draw((u8*)(0x80181000u+o),points,n,&w,color);
 sf_fast_poll();return 1;
}
'''
