/* Optional PS1 indexed scene surface. Geometry and HUD still belong to
 * Star-FlyBack. All GPU operations are confined to the native build. */
#ifndef SF_GPU_API_H
#define SF_GPU_API_H
#include "gba.h"
int sf_gpu_begin(u8 *back,int eligible);
void sf_gpu_end(void);
void sf_gpu_materialize_all(void);
int sf_gpu_flat(const s16 *xy,int n,int color);
int sf_gpu_fill(u8 *row,int rows,s32 xl,s32 sl,s32 xr,s32 sr,u32 color);
int sf_gpu_rectspan(u8 *dst,int width,int height,int color);
int sf_gpu_texspan(u8 *dst,int n,u32 uv,u32 duv,const u8 *tile,const u8 *lut,int step,int cross,int logsize);
int sf_gpu_wallquad(const s16 *pts,const s32 *uv,const u8 *tile,const u8 *lut);
#endif
