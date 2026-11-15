/* models.h: stage 17, low-poly textured/shaded GTE models for the player, people and the vehicle classes.
   Code only.  No Payback assets: every texel is generated here at map load, every colour comes from the map's own flat palette (side->flat).
   Included by sf3.c after the camera / projection / packet code and before sf3_frame.  Entities arrive by descriptor (look index, police flag).
   VRAM use: texture page (960,256) 4 bit, only v < 128;  CLUT rows x 960, y 448..481 (34 rows of 16). */
#ifndef MODELS_H
#define MODELS_H
#pragma clang attribute push(__attribute__((minsize, noinline)), apply_to = function)

enum { T_SIDE, T_TOP, T_GLASS, T_WIN, T_FRONT, T_REAR, T_WHEEL, T_BUSWIN, T_POLICE, T_TAXI, T_ARMOR, T_TRACK, T_SHIRT, T_FACE, T_JEANS, T_HEAD, T_FLAT = 16 };
#define MTP TPAGE(960, 256, 0, 0)
#define MROW(r) CLUT(960, 448 + (r))
enum { ROW_PED = 16, ROW_HERO = 32, ROW_COP = 33, NROWS = 34 };
static u16 mpal[NROWS][16];      /* 15 bit per palette entry (the CLUT rows and the flat faces use the same colours; index 0 is transparent) */
static int mdl_ready;
static void vram_dma(int x, int y, int w, int h, const void *src);

/* ------------------------------------------------------------------------------------------- generated texture atlas: 4 x 4 tiles of 32 x 32 texels, 4 bit */
static u8 *at_buf;
static inline void tpx(int t, int x, int y, int c) {
  if ((unsigned)x > 31 || (unsigned)y > 31) return;
  int gx = ((t & 3) << 5) + x, gy = ((t >> 2) << 5) + y; u8 *p = &at_buf[gy * 64 + (gx >> 1)];
  *p = (gx & 1) ? (*p & 0x0f) | (c << 4) : (*p & 0xf0) | c;
}
static void tfill(int t, int x0, int y0, int x1, int y1, int c) { for (int y = y0; y <= y1; y++) for (int x = x0; x <= x1; x++) tpx(t, x, y, c); }
static void tdisc(int t, int cx, int cy, int r, int c) { for (int y = cy - r; y <= cy + r; y++) for (int x = cx - r; x <= cx + r; x++) if ((x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r) tpx(t, x, y, c); }
static const u8 atlas_ops[][7] = { {0,0,0,0,31,31,1},{0,0,0,0,31,1,3},{0,0,0,25,31,31,2},{0,0,0,24,31,24,14},{0,0,0,2,0,24,2},{0,0,20,8,26,9,8},{0,0,20,10,26,10,2},{1,0,0,0,31,31,1},{1,0,0,0,31,0,3},{1,0,0,31,31,31,2},{1,0,15,2,16,29,3},{2,0,0,0,31,31,4},{2,2,2,0,30,31,5},{2,2,10,0,38,31,5},{2,2,18,0,46,31,5},{2,2,26,0,54,31,5},{2,0,0,0,31,1,14},{2,0,0,30,31,31,14},{2,0,0,0,1,31,14},{2,0,30,0,31,31,14},{3,0,0,0,31,31,2},{3,0,2,3,29,28,4},{3,2,6,3,20,28,5},{3,2,7,3,21,28,5},{3,2,13,3,27,28,5},{4,0,0,0,31,31,1},{4,0,0,0,31,2,3},{4,0,0,25,31,31,2},{4,0,0,23,31,24,14},{4,0,9,6,22,20,12},{4,0,9,8,22,8,8},{4,0,9,11,22,11,8},{4,0,9,14,22,14,8},{4,0,9,17,22,17,8},{4,0,1,7,7,15,8},{4,0,2,8,6,14,9},{4,0,24,7,30,15,8},{4,0,25,8,29,14,9},{4,0,11,26,20,30,13},{4,0,12,28,19,28,14},{5,0,0,0,31,31,1},{5,0,0,0,31,2,3},{5,0,0,24,31,31,2},{5,0,0,22,31,23,14},{5,0,1,6,9,15,14},{5,0,2,7,8,14,10},{5,0,22,6,30,15,14},{5,0,23,7,29,14,10},{5,0,3,12,7,13,11},{5,0,24,12,28,13,11},{5,0,11,25,20,29,13},{5,0,12,27,19,27,14},{6,1,16,16,15,0,6},{6,1,16,16,9,0,7},{6,1,16,16,4,0,8},{6,1,16,16,1,0,14},{6,2,16,12,16,7,14},{6,2,18,15,23,14,14},{6,2,17,19,20,23,14},{6,2,15,19,12,23,14},{6,2,14,15,9,14,14},{7,0,0,0,31,31,1},{7,0,0,28,31,31,2},{7,0,1,3,14,25,14},{7,0,2,4,13,24,4},{7,2,3,4,8,24,5},{7,0,17,3,30,25,14},{7,0,18,4,29,24,4},{7,2,19,4,24,24,5},{8,0,0,0,31,31,1},{8,0,0,0,31,1,3},{8,0,0,25,31,31,2},{8,0,0,10,31,17,15},{8,0,0,9,31,9,8},{8,0,3,12,5,15,8},{8,0,8,12,10,15,8},{8,0,13,12,15,15,8},{8,0,18,12,20,15,8},{8,0,23,12,25,15,8},{8,0,28,12,30,15,8},{9,0,0,0,31,31,1},{9,0,0,25,31,31,2},{9,0,0,9,3,12,8},{9,0,0,13,3,16,14},{9,0,4,9,7,12,14},{9,0,4,13,7,16,8},{9,0,8,9,11,12,8},{9,0,8,13,11,16,14},{9,0,12,9,15,12,14},{9,0,12,13,15,16,8},{9,0,16,9,19,12,8},{9,0,16,13,19,16,14},{9,0,20,9,23,12,14},{9,0,20,13,23,16,8},{9,0,24,9,27,12,8},{9,0,24,13,27,16,14},{9,0,28,9,31,12,14},{9,0,28,13,31,16,8},{9,0,0,0,31,1,3},{10,0,0,0,31,31,1},{10,0,0,0,31,1,3},{10,0,0,30,31,31,2},{10,0,15,0,16,31,2},{10,0,5,12,25,13,2},{10,1,4,4,1,0,14},{10,1,27,4,1,0,14},{10,1,4,12,1,0,14},{10,1,27,12,1,0,14},{10,1,4,20,1,0,14},{10,1,27,20,1,0,14},{10,1,4,28,1,0,14},{10,1,27,28,1,0,14},{11,0,0,0,31,31,14},{11,0,0,0,31,2,6},{11,0,0,0,31,0,12},{11,0,0,4,31,6,6},{11,0,0,4,31,4,12},{11,0,0,8,31,10,6},{11,0,0,8,31,8,12},{11,0,0,12,31,14,6},{11,0,0,12,31,12,12},{11,0,0,16,31,18,6},{11,0,0,16,31,16,12},{11,0,0,20,31,22,6},{11,0,0,20,31,20,12},{11,0,0,24,31,26,6},{11,0,0,24,31,24,12},{11,0,0,28,31,30,6},{11,0,0,28,31,28,12},{11,1,16,16,7,0,12},{11,1,16,16,4,0,7},{11,1,16,16,1,0,14},{12,0,0,0,31,31,1},{12,0,0,0,31,2,3},{12,0,0,28,31,31,2},{12,0,14,6,17,27,2},{12,0,11,0,20,4,6},{12,0,12,5,19,6,7},{12,0,3,12,9,17,2},{12,0,4,13,8,16,3},{12,0,0,22,31,23,12},{13,0,0,0,31,31,6},{13,0,0,0,31,9,8},{13,0,0,10,2,16,8},{13,0,29,10,31,16,8},{13,0,6,14,12,16,11},{13,0,19,14,25,16,11},{13,0,8,14,10,16,10},{13,0,21,14,23,16,10},{13,0,6,12,12,12,8},{13,0,19,12,25,12,8},{13,0,14,17,17,21,7},{13,0,11,25,20,26,7},{13,0,12,27,19,27,6},{14,0,0,0,31,31,4},{14,0,0,0,31,2,12},{14,0,15,3,16,31,5},{14,0,3,5,10,11,5},{14,0,4,6,9,10,4},{14,0,0,8,31,8,5},{14,0,0,14,31,14,5},{14,0,0,20,31,20,5},{14,0,0,26,31,26,5},{15,0,0,0,31,31,6},{15,0,0,0,31,14,8},{15,0,24,12,31,20,8} };
static void atlas_build(void) {
  at_buf = (u8 *)SF_TMP; for (int i = 0; i < 64 * 128; i++) at_buf[i] = 0;
  for (unsigned k = 0; k < sizeof atlas_ops / 7; k++) { const u8 *o = atlas_ops[k]; int t = o[0], a = o[2], b = o[3], c = o[4], d = o[5], col = o[6];
    if (o[1] == 0) tfill(t, a, b, c, d, col); else if (o[1] == 1) tdisc(t, a, b, c, col);
    else { int n = 32; for (int i = 0; i <= n; i++) tpx(t, a + (c - a) * i / n, b + (d - b) * i / n, col); } }
}
static inline u32 c24to15(u32 c) { u32 v = ((c & 255) >> 3) | (((c >> 8) & 255) >> 3) << 5 | (((c >> 16) & 255) >> 3) << 10; return v ? v : 0x0421; }
static inline u32 scale24(u32 c, int g) {   /* c * g / 128 per channel, clamped */
  u32 r = (c & 255) * g >> 7, gg = ((c >> 8) & 255) * g >> 7, b = ((c >> 16) & 255) * g >> 7; if (r > 255) r = 255; if (gg > 255) gg = 255; if (b > 255) b = 255; return r | gg << 8 | b << 16; }
static inline u32 c15to24(u32 v) { u32 r = v & 31, g = (v >> 5) & 31, b = (v >> 10) & 31; return (r << 3 | r >> 2) | (g << 3 | g >> 2) << 8 | (b << 3 | b >> 2) << 16; }
static void pal_car(int row, u32 paint, u32 dark, u32 light) {
  static const u32 k[12] = { 0x5C4A38, 0xC8B08C, 0x222222, 0xA8A8A8, 0xE0E0E0, 0xA0F0F8, 0x2020C0, 0x2090F0, 0x303030, 0xC8D8D8, 0x101010, 0xC04020 };
  u16 *p = mpal[row]; p[0] = 0; p[1] = c24to15(paint); p[2] = c24to15(dark); p[3] = c24to15(light); for (int i = 0; i < 12; i++) p[4 + i] = c24to15(k[i]);
}
static void pal_per(int row, u32 shirt, u32 jeans, u32 skin, u32 hair) {
  static const u32 k[4] = { 0x202428, 0x101010, 0xE8E8E8, 0x203048 };
  u16 *p = mpal[row]; p[0] = 0; p[1] = c24to15(shirt); p[2] = c24to15(scale24(shirt, 84)); p[3] = c24to15(scale24(shirt, 140)); p[4] = c24to15(jeans); p[5] = c24to15(scale24(jeans, 78)); p[6] = c24to15(skin);
  p[7] = c24to15(scale24(skin, 80)); p[8] = c24to15(hair); for (int i = 0; i < 4; i++) p[9 + i] = c24to15(k[i]); p[13] = p[14] = p[15] = 0x4210;
}
static void models_upload(void) {
  static const u8 shirts[8] = { 7, 11, 9, 8, 12, 13, 15, 3 };   /* the mod's own materials: brick, car, cream, teal, accent, ship, stunt, grass (merge.c dress()) */
  static const u32 skins[4] = { 0x78A8E0, 0x6890C8, 0x90B8E8, 0x405C90 }, hairs[4] = { 0x1C2C50, 0x103070, 0x203860, 0x484C50 };
  for (int m = 0; m < 16; m++) { u32 base = flat_col(m, 3, 0); pal_car(m, base, flat_col(m, 1, 0), scale24(base, 150)); }
  for (int k = 0; k < 16; k++) pal_per(ROW_PED + k, flat_col(shirts[k & 7], 3, 0), flat_col((k >> 3) ? 10 : 1, 3, 0), skins[k & 3], hairs[(k >> 1) & 3]);
  pal_per(ROW_HERO, flat_col(14, 3, 0), flat_col(6, 3, 0), skins[0], hairs[0]);      /* the stunt fox: orange jacket (M_GLOW), jeans (M_GLASS) */
  pal_per(ROW_COP, flat_col(13, 3, 0), flat_col(1, 2, 0), skins[2], hairs[3]);      /* an officer: blue (M_SHIP), dark trousers */
  atlas_build(); vram_dma(960, 256, 32, 128, at_buf);
  vram_dma(960, 448, 16, NROWS, mpal);
  mdl_ready = 1;
}

/* ------------------------------------------------------------------------------------------- face emitter: local-space GTE projection
   One matrix (camera x object yaw x scale) is loaded per entity; every vertex is then a local (x, y, z) in renderer units through RTPS.  Back faces are culled on the screen
   (NCLIP style), shades come from five axis shades worked out once per entity.  A face with a vertex behind the near plane goes through the CPU path (world corners, clipper). */
typedef struct { s32 px, py, pz; int ax, bx, sc; } XF;
static inline V3 xv(const XF *f, int lx, int ly, int lz) { return (V3){ f->px + ((lx * f->ax + lz * f->bx) >> 14), f->py + (ly * f->sc >> 8), f->pz + ((lz * f->ax - lx * f->bx) >> 14) }; }
static int msoft;   /* words of primitive buffer a model may still use (set per entity) */
static int mg[5], mL[3];          /* shade of the local +x, -x, +y, +z, -z faces; the sun in the entity's frame (1.14) */
static XF mxf;                    /* the entity's world transform (fallback and clip path) */
static inline int mgs(int d) { if (d < 0) d = 0; if (d > 16384) d = 16384; return 50 + ((d * 72) >> 14); }
static int mshade(s32 nx, s32 ny, s32 nz) {   /* shade of a local normal (sloped strips) */
  s32 mx = iabs_(nx), md = iabs_(ny), mn = iabs_(nz), t;
  if (md > mx) { t = mx; mx = md; md = t; } if (mn > mx) { t = mx; mx = mn; mn = t; } if (mn > md) { t = md; md = mn; mn = t; }
  s32 len = mx + (md >> 1) + (mn >> 2); if (len < 1) return 60;
  while (len > 6000) { nx >>= 1; ny >>= 1; nz >>= 1; len >>= 1; }
  return mgs((nx * mL[0] + ny * mL[1] + nz * mL[2]) / len);
}
static void mx_begin(const XF *f) {
  mxf = *f; int c = f->ax, s = f->bx, k = f->sc << 6; s32 m[9];
  const V3 *M[3] = { &mr, &mu, &mf };
  s32 d0x = (f->px << 2) - cpx6, d0y = (f->py << 2) - cpy6, d0z = (f->pz << 2) - cpz6, tr[3];
  for (int i = 0; i < 3; i++) { int sg = i == 1 ? -1 : 1; const V3 *a = M[i];
    m[3 * i] = sg * ((a->x * c - a->z * s) >> 16); m[3 * i + 1] = sg * ((a->y * k) >> 16); m[3 * i + 2] = sg * ((a->x * s + a->z * c) >> 16);
    tr[i] = sg * ((a->x * d0x + a->y * d0y + a->z * d0z) >> 14); }
  gte_set_rot(m); gte_set_trans(tr[0], tr[1], tr[2]);
  { int yc = fcos(0), ys = 0; (void)yc; (void)ys; }
}
static void mx_light(int ya) {
  int c = fcos(ya), s = fsin(ya); mL[0] = (4915 * c - 7864 * s) >> 14; mL[1] = 13435; mL[2] = (4915 * s + 7864 * c) >> 14;
  mg[0] = mgs(mL[0]); mg[1] = mgs(-mL[0]); mg[2] = mgs(mL[1]); mg[3] = mgs(mL[2]); mg[4] = mgs(-mL[2]);
}
static inline void lproj(const V3 *l, PV *o) {
  MTC2(0, ((u32)(l->x << 2) & 0xffff) | ((u32)(l->y << 2) << 16)); MTC2(1, l->z << 2); GTE(RTPS);
  u32 sxy = MFC2(14), sz = MFC2(19); o->sx = sxy; o->sy = sxy >> 16; o->z = sz >> 2;
}
static inline V3 tow(const V3 *l) { return xv(&mxf, l->x, l->y, l->z); }
static void mquad(const V3 *lw, const int *uv, u32 cmd, u32 clut, u32 tp, int key, int depth, const PV *pre) {
  PV p[4]; for (int i = 0; i < 4; i++) { if (pre) p[i] = pre[i]; else lproj(&lw[i], &p[i]); }
  int aff = 1, q = qcls(&p[0], &p[1], &p[2], &p[3], &aff);
  if (q == Q_SKIP) return;
  if (q == Q_CLIP) { V3 w[4]; for (int i = 0; i < 4; i++) w[i] = tow(&lw[i]); clip_emit_tex(w, uv, 4, bucket(key), cmd, clut, tp, 0, 0); return; }
  if (!aff && depth < 2) {   /* affine error over 2 px: split the longer screen edge */
    int dx = iabs_(p[1].sx - p[0].sx) + iabs_(p[1].sy - p[0].sy) + iabs_(p[2].sx - p[3].sx) + iabs_(p[2].sy - p[3].sy);
    int dy = iabs_(p[3].sx - p[0].sx) + iabs_(p[3].sy - p[0].sy) + iabs_(p[2].sx - p[1].sx) + iabs_(p[2].sy - p[1].sy);
    int e0 = 0, e1 = dx >= dy ? 1 : 3, f0 = dx >= dy ? 3 : 1, f1 = 2;    /* midpoints: (e0,e1) -> m4 and (f0,f1) -> m5 */
    V3 P[6]; int U[12]; for (int i = 0; i < 4; i++) { P[i] = lw[i]; U[2 * i] = uv[2 * i]; U[2 * i + 1] = uv[2 * i + 1]; }
    P[4] = (V3){ (lw[e0].x + lw[e1].x) >> 1, (lw[e0].y + lw[e1].y) >> 1, (lw[e0].z + lw[e1].z) >> 1 }; P[5] = (V3){ (lw[f0].x + lw[f1].x) >> 1, (lw[f0].y + lw[f1].y) >> 1, (lw[f0].z + lw[f1].z) >> 1 };
    U[8] = (uv[2 * e0] + uv[2 * e1]) >> 1; U[9] = (uv[2 * e0 + 1] + uv[2 * e1 + 1]) >> 1; U[10] = (uv[2 * f0] + uv[2 * f1]) >> 1; U[11] = (uv[2 * f0 + 1] + uv[2 * f1 + 1]) >> 1;
    static const u8 IA[2][4] = { { 0, 4, 5, 3 }, { 0, 1, 5, 4 } }, IB[2][4] = { { 4, 1, 2, 5 }, { 4, 5, 2, 3 } };
    for (int h = 0; h < 2; h++) { const u8 *I = h ? IB[dx >= dy ? 0 : 1] : IA[dx >= dy ? 0 : 1]; V3 q4[4]; int uq[8];
      for (int i = 0; i < 4; i++) { q4[i] = P[I[i]]; uq[2 * i] = U[2 * I[i]]; uq[2 * i + 1] = U[2 * I[i] + 1]; }
      mquad(q4, uq, cmd, clut, tp, key, depth + 1, 0); }
    return;
  }
  put_ft4(bucket(key), cmd, &p[0], &p[1], &p[3], &p[2], uv[0] | uv[1] << 8, uv[2] | uv[3] << 8, uv[6] | uv[7] << 8, uv[4] | uv[5] << 8, clut, tp);
}
/* one face.  lw: local corners TL, TR, BR, BL seen from outside; pp: their projections or 0; gi: 0..4 an axis shade (+x -x +y +z -z), else the shade itself;
   tile < T_FLAT: textured (palette row `row`), else flat in palette entry (tile - T_FLAT).  fl 1: double sided.  bias: towards the camera. */
static void mface(const V3 *lw, const PV *pp, int tile, int row, int gi, int bias, int fl) {
  if (msoft < 24) return;
  PV p[4]; for (int i = 0; i < 4; i++) { if (pp) p[i] = pp[i]; else lproj(&lw[i], &p[i]); }
  int key; int mnz = p[0].z; for (int i = 1; i < 4; i++) if (p[i].z < mnz) mnz = p[i].z;
  if (mnz >= NEAR) { int cr = (p[2].sx - p[0].sx) * (p[3].sy - p[1].sy) - (p[2].sy - p[0].sy) * (p[3].sx - p[1].sx); if (cr <= 0 && !(fl & 1)) return; key = ((p[0].z + p[1].z + p[2].z + p[3].z) >> 2) - bias; }
  else { V3 w[4]; for (int i = 0; i < 4; i++) w[i] = tow(&lw[i]);    /* behind the near plane: world cull, clipper */
    s32 d1x = w[2].x - w[0].x, d1y = w[2].y - w[0].y, d1z = w[2].z - w[0].z, d2x = w[3].x - w[1].x, d2y = w[3].y - w[1].y, d2z = w[3].z - w[1].z;
    s32 nx = d1y * d2z - d1z * d2y, ny = d1z * d2x - d1x * d2z, nz = d1x * d2y - d1y * d2x;
    if (nx * (camx - w[0].x) + ny * (camy - w[0].y) + nz * (camz - w[0].z) <= 0 && !(fl & 1)) return;
    key = zdepth((w[0].x + w[2].x) >> 1, (w[0].y + w[2].y) >> 1, (w[0].z + w[2].z) >> 1) - bias; }
  int g = gi < 8 ? mg[gi] : gi;
  if (tile >= T_FLAT) {
    u32 col = scale24(c15to24(mpal[row][tile - T_FLAT]), g);
    int q = qclass(&p[0], &p[1], &p[2], &p[3]); if (q == Q_SKIP) return; msoft -= 6;
    if (q == Q_OK && mnz >= NEAR) put_f4(bucket(key), 0, col, &p[0], &p[1], &p[3], &p[2]); else { V3 w[4]; for (int i = 0; i < 4; i++) w[i] = tow(&lw[i]); clip_emit_flat(w, 4, bucket(key), 0, col, 2); }
    return;
  }
  int u0 = (tile & 3) << 5, v0 = (tile >> 2) << 5, u1 = u0 + 31, v1 = v0 + 31; int uv[8] = { u0, v0, u1, v0, u1, v1, u0, v1 };
  msoft -= 10; mquad(lw, uv, FT4_MOD | (g << 16) | (g << 8) | g, MROW(row), MTP, key, 0, mnz >= NEAR ? p : 0);
}
/* a blob shadow: semi-transparent black quad on the ground (50 % of the ground behind) */
static void mshadow(int hx, int hz) {
  static const s8 cx[4] = { -1, 1, 1, -1 }, cz[4] = { 1, 1, -1, -1 }; PV p[4];
  for (int i = 0; i < 4; i++) { V3 l = { cx[i] * hx, 2, cz[i] * hz }; lproj(&l, &p[i]); }
  if (qclass(&p[0], &p[1], &p[2], &p[3]) != Q_OK || p[0].z < NEAR || p[1].z < NEAR || p[2].z < NEAR || p[3].z < NEAR) return;
  u32 *q = pnew(5); if (!q) return; msoft -= 6;
  q[1] = 0x2A000000; q[2] = pxy(&p[0]); q[3] = pxy(&p[1]); q[4] = pxy(&p[3]); q[5] = pxy(&p[2]);
  link_ot(bucket(((p[0].z + p[1].z + p[2].z + p[3].z) >> 2) + 90), q, 5);
}
/* a box from its 8 local corners (index = x + 2 y + 4 z bits): five faces (no bottom), tf = textures / flat entries of front, back, left, right, top */
static void mbox8(const V3 *c, const u8 *tf, int row, int bias) {
  static const u8 F[5][4] = { { 7, 6, 4, 5 }, { 2, 3, 1, 0 }, { 6, 2, 0, 4 }, { 3, 7, 5, 1 }, { 6, 7, 3, 2 } }, GI[5] = { 3, 4, 1, 0, 2 };
  PV p8[8]; u8 have = 0;
  for (int k = 0; k < 5; k++) { V3 lw[4]; PV pp[4];
    for (int i = 0; i < 4; i++) { int j = F[k][i]; lw[i] = c[j]; if (!((have >> j) & 1)) { lproj(&c[j], &p8[j]); have |= 1 << j; } pp[i] = p8[j]; }
    mface(lw, pp, tf[k], row, GI[k], bias, 0); }
}
static void mbox(int x0, int x1, int y0, int y1, int z0, int z1, const u8 *tf, int row, int bias) {
  V3 c[8]; for (int i = 0; i < 8; i++) c[i] = (V3){ (i & 1) ? x1 : x0, (i & 2) ? y1 : y0, (i & 4) ? z1 : z0 };
  mbox8(c, tf, row, bias);
}

/* ------------------------------------------------------------------------------------------- vehicles: sealed rings of stations (underside never seen, never drawn) */
typedef struct { s16 z, yb, yw, yr, wb, wr; u8 keep, kind; } Stn;     /* z along the car, yb bottom, yw belt, yr roof, wb/wr half width at belt/roof; kind: the strip to the next station (0 paint, 1 glass, 2 bed) */
typedef struct { const Stn *st; u8 ns, pm, tside, tup, capf, capr, mxl; s16 ox, oy, oz; } Ring;    /* mxl: the coarsest detail level it is still drawn at */    /* pm 255 = the body paint, else a palette row (material) */
typedef struct { const Ring *rg; u8 nr; s16 wx, wzf, wzr; u8 wheels, tall; } VSpec;
#define MAXST 10
#define MAXT0V 3      /* full-detail vehicles / people per frame (nearest first); the rest use the cheap levels */
#define MAXT0P 4
#define SALOON(L, cf, cb, rf, rb, w, hh, hd, ht, bed) { { L, 26, 62, 62, (w) - 6, (w) - 6, 3, 0 }, { (L) - 32, 22, (62 + (hh)) / 2, (62 + (hh)) / 2, w, w, 1, 0 }, { cf, 22, hh, hh, w, w, 1, 1 }, \
  { rf, 22, hh, 146, w, (w) - 18, 3, 0 }, { rb, 22, hd, 146, w, (w) - 18, 3, 1 }, { cb, 22, hd, hd, w, w, 1, (bed) ? 2 : 0 }, { -(L) + 22, 22, (ht) + 2, (ht) + 2, (w) - 3, (w) - 3, 0, (bed) ? 2 : 0 }, { -(L), 24, ht, ht, (w) - 6, (w) - 6, 3, 0 } }
static const Stn st_saloon[8] = SALOON(235, 70, -120, 30, -95, 112, 84, 86, 78, 0), st_limo[8] = SALOON(340, 120, -230, 80, -205, 112, 84, 86, 78, 0), st_pickup[8] = SALOON(245, 150, -20, 110, -10, 118, 84, 82, 82, 1);
static const Stn st_sport[] = {
  { 235, 20, 34, 34, 100, 100, 3, 0 }, { 150, 20, 56, 56, 112, 112, 1, 0 }, { 70, 20, 66, 66, 118, 118, 1, 1 }, { -15, 20, 68, 114, 122, 80, 3, 0 },
  { -105, 20, 72, 110, 124, 82, 3, 1 }, { -170, 20, 86, 86, 125, 125, 1, 0 }, { -225, 20, 90, 90, 120, 120, 0, 0 }, { -238, 24, 76, 76, 116, 116, 3, 0 } };
static const Stn st_van[] = {
  { 250, 22, 96, 96, 112, 112, 3, 0 }, { 214, 22, 100, 120, 118, 118, 3, 1 }, { 184, 22, 100, 206, 118, 118, 3, 0 }, { -245, 22, 100, 214, 118, 118, 3, 0 } };
static const Stn st_bus[] = {
  { 520, 22, 110, 270, 130, 126, 3, 1 }, { 400, 22, 110, 270, 130, 126, 0, 0 }, { 240, 22, 110, 270, 130, 126, 1, 0 }, { 80, 22, 110, 270, 130, 126, 0, 0 },
  { -80, 22, 110, 270, 130, 126, 0, 0 }, { -240, 22, 110, 270, 130, 126, 1, 0 }, { -400, 22, 110, 270, 130, 126, 0, 0 }, { -520, 22, 110, 270, 130, 126, 3, 0 } };
static const Stn st_hull[] = { { 285, 40, 72, 72, 120, 120, 3, 0 }, { 212, 30, 104, 104, 150, 150, 3, 0 }, { -268, 30, 105, 105, 150, 150, 3, 0 }, { -285, 36, 96, 96, 142, 142, 3, 0 } };
static const Stn st_track[] = { { 300, 0, 52, 52, 26, 26, 1, 0 }, { 236, 0, 78, 78, 26, 26, 1, 0 }, { 150, 0, 78, 78, 26, 26, 0, 0 }, { 60, 0, 78, 78, 26, 26, 0, 0 },
  { -60, 0, 78, 78, 26, 26, 0, 0 }, { -150, 0, 78, 78, 26, 26, 0, 0 }, { -236, 0, 78, 78, 26, 26, 1, 0 }, { -300, 0, 52, 52, 26, 26, 1, 0 } };
static const Stn st_turret[] = { { 100, 0, 18, 18, 66, 66, 3, 0 }, { 72, 0, 34, 58, 84, 62, 3, 0 }, { -78, 0, 34, 58, 84, 62, 3, 0 }, { -104, 0, 18, 18, 66, 66, 3, 0 } };
static const Stn st_gun[] = { { 470, 0, 11, 11, 9, 9, 3, 0 }, { 70, 0, 22, 22, 13, 13, 3, 0 } };
#define N_(a) (sizeof(a) / sizeof((a)[0]))
#define RING(st_, pm_, ts, tu, cf, cr, mx, ox, oy, oz) { st_, N_(st_), pm_, ts, tu, cf, cr, mx, ox, oy, oz }
static const Ring rg_saloon[1] = { RING(st_saloon, 255, T_SIDE, T_WIN, T_FRONT, T_REAR, 2, 0, 0, 0) }, rg_limo[1] = { RING(st_limo, 255, T_SIDE, T_WIN, T_FRONT, T_REAR, 2, 0, 0, 0) },
  rg_pickup[1] = { RING(st_pickup, 255, T_SIDE, T_WIN, T_FRONT, T_REAR, 2, 0, 0, 0) }, rg_police[1] = { RING(st_saloon, 255, T_POLICE, T_WIN, T_FRONT, T_REAR, 2, 0, 0, 0) },
  rg_taxi[1] = { RING(st_saloon, 255, T_TAXI, T_WIN, T_FRONT, T_REAR, 2, 0, 0, 0) }, rg_sport[1] = { RING(st_sport, 255, T_SIDE, T_WIN, T_FRONT, T_REAR, 2, 0, 0, 0) },
  rg_van[1] = { RING(st_van, 255, T_SIDE, T_SIDE, T_FRONT, T_REAR, 2, 0, 0, 0) }, rg_bus[1] = { RING(st_bus, 255, T_SIDE, T_BUSWIN, T_FRONT, T_REAR, 2, 0, 0, 0) },
  rg_tank[5] = { RING(st_hull, 255, T_ARMOR, T_ARMOR, T_ARMOR, T_ARMOR, 2, 0, 0, 0), RING(st_track, 1, T_TRACK, T_TRACK, T_TRACK, T_TRACK, 1, -152, 0, 0), RING(st_track, 1, T_TRACK, T_TRACK, T_TRACK, T_TRACK, 1, 152, 0, 0),
    RING(st_turret, 255, T_ARMOR, T_ARMOR, T_ARMOR, T_ARMOR, 2, 0, 105, 0), RING(st_gun, 10, T_FLAT + 1, T_FLAT + 1, T_FLAT + 1, T_FLAT + 1, 1, 0, 126, 0) };
static const VSpec vs_saloon = { rg_saloon, 1, 114, 150, -150, 1, 0 }, vs_limo = { rg_limo, 1, 114, 250, -250, 1, 0 }, vs_pickup = { rg_pickup, 1, 120, 160, -160, 1, 0 },
  vs_police = { rg_police, 1, 114, 150, -150, 1, 0 }, vs_taxi = { rg_taxi, 1, 114, 150, -150, 1, 0 }, vs_sport = { rg_sport, 1, 127, 160, -150, 1, 0 },
  vs_van = { rg_van, 1, 120, 160, -160, 1, 1 }, vs_bus = { rg_bus, 1, 132, 380, -380, 1, 1 }, vs_tank = { rg_tank, 5, 0, 0, 0, 0, 0 };
/* look index (the mod's looks[], descriptor +0x38 - 0x1a) -> shape, paint material (the mod's own), scale 256 = 1, extras: 1 police light bar, 2 taxi sign */
typedef struct { const VSpec *vs; u8 paint, scale, extra; } VLook;
#define S_ &vs_saloon
#define SP_ &vs_sport
#define V_ &vs_van
#define B_ &vs_bus
static const VLook vlooks[26] = { { S_, 8, 0, 0 }, { S_, 7, 224, 0 }, { SP_, 15, 0, 0 }, { B_, 12, 0, 0 }, { S_, 5, 0, 0 }, { S_, 11, 224, 0 }, { S_, 9, 0, 0 }, { V_, 13, 0, 0 }, { &vs_limo, 1, 0, 0 }, { &vs_police, 13, 0, 1 },
  { SP_, 11, 0, 0 }, { &vs_tank, 3, 0, 0 }, { SP_, 13, 0, 0 }, { &vs_taxi, 12, 0, 2 }, { V_, 9, 0, 0 }, { &vs_pickup, 7, 0, 0 }, { SP_, 14, 0, 0 }, { V_, 11, 0, 0 }, { S_, 11, 224, 0 }, { B_, 9, 0, 0 },
  { V_, 13, 0, 1 }, { V_, 8, 0, 0 }, { SP_, 14, 92, 0 }, { &vs_tank, 4, 0, 0 }, { &vs_pickup, 11, 0, 0 }, { S_, 10, 0, 0 } };
static const VLook *vlook(int k) { return &vlooks[k < 0 || k > 25 ? 0 : k]; }
/* a wheel: a box on the +-x side whose outer face is the round hub texture (corners transparent); far away one flat quad */
static void mwheel(int sx, int cz, int rad, int row, int lod, int wx) {
  if (lod) { int x1 = sx * wx; V3 w[4] = { { x1, 2 * rad, cz + rad }, { x1, 2 * rad, cz - rad }, { x1, 0, cz - rad }, { x1, 0, cz + rad } };
    if (sx > 0) { V3 t = w[0]; w[0] = w[1]; w[1] = t; t = w[2]; w[2] = w[3]; w[3] = t; }
    mface(w, 0, T_FLAT + 6, row, 16, 0, 0); return; }
  u8 tf[5] = { T_FLAT + 6, T_FLAT + 6, T_FLAT + 6, T_FLAT + 6, T_FLAT + 6 }; tf[sx > 0 ? 3 : 2] = T_WHEEL;
  mbox(sx > 0 ? wx - 24 : -wx, sx > 0 ? wx : 24 - wx, 0, 2 * rad, cz - rad, cz + rad, tf, row, 12);
}
static const s8 rface[5][9] = {   /* per strip: 4 x (station 0|1, vertex) ; kind 0 lower side, 1 upper side, 2 top */
  { 0, 1, 1, 1, 1, 0, 0, 0, 0 }, { 1, 4, 0, 4, 0, 5, 1, 5, 0 }, { 0, 2, 1, 2, 1, 1, 0, 1, 1 }, { 1, 3, 0, 3, 0, 4, 1, 4, 1 }, { 0, 2, 0, 3, 1, 3, 1, 2, 2 } };
static void mring(const Ring *r, int row, int lod) {
  if (lod > r->mxl) return;
  V3 v[MAXST][6]; PV pvc[MAXST * 6]; u8 pvh[MAXST * 6]; const Stn *S[MAXST]; int n = 0;
  int prow = r->pm == 255 ? row : r->pm;
  for (int i = 0; i < r->ns && n < MAXST; i++) { const Stn *s = &r->st[i]; if (lod && !((s->keep >> (lod - 1)) & 1)) continue; S[n] = s; int z = s->z + r->oz, ox = r->ox, oy = r->oy;
    v[n][0] = (V3){ ox - s->wb, oy + s->yb, z }; v[n][1] = (V3){ ox - s->wb, oy + s->yw, z }; v[n][2] = (V3){ ox - s->wr, oy + s->yr, z };
    v[n][3] = (V3){ ox + s->wr, oy + s->yr, z }; v[n][4] = (V3){ ox + s->wb, oy + s->yw, z }; v[n][5] = (V3){ ox + s->wb, oy + s->yb, z }; n++; }
  for (int i = 0; i < n * 6; i++) pvh[i] = 0;
#define RP(sv, vt) ({ int k_ = (sv) * 6 + (vt); if (!pvh[k_]) { lproj(&v[sv][vt], &pvc[k_]); pvh[k_] = 1; } &pvc[k_]; })
  for (int i = 0; i + 1 < n; i++) { const Stn *a = S[i], *b = S[i + 1]; int up = a->yr > a->yw || b->yr > b->yw;
    for (int q = 0; q < 5; q++) { const s8 *F = rface[q]; int kd = F[8]; V3 w[4]; PV pp[4]; int tt, gi;
      if (kd == 1 && !up) continue;
      for (int k = 0; k < 4; k++) { int sv = i + F[2 * k], vt = F[2 * k + 1]; w[k] = v[sv][vt]; pp[k] = *RP(sv, vt); }
      if (kd == 0) tt = lod ? T_FLAT + 1 : r->tside; else if (kd == 1) tt = lod ? T_FLAT + 4 : r->tup; else tt = a->kind == 1 ? (lod ? T_FLAT + 4 : T_GLASS) : (lod ? T_FLAT + 1 : T_TOP);
      gi = kd == 2 ? mshade(0, a->z - b->z, b->yr - a->yr) : (q == 0 || q == 2) ? 1 : 0;
      mface(w, pp, tt, kd == 2 && a->kind == 2 ? 9 : prow, gi, 0, 0); } }
  if (n < 2) return;
  for (int e = 0; e < 2; e++) { int si = e ? n - 1 : 0; const Stn *a = S[si]; V3 *va = v[si]; V3 w[4]; PV pp[4]; 
    static const u8 ci[2][4] = { { 4, 1, 0, 5 }, { 1, 4, 5, 0 } }, ui[2][4] = { { 3, 2, 1, 4 }, { 2, 3, 4, 1 } };
    for (int k = 0; k < 4; k++) { w[k] = va[ci[e][k]]; pp[k] = *RP(si, ci[e][k]); }
    mface(w, pp, lod ? (e ? T_FLAT + 2 : T_FLAT + 12) : (e ? r->capr : r->capf), prow, e ? 4 : 3, 0, 0);
    if (a->yr > a->yw) { for (int k = 0; k < 4; k++) { w[k] = va[ui[e][k]]; pp[k] = *RP(si, ui[e][k]); } mface(w, pp, lod ? T_FLAT + 4 : T_GLASS, prow, e ? 4 : 3, 0, 0); } }
#undef RP
}
static u32 t_vehl, t_pedl, n_veh, n_ped, n_t0v, n_t0p;   /* PROFILE (always on, one counter read per entity): hblank lines spent in the model code, entities drawn, full-detail ones this frame */
static void veh_draw_(s32 x, s32 y, s32 z, int ya, int look, int pol, int dist) {
  if (!mdl_ready) return;
  if (!in_view(x, y + 100, z, 600)) return;
  if (pol) look = (look == 20) ? 20 : 9;
  const VLook *lk = vlook(look); const VSpec *sp = lk->vs;
  int sc = lk->scale ? lk->scale : 256, lod = dist > 2400 ? 2 : dist > 1000 ? 1 : 0;
  if (lod == 0 && n_t0v >= MAXT0V) lod = 1; if (lod == 0) n_t0v++;
  int room = (int)(pbe - pb); if (room < 700) return; if (room < 1500 && lod < 1) lod = 1;
  msoft = room - 500; if (lod) { if (msoft > 330) msoft = 330; } else if (msoft > 700) msoft = 700;
  int s = fsin(ya), c = fcos(ya); XF f = { x, y, z, c * sc >> 8, s * sc >> 8, sc };
  int row = lk->paint;
  mx_begin(&f); mx_light(ya);
  mshadow(sp->tall ? 140 : 135, sp == &vs_bus ? 560 : sp == &vs_tank ? 300 : 260);
  for (int i = 0; i < sp->nr; i++) mring(&sp->rg[i], row, lod);
  if (sp->wheels && lod < 2) { for (int i = 0; i < 4; i++) mwheel((i & 1) ? 1 : -1, (i & 2) ? sp->wzr : sp->wzf, sp == &vs_sport ? 28 : 38, row, lod, sp->wx); }
  if (lk->extra == 1 && lod < 2) {   /* a light bar, red and blue, steady (no flashing) */
    static const u8 tr[5] = { T_FLAT + 10, T_FLAT + 10, T_FLAT + 10, T_FLAT + 10, T_FLAT + 10 }, tb[5] = { T_FLAT + 15, T_FLAT + 15, T_FLAT + 15, T_FLAT + 15, T_FLAT + 15 };
    int ry = sp == &vs_van ? 214 : 146; mbox(-62, -4, ry, ry + 14, -40, -8, tr, row, 14); mbox(4, 62, ry, ry + 14, -40, -8, tb, row, 14); }
  if (lk->extra == 2 && !lod) { static const u8 tt[5] = { T_TAXI, T_TAXI, T_FLAT + 15, T_FLAT + 15, T_FLAT + 8 }; mbox(-30, 30, 146, 164, -12, 12, tt, row, 14); }
  gte_setup();
}
static void veh_draw(s32 x, s32 y, s32 z, int ya, int look, int pol, int dist) { u32 t0 = HLINES(); veh_draw_(x, y, z, ya, look, pol, dist); t_vehl += (HLINES() - t0) & 0xffff; n_veh++; }

/* ------------------------------------------------------------------------------------------- people: seven boxes (two of them mirrored), swinging limbs */
typedef struct { s16 spd, ph, x, z; u8 ok; } Anim;
static Anim anim[64];
static int anim_step(int id, s32 x, s32 z) {    /* returns the speed in 1/16 unit a frame, advances the stride phase by the distance walked */
  Anim *a = &anim[id & 63]; int d = 0;
  if (a->ok) { d = iabs_(x - a->x) + iabs_(z - a->z); if (d > 300) d = 0; }
  a->ok = 1; a->x = x; a->z = z; a->spd = (a->spd * 3 + d * 16) >> 2;
  a->ph = (a->ph + d * 300) & 0xffff;                     /* one full cycle (two steps) = 218 units walked */
  return a->spd;
}
typedef struct { s8 x0, x1; s16 y0, y1; s8 z0, z1; u8 grp, tf, mir; } PPart;    /* grp 0 body, 1 leg (swings about the hip), 2 arm (about the shoulder); tf: face set; mir: also drawn mirrored (the other leg / arm) */
static const PPart ppart[] = {
  { -24, -5, 16, 100, -11, 11, 1, 0, 1 }, { -25, -4, 0, 16, -8, 22, 1, 1, 1 }, { -48, -38, 108, 176, -8, 8, 2, 2, 1 }, { -48, -38, 92, 108, -7, 7, 2, 3, 1 },
  { -34, 34, 96, 178, -15, 15, 0, 4, 0 }, { -16, 16, 182, 226, -14, 17, 0, 5, 0 }, { -18, 18, 206, 236, -22, 6, 0, 6, 0 } };
static const u8 pfaces[7][5] = { { T_JEANS, T_FLAT + 5, T_FLAT + 4, T_FLAT + 4, T_FLAT + 4 }, { T_FLAT + 9, T_FLAT + 9, T_FLAT + 9, T_FLAT + 9, T_FLAT + 9 }, { T_FLAT + 1, T_FLAT + 2, T_FLAT + 2, T_FLAT + 1, T_FLAT + 3 },
  { T_FLAT + 6, T_FLAT + 7, T_FLAT + 7, T_FLAT + 6, T_FLAT + 6 }, { T_SHIRT, T_FLAT + 2, T_FLAT + 1, T_FLAT + 1, T_FLAT + 3 }, { T_FACE, T_FLAT + 8, T_HEAD, T_HEAD, T_FLAT + 8 }, { T_FLAT + 8, T_FLAT + 8, T_FLAT + 8, T_FLAT + 8, T_FLAT + 8 } };
static void ped_lite(s32 x, s32 y, s32 z, int row) {   /* far away: three camera-facing flat quads (legs, jacket, head) */
  int key = zdepth(x, y, z);
  billboard(x, y, z, 24, 0, 100, scale24(c15to24(mpal[row][4]), 96), key); billboard(x, y, z, 38, 100, 180, scale24(c15to24(mpal[row][1]), 100), key - 2); billboard(x, y, z, 15, 182, 226, scale24(c15to24(mpal[row][6]), 100), key - 4);
}
static void ped_draw_(s32 x, s32 y, s32 z, int ya, int id, int row, int dist) {
  if (!mdl_ready) return;
  if (!in_view(x, y + 110, z, 260)) return;
  if (dist > 1300 || n_t0p >= MAXT0P) { anim_step(id, x, z); ped_lite(x, y, z, row); return; }
  n_t0p++;
  int room = (int)(pbe - pb); if (room < 500) return; msoft = room - 400; if (msoft > 380) msoft = 380;
  int sp16 = anim_step(id, x, z), amp = sp16 < 6 ? 0 : sp16 > 160 ? 90 : 30 + (sp16 - 6) * 60 / 154;
  int run = sp16 > 96, ph = anim[id & 63].ph, sw = fsin(ph) * amp >> 14;     /* swing: sine in 1/128 */
  int bob = amp ? (iabs_(fsin(ph)) * (run ? 9 : 4)) >> 14 : 0, lean = run ? 10 : 0;
  int s = fsin(ya), c = fcos(ya), sc = 236; XF f = { x, y, z, c * sc >> 8, s * sc >> 8, sc };
  mx_begin(&f); mx_light(ya); mshadow(70, 70);
  for (unsigned k = 0; k < sizeof ppart / sizeof ppart[0]; k++) for (int m = 0; m <= ppart[k].mir; m++) { const PPart *pp = &ppart[k];
    int sn = pp->grp == 0 ? 0 : (pp->grp == 1) == (m == 0) ? sw : -sw, cs = 128 - ((sn * sn) >> 8), piv = pp->grp == 1 ? 100 : 176;
    int tp = (pp->tf == 4);    /* torso: narrower at the hem */
    int X0 = m ? -pp->x1 : pp->x0, X1 = m ? -pp->x0 : pp->x1;
    V3 c8[8]; for (int i = 0; i < 8; i++) { int hi = (i >> 1) & 1, vx = (i & 1) ? X1 : X0, vy = hi ? pp->y1 : pp->y0, vz = (i & 4) ? pp->z1 : pp->z0, oy = vy, oz = vz;
      if (tp && !hi) vx = vx * 3 / 4;
      if (pp->grp) { int dy = vy - piv; oz = (vz * cs - dy * sn) >> 7; oy = piv + ((dy * cs + vz * sn) >> 7); } else if (hi && k > 3) oz += lean;
      c8[i] = (V3){ vx, oy + bob, oz }; }
    mbox8(c8, pfaces[pp->tf], row, 0);
  }
  gte_setup(); (void)dist;
}
static void ped_draw(s32 x, s32 y, s32 z, int ya, int id, int row, int dist) { u32 t0 = HLINES(); ped_draw_(x, y, z, ya, id, row, dist); t_pedl += (HLINES() - t0) & 0xffff; n_ped++; }
static inline int ped_row(int id, int pol, int hero) { return hero ? ROW_HERO : pol ? ROW_COP : ROW_PED + ((id * 5 + (id >> 3)) & 15); }
#pragma clang attribute pop
#endif
