/* Flat-shaded polygon renderer for mode 4 (240x160, 8 bits per pixel, page flipped). */
#ifndef RENDER_H
#define RENDER_H
#include "fx.h"

#define FOCAL 136                 /* projection scale: screen x = 120 + FOCAL * x / z */
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
/* screen-space polygon in 28.4 fixed point (already inside the screen) */
void r_poly2d(const s32 *xy, int n, int color, int key, int bg);
void r_sky(const u8 *colors, const s32 *bounds, int nbands, int ndraw);
void r_flush_bg(void);            /* draw the background list into the back buffer */
void r_flush_fg(void);            /* then everything else, far to near */
void r_flip(void);
void r_pixel(int x, int y, int color);
int fog_of(int z);

#endif
