/* Payback's own 32 x 32 tiles on Stunt Fox's polygons (MERGE build only).

   Inside Payback the screen uses Payback's palette, so its tiles are drawn as they are: the
   ground and roofs by rows, a city cell (1024 units) to a tile, and walls by columns, a tile
   for every 1024 x 1024 units of wall. Texels are 2 x 2 pixels. The tiles are found through
   Payback's own table, so the ones it keeps in fast RAM are used from there. */
#ifndef TEX_H
#define TEX_H
#include "fx.h"

#define TEX_FAR 6500               /* ground and roofs nearer than this are textured */
#define TEX_WALL_FAR 5000          /* ... and walls */
#define TEX_IDS 0x318              /* Payback's tile ids */
#define PB_TEXTAB ((const u8 *const *)0x02002c60)   /* Payback's tile pointers, by id */

/* polygon kinds (the top bits of a polygon's vertex count) */
enum { PT_FLAT, PT_FLOOR, PT_GROUND, PT_WALL };

typedef struct {
    s32 k;                         /* the plane's height as a scale toward the camera, 16.16 */
    s32 kinv;
} TexFloor;

typedef struct {
    s32 w[3], a[3], b[3];          /* at screen (x, y): w0 + x * w1 + y * w2, and so a and b */
    const u8 *tile[4];             /* a tile for each 1024 units along the wall */
    const u8 *lut;                 /* darker colours, or 0 */
} TexWall;

extern const u8 pb_pmap[256], pb_sky[16], pb_avg[TEX_IDS];
extern u8 pb_shade[3][256];          /* (in RAM: read for every wall texel) */

void tex_frame(void);              /* per frame, after the camera is set: ground for every row */
extern int tex_on;                 /* textures this frame (Payback's palette is up, low enough) */
const u8 *tex_tile(int id);        /* Payback's tile id -> its texels, or 0 */
/* a wall's mapping from camera space: o its origin (units), along the wall and down (1.14) */
void tex_wall_setup(TexWall *t, V3 o, V3 along, V3 down);
void tex_floor(TexFloor *fl, s32 h);   /* a roof at height h (units) */

/* the rasterisers (render.c calls these) */
void tex_rows(u8 *back, int y, int rows, s32 xl, s32 sl, s32 xr, s32 sr, int type, const void *info,
              int color, int *done);
void tex_wall(u8 *back, const s16 *xy, int n, const TexWall *t, int color);

#endif
