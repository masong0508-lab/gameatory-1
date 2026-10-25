/* Flat-shaded polygon renderer for mode 4 (240x160, 8 bits per pixel, page flipped). */
#ifndef RENDER_H
#define RENDER_H
#include "fx.h"

#define FOCAL_NORMAL 136
#define FOCAL_MAX 176             /* (first person) */
#define FRX 214                   /* cull margins: sqrt(FOCAL_MAX^2 + 121^2) and sqrt(FOCAL_MAX^2 + 81^2), good for every lens (a little wide for the normal one) */
#define FRY 194
extern s32 focal;                         /* the projection scale now: FOCAL_NORMAL, or narrower in first person */
void r_set_focal(s32 f);
#define FOCAL focal               /* projection scale: screen x = 120 + FOCAL * x / z */
#define NEAR 24                   /* near clip plane, units */
#define MAXV 16

typedef struct {
    V3 pos;
    M3 m;
} Camera;

extern Camera cam;
extern u32 frame_count;           /* vblanks, counted by the IRQ handler */
extern int r_polys;               /* polygons drawn last frame */

/* palette index of material m at light 0..3 and fog 0..3 */
#define COLOR(m, l, f) ((m) * 16 + (l) * 4 + (f))

void r_init(void);
void r_begin(void);               /* start a frame: clears the polygon lists */
V3 r_cam(V3 world);               /* world point -> camera space (|d| < 40000) */
V3 r_cam_far(V3 world, int shift);/* same, with the offset scaled down by 2^shift first */
/* camera-space polygon. key: depth for sorting (-1: the average z, -2: the farthest point,
   for surfaces things stand on); bg: draw before everything else, in submission order (sky,
   ground, lots) */
void r_poly(const V3 *v, int n, int color, int key, int bg);
#ifdef MERGE
/* a convex polygon of up to 26 vertices (a planet's limb); background only, no sort key. Its corners come with their sides
   (r_ocode: bit 0 the near plane, 1 .. 4 the view's right, left, top and bottom; fl: the projection's scale), in buffers of
   NPOLYN of each that are used up in the cutting */
static inline u8 r_ocode(const V3 *p, s32 fl)
{
    s32 zx = p->z * 121, zy = p->z * 81, x = p->x * fl, y = p->y * fl;
    return ((p->z - NEAR) >> 31 & 1) | ((zx - x) >> 31 & 2) | ((zx + x) >> 31 & 4) | ((zy - y) >> 31 & 8) | ((zy + y) >> 31 & 16);
}
#define NPOLYN 32
void r_polyn(V3 *v, u8 *oc, int n, int color, int bg);
void *r_scratch(int bytes);
/* a polygon with Payback's tiles on it (type PT_*, info its TexFloor or TexWall, copied) */
void r_poly_tex(const V3 *v, int n, int color, int key, int bg, int type, const void *info);
void r_reset(void);              /* the next frame clears the buckets whole (they carry over between frames) */
int r_key(const V3 *v, int n);   /* the sort key key -1 would give */
extern const u8 *r_pmap;          /* our colours -> the palette on screen (0: the same); colours
                                     from 0x100 up are that palette's own indices */
#endif
/* screen-space polygon in 28.4 fixed point (already inside the screen) */
void r_poly2d(const s32 *xy, int n, int color, int key, int bg);
void r_sky(const u16 *colors, const s32 *bounds, int nbands, int ndraw);
void r_back(void);                /* (MERGE) the target page only, for a menu's 2D drawing */
void r_flush_bg(void);            /* draw the background list into the back buffer */
void r_flush_fg(void);            /* then everything else, far to near */
#ifdef MERGE
void r_end(void);                 /* the frame's polygons are drawn: give the pool's RAM back */
#endif
void r_flip(void);
void r_pixel(int x, int y, int color);
u8 *r_target(void);                /* the page being drawn */
int fog_of(int z);
extern int r_nofog;               /* fog_of gives 0 (in space) */

#endif
