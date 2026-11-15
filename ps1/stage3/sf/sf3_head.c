/* sf.c: Stage 2b. Star-FlyBack / Stunt Fox world (Freedom City) drawn by the PS1 GPU, GTE projection, painter's OT.
   One translation unit, no SDK.  Data (WORLD.SFW, ATLAS.VRM, CLUT.BIN, SIDE.BIN, FONT.VRM) is linked in by data.s. */
#include "ps1.h"

#ifndef ERRPX
#define ERRPX 2
#endif
#ifndef HUD0
#define HUD0 0
#endif
#ifndef POSE
#define POSE -1
#endif
#ifndef FOG_TEX
#define FOG_TEX 1
#endif
#ifndef DEBUG_UNDERLAY
#define DEBUG_UNDERLAY 0
#endif
#ifndef REACH
#define REACH 12288
#endif

#ifdef NOFAN
#define NOFANX 1
#else
#define NOFANX 0
#endif
#define H_FOCAL 181
#define NEAR 32
#define CELL 1024
#define TEX_FAR 6500
#define TEX_WALL_FAR 5000
#define TEX_TOP 12000

#include "sfmem.h"
extern const u8 side_blob[];

/* ------------------------------------------------------------------------------------------- data */
typedef struct { s32 x, y, z; } V3;
static int errpx = ERRPX;
typedef struct { u8 x0, z0, x1, z1; s16 h; u8 mat; s8 base; } Box;
typedef struct { u8 x0, z0, x1, z1; s16 h0, h1; u8 dir, mat; } Ramp;
typedef struct { u16 x, z; u8 h, kind; s8 base; u8 r; } Tree;
typedef struct { s16 lo, hi; u8 shape, mat; } Cell;
typedef struct { u8 gmask[2048]; u16 slot_id[384]; u16 avg555[384]; u8 mesh[384]; u32 avgcol[384]; u32 flat[256]; u32 sky9[9]; u32 fog; s16 sint[4096]; } Side;
static const Side *side;
static const Box *boxes; static const Ramp *ramps; static const u16 *sector, *items; static const u16 *cellidx; static const Cell *celldict;
static const Tree *trees; static const u16 *ctex, *btex, *dtex; static const u8 *deckl; static int ndeck;
static int nbox, nramp, ntree;

static void world_init(void) {
  const u8 *b = (const u8 *)SF_WORLD; const u32 *h = (const u32 *)b;
  nbox = h[1]; nramp = h[2]; ntree = h[3]; ndeck = h[5];
  boxes = (const Box *)(b + h[6]); ramps = (const Ramp *)(b + h[7]); sector = (const u16 *)(b + h[8]); items = (const u16 *)(b + h[9]);
  trees = (const Tree *)(b + h[10]); ctex = (const u16 *)(b + h[11]); btex = (const u16 *)(b + h[12]); dtex = (const u16 *)(b + h[13]);
  cellidx = (const u16 *)(b + h[14]); celldict = (const Cell *)(b + h[15]); deckl = b + h[16];
  side = (const Side *)side_blob;
}
static const s8 zero4[4];
static const s8 *deck_get(int i) {   /* sparse deck table: sorted (u16 cell, s8 d[4]) records of 6 bytes */
  int lo = 0, hi = ndeck - 1;
  while (lo <= hi) { int m = (lo + hi) >> 1; const u8 *p = deckl + 6 * m; int k = p[0] | p[1] << 8; if (k == i) return (const s8 *)(p + 2); if (k < i) lo = m + 1; else hi = m - 1; }
  return zero4;
}

/* ------------------------------------------------------------------------------------------- lists */
#define PBW SF_PBW
#define pbuf ((u32 (*)[PBW])SF_PBUF)
#define otab ((u32 (*)[OTN])SF_OT)
static u32 *otc, *pbs, *pbe; static int cur;
static u32 bg_head, hud_head; static u32 *bg_tail, *hud_tail;
static int ovf;           /* primitive pool overflow counter */
static int lod;           /* adaptive level of detail 0..3 */
static int g_bg;          /* 1: textured packets go to the background list (ground) */
static int nprim; static u32 t_rect, t_clipt, t_qoff, t_qf; static u32 t_cb, t_cr, t_ct, t_sec; static int dbgcell; static u32 t_gc, t_gc01; static u32 g_leaf, g_proj, g_clip, g_cleaf; static u32 c_box, c_ramp, c_tree, c_proj, c_clip, c_rect, c_gcell, c_leaf, c_cleaf, c_cells, c_cullcell; static u32 ph_sky, ph_gnd, ph_city, ph_hud;
#define ADDR(p) ((u32)(p) & 0xFFFFFF)

static void list_begin(int c) {
  cur = c; otc = otab[c]; pbs = pbuf[c]; pb = pbs; pbe = pbs + PBW - 64; nprim = 0;
  D6_MADR = ADDR(&otc[OTN - 1]); D6_BCR = OTN; D6_CHCR = 0x11000002; while (D6_CHCR & 0x01000000) {}
  hud_head = 0x00FFFFFF; otc[0] = ADDR(&hud_head); hud_tail = &hud_head;
  bg_head = ADDR(&otc[OTN - 1]); bg_tail = &bg_head;
}
static inline int bucket(int key) { key >>= 5; return key < 0 ? 0 : key > OTN - 1 ? OTN - 1 : key; }
static inline u32 *pnew(int words) { u32 *p = pb; if (p >= pbe) { ovf++; return 0; } pb = p + words + 1; nprim++; return p; }
static inline void link_ot(int bk, u32 *p, int w) { p[0] = ((u32)w << 24) | otc[bk]; otc[bk] = ADDR(p); }
static inline void link_bg(u32 *p, int w) { p[0] = ((u32)w << 24) | ADDR(&otc[OTN - 1]); *bg_tail = (*bg_tail & 0xFF000000) | ADDR(p); bg_tail = p; }
static inline void link_hud(u32 *p, int w) { p[0] = ((u32)w << 24) | 0x00FFFFFF; *hud_tail = (*hud_tail & 0xFF000000) | ADDR(p); hud_tail = p; }
#ifndef FIELDS
#define FIELDS 3
#endif
static void list_send(void) {
  *bg_tail = (*bg_tail & 0xFF000000) | ADDR(&otc[OTN - 1]);
  while (!(GP1 & 0x04000000)) {} D2_MADR = ADDR(&bg_head); D2_BCR = 0; D2_CHCR = 0x01000401;
}

/* ------------------------------------------------------------------------------------------- camera */
static s32 cpx, cpy, cpz;           /* camera position, units << 8 */
static s32 cpx6, cpy6, cpz6, cpx8, cpy8, cpz8;
static s32 camx, camy, camz;        /* units */
static V3 mr, mu, mf;               /* camera axes, 1.14 (r already mirrored) */
static int yaw, pitch;              /* u16 turn, s16 */
static inline int fsin(int a) { return side->sint[(a >> 4) & 4095]; }
static inline int fcos(int a) { return side->sint[((a + 16384) >> 4) & 4095]; }
static void gte_setup(void) {
  s32 m[9] = { mr.x >> 2, mr.y >> 2, mr.z >> 2, -(mu.x >> 2), -(mu.y >> 2), -(mu.z >> 2), mf.x >> 2, mf.y >> 2, mf.z >> 2 };
  gte_set_rot(m); gte_set_trans(0, 0, 0);
  CTC2(24, (160 << 16) + 0x8000); CTC2(25, (120 << 16) + 0x8000); CTC2(26, H_FOCAL);
  CTC2(29, 43 * 4096 / 4096 * 0 + 0); CTC2(30, 0);
}
static void cam_from_angles(void) {
  int sy = fsin(yaw), cy = fcos(yaw), sp = fsin(pitch), cp = fcos(pitch);
  mf.x = sy * cp >> 14; mf.y = sp; mf.z = cy * cp >> 14;
  mu.x = -(sy * sp >> 14); mu.y = cp; mu.z = -(cy * sp >> 14);
  mr.x = -cy; mr.y = 0; mr.z = sy;
}
static void cam_commit(void) { camx = cpx >> 8; camy = cpy >> 8; camz = cpz >> 8; cpx6 = cpx >> 6; cpy6 = cpy >> 6; cpz6 = cpz >> 6; cpx8 = camx; cpy8 = camy; cpz8 = camz; gte_setup(); }
static inline s32 dotv(const V3 *a, s32 x, s32 y, s32 z) { return (a->x * x + a->y * y + a->z * z) >> 14; }
/* camera-space depth of a world point */
static inline int zdepth(s32 x, s32 y, s32 z) { return dotv(&mf, x - camx, y - camy, z - camz); }

/* ------------------------------------------------------------------------------------------- projection */
#define TIER_Q 18400   /* quarter-unit tier while every |component| < 4600 units (GTE IR range) */
static inline int absi(int v) { return v < 0 ? -v : v; }
typedef struct { s16 sx, sy, z, st; } PV;     /* z = real depth, 0 when not computable */
static inline void proj(s32 x, s32 y, s32 z, PV *o) {
  c_proj++;
  s32 dx = (x << 2) - cpx6, dy = (y << 2) - cpy6, dz = (z << 2) - cpz6; int sh = 2;
  if (absi(dx) >= TIER_Q || absi(dy) >= TIER_Q || absi(dz) >= TIER_Q) {   /* same rule as grid_tex fast path: shared vertices round identically */
    dx = x - cpx8; dy = y - cpy8; dz = z - cpz8; sh = 0;
    if (((u32)(dx + 18000) | (u32)(dy + 18000) | (u32)(dz + 18000)) >= 36000u) { o->z = 0; o->sx = 0; o->sy = 0; return; }
  }
  MTC2(0, (dx & 0xffff) | ((u32)dy << 16)); MTC2(1, dz);
  GTE(RTPS);
  u32 sxy = MFC2(14), sz = MFC2(19);
  o->sx = sxy; o->sy = sxy >> 16; o->z = sz >> sh;
}
/* classification of a screen quad from its 4 vertices */
#define Q_SKIP 0
#define Q_OK 1
#define Q_CLIP 2
static inline int qclass(const PV *a, const PV *b, const PV *c, const PV *d) {
  int mnz = a->z, mxz = a->z;
  if (b->z < mnz) mnz = b->z; if (b->z > mxz) mxz = b->z; if (c->z < mnz) mnz = c->z; if (c->z > mxz) mxz = c->z; if (d->z < mnz) mnz = d->z; if (d->z > mxz) mxz = d->z;
  if (mxz < NEAR) return Q_SKIP;
  if (mnz < NEAR) return Q_CLIP;
  int x0 = a->sx, x1 = x0, y0 = a->sy, y1 = y0;
  int v;
  v = b->sx; if (v < x0) x0 = v; if (v > x1) x1 = v; v = c->sx; if (v < x0) x0 = v; if (v > x1) x1 = v; v = d->sx; if (v < x0) x0 = v; if (v > x1) x1 = v;
  v = b->sy; if (v < y0) y0 = v; if (v > y1) y1 = v; v = c->sy; if (v < y0) y0 = v; if (v > y1) y1 = v; v = d->sy; if (v < y0) y0 = v; if (v > y1) y1 = v;
  if (x1 < 0 || x0 > 319 || y1 < 0 || y0 > 239) return Q_SKIP;
  if (x0 <= -1024 || x1 >= 1023 || y0 <= -1024 || y1 >= 1023 || x1 - x0 > 1020 || y1 - y0 > 508) return Q_CLIP;
  return Q_OK;
}
/* per-vertex outcode: OC_BAD when the vertex is behind the near plane or too far outside the screen for a polygon to be safe, OC_OFF bits for the four sides */
#define OC_BAD 33
#define OC_OFF 30
static inline int ocode(const PV *p) {
  int sx = p->sx, sy = p->sy, o = p->z < NEAR ? 1 : 0;
  if (sx < 0) o |= 2; else if (sx > 319) o |= 4;
  if (sy < 0) o |= 8; else if (sy > 239) o |= 16;
  if (sx < -400 || sx > 620 || sy < -200 || sy > 310) o |= 32;
  return o;
}
/* qclass plus the affine-error test (screen extent x depth spread against 2 px) of a clean quad */
static inline int qcls(const PV *a, const PV *b, const PV *c, const PV *d, int *aff) {
  int mnz = a->z, mxz = mnz, x0 = a->sx, x1 = x0, y0 = a->sy, y1 = y0, v;
  v = b->z; if (v < mnz) mnz = v; if (v > mxz) mxz = v; v = c->z; if (v < mnz) mnz = v; if (v > mxz) mxz = v; v = d->z; if (v < mnz) mnz = v; if (v > mxz) mxz = v;
  if (mxz < NEAR) return Q_SKIP;
  if (mnz < NEAR) return Q_CLIP;
  v = b->sx; if (v < x0) x0 = v; if (v > x1) x1 = v; v = c->sx; if (v < x0) x0 = v; if (v > x1) x1 = v; v = d->sx; if (v < x0) x0 = v; if (v > x1) x1 = v;
  v = b->sy; if (v < y0) y0 = v; if (v > y1) y1 = v; v = c->sy; if (v < y0) y0 = v; if (v > y1) y1 = v; v = d->sy; if (v < y0) y0 = v; if (v > y1) y1 = v;
  if (x1 < 0 || x0 > 319 || y1 < 0 || y0 > 239) return Q_SKIP;
  if (x0 <= -1024 || x1 >= 1023 || y0 <= -1024 || y1 >= 1023 || x1 - x0 > 1020 || y1 - y0 > 508) return Q_CLIP;
  int L = x1 - x0; if (y1 - y0 > L) L = y1 - y0;
  *aff = L * (mxz - mnz) <= 2 * errpx * (mxz + mnz);
  return Q_OK;
}
static inline u32 pxy(const PV *p) { return ((u32)(u16)p->sy << 16) | (u16)p->sx; }

/* ------------------------------------------------------------------------------------------- packets */
#define FT4_RAW 0x2D000000
#define FT4_MOD 0x2C000000
static u32 side_col(u32 rgb, int g) { /* modulate a 0xBBGGRR colour by g/128 */
  u32 r = (rgb & 255) * g >> 7, gg = ((rgb >> 8) & 255) * g >> 7, b = ((rgb >> 16) & 255) * g >> 7; return r | gg << 8 | b << 16; }

static inline void put_ft4(int bk, u32 cmd, const PV *a, const PV *b, const PV *c, const PV *d, u32 ua, u32 ub, u32 uc, u32 ud, u32 clut, u32 tp) {
  u32 *p = pnew(9); if (!p) return;
  p[1] = cmd; p[2] = pxy(a); p[3] = ua | (clut << 16); p[4] = pxy(b); p[5] = ub | (tp << 16); p[6] = pxy(c); p[7] = uc; p[8] = pxy(d); p[9] = ud; if (g_bg) link_bg(p, 9); else link_ot(bk, p, 9);
}
static int g_src;
#ifdef DEBUG_SRC
static const u32 dbgcol[16]={0,0x0000FF,0x00FF00,0xFF0000,0x00FFFF,0xFF00FF,0xFFFF00,0xFFFFFF,0x0080FF,0x80FF00,0xFF8000,0x8000FF,0x00FF80,0xFF0080,0x808080,0x404040};
#define DBGC(r) (g_src?dbgcol[g_src&15]:(r))
#else
#define DBGC(r) (r)
#endif
static inline void put_f4(int bk, int bg, u32 rgb, const PV *a, const PV *b, const PV *c, const PV *d) {
  u32 *p = pnew(5); if (!p) return;
  p[1] = 0x28000000 | DBGC(rgb); p[2] = pxy(a); p[3] = pxy(b); p[4] = pxy(c); p[5] = pxy(d); if (bg) link_bg(p, 5); else link_ot(bk, p, 5);
}
static inline void put_f3x(int bk, int bg, u32 rgb, u32 a, u32 b, u32 c) {
  u32 *p = pnew(4); if (!p) return;
  p[1] = 0x20000000 | DBGC(rgb); p[2] = a; p[3] = b; p[4] = c; if (bg) link_bg(p, 4); else link_ot(bk, p, 4);
}
static inline void put_ft3x(int bk, u32 cmd, u32 a, u32 ua, u32 b, u32 ub, u32 c, u32 uc, u32 clut, u32 tp) {
  u32 *p = pnew(7); if (!p) return;
  p[1] = cmd & ~0x08000000u; p[1] = (cmd & 0xFF000000) == FT4_RAW ? (0x25000000 | (cmd & 0xFFFFFF)) : (0x24000000 | (cmd & 0xFFFFFF));
  p[2] = a; p[3] = ua | (clut << 16); p[4] = b; p[5] = ub | (tp << 16); p[6] = c; p[7] = uc; if (g_bg) link_bg(p, 7); else link_ot(bk, p, 7);
}

/* ------------------------------------------------------------------------------------------- CPU clipper */
typedef struct { s32 x, y, z, u, v; } CV;
#define MAXCV 16
/* camera-space point at scale sh (2: quarter units, 0: units, -3: eighth) */
static void cpu_cam(s32 x, s32 y, s32 z, int sh, CV *o) {
  s32 dx, dy, dz;
  if (sh >= 0) { dx = (x << sh) - (cpx >> (8 - sh)); dy = (y << sh) - (cpy >> (8 - sh)); dz = (z << sh) - (cpz >> (8 - sh)); }
  else { dx = (x >> -sh) - (cpx >> (8 - sh)); dy = (y >> -sh) - (cpy >> (8 - sh)); dz = (z >> -sh) - (cpz >> (8 - sh)); }
  o->x = dotv(&mr, dx, dy, dz); o->y = dotv(&mu, dx, dy, dz); o->z = dotv(&mf, dx, dy, dz);
}
static const s16 PLN[5][3] = { { 0, 0, 1 }, { H_FOCAL, 0, 512 }, { -H_FOCAL, 0, 511 }, { 0, -H_FOCAL, 251 }, { 0, H_FOCAL, 260 } };
#define PLANE(pl, v, nz) (PLN[pl][0] * (v)->x + PLN[pl][1] * (v)->y + PLN[pl][2] * (v)->z - ((pl) == 0 ? (nz) : 0))
static inline s32 plane(int i, const CV *v, int nearz) { return PLN[i][0] * v->x + PLN[i][1] * v->y + PLN[i][2] * v->z - (i == 0 ? nearz : 0); }
static int clip_poly(const CV *in, int n, CV *out, int nearz, int useuv) {
  c_clip++;
  CV a[MAXCV], b[MAXCV]; int na = n, nb;
  s32 mn[5] = { 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff }, mx[5] = { -0x7fffffff, -0x7fffffff, -0x7fffffff, -0x7fffffff, -0x7fffffff };
  for (int i = 0; i < n; i++) { a[i] = in[i];
    for (int pl = 0; pl < 5; pl++) { s32 v = plane(pl, &in[i], nearz); if (v < mn[pl]) mn[pl] = v; if (v > mx[pl]) mx[pl] = v; } }
  for (int pl = 0; pl < 5; pl++) if (mx[pl] < 0) return 0;
  CV *src = a, *dst = b;
  for (int pl = 0; pl < 5; pl++) {
    if (mn[pl] >= 0) continue;
    nb = 0;
    for (int i = 0; i < na; i++) {
      const CV *p = &src[i], *q = &src[(i + 1) % na];
      s32 dp = plane(pl, p, nearz), dq = plane(pl, q, nearz);
      if (dp >= 0 && nb < MAXCV) dst[nb++] = *p;
      if ((dp >= 0) != (dq >= 0) && nb < MAXCV) {
        s32 num = dp, den = dp - dq;
        while (den > (1 << 18) || den < -(1 << 18)) { num >>= 1; den >>= 1; }
        if (den == 0) continue;
        s32 t = (num << 12) / den;
        CV o; o.x = p->x + (((q->x - p->x) * t) >> 12); o.y = p->y + (((q->y - p->y) * t) >> 12); o.z = p->z + (((q->z - p->z) * t) >> 12);
        if (useuv) { o.u = p->u + (((q->u - p->u) * t) >> 12); o.v = p->v + (((q->v - p->v) * t) >> 12); } else { o.u = 0; o.v = 0; }
        dst[nb++] = o;
      }
    }
    CV *tmp = src; src = dst; dst = tmp; na = nb; if (na < 3) return 0;
  }
  for (int i = 0; i < na; i++) out[i] = src[i];
  return na;
}
static inline u32 cpu_proj(const CV *v) {
  s32 z = v->z; if (z < 1) z = 1;
  s32 nx = H_FOCAL * v->x, ny = H_FOCAL * v->y;
  s32 sx = 160 + (nx + (nx < 0 ? -(z >> 1) : (z >> 1))) / z, sy = 120 - (ny + (ny < 0 ? -(z >> 1) : (z >> 1))) / z;
  if (sx < -352) sx = -352; if (sx > 671) sx = 671; if (sy < -131) sy = -131; if (sy > 380) sy = 380;
  return ((u32)(u16)sy << 16) | (u16)sx;
}
/* a textured polygon of up to 4 world points (order TL,TR,BR,BL as a ring) with uv in texels, clipped and emitted as a fan */
static void clip_emit_tex2(const V3 *w, const int *uv, int n, int bk, u32 cmd, u32 clut, u32 tp, int ubase, int vbase);
static void clip_emit_tex(const V3 *w, const int *uv /* u,v pairs */, int n, int bk, u32 cmd, u32 clut, u32 tp, int ubase, int vbase) { u32 t0 = TICKS8(); clip_emit_tex2(w, uv, n, bk, cmd, clut, tp, ubase, vbase); t_clipt += (TICKS8() - t0) & 0xffff; }
static void clip_emit_tex2(const V3 *w, const int *uv, int n, int bk, u32 cmd, u32 clut, u32 tp, int ubase, int vbase) {
#ifdef NOCLIP
  return;
#endif
  CV in[8], out[MAXCV]; int sh = 2;
  for (int i = 0; i < n; i++) { s32 dx = (w[i].x << 2) - (cpx >> 6), dy = (w[i].y << 2) - (cpy >> 6), dz = (w[i].z << 2) - (cpz >> 6);
    if (((u32)(dx + 32768) | (u32)(dy + 32768) | (u32)(dz + 32768)) >= 65536u) sh = 0; }
  for (int i = 0; i < n; i++) { cpu_cam(w[i].x, w[i].y, w[i].z, sh, &in[i]); in[i].u = uv[2 * i] << 8; in[i].v = uv[2 * i + 1] << 8; }
  int m = clip_poly(in, n, out, NEAR << sh, 1);
  if (m < 3) return;
  u32 sxy[MAXCV]; u32 uvw[MAXCV];
  for (int i = 0; i < m; i++) {
    sxy[i] = cpu_proj(&out[i]);
    int u = (out[i].u + 128) >> 8, v = (out[i].v + 128) >> 8; if (u < 0) u = 0; if (v < 0) v = 0; if (u > 255) u = 255; if (v > 255) v = 255;
    uvw[i] = (u + ubase) | ((v + vbase) << 8);
  }
  for (int i = 1; i + 1 < m; i++) put_ft3x(bk, cmd, sxy[0], uvw[0], sxy[i], uvw[i], sxy[i + 1], uvw[i + 1], clut, tp);
}
/* flat polygon, ring order, any n <= 8, sh: 2 quarter units, 0 units, -3 eighth (far plane) */
static void clip_emit_flat(const V3 *w, int n, int bk, int bg, u32 rgb, int sh) {
#ifdef NOCLIP
  return;
#endif
  CV in[8], out[MAXCV];
  if (sh == 2) for (int i = 0; i < n; i++) { s32 dx = (w[i].x << 2) - (cpx >> 6), dy = (w[i].y << 2) - (cpy >> 6), dz = (w[i].z << 2) - (cpz >> 6);
    if (((u32)(dx + 32768) | (u32)(dy + 32768) | (u32)(dz + 32768)) >= 65536u) sh = 0; }
  for (int i = 0; i < n; i++) cpu_cam(w[i].x, w[i].y, w[i].z, sh, &in[i]);
  int m = clip_poly(in, n, out, sh >= 0 ? NEAR << sh : NEAR >> -sh, 0);
  if (m < 3) return;
  u32 s[MAXCV]; for (int i = 0; i < m; i++) s[i] = cpu_proj(&out[i]);
  for (int i = 1; i + 1 < m; i++) put_f3x(bk, bg, rgb, s[0], s[i], s[i + 1]);
}
/* flat quad TL,TR,BL,BR (Z order) in the world; GTE when clean */
static void quad_flat2(V3 a, V3 b, V3 c, V3 d, u32 rgb, int key, int bg);
static void quad_flat(V3 a, V3 b, V3 c, V3 d, u32 rgb, int key, int bg) { u32 t0 = TICKS8(); quad_flat2(a, b, c, d, rgb, key, bg); t_qf += (TICKS8() - t0) & 0xffff; }
static void quad_flat2(V3 a, V3 b, V3 c, V3 d, u32 rgb, int key, int bg) {
  PV p[4]; proj(a.x, a.y, a.z, &p[0]); proj(b.x, b.y, b.z, &p[1]); proj(c.x, c.y, c.z, &p[2]); proj(d.x, d.y, d.z, &p[3]);
  int q = qclass(&p[0], &p[1], &p[2], &p[3]);
  if (q == Q_SKIP) return;
  if (q == Q_OK) { put_f4(bucket(key), bg, rgb, &p[0], &p[1], &p[2], &p[3]); return; }
  V3 w[4] = { a, b, d, c }; clip_emit_flat(w, 4, bucket(key), bg, rgb, 2);
}

/* 1 when a world quad (corners as given) is certainly not on screen */
static int quad_off2(V3 a, V3 b, V3 c, V3 d);
static int quad_off(V3 a, V3 b, V3 c, V3 d) { u32 t0 = TICKS8(); int r = quad_off2(a, b, c, d); t_qoff += (TICKS8() - t0) & 0xffff; return r; }
static int quad_off2(V3 a, V3 b, V3 c, V3 d) {
  PV p[4]; proj(a.x, a.y, a.z, &p[0]); proj(b.x, b.y, b.z, &p[1]); proj(c.x, c.y, c.z, &p[2]); proj(d.x, d.y, d.z, &p[3]);
  return qclass(&p[0], &p[1], &p[2], &p[3]) == Q_SKIP;
}
/* ------------------------------------------------------------------------------------------- textured rectangle */
static inline int ilog2n(int n) { return n >= 8 ? 3 : n >= 4 ? 2 : n >= 2 ? 1 : 0; }
static inline u32 clut_for(int z) {
#if FOG_TEX
  if (z > 4096) { int f = (z - 4096) * 8 / 8192; if (f > 7) f = 7; return CLUT(0, 480 + f); }
#endif
  return CLUT(0, 480);
}
static int zkey_center(V3 O, V3 A, V3 B) { return zdepth(O.x + ((A.x + B.x) >> 1), O.y + ((A.y + B.y) >> 1), O.z + ((A.z + B.z) >> 1)); }
/* draw parallelogram O, O+A, O+B, O+A+B textured with tile `slot`: u over A 0..ua1, v over B 0..vb1 (texels, inclusive end).
   nforce > 0: fixed subdivision; else by the 2 px error rule up to maxn.  key < -1000000: from the centre. */
static PV gvx[9][9]; static u16 gcur;
static V3 rO, rA, rB; static int rua1, rvb1, rbk, rub, rvb, rsmin, rforce; static u32 rcmd, rclut, rtp;
static inline PV *gv(int i, int j) {
  PV *p = &gvx[j][i];
  if (p->st != gcur) {
    proj(rO.x + ((rA.x * i) >> 3) + ((rB.x * j) >> 3), rO.y + ((rA.y * i) >> 3) + ((rB.y * j) >> 3), rO.z + ((rA.z * i) >> 3) + ((rB.z * j) >> 3), p);
    p->st = gcur; }
  return p;
}
static void emit_leaf(int i, int j, int si, int sj, PV *a, PV *b, PV *c, PV *d, int q) {
  int ua1 = rua1, vb1 = rvb1;
  int u0 = i == 8 ? ua1 : ((ua1 + 1) * i >> 3), u1 = (i + si) == 8 ? ua1 : ((ua1 + 1) * (i + si) >> 3);
  int v0 = j == 8 ? vb1 : ((vb1 + 1) * j >> 3), v1 = (j + sj) == 8 ? vb1 : ((vb1 + 1) * (j + sj) >> 3);
  c_leaf++;
  if (q == Q_OK) {
    put_ft4(rbk, rcmd, a, b, c, d, (rub + u0) | ((rvb + v0) << 8), (rub + u1) | ((rvb + v0) << 8), (rub + u0) | ((rvb + v1) << 8), (rub + u1) | ((rvb + v1) << 8), rclut, rtp);
  } else {
    c_cleaf++; V3 w[4]; int uv[8];
    #define WP(ii, jj, o) w[o].x = rO.x + ((rA.x * (ii)) >> 3) + ((rB.x * (jj)) >> 3); w[o].y = rO.y + ((rA.y * (ii)) >> 3) + ((rB.y * (jj)) >> 3); w[o].z = rO.z + ((rA.z * (ii)) >> 3) + ((rB.z * (jj)) >> 3);
    WP(i, j, 0) WP(i + si, j, 1) WP(i + si, j + sj, 2) WP(i, j + sj, 3)
    uv[0] = u0; uv[1] = v0; uv[2] = u1; uv[3] = v0; uv[4] = u1; uv[5] = v1; uv[6] = u0; uv[7] = v1;
    clip_emit_tex(w, uv, 4, rbk, rcmd, rclut, rtp, rub, rvb);
  }
}
static u32 c_nodes;
/* Adaptive subdivision over the 8 x 8 lattice, per axis: the affine error along an axis is (screen length along it) x (depth spread along it), so a wall
   that recedes only along its length is split along the length only (a binary tree, not a quadtree).  si, sj: size in lattice steps. */
static void rq(int i, int j, int si, int sj) {
  c_nodes++;
  PV *a = gv(i, j), *b = gv(i + si, j), *c = gv(i, j + sj), *d = gv(i + si, j + sj);
  int q = qclass(a, b, c, d);
  if (q == Q_SKIP) return;
  int su = 0, sv = 0;                                   /* split along u / along v */
  if (q == Q_CLIP) { su = si > 2; sv = sj > 2; }
  else if (!rforce) {
    int zs = a->z + b->z + c->z + d->z;
    int lu = absi(b->sx - a->sx), t = absi(b->sy - a->sy); if (t > lu) lu = t; t = absi(d->sx - c->sx); if (t > lu) lu = t; t = absi(d->sy - c->sy); if (t > lu) lu = t;
    int lv = absi(c->sx - a->sx); t = absi(c->sy - a->sy); if (t > lv) lv = t; t = absi(d->sx - b->sx); if (t > lv) lv = t; t = absi(d->sy - b->sy); if (t > lv) lv = t;
    int du = absi(a->z - b->z), dd = absi(c->z - d->z); if (dd > du) du = dd; int dv = absi(a->z - c->z); dd = absi(b->z - d->z); if (dd > dv) dv = dd;
    int lim = errpx * zs;                               /* 2 * errpx * (zmx + zmn), with zmx + zmn about zs / 2 */
    su = lu * du > lim && si > rsmin; sv = lv * dv > lim && sj > rsmin;
  }
  if (!su && !sv) { emit_leaf(i, j, si, sj, a, b, c, d, q); return; }
  int hi = su ? si >> 1 : si, hj = sv ? sj >> 1 : sj;
  rq(i, j, hi, hj); if (su) rq(i + hi, j, hi, hj); if (sv) { rq(i, j + hj, hi, hj); if (su) rq(i + hi, j + hj, hi, hj); }
}
static inline void projq(s32 dx, s32 dy, s32 dz, int sh, PV *o) {
  MTC2(0, (dx & 0xffff) | ((u32)dy << 16)); MTC2(1, dz);
  GTE(RTPS);
  u32 sxy = MFC2(14), sz = MFC2(19);
  o->sx = sxy; o->sy = sxy >> 16; o->z = sz >> sh;
}
/* Ground cell edges next to a finer neighbour: the boundary quad of the coarse cell gets the neighbour's vertices on its edge and is drawn as a
   fan around its centre, so both sides use identical vertices (no T-junction).  g_edge[side] = subdivision factor, sides: 0 -z, 1 +z, 2 -x, 3 +x. */
static int g_edge[4], g_edge_any;
static void fan_quad(int i, int j, int n, int st) {
  int pi[36], pj[36], m = 0;                               /* lattice coordinates in sixteenths of the cell */
  int i0 = i * st, i1 = i0 + st, j0 = j * st, j1 = j0 + st;
  int fz0 = j == 0 ? g_edge[0] : 1, fz1 = j == n - 1 ? g_edge[1] : 1, fx0 = i == 0 ? g_edge[2] : 1, fx1 = i == n - 1 ? g_edge[3] : 1;
  static const u8 L2[9] = { 0, 0, 1, 0, 2, 0, 0, 0, 3 };
  int sz0 = st >> L2[fz0], sz1 = st >> L2[fz1], sx0 = st >> L2[fx0], sx1 = st >> L2[fx1];
  for (int k = 0; k < fz0; k++) { pi[m] = 2 * (i0 + k * sz0); pj[m++] = 2 * j0; }
  for (int k = 0; k < fx1; k++) { pi[m] = 2 * i1; pj[m++] = 2 * (j0 + k * sx1); }
  for (int k = 0; k < fz1; k++) { pi[m] = 2 * (i1 - k * sz1); pj[m++] = 2 * j1; }
  for (int k = 0; k < fx0; k++) { pi[m] = 2 * i0; pj[m++] = 2 * (j1 - k * sx0); }
  /* apex: a corner touching no refined edge (it is then an end of unrefined edges only); none: fan around the centre */
  int ap = -1; { int cid[4] = { 0, fz0, fz0 + fx1, fz0 + fx1 + fz1 }, cex[4] = { (fz0 > 1) | (fx0 > 1), (fz0 > 1) | (fx1 > 1), (fx1 > 1) | (fz1 > 1), (fz1 > 1) | (fx0 > 1) };
    for (int k = 0; k < 4; k++) if (!cex[k]) { ap = cid[k]; break; } }
  int np = m; if (ap < 0) { ap = m; pi[m] = i0 + i1; pj[m++] = j0 + j1; }
  PV pv[36]; V3 w[36]; int uu[36], vv[36]; int ok = 1, mnz = 1 << 30, x0 = 9999, x1 = -9999, y0 = 9999, y1 = -9999;
  for (int k = 0; k < m; k++) {
    int a = pi[k], b = pj[k];
    V3 q = { rO.x + ((rA.x * a) >> 4) + ((rB.x * b) >> 4), rO.y + ((rA.y * a) >> 4) + ((rB.y * b) >> 4), rO.z + ((rA.z * a) >> 4) + ((rB.z * b) >> 4) };
    PV *o = &pv[k]; proj(q.x, q.y, q.z, o); w[k] = q;
    uu[k] = a == 16 ? rua1 : (a * (rua1 + 1)) >> 4; vv[k] = b == 16 ? rvb1 : (b * (rvb1 + 1)) >> 4;
    if (o->z < mnz) mnz = o->z; if (o->sx < x0) x0 = o->sx; if (o->sx > x1) x1 = o->sx; if (o->sy < y0) y0 = o->sy; if (o->sy > y1) y1 = o->sy;
  }
  if (mnz >= NEAR && (x1 < 0 || x0 > 319 || y1 < 0 || y0 > 239)) return;
  if (mnz < NEAR || x0 <= -1000 || x1 >= 1000 || y0 <= -1000 || y1 >= 1000 || x1 - x0 > 1000 || y1 - y0 > 500) ok = 0;
  for (int k = 0; k < np; k++) {
    int k2 = k + 1 == np ? 0 : k + 1;
    if (k == ap || k2 == ap) continue;                    /* the apex's own edges are not drawn as triangles */
    c_leaf++;
    if (ok) put_ft3x(rbk, rcmd, pxy(&pv[ap]), (rub + uu[ap]) | ((rvb + vv[ap]) << 8), pxy(&pv[k]), (rub + uu[k]) | ((rvb + vv[k]) << 8), pxy(&pv[k2]), (rub + uu[k2]) | ((rvb + vv[k2]) << 8), rclut, rtp);
    else { V3 tw[3] = { w[ap], w[k], w[k2] }; int tuv[6] = { uu[ap], vv[ap], uu[k], vv[k], uu[k2], vv[k2] }; c_cleaf++; clip_emit_tex(tw, tuv, 3, rbk, rcmd, rclut, rtp, rub, rvb); }
  }
}
static void grid_tex(int n) {
  PV row[2][9]; int st = 8 / n, uu[9], vv[9];
  for (int i = 0; i <= n; i++) { uu[i] = i == n ? rua1 : (rua1 + 1) * i / n; vv[i] = i == n ? rvb1 : (rvb1 + 1) * i / n; }
  /* incremental inputs when the whole rectangle is within the quarter-unit range */
  s32 m0 = absi(rO.x - camx) + absi(rA.x) + absi(rB.x), m1 = absi(rO.y - camy) + absi(rA.y) + absi(rB.y), m2 = absi(rO.z - camz) + absi(rA.z) + absi(rB.z);
  int fast = m0 < 4600 && m1 < 4600 && m2 < 4600;
  s32 ax = ((rA.x * st) >> 3) << 2, ay = ((rA.y * st) >> 3) << 2, az = ((rA.z * st) >> 3) << 2, bx = ((rB.x * st) >> 3) << 2, by = ((rB.y * st) >> 3) << 2, bz = ((rB.z * st) >> 3) << 2;
  s32 x0 = (rO.x << 2) - cpx6, y0 = (rO.y << 2) - cpy6, z0 = (rO.z << 2) - cpz6;
  if (fast) { s32 x = x0, y = y0, z = z0; for (int i = 0; i <= n; i++) { projq(x, y, z, 2, &row[0][i]); x += ax; y += ay; z += az; } }
  else for (int i = 0; i <= n; i++) proj(rO.x + ((rA.x * (i * st)) >> 3), rO.y + ((rA.y * (i * st)) >> 3), rO.z + ((rA.z * (i * st)) >> 3), &row[0][i]);
  for (int j = 0; j < n; j++) {
    int jj = (j + 1) * st; PV *r0 = row[j & 1], *r1 = row[(j + 1) & 1];
    if (fast) { s32 x = x0 + bx * (j + 1), y = y0 + by * (j + 1), z = z0 + bz * (j + 1); for (int i = 0; i <= n; i++) { projq(x, y, z, 2, &r1[i]); x += ax; y += ay; z += az; } }
    else for (int i = 0; i <= n; i++) proj(rO.x + ((rA.x * (i * st)) >> 3) + ((rB.x * jj) >> 3), rO.y + ((rA.y * (i * st)) >> 3) + ((rB.y * jj) >> 3), rO.z + ((rA.z * (i * st)) >> 3) + ((rB.z * jj) >> 3), &r1[i]);
    u8 o0[9], o1[9]; for (int i = 0; i <= n; i++) { o0[i] = ocode(&r0[i]); o1[i] = ocode(&r1[i]); }
    u32 va = (rvb + vv[j]) << 8, vc = (rvb + vv[j + 1]) << 8;
    for (int i = 0; i < n; i++) {
      if (g_edge_any && ((j == 0 && g_edge[0] > 1) || (j == n - 1 && g_edge[1] > 1) || (i == 0 && g_edge[2] > 1) || (i == n - 1 && g_edge[3] > 1))) { fan_quad(i, j, n, st); continue; }
      PV *a = &r0[i], *b = &r0[i + 1], *c = &r1[i], *d = &r1[i + 1];
      int ca = o0[i], cb = o0[i + 1], cc = o1[i], cd = o1[i + 1];
      if (!((ca | cb | cc | cd) & OC_BAD)) {              /* clean quad: no clipping needed, only the off-screen test */
        if (ca & cb & cc & cd & OC_OFF) continue;
        c_leaf++; u32 ua = rub + uu[i], ub = rub + uu[i + 1];
        put_ft4(rbk, rcmd, a, b, c, d, ua | va, ub | va, ua | vc, ub | vc, rclut, rtp);
        continue;
      }
      int q = qclass(a, b, c, d); if (q == Q_SKIP) continue;
      c_leaf++;
      if (q == Q_OK) {
        put_ft4(rbk, rcmd, a, b, c, d, (rub + uu[i]) | ((rvb + vv[j]) << 8), (rub + uu[i + 1]) | ((rvb + vv[j]) << 8), (rub + uu[i]) | ((rvb + vv[j + 1]) << 8), (rub + uu[i + 1]) | ((rvb + vv[j + 1]) << 8), rclut, rtp);
      } else {
        c_cleaf++; V3 w[4]; int uv[8]; int ii = i * st, i2 = (i + 1) * st, j0 = j * st, j2 = jj;
        WP(ii, j0, 0) WP(i2, j0, 1) WP(i2, j2, 2) WP(ii, j2, 3)
        uv[0] = uu[i]; uv[1] = vv[j]; uv[2] = uu[i + 1]; uv[3] = vv[j]; uv[4] = uu[i + 1]; uv[5] = vv[j + 1]; uv[6] = uu[i]; uv[7] = vv[j + 1];
        clip_emit_tex(w, uv, 4, rbk, rcmd, rclut, rtp, rub, rvb);
      }
    }
  }
}
/* draw the parallelogram O, O+A, O+B, O+A+B textured with tile `slot`: u over A 0..ua1, v over B 0..vb1 (texels, inclusive end).
   Adaptive quadtree over an 8 x 8 lattice (lazy shared vertices): a piece is a single quad when its affine error is under ~2 px.
   nforce > 0: fixed n x n.  key < -1000000: depth of the centre.  maxn: finest n allowed. */
static void rect_tex2(V3 O, V3 A, V3 B, int slot, int ua1, int vb1, u32 cmd, int key, int nforce, int maxn);
static void rect_tex(V3 O, V3 A, V3 B, int slot, int ua1, int vb1, u32 cmd, int key, int nforce, int maxn) { u32 t0 = TICKS8(); rect_tex2(O, A, B, slot, ua1, vb1, cmd, key, nforce, maxn); t_rect += (TICKS8() - t0) & 0xffff; }
static void rect_tex2(V3 O, V3 A, V3 B, int slot, int ua1, int vb1, u32 cmd, int key, int nforce, int maxn) {
  c_rect++;
  if (key < -1000000) key = zkey_center(O, A, B);
  rO = O; rA = A; rB = B; rua1 = ua1; rvb1 = vb1; rcmd = cmd; rbk = bucket(key); rforce = nforce;
  int pg = slot >> 6, k = slot & 63; rub = (k & 7) * 32; rvb = (k >> 3) * 32;
  rtp = TPAGE(320 + 128 * (pg % 5), 256 * (pg / 5), 1, 0); rclut = clut_for(key);
  rsmin = nforce ? 8 / nforce : 8 / maxn;
  if (++gcur == 0) { for (int j = 0; j < 9; j++) for (int i = 0; i < 9; i++) gvx[j][i].st = 0; gcur = 1; }
  if (nforce) grid_tex(nforce); else rq(0, 0, 8, 8);
}

/* ------------------------------------------------------------------------------------------- wall lattice */
/* One wall side as a lattice of vertices (L columns x nr rows of 1 cell, last row shorter), every vertex projected once and shared by the
   cells around it.  A cell that is clean and whose affine error is small is one quad; anything else goes through the general rect_tex / quad_flat. */
#define WMAXC 8
#define WMAXR 9
static PV wvx[WMAXR + 1][WMAXC + 1]; static u16 wcur; static V3 wO, wA; static int wtot;
static inline PV *wv(int i, int j) {
  PV *p = &wvx[j][i];
  if (p->st != wcur) { int yy = j * CELL; if (yy > wtot) yy = wtot; proj(wO.x + wA.x * i, wO.y - yy, wO.z + wA.z * i, p); p->st = wcur; }
  return p;
}
static void wall_grid(V3 O, V3 A, int L, int total, const u16 *bt, int fkey, u32 g) {
  u32 rgb = g | g << 8 | g << 16; int bk = bucket(fkey), nr = (total + CELL - 1) / CELL; u32 clut = clut_for(fkey);
  wO = O; wA = A; wtot = total; if (++wcur == 0) { for (int j = 0; j <= WMAXR; j++) for (int i = 0; i <= WMAXC; i++) wvx[j][i].st = 0; wcur = 1; }
  for (int i = 0; i < L; i++) {
    u16 t = bt[i > 3 ? 3 : i]; if (t == 0xffff) continue;
    int mesh = side->mesh[t], slot = t, pg = slot >> 6, k = slot & 63, ub = (k & 7) * 32, vb = (k >> 3) * 32; u32 tp = TPAGE(320 + 128 * (pg % 5), 256 * (pg / 5), 1, 0);
    for (int j = 0; j < nr; j++) {
      int seg = total - j * CELL; if (seg > CELL) seg = CELL;
      int vb1 = seg == CELL ? 31 : (seg * 32 >> 10) - 1; if (vb1 < 0) vb1 = 0;
      PV *a = wv(i, j), *b = wv(i + 1, j), *c = wv(i, j + 1), *d = wv(i + 1, j + 1); int aff = 0;
      int q = qcls(a, b, c, d, &aff);
      if (q == Q_SKIP) continue;
      if (q == Q_OK && (aff || mesh)) {
        if (mesh) put_f4(bk, 0, side_col(side->avgcol[t], g), a, b, c, d);
        else put_ft4(bk, FT4_MOD | rgb, a, b, c, d, ub | (vb << 8), (ub + 31) | (vb << 8), ub | ((vb + vb1) << 8), (ub + 31) | ((vb + vb1) << 8), clut, tp);
        continue;
      }
      V3 Oc = { O.x + A.x * i, O.y - j * CELL, O.z + A.z * i }, Bc = { 0, -seg, 0 };
      if (mesh) { V3 p1 = { Oc.x + A.x, Oc.y, Oc.z + A.z }; quad_flat(Oc, p1, (V3){ Oc.x, Oc.y - seg, Oc.z }, (V3){ p1.x, Oc.y - seg, p1.z }, side_col(side->avgcol[t], g), fkey, 0); }
      else rect_tex(Oc, A, Bc, t, 31, vb1, FT4_MOD | rgb, fkey, 0, 8);
    }
  }
}
/* ------------------------------------------------------------------------------------------- sky */
static void sky_draw(void) {
  /* 9 bands: level lines at sines {9000,5000,2500,800,0,-300,-1200,-3000}/16384.  A band is drawn as everything below its upper line. */
  static const s16 lv[8] = { 9000, 5000, 2500, 800, 0, -300, -1200, -3000 };
  u32 *p = pnew(5);
  if (p) { p[1] = 0x28000000 | side->sky9[0]; p[2] = XY(0, 0); p[3] = XY(320, 0); p[4] = XY(0, 240); p[5] = XY(320, 240); link_bg(p, 5); }
  for (int k = 0; k < 8; k++) {
    int uy = mu.y < 64 ? 64 : mu.y;
    /* sy = 120 - H*(L - f.y)/u.y  (r.y = 0: no roll) */
    s32 num = (s32)H_FOCAL * (lv[k] - mf.y); s32 sy = 120 - num / uy;
    if (sy < -2000) sy = -2000; if (sy > 2000) sy = 2000;
    if (sy >= 240) continue;
    if (sy < 0) sy = 0;
    p = pnew(5); if (!p) return;
    p[1] = 0x28000000 | side->sky9[k + 1]; p[2] = XY(0, sy); p[3] = XY(320, sy); p[4] = XY(0, 240); p[5] = XY(320, 240); link_bg(p, 5);
  }
}

/* ------------------------------------------------------------------------------------------- ground */
static inline int slot_of(u16 t) { return t; }
static inline u32 flat_col(int m, int l, int f) { return side->flat[((m & 15) * 4 + l) * 4 + f]; }
static u32 ground_stat[4];
static void ground_cell(int cx, int cz, int ring) {
#ifdef NOFAN
  g_edge_any = 0;
#endif
  u16 t = ctex[cx * 128 + cz]; if (t == 0xffff) return;
  V3 O = { cx * CELL, 0, cz * CELL }, A = { CELL, 0, 0 }, B = { 0, 0, CELL };
  int far = ring >= 7;
  if (far) {
#ifndef FAR_FLAT_GROUND
    return;
#endif
    V3 p0 = O, p1 = { O.x + CELL, 0, O.z }, p2 = { O.x, 0, O.z + CELL }, p3 = { O.x + CELL, 0, O.z + CELL };
    g_src=10, quad_flat(p0, p1, p2, p3, side->avgcol[t], 0, 1); return;
  }
  static const u8 ntab[4][7] = { { 8, 4, 4, 2, 2, 1, 1 }, { 8, 4, 2, 2, 1, 1, 1 }, { 4, 4, 2, 2, 1, 1, 1 }, { 4, 2, 2, 1, 1, 1, 1 } };
  int n = ntab[lod][ring];
  g_edge_any = 0;
  for (int sd = 0; sd < 4; sd++) {
    int nx = cx + (sd == 2 ? -1 : sd == 3 ? 1 : 0), nz = cz + (sd == 0 ? -1 : sd == 1 ? 1 : 0); g_edge[sd] = 1;
    if ((unsigned)nx > 127 || (unsigned)nz > 127 || ctex[nx * 128 + nz] == 0xffff) continue;
    int ni = nx * 128 + nz; if (!(side->gmask[ni >> 3] >> (ni & 7) & 1)) continue;
    int dx = nx - (camx >> 10), dz = nz - (camz >> 10); dx = absi(dx); dz = absi(dz); int nr = dx > dz ? dx : dz;
    if (nr >= 7) continue;
    int nn = ntab[lod][nr]; if (nn > n && !NOFANX) { g_edge[sd] = nn / n;  /* power of two */ g_edge_any = 1; }
  }
  g_bg = 1; rect_tex(O, A, B, t, 31, 31, FT4_RAW, 0, n, n); g_bg = 0; g_edge_any = 0;
}

/* ------------------------------------------------------------------------------------------- visibility */
static inline int in_view(s32 x, s32 y, s32 z, int r) {
  s32 dx = x - camx, dy = y - camy, dz = z - camz;
  s32 cx = dotv(&mr, dx, dy, dz), cy = dotv(&mu, dx, dy, dz), cz = dotv(&mf, dx, dy, dz);
  if (cz < -r) return 0;
  s32 rx = r * 242, ry = r * 218;
  if (H_FOCAL * cx - 161 * cz > rx || -H_FOCAL * cx - 161 * cz > rx) return 0;
  if (H_FOCAL * cy - 121 * cz > ry || -H_FOCAL * cy - 121 * cz > ry) return 0;
  return 1;
}
static int reach = REACH;
static void ground_draw(void) {
  int ccx = camx >> 10, ccz = camz >> 10;
  for (int dz = -12; dz <= 12; dz++) for (int dx = -12; dx <= 12; dx++) {
    int cx = ccx + dx, cz = ccz + dz;
    if ((unsigned)cx > 127 || (unsigned)cz > 127) continue;
    int i = cx * 128 + cz; if (!(side->gmask[i >> 3] >> (i & 7) & 1)) continue;
    int ring = (dx < 0 ? -dx : dx) > (dz < 0 ? -dz : dz) ? (dx < 0 ? -dx : dx) : (dz < 0 ? -dz : dz);
    c_cullcell++; if (!in_view(cx * CELL + 512, 0, cz * CELL + 512, 740)) continue;
    c_cells++;
#ifndef NOGCELL
    { u32 t0_ = TICKS8(); u32 l0_ = c_leaf, p0_ = c_proj; ground_cell(cx, cz, ring); if (dbgcell && ring <= 2) { dbg("cell "); ddec(cx); ddec(cz); ddec(ring); ddec((TICKS8() - t0_) & 0xffff); ddec(c_leaf - l0_); ddec(c_proj - p0_); dbg("\n"); } t_gc += (TICKS8() - t0_) & 0xffff; if (ring <= 1) t_gc01 += (TICKS8() - t0_) & 0xffff; }
#endif
  }
}
/* one big flat island at y 0 under everything (far shift 3) */
static void island_draw(u32 rgb) {
  V3 w[4] = { { 0, 0, 0 }, { 131072, 0, 0 }, { 131072, 0, 131072 }, { 0, 0, 131072 } };
  clip_emit_flat(w, 4, 0, 1, rgb, -3);
}

/* ------------------------------------------------------------------------------------------- city items */
static const u8 lightg[4] = { 74, 92, 110, 128 };
#define st_box ((u16 *)SF_ST)
#define st_ramp ((u16 *)(SF_ST + 6144))
#define st_tree ((u16 *)(SF_ST + 8192))
static u16 stamp;
static inline int dist_rect(int X0, int Z0, int X1, int Z1) {       /* Chebyshev distance of the camera to a rectangle */
  int dx = X0 - camx > camx - X1 ? X0 - camx : camx - X1; if (dx < 0) dx = 0;
  int dz = Z0 - camz > camz - Z1 ? Z0 - camz : camz - Z1; if (dz < 0) dz = 0;
  return dx > dz ? dx : dz;
}
/* A distant wall as ONE textured quad: the 32x32 tile repeats through the GPU texture window (E2h, mask 0x1C = 32 texels), L times along
   and once a cell up.  The window is set and reset by two command packets around the polygon (list order: set, polygon, reset). */
static void far_wall_tex(V3 a0, V3 a1, int bot, u16 t, int L, int total, int key, u32 rgb) {
  PV p[4]; proj(a0.x, a0.y, a0.z, &p[0]); proj(a1.x, a1.y, a1.z, &p[1]); proj(a0.x, bot, a0.z, &p[2]); proj(a1.x, bot, a1.z, &p[3]);
  int q = qclass(&p[0], &p[1], &p[2], &p[3]);
  if (q == Q_SKIP) return;
  if (q == Q_CLIP) { quad_flat(a0, a1, (V3){ a0.x, bot, a0.z }, (V3){ a1.x, bot, a1.z }, side_col(side->avgcol[t], rgb & 255), key, 0); return; }
  int pg = t >> 6, k = t & 63, ub = (k & 7) * 32, vb = (k >> 3) * 32;
  int u1 = L * 32 - 1; if (u1 > 255) u1 = 255; int v1 = (total >> 5) - 1; if (v1 > 255) v1 = 255; if (v1 < 0) v1 = 0;
  u32 *pr = pnew(1), *pp = pnew(9), *ps = pnew(1); if (!pr || !pp || !ps) return;
  int bk = bucket(key);
  pr[1] = 0xE2000000; link_ot(bk, pr, 1);
  pp[1] = FT4_MOD | rgb; pp[2] = pxy(&p[0]); pp[3] = 0 | (clut_for(key) << 16); pp[4] = pxy(&p[1]); pp[5] = u1 | (TPAGE(320 + 128 * (pg % 5), 256 * (pg / 5), 1, 0) << 16);
  pp[6] = pxy(&p[2]); pp[7] = v1 << 8; pp[8] = pxy(&p[3]); pp[9] = u1 | (v1 << 8); link_ot(bk, pp, 9);
  ps[1] = 0xE2000000 | 0x1C | (0x1C << 5) | (((ub >> 3) & 0x1C) << 10) | (((vb >> 3) & 0x1C) << 15); link_ot(bk, ps, 1);
}
static void draw_box(int k) {
  const Box *b = &boxes[k]; c_box++;
  int X0 = b->x0 * CELL, Z0 = b->z0 * CELL, X1 = b->x1 * CELL, Z1 = b->z1 * CELL, h = b->h, bot = b->base * 64, hid = b->mat >> 4, mat = b->mat & 15;
  int dd = dist_rect(X0, Z0, X1, Z1);
  if (dd > reach) return;
  int w = X1 - X0, d = Z1 - Z0, ww = w > d ? w : d, hh = h - bot;
  if (!in_view((X0 + X1) >> 1, (h + bot) >> 1, (Z0 + Z1) >> 1, ww * 3 / 4 * 11 / 10 + (hh > 0 ? hh : -hh) / 2 + 64)) return;
  int isdeck = bot != 0;
  /* top */
  if (camy > h) {
    int key = zdepth((X0 + X1) >> 1, h, (Z0 + Z1) >> 1);
    if (dd > TEX_FAR || camy > TEX_TOP) {
      int mx = (b->x0 + b->x1) >> 1, mz = (b->z0 + b->z1) >> 1; u16 t = isdeck ? dtex[mx * 128 + mz] : ctex[mx * 128 + mz];
      u32 col = t == 0xffff ? flat_col(mat, 3, 0) : side->avgcol[t];
      g_src=1, quad_flat((V3){ X0, h, Z0 }, (V3){ X1, h, Z0 }, (V3){ X0, h, Z1 }, (V3){ X1, h, Z1 }, col, key, 0);
    } else {
      int maxn = (b->x1 - b->x0) * (b->z1 - b->z0) > 4 ? 2 : 4;
      if (!quad_off((V3){ X0, h, Z0 }, (V3){ X1, h, Z0 }, (V3){ X0, h, Z1 }, (V3){ X1, h, Z1 }))
      for (int cx = b->x0; cx < b->x1; cx++) for (int cz = b->z0; cz < b->z1; cz++) {
        u16 t = isdeck ? dtex[cx * 128 + cz] : ctex[cx * 128 + cz]; if (t == 0xffff) continue;
        rect_tex((V3){ cx * CELL, h, cz * CELL }, (V3){ CELL, 0, 0 }, (V3){ 0, 0, CELL }, t, 31, 31, FT4_RAW, key, 0, maxn);
      }
    }
  }
  if (isdeck && camy < bot) {
    int key = zdepth((X0 + X1) >> 1, bot, (Z0 + Z1) >> 1);
    g_src=3, quad_flat((V3){ X0, bot, Z0 }, (V3){ X1, bot, Z0 }, (V3){ X0, bot, Z1 }, (V3){ X1, bot, Z1 }, flat_col(mat, 0, 0), key, 0);
  }
  int total = h - bot; if (total <= 0) return;
  for (int sd = 0; sd < 4; sd++) {
    /* sides -z,+x,+z,-x ; hidden bits: +x 1, -x 2, +z 4, -z 8 (after >>4) */
    static const u8 hidbit[4] = { 8, 1, 4, 2 }; static const u8 light[4] = { 1, 2, 1, 0 };
    if (hid & hidbit[sd]) continue;
    int vis = sd == 0 ? camz < Z0 : sd == 1 ? camx > X1 : sd == 2 ? camz > Z1 : camx < X0;
    if (!vis) continue;
    int alongx = (sd == 0 || sd == 2); int L = alongx ? b->x1 - b->x0 : b->z1 - b->z0;
    int px = sd == 1 ? X1 : X0, pz = sd == 2 ? Z1 : Z0;
    int fd = alongx ? (camz < Z0 ? Z0 - camz : camz - Z1) : (camx < X0 ? X0 - camx : camx - X1); if (fd < 0) fd = 0;
    int far = fd > TEX_WALL_FAR;
    int fkey = zdepth(alongx ? (X0 + X1) >> 1 : px, (h + bot) >> 1, alongx ? pz : (Z0 + Z1) >> 1);
    u32 g = lightg[light[sd]]; u32 rgb = g | g << 8 | g << 16;
    if (far) {
      u16 t = btex[16 * k + 4 * sd + (L > 2 ? 1 : 0)]; u32 col = t == 0xffff ? flat_col(mat, light[sd], 0) : side_col(side->avgcol[t], g);
      V3 a0 = alongx ? (V3){ X0, h, pz } : (V3){ px, h, Z0 }, a1 = alongx ? (V3){ X1, h, pz } : (V3){ px, h, Z1 };
      if (t != 0xffff && !side->mesh[t]) { far_wall_tex(a0, a1, bot, t, L, total, fkey, rgb); continue; }
      g_src=2, quad_flat(a0, a1, (V3){ a0.x, bot, a0.z }, (V3){ a1.x, bot, a1.z }, col, fkey, 0);
      continue;
    }
    { V3 fa = alongx ? (V3){ X0, h, pz } : (V3){ px, h, Z0 }, fb = alongx ? (V3){ X1, h, pz } : (V3){ px, h, Z1 };
      if (quad_off(fa, fb, (V3){ fa.x, bot, fa.z }, (V3){ fb.x, bot, fb.z })) continue; }
    if (L <= WMAXC && (total + CELL - 1) / CELL <= WMAXR) {
      V3 O = alongx ? (V3){ X0, h, pz } : (V3){ px, h, Z0 }, A = alongx ? (V3){ CELL, 0, 0 } : (V3){ 0, 0, CELL };
      wall_grid(O, A, L, total, &btex[16 * k + 4 * sd], fkey, g); continue;
    }
    for (int i = 0; i < L; i++) {
      u16 t = btex[16 * k + 4 * sd + (i > 3 ? 3 : i)]; if (t == 0xffff) continue;
      for (int j = 0; j * CELL < total; j++) {
        int seg = total - j * CELL; if (seg > CELL) seg = CELL;
        int vb1 = seg == CELL ? 31 : (seg * 32 >> 10) - 1; if (vb1 < 0) vb1 = 0;
        V3 O = alongx ? (V3){ X0 + i * CELL, h - j * CELL, pz } : (V3){ px, h - j * CELL, Z0 + i * CELL };
        V3 A = alongx ? (V3){ CELL, 0, 0 } : (V3){ 0, 0, CELL }, B = { 0, -seg, 0 };
        if (side->mesh[t]) { V3 p1 = { O.x + A.x, O.y, O.z + A.z }; g_src=4, quad_flat(O, p1, (V3){ O.x, O.y - seg, O.z }, (V3){ p1.x, O.y - seg, p1.z }, side_col(side->avgcol[t], g), fkey, 0); continue; }
        rect_tex(O, A, B, t, 31, vb1, FT4_MOD | rgb, fkey, 0, 8);
      }
    }
  }
}
static inline int ramp_y(const Ramp *r, int x, int z) {
  int d = r->dir & 7, X0 = r->x0 * CELL, Z0 = r->z0 * CELL, len, pos;
  switch (d) {
    case 2: len = (r->z1 - r->z0) * CELL; pos = z - Z0; break;
    case 3: len = (r->x1 - r->x0) * CELL; pos = x - X0; break;
    case 4: len = (r->z1 - r->z0) * CELL; pos = r->z1 * CELL - z; break;
    case 5: len = (r->x1 - r->x0) * CELL; pos = r->x1 * CELL - x; break;
    default: return r->h0;
  }
  return r->h0 + (r->h1 - r->h0) * pos / len;
}
static inline int col_near(u32 a, u32 b) {
  int dr = (int)(a & 255) - (int)(b & 255), dg = (int)((a >> 8) & 255) - (int)((b >> 8) & 255), db = (int)((a >> 16) & 255) - (int)((b >> 16) & 255);
  return absi(dr) < 8 && absi(dg) < 8 && absi(db) < 8;
}
/* flat quads in each cell's own average colour, runs of near-equal colour along z merged into one quad (a ramp is not one tile) */
static void ramp_flat(const Ramp *r, int isdeck, int mat, int key, int sunk) {
  (void)mat;
  for (int cx = r->x0; cx < r->x1; cx++) {
    int cz = r->z0;
    while (cz < r->z1) {
      u16 t = isdeck ? dtex[cx * 128 + cz] : ctex[cx * 128 + cz];
      if (t == 0xffff) { cz++; continue; }
      u32 col = side->avgcol[t]; int e = cz + 1;
      while (e < r->z1) { u16 t2 = isdeck ? dtex[cx * 128 + e] : ctex[cx * 128 + e]; if (t2 == 0xffff || !col_near(col, side->avgcol[t2])) break; e++; }
      int xa = cx * CELL, xb = xa + CELL, za = cz * CELL, zb = e * CELL;
      g_src=5, quad_flat((V3){ xa, ramp_y(r, xa, za), za }, (V3){ xb, ramp_y(r, xb, za), za }, (V3){ xa, ramp_y(r, xa, zb), zb }, (V3){ xb, ramp_y(r, xb, zb), zb }, col, key, sunk);
      cz = e;
    }
  }
}
static void draw_ramp(int k) {
  const Ramp *r = &ramps[k]; c_ramp++;
  int X0 = r->x0 * CELL, Z0 = r->z0 * CELL, X1 = r->x1 * CELL, Z1 = r->z1 * CELL, mat = r->mat & 15, isdeck = r->dir & 0x80;
  int dd = dist_rect(X0, Z0, X1, Z1); if (dd > reach) return;
  int w = X1 - X0, d = Z1 - Z0, ww = w > d ? w : d, ym = (r->h0 + r->h1) >> 1, hh = r->h1 - r->h0; if (hh < 0) hh = -hh;
  if (!in_view((X0 + X1) >> 1, ym, (Z0 + Z1) >> 1, ww * 3 / 4 * 11 / 10 + hh / 2 + 1100)) return;
  /* key -2: farthest corner */
  int kz = 0, t0;
  t0 = zdepth(X0, ramp_y(r, X0, Z0), Z0); if (t0 > kz) kz = t0; t0 = zdepth(X1, ramp_y(r, X1, Z0), Z0); if (t0 > kz) kz = t0;
  t0 = zdepth(X0, ramp_y(r, X0, Z1), Z1); if (t0 > kz) kz = t0; t0 = zdepth(X1, ramp_y(r, X1, Z1), Z1); if (t0 > kz) kz = t0;
  int key = kz;
  int sunk = !isdeck && r->h0 <= 0 && r->h1 <= 0;
  if (sunk) { g_bg = 1; if (mat == 6) mat = 5; }
  if (dd > TEX_FAR || camy > TEX_TOP) {
    ramp_flat(r, isdeck, mat, key, sunk);
  } else {
    int maxn = (r->x1 - r->x0) * (r->z1 - r->z0) > 16 ? 2 : 4;
    if (sunk) ramp_flat(r, isdeck, mat, key, sunk);          /* underlay in the BG list: a T-junction sliver between textured pieces shows the tile colour, not the island */
    for (int cx = r->x0; cx < r->x1; cx++) for (int cz = r->z0; cz < r->z1; cz++) {
      u16 t = isdeck ? dtex[cx * 128 + cz] : ctex[cx * 128 + cz]; if (t == 0xffff) continue;
      int x = cx * CELL, z = cz * CELL, y0 = ramp_y(r, x, z);
      rect_tex((V3){ x, y0, z }, (V3){ CELL, ramp_y(r, x + CELL, z) - y0, 0 }, (V3){ 0, ramp_y(r, x, z + CELL) - y0, CELL }, t, 31, 31, FT4_RAW, key, 0, maxn);
    }
  }
  /* sides: per cell along each edge, against the ground beside (cell table) */
  for (int e = 0; e < 4; e++) {
    int alongx = e == 0 || e == 2; int L = alongx ? r->x1 - r->x0 : r->z1 - r->z0;
    for (int i = 0; i < L; i++) {
      int cx, cz, nx, nz, ax, az, bx, bz;
      if (e == 0) { cx = r->x0 + i; cz = r->z0; nx = cx; nz = cz - 1; ax = cx * CELL; bx = ax + CELL; az = bz = Z0; }
      else if (e == 2) { cx = r->x0 + i; cz = r->z1 - 1; nx = cx; nz = cz + 1; ax = cx * CELL; bx = ax + CELL; az = bz = Z1; }
      else if (e == 1) { cz = r->z0 + i; cx = r->x1 - 1; nz = cz; nx = cx + 1; az = cz * CELL; bz = az + CELL; ax = bx = X1; }
      else { cz = r->z0 + i; cx = r->x0; nz = cz; nx = cx - 1; az = cz * CELL; bz = az + CELL; ax = bx = X0; }
      int nh = ((unsigned)nx > 127 || (unsigned)nz > 127) ? 0 : celldict[cellidx[nx * 128 + nz]].hi;
      int ya = ramp_y(r, ax, az), yb = ramp_y(r, bx, bz);
      int yt = ya < yb ? ya : yb, ya2 = ya, yb2 = yb;
      int outward = nh < yt, inward = nh > ya && nh > yb;
      int vis;
      if (e == 0) vis = outward ? camz < Z0 : camz > Z0; else if (e == 2) vis = outward ? camz > Z1 : camz < Z1;
      else if (e == 1) vis = outward ? camx > X1 : camx < X1; else vis = outward ? camx < X0 : camx > X0;
      if (!vis) continue;
      u32 col = flat_col(mat == 6 ? 5 : mat, alongx ? 0 : 1, 0); int fk = zdepth((ax + bx) >> 1, yt, (az + bz) >> 1);
      if (outward) {
        int bt = nh; if (bt < -4096) bt = -4096; if (isdeck) bt = yt - 192; if (bt >= yt) continue;
        g_src=6, quad_flat((V3){ ax, ya2, az }, (V3){ bx, yb2, bz }, (V3){ ax, bt, az }, (V3){ bx, bt, bz }, col, fk, 0);
      } else if (inward) {
        int tp = nh > 0 ? 0 : nh; if (tp <= ya && tp <= yb) continue;
        g_src=7, quad_flat((V3){ ax, tp, az }, (V3){ bx, tp, bz }, (V3){ ax, ya2, az }, (V3){ bx, yb2, bz }, col, fk, sunk);
      }
    }
  }
  g_bg = 0;
}
/* camera-facing flat shapes */
static void billboard(s32 fx, s32 fy, s32 fz, int hw, int y0, int y1, u32 rgb, int key) {
  /* a rectangle facing the camera: width 2*hw, from fy+y0 to fy+y1, at the foot's depth */
  CV c; cpu_cam(fx, fy, fz, 0, &c); if (c.z < 40) return;
  s32 z = c.z; int sx0 = 160 + (H_FOCAL * (c.x - hw)) / z, sx1 = 160 + (H_FOCAL * (c.x + hw)) / z;
  int sy0 = 120 - (H_FOCAL * (c.y + y1)) / z, sy1 = 120 - (H_FOCAL * (c.y + y0)) / z;
  if (sx1 < 0 || sx0 > 319 || sy1 < 0 || sy0 > 239) return;
  if (sx0 < -300) sx0 = -300; if (sx1 > 600) sx1 = 600; if (sy0 < -100) sy0 = -100; if (sy1 > 340) sy1 = 340;
  u32 *p = pnew(5); if (!p) return;
  p[1] = 0x28000000 | rgb; p[2] = XY(sx0, sy0); p[3] = XY(sx1, sy0); p[4] = XY(sx0, sy1); p[5] = XY(sx1, sy1); link_ot(bucket(key), p, 5);
}
static void hexagon(int cxs, int cys, int rr, u32 rgb, int key) {
  static const s8 hx[6] = { 4, 2, -2, -4, -2, 2 }, hy[6] = { 0, 3, 3, 0, -3, -3 };
  u32 v[6]; for (int i = 0; i < 6; i++) v[i] = XY(cxs + hx[i] * rr / 4, cys + hy[i] * rr / 3 * 1);
  for (int i = 1; i < 5; i++) put_f3x(bucket(key), 0, rgb, v[0], v[i], v[i + 1]);
}
static void draw_tree(int k) {
  const Tree *t = &trees[k]; int kind = t->kind;
  if (kind < 2) {
    int x = t->x * 4, z = t->z * 4, h = t->h * 8, base = t->base * 64, rr = t->r * 4;
    CV c; cpu_cam(x, base, z, 0, &c);
    if (c.z < 420 || c.z > 6000) return;
    if (c.z < 760 && (c.x < 360 && c.x > -360)) return;
    int R = 3 * h / 8; if (rr > R) R = rr;
    s32 zz = c.z; int sx = 160 + H_FOCAL * c.x / zz, sy = 120 - H_FOCAL * (c.y + h - R) / zz, rp = H_FOCAL * R / zz;
    if (sx + rp < 0 || sx - rp > 319 || sy + rp < -50 || sy - rp > 300) return;
    if (rp > 200) return;
    int key = zz;
    int tw = H_FOCAL * (h / 16) / zz; if (tw < 1) tw = 1;
    int sbx = 160 + H_FOCAL * c.x / zz, sby = 120 - H_FOCAL * c.y / zz;
    u32 *p = pnew(5);
    if (p) { p[1] = 0x28000000 | flat_col(10, 1, 0); p[2] = XY(sbx - tw, sy); p[3] = XY(sbx + tw, sy); p[4] = XY(sbx - tw, sby); p[5] = XY(sbx + tw, sby); link_ot(bucket(key), p, 5); }
    hexagon(sx, sy, rp, flat_col(3, 1, 0), key);
    hexagon(sx - rp / 5, sy - rp / 5, rp * 3 / 4, flat_col(3, 2, 0), key);
  } else if (kind < 6) {
    int e = kind - 2, cx = t->x & 127, cz = t->z & 127; int bot = (((int)t->base << 8) | t->h) << 5;
    int ax, az, bx, bz;
    if (e == 0) { ax = cx * CELL; az = cz * CELL; bx = ax + CELL; bz = az; }
    else if (e == 1) { ax = (cx + 1) * CELL; az = cz * CELL; bx = ax; bz = az + CELL; }
    else if (e == 2) { ax = cx * CELL; az = (cz + 1) * CELL; bx = ax + CELL; bz = az; }
    else { ax = cx * CELL; az = cz * CELL; bx = ax; bz = az + CELL; }
    int key = zdepth((ax + bx) >> 1, bot + 100, (az + bz) >> 1); if (key > 5000) return;
    g_src=8, quad_flat((V3){ ax, bot + 92, az }, (V3){ bx, bot + 92, bz }, (V3){ ax, bot + 70, az }, (V3){ bx, bot + 70, bz }, flat_col(10, 3, 0), key, 0);
    g_src=8, quad_flat((V3){ ax, bot + 172, az }, (V3){ bx, bot + 172, bz }, (V3){ ax, bot + 150, az }, (V3){ bx, bot + 150, bz }, flat_col(10, 2, 0), key, 0);
  } else if (kind <= 8) {
    int x = t->x * 4, z = t->z * 4, base = t->base * 64;
    CV c; cpu_cam(x, base, z, 0, &c); if (c.z < 200 || c.z > 4500) return;
    if (kind == 6) billboard(x, base, z, 150, 0, 140, flat_col(7, 2, 0), c.z);
    else if (kind == 7) billboard(x, base, z, 45, 0, 150, flat_col(10, 1, 0), c.z);
    else { billboard(x, base, z, 12, 0, 520, flat_col(10, 2, 0), c.z); billboard(x, base, z, 50, 520, 560, flat_col(12, 3, 0), c.z); }
  }
}
static void city_draw(void) {
#ifdef NOCITY
  return;
#endif
  stamp++; if (!stamp) { for (int i = 0; i < 3072; i++) st_box[i] = 0; for (int i = 0; i < 1024; i++) st_ramp[i] = 0; for (int i = 0; i < 2304; i++) st_tree[i] = 0; stamp = 1; }
  int csx = camx >> 13, csz = camz >> 13, vs = (reach + 1024 + 8191) >> 13;
  for (int sx = csx - vs; sx <= csx + vs; sx++) for (int sz = csz - vs; sz <= csz + vs; sz++) {
    if ((unsigned)sx > 15 || (unsigned)sz > 15) continue;
    if (dist_rect(sx * 8192, sz * 8192, sx * 8192 + 8192, sz * 8192 + 8192) > reach + 1024) continue;
    if (!in_view(sx * 8192 + 4096, 1500, sz * 8192 + 4096, 7300)) continue;
    int s = sx * 16 + sz, first = sector[2 * s], cnt = sector[2 * s + 1];
    for (int i = 0; i < cnt; i++) {
      u16 it = items[first + i]; int kind = it >> 13, idx = it & 0x1fff;
      u32 tq = TICKS8();
      if (kind == 0) { if (st_box[idx] == stamp) continue; st_box[idx] = stamp; u32 l0_ = c_leaf, p0_ = c_proj, r0_ = c_rect, k0_ = c_cleaf; draw_box(idx); u32 dt_ = (TICKS8() - tq) & 0xffff; t_cb += dt_; if (dbgcell && dt_ > 800) { dbg("box "); ddec(idx); ddec(boxes[idx].x1 - boxes[idx].x0); ddec(boxes[idx].z1 - boxes[idx].z0); ddec(boxes[idx].h); ddec(dt_ / 270); dbg("rect "); ddec(c_rect - r0_); dbg("leaf "); ddec(c_leaf - l0_); ddec(c_cleaf - k0_); dbg("proj "); ddec(c_proj - p0_); dbg("\n"); } }
      else if (kind == 2) { if (st_ramp[idx] == stamp) continue; st_ramp[idx] = stamp; draw_ramp(idx); t_cr += (TICKS8() - tq) & 0xffff; }
      else if (kind == 5) { if (st_tree[idx] == stamp) continue; st_tree[idx] = stamp; draw_tree(idx); t_ct += (TICKS8() - tq) & 0xffff; }
    }
  }
}

/* ------------------------------------------------------------------------------------------- vehicle model (flat boxes) */
static void obox(s32 cx, s32 cy, s32 cz, int ya, int hx, int hy, int hz, int mat) {
  int s = fsin(ya), c = fcos(ya);
  #define CP(sx, sy, sz) ((V3){ cx + (((sx) * hx * c + (sz) * hz * s) >> 14), cy + (sy) * hy, cz + (((sz) * hz * c - (sx) * hx * s) >> 14) })
  V3 p[8]; for (int i = 0; i < 8; i++) p[i] = CP((i & 1) ? 1 : -1, (i & 2) ? 1 : -1, (i & 4) ? 1 : -1);
  #undef CP
  /* index = x + 2*y + 4*z bits: 1 = +, 0 = - */
  struct { u8 a, b, c, d; s8 nx, ny, nz; u8 l; } F[6] = {
    { 2, 3, 6, 7, 0, 1, 0, 3 }, { 6, 7, 4, 5, 0, 0, 1, 2 }, { 0, 1, 2, 3, 0, 0, -1, 1 }, { 3, 7, 1, 5, 1, 0, 0, 2 }, { 6, 2, 4, 0, -1, 0, 0, 0 }, { 0, 4, 1, 5, 0, -1, 0, 0 } };
  /* top: -x-z.. order Z: (-x,+y,-z),(+x,+y,-z),(-x,+y,+z),(+x,+y,+z) = idx 2,3,6,7 ; front +z: (-x,+y),(+x,+y),(-x,-y),(+x,-y) = 6,7,4,5 ;
     back -z: 0,1,2,3 reversed vertically: top first = 2,3,0,1 */
  F[2].a = 2; F[2].b = 3; F[2].c = 0; F[2].d = 1;
  F[3].a = 3; F[3].b = 7; F[3].c = 1; F[3].d = 5;   /* +x side: top from -z to +z */
  F[4].a = 6; F[4].b = 2; F[4].c = 4; F[4].d = 0;   /* -x side */
  F[5].a = 0; F[5].b = 4; F[5].c = 1; F[5].d = 5;   /* bottom (never seen) */
  for (int f = 0; f < 5; f++) {
    s32 nx = (F[f].nx * c + F[f].nz * s), nz = (F[f].nz * c - F[f].nx * s), ny = F[f].ny * 16384; nx *= F[f].nx || F[f].nz ? 1 : 0;
    if (F[f].nx) { nx = F[f].nx * c; nz = -F[f].nx * s; } if (F[f].nz) { nx = F[f].nz * s; nz = F[f].nz * c; }
    V3 ctr = { (p[F[f].a].x + p[F[f].d].x) >> 1, (p[F[f].a].y + p[F[f].d].y) >> 1, (p[F[f].a].z + p[F[f].d].z) >> 1 };
    s32 d = (nx * (camx - ctr.x) + ny * (camy - ctr.y) + nz * (camz - ctr.z)) >> 14; if (d <= 0) continue;
    quad_flat(p[F[f].a], p[F[f].b], p[F[f].c], p[F[f].d], flat_col(mat, F[f].l, 0), zdepth(ctr.x, ctr.y, ctr.z) - 20, 0);
  }
}
static void car_draw(s32 x, s32 y, s32 z, int ya) {
  int s = fsin(ya), c = fcos(ya);
  obox(x, y + 70, z, ya, 112, 38, 235, 11);                                              /* body */
  obox(x - (s * 25 >> 14), y + 140, z - (c * 25 >> 14), ya, 98, 34, 120, 6);             /* cabin (glass) */
  for (int i = 0; i < 4; i++) { int sx = (i & 1) ? 112 : -112, sz = (i & 2) ? 150 : -150;
    obox(x + ((sx * c + sz * s) >> 14), y + 30, z + ((sz * c - sx * s) >> 14), ya, 14, 30, 36, 1); }
}

/* ------------------------------------------------------------------------------------------- HUD */
static int fontx_ok;
static void hud_str(int x, int y, const char *s, u32 rgb) {
  u32 *p = pnew(1); if (!p) return; p[1] = 0xE1000400 | TPAGE(960, 0, 0, 0); link_hud(p, 1);
  for (; *s; s++) {
    int ch = *s; if (ch >= 'a' && ch <= 'z') ch -= 32; if (ch < 32 || ch > 127) ch = '?';
    int gi = ch - 32; if (ch != ' ') {
      u32 *q = pnew(4); if (!q) return; q[1] = 0x64000000 | rgb; q[2] = XY(x, y); q[3] = ((gi & 15) * 8) | ((gi >> 4) * 8 << 8) | (CLUT(0, 488) << 16); q[4] = 6 | (8 << 16); link_hud(q, 4); }
    x += 6;
  }
}
static void hud_box(int x, int y, int w, int h) { u32 *p = pnew(3); if (!p) return; p[1] = 0x60000000; p[2] = XY(x, y); p[3] = XY(w, h); link_hud(p, 3); }
static char *fmt_int(char *d, int v, int minw) {
  char t[12]; int n = 0; u32 u = v < 0 ? -v : v; do { t[n++] = '0' + u % 10; u /= 10; } while (u);
  if (v < 0) t[n++] = '-'; while (n < minw) t[n++] = ' ';
  while (n) *d++ = t[--n]; *d = 0; return d;
}
static char *fmt_s(char *d, const char *s) { while (*s) *d++ = *s++; *d = 0; return d; }

/* ------------------------------------------------------------------------------------------- driving */
static int mode;                 /* 0 car, 1 fly */
static s32 car_x, car_y, car_z, car_v; static int car_h;   /* x,y,z units << 8, speed units<<8 a tick */
static s32 fly_v;
static int ground_at(int x, int z, int y) {
  int cx = x >> 10, cz = z >> 10; if ((unsigned)cx > 127 || (unsigned)cz > 127) return 100000;
  int i = cx * 128 + cz; const Cell *c = &celldict[cellidx[i]]; int h;
  switch (c->shape) {
    case 2: h = c->lo + (c->hi - c->lo) * (z & 1023) / 1024; break;
    case 3: h = c->lo + (c->hi - c->lo) * (x & 1023) / 1024; break;
    case 4: h = c->lo + (c->hi - c->lo) * (1023 - (z & 1023)) / 1024; break;
    case 5: h = c->lo + (c->hi - c->lo) * (1023 - (x & 1023)) / 1024; break;
    default: h = c->hi;
  }
  const s8 *d = deck_get(i);
  if (d[0] | d[1] | d[2] | d[3]) { int top = (d[1] + 40) * 64; if (y + 64 >= top && top > h) h = top; else if (top > h && y + 64 < top && y > (d[0] + 40) * 64) { /* under the deck: ground */ } }
  return h;
}
static int car_blocked(s32 x, s32 z, int y) {
  int s = fsin(car_h), c = fcos(car_h);
  static const s16 off[5][2] = { { 0, 0 }, { 112, 235 }, { -112, 235 }, { 112, -235 }, { -112, -235 } };
  for (int i = 0; i < 5; i++) {
    int ox = off[i][0], oz = off[i][1];
    int wx = (x >> 8) + ((ox * c + oz * s) >> 14), wz = (z >> 8) + ((oz * c - ox * s) >> 14);
    if (ground_at(wx, wz, y) > y + 48) return 1;
  }
  return 0;
}
static void drive_tick(u32 pad) {
  if (mode == 0) {
    int acc = pad & (1 << 14), brk = pad & (1 << 15), lf = pad & (1 << 7), rt = pad & (1 << 5);
    if (acc) car_v += 160; if (brk) { car_v -= car_v > 0 ? 320 : 120; }
    car_v -= car_v >> 6; if (!acc && !brk) car_v -= car_v >> 5;
    if (car_v > 6144) car_v = 6144; if (car_v < -2048) car_v = -2048;
    int sp = car_v < 0 ? -car_v : car_v; int rate = (sp * 260 / 6144) + (sp ? 20 : 0); if (rate > 300) rate = 300; if (car_v < 0) rate = -rate;
    if (lf) car_h += rate; if (rt) car_h -= rate; car_h &= 0xffff;
    int s = fsin(car_h), c = fcos(car_h);
    s32 nx = car_x + (car_v * s >> 14), nz = car_z + (car_v * c >> 14); int cy = car_y >> 8;
    if (!car_blocked(nx, car_z, cy)) car_x = nx; else car_v = car_v / 2;
    if (!car_blocked(car_x, nz, cy)) car_z = nz; else car_v = car_v / 2;
    int g = ground_at(car_x >> 8, car_z >> 8, cy); int ys = g; if (g > cy + 48) ys = cy;
    car_y += ((ys << 8) - car_y) >> 2;
  } else {
    int turbo = (pad & (1 << 8)) ? 4 : (pad & (1 << 9)) ? 0 : 1; int sp = turbo == 4 ? 24 * 256 : turbo == 0 ? 3 * 256 : 10 * 256;
    if (pad & (1 << 7)) yaw += 300; if (pad & (1 << 5)) yaw -= 300; yaw &= 0xffff;
    if (pad & (1 << 10)) pitch += 150; if (pad & (1 << 11)) pitch -= 150; if (pitch > 15000) pitch = 15000; if (pitch < -15000) pitch = -15000;
    int s = fsin(yaw), c = fcos(yaw);
    if (pad & (1 << 4)) { cpx += sp * s >> 14; cpz += sp * c >> 14; }
    if (pad & (1 << 6)) { cpx -= sp * s >> 14; cpz -= sp * c >> 14; }
    if (pad & (1 << 14)) cpy += sp; if (pad & (1 << 15)) cpy -= sp;
    if (cpy < 60 << 8) cpy = 60 << 8;
    if (cpx < 0) cpx = 0; if (cpz < 0) cpz = 0; if (cpx > (131071 << 8)) cpx = 131071 << 8; if (cpz > (131071 << 8)) cpz = 131071 << 8;
  }
}
static void chase_update(void) {
  int s = fsin(car_h), c = fcos(car_h);
  s32 tx = car_x - (s * 820 >> 14 << 8), tz = car_z - (c * 820 >> 14 << 8), ty = car_y + (300 << 8);
  cpx += (tx - cpx) >> 2; cpz += (tz - cpz) >> 2; cpy += (ty - cpy) >> 2;
  /* pull in when the camera would sit in a wall or underground */
  for (int k = 0; k < 6; k++) {
    int gh = ground_at(cpx >> 8, cpz >> 8, cpy >> 8);
    if (gh < (cpy >> 8) - 60) break;
    cpx = car_x + ((cpx - car_x) >> 1); cpz = car_z + ((cpz - car_z) >> 1);
    if (gh < (cpy >> 8) + 100) { int g2 = ground_at(cpx >> 8, cpz >> 8, cpy >> 8); if (g2 < (cpy >> 8) - 60) break; }
  }
  int want = car_h; int dy = (short)(want - yaw); yaw = (yaw + (dy >> 2)) & 0xffff;
  pitch = -2300;
}

/* ------------------------------------------------------------------------------------------- vram upload */
static void vram_dma(int x, int y, int w, int h, const void *src) {
  int words = w * h / 2; gpu_idle();
  gp0(0xA0000000); gp0(XY(x, y)); gp0(XY(w, h));
  if (words % 16) { const u16 *d = src; for (int n = words; n > 0; n--) { gp0(d[0] | ((u32)d[1] << 16)); d += 2; } return; }
  D2_MADR = ADDR(src); D2_BCR = ((words / 16) << 16) | 16; D2_CHCR = 0x01000201; while (D2_CHCR & 0x01000000) {}
}
