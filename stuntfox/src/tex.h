/* Payback's own 32 x 32 tiles on Stunt Fox's polygons (MERGE build only).

   Inside Payback the screen uses Payback's palette, so its tiles are drawn as they are: the
   ground and roofs by rows, a city cell (1024 units) to a tile, and walls by columns, a tile
   for every 1024 x 1024 units of wall. Texels are 2 x 2 pixels. The tiles are found through
   Payback's own table, so the ones it keeps in fast RAM are used from there. */
#ifndef TEX_H
#define TEX_H
#include "fx.h"

#define TEX_FAR 6500               /* ground and roofs nearer than this are textured */
#define TEX_WALL_FAR 5000          /* ... and walls (each column on its own) */
#define TEX_TOP 12000              /* ground and roofs: no tiles from a camera higher than this */
#define TEX_IDS 0x318              /* Payback's tile ids */
#define PB_TEXTAB ((const u8 *const *)0x02002c60)   /* Payback's tile pointers, by id */
/* Payback's water is not one of its tiles: its renderer draws water cells (tile 0x311) from an
   image of its own at 0x082f6de8. Our world data names water TEX_WATER, an id no map uses,
   and merge.c points that id's entry 8 KiB into the image: 1024 bytes of it, read as a tile */
#define TEX_WATER 0x317
#define PB_WATER ((const u8 *)0x082f8de8)

/* polygon kinds (the top bits of a polygon's vertex count) */
enum { PT_FLAT, PT_FLOOR, PT_GROUND, PT_WALL };

typedef struct {
    s32 k;                         /* the plane's height as a scale toward the camera, 16.16 */
    s32 kinv;
    const u16 *tab;                /* each cell's tile id on it: world.ctex, a deck's world.dtex */
} TexFloor;

typedef struct {
    s32 w[3], a[3], b[3];          /* at screen (x, y): w0 + x * w1 + y * w2, and so a and b */
    const u8 *tile[4];             /* a tile for each 1024 units along the wall */
    const u8 *lut;                 /* darker colours, or 0 */
    s32 wlim;                      /* columns with |w| below this are past tex_wall_far: flat */
    u32 skip[4];                   /* columns (two pixels each) nearer walls hide: not drawn */
} TexWall;

extern const u8 pb_pmap[256], pb_sky[16], pb_avg[TEX_IDS];
extern const u32 pb_mesh[(TEX_IDS + 31) / 32];   /* a bit per tile: a fine mesh (a fence), drawn flat on walls */
extern u8 pb_shade[3][256];          /* (in RAM: read for every wall texel) */

void tex_frame(void);              /* per frame, after the camera is set: ground for every row */
extern s32 tex_wall_far, tex_floor_far, tex_far;   /* GAME SETTINGS' speed: tiles on walls and on distant roofs end here */
extern int tex_on;                 /* Payback's tiles and colours this frame (its palette is up) */
const u8 *tex_tile(int id);        /* Payback's tile id -> its texels, or 0 */
/* a wall's mapping from camera space: o its origin (units), along the wall and down (1.14) */
void tex_wall_setup(TexWall *t, V3 o, V3 along, V3 down);
void tex_floor(TexFloor *fl, s32 h);   /* a roof at height h (units), the cells' tops' tiles */

/* the rasterisers (render.c calls these) */
void tex_rows(u8 *back, int y, int rows, s32 xl, s32 sl, s32 xr, s32 sr, int type, const void *info,
              int color, int *done);
void tex_wall(u8 *back, const s16 *xy, int n, const TexWall *t, int color);
/* what nearer walls hide (render.c, before drawing): every wall polygon of the frame, nearest
   first, then tex_cover_done; tex_bg is set while the background is drawn */
void tex_cover_clear(void);
void tex_occlude(const s16 *xy, int n, TexWall *t);
void tex_cover_done(void);
extern u8 tex_bg;

#endif
