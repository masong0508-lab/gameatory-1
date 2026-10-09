/* Flat 2D drawing over the finished 3D picture (MERGE build): text in Stunt Fox's own font,
   boxes, lines and see-through panels, straight into the page being drawn. Colours are ours
   (COLOR(...)) or Payback's own palette indices from 0x100 up, as for r_poly. */
#ifndef DRAW2D_H
#define DRAW2D_H
#include "gba.h"

#define TEXT_W 6                   /* pixels per letter */
void d_text(int x, int y, const char *s, int color);
void d_rect(int x, int y, int w, int h, int color);
void d_panel(int x, int y, int w, int h);          /* darkens what is there */
void d_hline(int x0, int x1, int y, int color);
void d_vline(int x, int y0, int y1, int color);
void d_pixel(int x, int y, int color);
/* decimal (and m:ss) into buf; return the end */
char *d_num(char *buf, int v);
char *d_time(char *buf, int seconds);
char *d_cat(char *buf, const char *s);

#endif
