/* sf.c: Stage 2b. Star-FlyBack / Stunt Fox world (Freedom City) drawn by the PS1 GPU, GTE projection, painter's OT.
   One translation unit, no SDK.  Data (WORLD.SFW, ATLAS.VRM, CLUT.BIN, SIDE.BIN, FONT.VRM) is linked in by data.s. */
#include "ps1.h"
#ifdef PROF
#define TK() TICKS8()          /* PROFILE build: per-section timers (1/270 line) */
#define PHT() HLINES()
#define CNT(x) ((x)++)
#else
#define CNT(x) ((void)0)
#define TK() 0
#define PHT() 0
#endif

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
#ifndef FIELDS
#define FIELDS 2                /* 30 fps: budget = FIELDS * 263 - 70 hblank lines (emulator lines) */
#endif
#ifndef LODCALM
#define LODCALM 75
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

/* ------------------------------------------------------------------------------------------- data */
typedef struct { s32 x, y, z; } V3;
static int errpx = ERRPX;
typedef struct { u8 x0, z0, x1, z1; s16 h; u8 mat; s8 base; } Box;
typedef struct { u8 x0, z0, x1, z1; s16 h0, h1; u8 dir, mat; } Ramp;
typedef struct { u16 x, z; u8 h, kind; s8 base; u8 r; } Tree;
typedef struct { s16 lo, hi; u8 shape, mat; } Cell;
typedef struct { u8 gmask[2048]; u16 slot_id[448]; u16 avg555[448]; u8 mesh[448]; u32 avgcol[448]; u32 flat[256]; u32 sky9[9]; u32 fog; } Side;   /* stage 7: the sin table (8 KB, the same in every map) lives in sint_tab, only the fields before it are per map (7144 bytes) */
static s16 sint_tab[4096];
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
  side = (const Side *)SF_SIDE;
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
static int nprim; static u32 t_rect, t_clipt, t_qoff, t_qf; static u32 t_cb, t_cr, t_ct, t_sec; static int dbgcell; static u32 t_pa, t_pb, t_pc, t_pd, t_pe, t_pf; static u32 t_gc, t_gc01, t_wg, t_fw, t_top, t_in, c_wg, c_wcell, c_wq, c_wf; static u32 g_leaf, g_proj, g_clip, g_cleaf; static u32 c_box, c_ramp, c_tree, c_proj, c_clip, c_rect, c_gcell, c_leaf, c_cleaf, c_cells, c_cullcell; static u32 ph_sky, ph_gnd, ph_city, ph_hud;
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
static inline int iabs_(int v) { return v < 0 ? -v : v; }
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
static inline int fsin(int a) { return sint_tab[(a >> 4) & 4095]; }
static inline int fcos(int a) { return sint_tab[((a + 16384) >> 4) & 4095]; }
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
  CNT(c_proj);
  s32 dx = (x << 2) - cpx6, dy = (y << 2) - cpy6, dz = (z << 2) - cpz6; int sh = 2;
  if (absi(dx) >= TIER_Q || absi(dy) >= TIER_Q || absi(dz) >= TIER_Q) {   /* same rule as grid_tex fast path: shared vertices round identically */
    dx = x - cpx8; dy = y - cpy8; dz = z - cpz8; sh = 0;
#ifdef OLDCLIP
    if (((u32)(dx + 18000) | (u32)(dy + 18000) | (u32)(dz + 18000)) >= 36000u)
#else
    if (((u32)(dx + 32768) | (u32)(dy + 32768) | (u32)(dz + 32768)) >= 65536u)   /* stage5 clipfix: each |d| < 32768 (old 18000 bound was an OR of offsets, wrong for valid far vertices) */
#endif
    { o->z = 0; o->sx = 0; o->sy = 0; return; }
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
  CNT(c_clip);
  CV a[MAXCV], b[MAXCV]; int na = n, nb;
  s32 mn[5] = { 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff, 0x7fffffff }, mx[5] = { -0x7fffffff, -0x7fffffff, -0x7fffffff, -0x7fffffff, -0x7fffffff };
  for (int i = 0; i < n; i++) { a[i] = in[i];
    for (int pl = 0; pl < 5; pl++) { s32 v = plane(pl, &in[i], nearz); if (v < mn[pl]) mn[pl] = v; if (v > mx[pl]) mx[pl] = v; } }
  for (int pl = 0; pl < 5; pl++) if (mx[pl] < 0) return 0;
  CV *src = a, *dst = b;
  for (int pl = 0; pl < 5; pl++) {
    if (mn[pl] >= 0) continue;
    nb = 0;
    s32 dv[MAXCV]; for (int i = 0; i < na; i++) dv[i] = plane(pl, &src[i], nearz);   /* one plane value per vertex (was two per edge) */
    for (int i = 0; i < na; i++) {
      int i1 = i + 1 == na ? 0 : i + 1; const CV *p = &src[i], *q = &src[i1];
      s32 dp = dv[i], dq = dv[i1];
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
static void clip_emit_tex(const V3 *w, const int *uv /* u,v pairs */, int n, int bk, u32 cmd, u32 clut, u32 tp, int ubase, int vbase) { u32 t0 = TK(); clip_emit_tex2(w, uv, n, bk, cmd, clut, tp, ubase, vbase); t_clipt += (TK() - t0) & 0xffff; }
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
static void quad_flat(V3 a, V3 b, V3 c, V3 d, u32 rgb, int key, int bg) { u32 t0 = TK(); quad_flat2(a, b, c, d, rgb, key, bg); t_qf += (TK() - t0) & 0xffff; }
static void quad_flat2(V3 a, V3 b, V3 c, V3 d, u32 rgb, int key, int bg) {
  PV p[4]; proj(a.x, a.y, a.z, &p[0]); proj(b.x, b.y, b.z, &p[1]); proj(c.x, c.y, c.z, &p[2]); proj(d.x, d.y, d.z, &p[3]);
  int q = qclass(&p[0], &p[1], &p[2], &p[3]);
  if (q == Q_SKIP) return;
  if (q == Q_OK) { put_f4(bucket(key), bg, rgb, &p[0], &p[1], &p[2], &p[3]); return; }
  V3 w[4] = { a, b, d, c }; clip_emit_flat(w, 4, bucket(key), bg, rgb, 2);
}

/* 1 when a world quad (corners as given) is certainly not on screen */
static int quad_off2(V3 a, V3 b, V3 c, V3 d);
static int quad_off(V3 a, V3 b, V3 c, V3 d) { u32 t0 = TK(); int r = quad_off2(a, b, c, d); t_qoff += (TK() - t0) & 0xffff; return r; }
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
  CNT(c_leaf);
  if (q == Q_OK) {
    put_ft4(rbk, rcmd, a, b, c, d, (rub + u0) | ((rvb + v0) << 8), (rub + u1) | ((rvb + v0) << 8), (rub + u0) | ((rvb + v1) << 8), (rub + u1) | ((rvb + v1) << 8), rclut, rtp);
  } else {
    CNT(c_cleaf); V3 w[4]; int uv[8];
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
  CNT(c_nodes);
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
    CNT(c_leaf);
    if (ok) put_ft3x(rbk, rcmd, pxy(&pv[ap]), (rub + uu[ap]) | ((rvb + vv[ap]) << 8), pxy(&pv[k]), (rub + uu[k]) | ((rvb + vv[k]) << 8), pxy(&pv[k2]), (rub + uu[k2]) | ((rvb + vv[k2]) << 8), rclut, rtp);
    else { V3 tw[3] = { w[ap], w[k], w[k2] }; int tuv[6] = { uu[ap], vv[ap], uu[k], vv[k], uu[k2], vv[k2] }; CNT(c_cleaf); clip_emit_tex(tw, tuv, 3, rbk, rcmd, rclut, rtp, rub, rvb); }
  }
}
static void grid_tex(int n) {
  u32 tg_ = TK(); PV row[2][9]; int st = 8 / n, uu[9], vv[9];
  for (int i = 0; i <= n; i++) { uu[i] = i == n ? rua1 : (rua1 + 1) * i / n; vv[i] = i == n ? rvb1 : (rvb1 + 1) * i / n; }
  /* incremental inputs when the whole rectangle is within the quarter-unit range */
  s32 m0 = absi(rO.x - camx) + absi(rA.x) + absi(rB.x), m1 = absi(rO.y - camy) + absi(rA.y) + absi(rB.y), m2 = absi(rO.z - camz) + absi(rA.z) + absi(rB.z);
  int fast = m0 < 4600 && m1 < 4600 && m2 < 4600;
  s32 ax = ((rA.x * st) >> 3) << 2, ay = ((rA.y * st) >> 3) << 2, az = ((rA.z * st) >> 3) << 2, bx = ((rB.x * st) >> 3) << 2, by = ((rB.y * st) >> 3) << 2, bz = ((rB.z * st) >> 3) << 2;
  s32 x0 = (rO.x << 2) - cpx6, y0 = (rO.y << 2) - cpy6, z0 = (rO.z << 2) - cpz6;
  if (fast) { s32 x = x0, y = y0, z = z0; for (int i = 0; i <= n; i++) { projq(x, y, z, 2, &row[0][i]); x += ax; y += ay; z += az; } }
  else for (int i = 0; i <= n; i++) proj(rO.x + ((rA.x * (i * st)) >> 3), rO.y + ((rA.y * (i * st)) >> 3), rO.z + ((rA.z * (i * st)) >> 3), &row[0][i]);
  t_pc += (TK() - tg_) & 0xffff;
  for (int j = 0; j < n; j++) {
    u32 tj_ = TK(); int jj = (j + 1) * st; PV *r0 = row[j & 1], *r1 = row[(j + 1) & 1];
    if (fast) { s32 x = x0 + bx * (j + 1), y = y0 + by * (j + 1), z = z0 + bz * (j + 1); for (int i = 0; i <= n; i++) { projq(x, y, z, 2, &r1[i]); x += ax; y += ay; z += az; } }
    else for (int i = 0; i <= n; i++) proj(rO.x + ((rA.x * (i * st)) >> 3) + ((rB.x * jj) >> 3), rO.y + ((rA.y * (i * st)) >> 3) + ((rB.y * jj) >> 3), rO.z + ((rA.z * (i * st)) >> 3) + ((rB.z * jj) >> 3), &r1[i]);
    u8 o0[9], o1[9]; for (int i = 0; i <= n; i++) { o0[i] = ocode(&r0[i]); o1[i] = ocode(&r1[i]); }
    u32 va = (rvb + vv[j]) << 8, vc = (rvb + vv[j + 1]) << 8;
    t_pd += (TK() - tj_) & 0xffff;
    for (int i = 0; i < n; i++) {
      if (g_edge_any && ((j == 0 && g_edge[0] > 1) || (j == n - 1 && g_edge[1] > 1) || (i == 0 && g_edge[2] > 1) || (i == n - 1 && g_edge[3] > 1))) { u32 tf_ = TK(); fan_quad(i, j, n, st); t_pf += (TK() - tf_) & 0xffff; continue; }
      PV *a = &r0[i], *b = &r0[i + 1], *c = &r1[i], *d = &r1[i + 1];
      int ca = o0[i], cb = o0[i + 1], cc = o1[i], cd = o1[i + 1];
      if (!((ca | cb | cc | cd) & OC_BAD)) {              /* clean quad: no clipping needed, only the off-screen test */
        if (ca & cb & cc & cd & OC_OFF) continue;
        CNT(c_leaf); u32 ua = rub + uu[i], ub = rub + uu[i + 1];
        put_ft4(rbk, rcmd, a, b, c, d, ua | va, ub | va, ua | vc, ub | vc, rclut, rtp);
        continue;
      }
      int q = qclass(a, b, c, d); if (q == Q_SKIP) continue;
      CNT(c_leaf);
      if (q == Q_OK) {
        put_ft4(rbk, rcmd, a, b, c, d, (rub + uu[i]) | ((rvb + vv[j]) << 8), (rub + uu[i + 1]) | ((rvb + vv[j]) << 8), (rub + uu[i]) | ((rvb + vv[j + 1]) << 8), (rub + uu[i + 1]) | ((rvb + vv[j + 1]) << 8), rclut, rtp);
      } else {
        CNT(c_cleaf); V3 w[4]; int uv[8]; int ii = i * st, i2 = (i + 1) * st, j0 = j * st, j2 = jj;
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
static void rect_tex(V3 O, V3 A, V3 B, int slot, int ua1, int vb1, u32 cmd, int key, int nforce, int maxn) { u32 t0 = TK(); rect_tex2(O, A, B, slot, ua1, vb1, cmd, key, nforce, maxn); t_rect += (TK() - t0) & 0xffff; }
static void rect_tex2(V3 O, V3 A, V3 B, int slot, int ua1, int vb1, u32 cmd, int key, int nforce, int maxn) {
  CNT(c_rect);
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
  CNT(c_wg); wO = O; wA = A; wtot = total; if (++wcur == 0) { for (int j = 0; j <= WMAXR; j++) for (int i = 0; i <= WMAXC; i++) wvx[j][i].st = 0; wcur = 1; }
  for (int i = 0; i < L; i++) {
    u16 t = bt[i > 3 ? 3 : i]; if (t == 0xffff) continue;
    int mesh = side->mesh[t], slot = t, pg = slot >> 6, k = slot & 63, ub = (k & 7) * 32, vb = (k >> 3) * 32; u32 tp = TPAGE(320 + 128 * (pg % 5), 256 * (pg / 5), 1, 0);
    for (int j = 0; j < nr; j++) {
      int seg = total - j * CELL; if (seg > CELL) seg = CELL;
      int vb1 = seg == CELL ? 31 : (seg * 32 >> 10) - 1; if (vb1 < 0) vb1 = 0;
      PV *a = wv(i, j), *b = wv(i + 1, j), *c = wv(i, j + 1), *d = wv(i + 1, j + 1); int aff = 0;
      int q = qcls(a, b, c, d, &aff); CNT(c_wcell);
      if (q == Q_SKIP) continue;
      if (q == Q_OK && (aff || mesh)) { CNT(c_wq);
        if (mesh) put_f4(bk, 0, side_col(side->avgcol[t], g), a, b, c, d);
        else put_ft4(bk, FT4_MOD | rgb, a, b, c, d, ub | (vb << 8), (ub + 31) | (vb << 8), ub | ((vb + vb1) << 8), (ub + 31) | ((vb + vb1) << 8), clut, tp);
        continue;
      }
      CNT(c_wf); V3 Oc = { O.x + A.x * i, O.y - j * CELL, O.z + A.z * i }, Bc = { 0, -seg, 0 };
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
  u32 te_ = TK();
  g_edge_any = 0;
  if ((ring == 0 || ntab[lod][ring - 1] <= n)) { g_edge[0] = g_edge[1] = g_edge[2] = g_edge[3] = 1; }   /* a finer neighbour can only be in ring - 1 */
  else for (int sd = 0; sd < 4; sd++) {
    int nx = cx + (sd == 2 ? -1 : sd == 3 ? 1 : 0), nz = cz + (sd == 0 ? -1 : sd == 1 ? 1 : 0); g_edge[sd] = 1;
    if ((unsigned)nx > 127 || (unsigned)nz > 127 || ctex[nx * 128 + nz] == 0xffff) continue;
    int ni = nx * 128 + nz; if (!(side->gmask[ni >> 3] >> (ni & 7) & 1)) continue;
    int dx = nx - (camx >> 10), dz = nz - (camz >> 10); dx = absi(dx); dz = absi(dz); int nr = dx > dz ? dx : dz;
    if (nr >= 7) continue;
    int nn = ntab[lod][nr]; if (nn > n && !NOFANX) { g_edge[sd] = nn / n;  /* power of two */ g_edge_any = 1; }
  }
  t_pa += (TK() - te_) & 0xffff; te_ = TK();
  g_bg = 1; rect_tex(O, A, B, t, 31, 31, FT4_RAW, 0, n, n); g_bg = 0; g_edge_any = 0;
  t_pb += (TK() - te_) & 0xffff;
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
  /* rings >= 7 draw nothing (ground_cell returns before emitting), so only |dx|,|dz| <= 6 are visited.  The in_view test of each cell centre (y 0, r 740) is evaluated
     with the three camera-axis dot products accumulated incrementally (exact integer sums, same value as dotv: identical result, a handful of adds a cell). */
  s32 X0 = (ccx - 6) * CELL + 512 - camx, Z0 = (ccz - 6) * CELL + 512 - camz, Y = -camy;
  s32 sr = mr.x * X0 + mr.y * Y + mr.z * Z0, su = mu.x * X0 + mu.y * Y + mu.z * Z0, sf = mf.x * X0 + mf.y * Y + mf.z * Z0;
  s32 drx = mr.x * CELL, dux = mu.x * CELL, dfx = mf.x * CELL, drz = mr.z * CELL, duz = mu.z * CELL, dfz = mf.z * CELL;
  const s32 RX = 740 * 242, RY = 740 * 218;
  for (int dz = -6; dz <= 6; dz++, sr += drz, su += duz, sf += dfz) {
    int cz = ccz + dz; if ((unsigned)cz > 127) continue;
    s32 r_ = sr, u_ = su, f_ = sf;
    for (int dx = -6; dx <= 6; dx++, r_ += drx, u_ += dux, f_ += dfx) {
      int cx = ccx + dx;
      if ((unsigned)cx > 127) continue;
      int i = cx * 128 + cz; if (!(side->gmask[i >> 3] >> (i & 7) & 1)) continue;
      CNT(c_cullcell);
      s32 vx = r_ >> 14, vy = u_ >> 14, vz = f_ >> 14;
      if (vz < -740) continue;
      if (H_FOCAL * vx - 161 * vz > RX || -H_FOCAL * vx - 161 * vz > RX) continue;
      if (H_FOCAL * vy - 121 * vz > RY || -H_FOCAL * vy - 121 * vz > RY) continue;
      int adx = dx < 0 ? -dx : dx, adz = dz < 0 ? -dz : dz, ring = adx > adz ? adx : adz;
      CNT(c_cells);
#ifndef NOGCELL
      { u32 t0_ = TK(); ground_cell(cx, cz, ring); t_gc += (TK() - t0_) & 0xffff; }
#endif
    }
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
  const Box *b = &boxes[k]; CNT(c_box);
  int X0 = b->x0 * CELL, Z0 = b->z0 * CELL, X1 = b->x1 * CELL, Z1 = b->z1 * CELL, h = b->h, bot = b->base * 64, hid = b->mat >> 4, mat = b->mat & 15;
  int dd = dist_rect(X0, Z0, X1, Z1);
  if (dd > reach) return;
  int w = X1 - X0, d = Z1 - Z0, ww = w > d ? w : d, hh = h - bot;
  if (!in_view((X0 + X1) >> 1, (h + bot) >> 1, (Z0 + Z1) >> 1, ww * 3 / 4 * 11 / 10 + (hh > 0 ? hh : -hh) / 2 + 64)) return;
  int isdeck = bot != 0;
  /* top */
  u32 tt_ = TK();
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
  t_top += (TK() - tt_) & 0xffff;
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
      if (t != 0xffff && !side->mesh[t]) { u32 tz_ = TK(); far_wall_tex(a0, a1, bot, t, L, total, fkey, rgb); t_fw += (TK() - tz_) & 0xffff; continue; }
      g_src=2, quad_flat(a0, a1, (V3){ a0.x, bot, a0.z }, (V3){ a1.x, bot, a1.z }, col, fkey, 0);
      continue;
    }
    { V3 fa = alongx ? (V3){ X0, h, pz } : (V3){ px, h, Z0 }, fb = alongx ? (V3){ X1, h, pz } : (V3){ px, h, Z1 };
      if (quad_off(fa, fb, (V3){ fa.x, bot, fa.z }, (V3){ fb.x, bot, fb.z })) continue; }
    if (L <= WMAXC && (total + CELL - 1) / CELL <= WMAXR) {
      V3 O = alongx ? (V3){ X0, h, pz } : (V3){ px, h, Z0 }, A = alongx ? (V3){ CELL, 0, 0 } : (V3){ 0, 0, CELL };
      { u32 tz_ = TK(); wall_grid(O, A, L, total, &btex[16 * k + 4 * sd], fkey, g); t_wg += (TK() - tz_) & 0xffff; } continue;
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
  const Ramp *r = &ramps[k]; CNT(c_ramp);
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
/* ---- stage 17 trees: Gouraud-shaded canopies, firs in tiers, distance LOD ----
   A tree is a camera-facing cut-out (Payback's trees are round/conical cut-outs too): every vertex carries one of the four
   grass lights, so the canopy shades smoothly from the lit upper left to the dark lower right (one Gouraud triangle is the
   same cost as a flat one).  Near trees (z < T17_NEAR) have an irregular rim and leaf flecks, middle ones a plain rim, far
   ones a hexagon / one cone: no more work per far tree than the old two hexagons.  Pieces are submitted last-drawn first
   (a bucket's newest primitive is drawn first). */
#define T17_NEAR 2600
#define T17_MID 4200
static inline void gt3(int bk, u32 c0, u32 a, u32 c1, u32 b, u32 c2, u32 c) {
  u32 *p = pnew(6); if (!p) return;
  p[1] = 0x30000000 | c0; p[2] = a; p[3] = c1; p[4] = b; p[5] = c2; p[6] = c; link_ot(bk, p, 6);
}
static const s8 t17_cs[10][2] = { { 0, 16 }, { 9, 13 }, { 15, 5 }, { 15, -5 }, { 9, -13 }, { 0, -16 }, { -9, -13 }, { -15, -5 }, { -15, 5 }, { -9, 13 } };   /* (x, y up) 16ths, a 10-gon */
static void tree17(int k, const Tree *t, int kind, s32 x, s32 base, s32 z, s32 h, s32 R) {
  (void)k;
  CV c; cpu_cam(x, base, z, 0, &c);
  if (c.z < 420 || c.z > 6000) return;
  if (c.z < 760 && (c.x < 360 && c.x > -360)) return;
  s32 zz = c.z; int sx = 160 + H_FOCAL * c.x / zz, sby = 120 - H_FOCAL * c.y / zz;
  int rp = H_FOCAL * R / zz, hp = H_FOCAL * h / zz;
  if (sx + rp < 0 || sx - rp > 319 || sby - hp - 8 > 300 || sby + 8 < -50) return;
  if (rp > 200) return;
  int key = zz, bk = bucket(key), near = zz < T17_NEAR, mid = zz < T17_MID;
  u32 cl[4] = { flat_col(3, 0, 0), flat_col(3, 1, 0), flat_col(3, 2, 0), flat_col(3, 3, 0) };
  u32 trunkc = flat_col(10, 1, 0);
  int tw = H_FOCAL * (h / 16) / zz; if (tw < 1) tw = 1;
  if (kind == 1) {
    /* a fir: tiers (bottom, top: 25ths of the height; half width: 16ths of the crown), top first; each tier a fan from its apex over a
       ragged lower edge, lit on the left */
    static const u8 T3[3][3] = { { 16, 25, 8 }, { 10, 19, 12 }, { 4, 13, 16 } };
    static const u8 T2[2][3] = { { 11, 25, 10 }, { 4, 17, 16 } };
    static const u8 T1[1][3] = { { 4, 25, 16 } };
    const u8 (*tr)[3] = near ? T3 : mid ? T2 : T1; int n = near ? 3 : mid ? 2 : 1;
    for (int i = 0; i < n; i++) {
      int dk = near ? i : mid ? 2 * i : 1;          /* darker tiers lower down */
      int hw = rp * tr[i][2] >> 4, yb = sby - hp * tr[i][0] / 25, yt = sby - hp * tr[i][1] / 25, ra = hp / 25 + 1;
      u32 ca = cl[dk > 3 ? 0 : 3 - dk], cb = cl[dk > 2 ? 0 : 2 - dk], cm = cl[dk > 1 ? 0 : 1 - dk], cd = cl[0];
      u32 pa = XY(sx, yt), p0 = XY(sx - hw, yb), p1 = XY(sx - hw / 2, yb - ra), p2 = XY(sx, yb + (ra >> 1)), p3 = XY(sx + hw / 2, yb - ra), p4 = XY(sx + hw, yb);
      if (near) {
        gt3(bk, ca, pa, cm, p3, cd, p4); gt3(bk, ca, pa, cm, p2, cm, p3);
        gt3(bk, ca, pa, cb, p1, cm, p2); gt3(bk, ca, pa, cb, p0, cb, p1);
      } else { gt3(bk, ca, pa, cm, p2, cd, p4); gt3(bk, ca, pa, cb, p0, cm, p2); }
    }
    int th = hp * (near || mid ? 6 : 5) / 25;
    u32 *p = pnew(5);
    if (p) { p[1] = 0x28000000 | trunkc; p[2] = XY(sx - tw, sby - th); p[3] = XY(sx + tw, sby - th); p[4] = XY(sx - tw, sby); p[5] = XY(sx + tw, sby); link_ot(bk, p, 5); }
    return;
  }
  /* a broad tree: a fan from a bright point up and left of the middle over a 10-gon (6-gon far) rim, the rim's light by its direction */
  int cy = sby - hp + rp, ncv = near ? 10 : mid ? 10 : 6;
  u32 hv = (u32)(x * 73856093u ^ z * 19349663u) >> 7;
  int ox[10], oy[10]; u32 oc[10];
  for (int i = 0; i < ncv; i++) {
    int ux, uy;
    if (ncv == 10) { ux = t17_cs[i][0]; uy = t17_cs[i][1]; } else { static const s8 hx[6] = { 0, 14, 14, 0, -14, -14 }, hy[6] = { 16, 8, -8, -16, -8, 8 }; ux = hx[i]; uy = hy[i]; }
    int rr = near ? (((hv >> i) & 1) ? 16 : 13) : 16;      /* a ragged outline: leaf clumps */
    ox[i] = sx + ux * rp * rr / 256; oy[i] = cy - uy * rp * rr / 256;
    int lit = (uy - ux) * 3 / 20 + 2;                        /* light from the upper left, 0..3 */
    oc[i] = cl[lit < 0 ? 0 : lit > 3 ? 3 : lit];
  }
  int bx = sx - rp / 4, by = cy - rp / 4; u32 pb_ = XY(bx, by);
  if (near) {   /* leaf flecks: two dark and two light, fixed by the tree's place */
    int f0 = (int)(hv & 7), f1 = (int)((hv >> 3) & 7);
    int dx0 = rp * (f0 - 3) / 12, dy0 = rp * (f1 - 3) / 12;
    u32 fd = XY(sx + rp / 3 + dx0 / 2, cy + rp / 4 + dy0 / 2);
    gt3(bk, cl[3], XY(sx - rp / 3, cy - rp / 3), cl[2], XY(sx - rp / 3 + rp / 6, cy - rp / 3 + rp / 6), cl[2], XY(sx - rp / 3 - rp / 6, cy - rp / 3 + rp / 6));
    gt3(bk, cl[0], fd, cl[0], XY(sx + rp / 3 + dx0 / 2 + rp / 5, cy + rp / 4 + dy0 / 2 + rp / 8), cl[0], XY(sx + rp / 3 + dx0 / 2 - rp / 8, cy + rp / 4 + dy0 / 2 + rp / 5));
    gt3(bk, cl[0], XY(sx + rp / 8, cy - rp / 6), cl[0], XY(sx + rp / 3, cy - rp / 6 + rp / 6), cl[0], XY(sx + rp / 14, cy - rp / 6 + rp / 5));
  }
  for (int i = 0; i < ncv; i++) { int j = i + 1 == ncv ? 0 : i + 1; gt3(bk, cl[3], pb_, oc[i], XY(ox[i], oy[i]), oc[j], XY(ox[j], oy[j])); }
  u32 *p = pnew(5);
  if (p) { p[1] = 0x28000000 | trunkc; p[2] = XY(sx - tw, cy); p[3] = XY(sx + tw, cy); p[4] = XY(sx - tw, sby); p[5] = XY(sx + tw, sby); link_ot(bk, p, 5); }
}
static void draw_tree(int k) {
  const Tree *t = &trees[k]; int kind = t->kind;
  if (kind < 2) {
    int x = t->x * 4, z = t->z * 4, h = t->h * 8, base = t->base * 64, rr = t->r * 4;
    int R = 3 * h / 8; if (rr > R) R = rr;
    tree17(k, t, kind, x, base, z, h, R);
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
      u32 tq = TK();
      if (kind == 0) { if (st_box[idx] == stamp) continue; st_box[idx] = stamp; u32 l0_ = c_leaf, p0_ = c_proj, r0_ = c_rect, k0_ = c_cleaf; draw_box(idx); u32 dt_ = (TK() - tq) & 0xffff; t_cb += dt_; if (dbgcell && dt_ > 800) { dbg("box "); ddec(idx); ddec(boxes[idx].x1 - boxes[idx].x0); ddec(boxes[idx].z1 - boxes[idx].z0); ddec(boxes[idx].h); ddec(dt_ / 270); dbg("rect "); ddec(c_rect - r0_); dbg("leaf "); ddec(c_leaf - l0_); ddec(c_cleaf - k0_); dbg("proj "); ddec(c_proj - p0_); dbg("\n"); } }
      else if (kind == 2) { if (st_ramp[idx] == stamp) continue; st_ramp[idx] = stamp; draw_ramp(idx); t_cr += (TK() - tq) & 0xffff; }
      else if (kind == 5) { if (st_tree[idx] == stamp) continue; st_tree[idx] = stamp; draw_tree(idx); t_ct += (TK() - tq) & 0xffff; }
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
  PV pv[8]; u32 have = 0;   /* corners are projected once, on first use by a visible face (same values quad_flat would compute) */
  for (int f = 0; f < 5; f++) {
    s32 nx = (F[f].nx * c + F[f].nz * s), nz = (F[f].nz * c - F[f].nx * s), ny = F[f].ny * 16384; nx *= F[f].nx || F[f].nz ? 1 : 0;
    if (F[f].nx) { nx = F[f].nx * c; nz = -F[f].nx * s; } if (F[f].nz) { nx = F[f].nz * s; nz = F[f].nz * c; }
    V3 ctr = { (p[F[f].a].x + p[F[f].d].x) >> 1, (p[F[f].a].y + p[F[f].d].y) >> 1, (p[F[f].a].z + p[F[f].d].z) >> 1 };
    s32 d = (nx * (camx - ctr.x) + ny * (camy - ctr.y) + nz * (camz - ctr.z)) >> 14; if (d <= 0) continue;
    int vi[4] = { F[f].a, F[f].b, F[f].c, F[f].d };
    for (int k = 0; k < 4; k++) if (!(have >> vi[k] & 1)) { proj(p[vi[k]].x, p[vi[k]].y, p[vi[k]].z, &pv[vi[k]]); have |= 1u << vi[k]; }
    PV *qa = &pv[vi[0]], *qb = &pv[vi[1]], *qc = &pv[vi[2]], *qd = &pv[vi[3]];
    int key = zdepth(ctr.x, ctr.y, ctr.z) - 20, qq = qclass(qa, qb, qc, qd);
    if (qq == Q_SKIP) continue;
    if (qq == Q_OK) { put_f4(bucket(key), 0, flat_col(mat, F[f].l, 0), qa, qb, qc, qd); continue; }
    { V3 w[4] = { p[vi[0]], p[vi[1]], p[vi[3]], p[vi[2]] }; clip_emit_flat(w, 4, bucket(key), 0, flat_col(mat, F[f].l, 0), 2); }
  }
}
static void car_draw(s32 x, s32 y, s32 z, int ya) {
#ifndef NOCARCULL
  if (!in_view(x, y + 100, z, 330)) return;   /* bounding sphere (car half-diagonal 262 + wheels) outside the view frustum: every face would be Q_SKIP */
#endif
  int s = fsin(ya), c = fcos(ya);
  obox(x, y + 70, z, ya, 112, 38, 235, 11);                                              /* body */
  obox(x - (s * 25 >> 14), y + 140, z - (c * 25 >> 14), ya, 98, 34, 120, 6);             /* cabin (glass) */
  for (int i = 0; i < 4; i++) { int sx = (i & 1) ? 112 : -112, sz = (i & 2) ? 150 : -150;
    obox(x + ((sx * c + sz * s) >> 14), y + 30, z + ((sz * c - sx * s) >> 14), ya, 14, 30, 36, 1); }
}

#ifndef OLDMODELS
#include "models.h"
#endif
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
/* cell floor of the loaded world at world units (x,z), decks ignored; 100000 outside the grid (stage 13: lets the glue lift a guest pose that is far below this world's ground) */
int sf3_floor_at(int x, int z) { return ground_at(x, z, -100000); }
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
/* stage 19: command word after the GPU is idle, the two parameters without a wait, every data word by DMA2 (blocks of 16, a remainder as one
   shorter block): bit 26 stays clear while GP0(A0h) waits for its parameters and data (psx-spx "Ready Bits") */
static void vram_dma(int x, int y, int w, int h, const void *src) {
  gpu_idle();
  gp0c(0xA0000000); gp0p(XY(x, y)); gp0p(XY(w, h));
  gpu_dma(src, ((u32)(w * h) + 1) >> 1);
}
/* ------------------------------------------------------------------------------------------- vram upload (streamed from SF3A.BIN) */
extern void sf3_cd_read(u32 lba, u32 nsec, u8 *dst);
extern const u32 CD_SF3W_LBA;   /* stage 7: LBA of SF3M.BIN (all 11 maps, see tools/mkmaps7.py) */
static u8 *const sf_tmp = (u8 *)SF_TMP;      /* the primitive buffer doubles as the upload buffer at start */
static void upload_all(u32 lba) {
  dbg("up a\n"); sf3_cd_read(lba, 1, sf_tmp); lba += 1; dbg("up b\n");
  const u32 *h = (const u32 *)sf_tmp; u32 npg = h[0], nclut = h[1], nfont = h[2]; u16 rc[4 * 8]; for (u32 i = 0; i < 4 * npg && i < 32; i++) rc[i] = ((const u16 *)(sf_tmp + 16))[i];
  for (u32 i = 0; i < npg; i++) {
    sf3_cd_read(lba, 32, sf_tmp); lba += 32;          /* one 64 KB atlas page */
    vram_dma(rc[4 * i], rc[4 * i + 1], 128, 256, sf_tmp);
  }
  u32 cs = (nclut + 2047) / 2048, fs = (nfont + 2047) / 2048;
  sf3_cd_read(lba, cs, sf_tmp); lba += cs; vram_dma(0, 480, 256, 8, sf_tmp);
  sf3_cd_read(lba, fs, sf_tmp);
  const u16 *f = (const u16 *)sf_tmp; vram_dma(f[0], f[1], f[2], f[3], sf_tmp + 8); vram_dma(0, 488, 16, 1, sf_tmp + 8 + 3072);
}

/* ------------------------------------------------------------------------------------------- stage 3 entry points */
#include "../include/sf_entity.h"
int sf3_sin(int a) { return fsin(a); }
u8 sf3_plook, sf3_ppol; u32 sf3_mt = 0xffff;    /* the controlled entity's look / police flag (set by gather3); test view number shown in the HUD */
u32 sf3_ph[8], sf3_cnt[32]; /* PROFILE: TICKS8 (1/270 line) per phase: sky island city ground car/ents hud send; counters proj leaf clip prim */
u32 sf3_hash;
s32 sf3_score, sf3_hp, sf3_clock; u32 sf3_stat_eng, sf3_stat_prim, sf3_stat_ovf, sf3_stat_lod, sf3_frames, sf3_stat_gpu;
static int sf3_have; int sf3_hide_player;
u32 sf3_w_lba, sf3_w_len;   /* stage 13: first sector / byte length of the loaded map's world file (read-only data in the renderer window): rt.c re-reads a slice of it after a cold-code overlay hit it */
u32 sf3_map_cur, sf3_map_x, sf3_map_y, sf3_map_z, sf3_map_loads; static int cam_first = 1;
/* stage 7: load map n (0..10) from SF3M.BIN on the CD: world, atlas (VRAM upload), side tables.  Runs between frames (the primitive buffer is the upload buffer).
   Returns 0, or -1 with the old map still in place if the header or the world magic is wrong. */
int sf3_map_load(u32 n) {
  if (n > 10) return -1;
  sf3_cd_read(CD_SF3W_LBA, 1, sf_tmp);
  const u32 *hd = (const u32 *)sf_tmp; if (hd[0] != 0x4d334653 || hd[1] != 11) { dbg("SF3M bad header\n"); return -1; }
  const u32 *e = hd + 2 + 8 * n; u32 first = e[0], wsec = e[1], asec = e[2], sbytes = e[3], sx = e[4], sy = e[5], sz = e[6];
  u32 lba = CD_SF3W_LBA + first; sf3_w_lba = lba; sf3_w_len = wsec * 2048;
  sf3_cd_read(lba, wsec, (u8 *)SF_WORLD);
  if (*(const u32 *)SF_WORLD != 0x57334653) { dbg("SF3W bad magic\n"); return -1; }
  sf3_cd_read(lba + wsec + asec, (sbytes + 2047) / 2048, sf_tmp); { u32 nf = sbytes - 8192; for (u32 i = 0; i < nf; i++) ((u8 *)SF_SIDE)[i] = sf_tmp[i]; if (!sf3_map_loads) for (u32 i = 0; i < 4096; i++) sint_tab[i] = ((const s16 *)(sf_tmp + nf))[i]; }
  world_init(); upload_all(lba + wsec);
#ifndef OLDMODELS
  models_upload();
#endif
  for (u32 i = 0; i < 3072 + 1024 + 2304; i++) ((volatile u16 *)SF_ST)[i] = 0;
  sf3_map_cur = n; sf3_map_x = sx; sf3_map_y = sy; sf3_map_z = sz; sf3_map_loads++; cam_first = 1;
  return 0;
}
u32 sf3_first_map;   /* stage 13: the map the guest's level runs on (0 when the renderer starts with the program) */
int sf3_init(void) {
  dbg("sf3_init a\n"); timers_init();
GP1 = 0x04000002; DPCR |= 0x08000800;
  if (sf3_map_load(sf3_first_map)) return -1;
  dbg("sf3 init ok\n"); sf3_have = 1; return 0;
}

/* ------------------------------------------------------------------------------------------- stage 7: ragdolls (world callbacks for the stage 5 solver, drawing) */
#include "../rd/ragdoll_ps1.h"
extern s32 rd_pos[4][RP_P][3]; extern u8 rd_live[4]; extern u32 rd_shirt[4];
#define U2F(u) ((fx)(u) << 14)                      /* renderer units (64 a metre) -> Q20 metres */
static int rpw_floor(void *u, fx x, fx z, fx y, fx *h, rp_v3 *n, int *mat) {
  (void)u; int ux = x >> 14, uz = z >> 14, uy = y >> 14; int g = ground_at(ux, uz, uy);
  if (g > 90000) { *h = 0; *n = (rp_v3){ 0, RP_ONE, 0 }; *mat = RP_ROAD; return 1; }
  *h = U2F(g); *mat = RP_ROAD; *n = (rp_v3){ 0, RP_ONE, 0 };
  const Cell *c = &celldict[cellidx[(ux >> 10) * 128 + (uz >> 10)]];
  if (c->shape >= 2 && c->shape <= 5) {       /* ramp cell: normal from the slope (units of height over 1024 units of run) */
    int sl = c->hi - c->lo; if (c->shape >= 4) sl = -sl; int s10 = sl; int s2 = (s10 * s10) >> 0;   /* Q20 of s^2 */
    int f = RP_ONE - (s2 >> 1) + ((s2 >> 10) * (s2 >> 10) * 3 >> 3 >> 0); if (f < RP_ONE / 2) f = RP_ONE / 2;
    int sn = (int)(((long)s10 * f) >> 10);   /* Q20 sin-like component */
    if (c->shape == 2 || c->shape == 4) n->z = -sn; else n->x = -sn;
    n->y = f; }
  return 1;
}
static int isqrt32(u32 v) { u32 r = 0, b = 1u << 30; while (b > v) b >>= 2; while (b) { if (v >= r + b) { v -= r + b; r = (r >> 1) + b; } else r >>= 1; b >>= 2; } return (int)r; }
static int rpw_solid(void *u, rp_v3 p, fx r, rp_v3 *n, fx *depth) {
  (void)u; int ux = p.x >> 14, uy = p.y >> 14, uz = p.z >> 14, ru = (r >> 14) + 1;
  int sx = ux >> 13, sz = uz >> 13; if ((unsigned)sx > 15 || (unsigned)sz > 15) return 0;
  int s = sx * 16 + sz, first = sector[2 * s], cnt = sector[2 * s + 1];
  for (int i = 0; i < cnt; i++) {
    u16 it = items[first + i]; if ((it >> 13) != 0) continue; const Box *b = &boxes[it & 0x1fff];
    int X0 = b->x0 * CELL, Z0 = b->z0 * CELL, X1 = b->x1 * CELL, Z1 = b->z1 * CELL, top = b->h, bot = b->base ? b->base * 64 : -4096;
    if (ux < X0 - ru || ux > X1 + ru || uz < Z0 - ru || uz > Z1 + ru || uy < bot - ru || uy > top + ru) continue;
    int cx = ux < X0 ? X0 : ux > X1 ? X1 : ux, cy = uy < bot ? bot : uy > top ? top : uy, cz = uz < Z0 ? Z0 : uz > Z1 ? Z1 : uz;
    int dx = ux - cx, dy = uy - cy, dz = uz - cz; u32 l2 = dx * dx + dy * dy + dz * dz;
    if (l2 > 0) { int l = isqrt32(l2); if (l >= ru - 1 && l * 16384 >= (r >> 0)) continue; if (l == 0) continue;
      *n = (rp_v3){ (dx << 20) / l, (dy << 20) / l, (dz << 20) / l }; *depth = r - ((fx)l << 14); if (*depth <= 0) continue; return 1; }
    { int f[6] = { ux - X0, X1 - ux, uy - bot, top - uy, uz - Z0, Z1 - uz }, k = 0; for (int j = 1; j < 6; j++) if (f[j] < f[k]) k = j;
      static const s8 nn[6][3] = { { -1, 0, 0 }, { 1, 0, 0 }, { 0, -1, 0 }, { 0, 1, 0 }, { 0, 0, -1 }, { 0, 0, 1 } };
      *n = (rp_v3){ nn[k][0] << 20, nn[k][1] << 20, nn[k][2] << 20 }; *depth = ((fx)f[k] << 14) + r; return 1; }
  }
  return 0;
}
static int rpw_sweep(void *u, rp_v3 a, rp_v3 b, fx r, fx *t, rp_v3 *n) {
  for (int k = 1; k <= 4; k++) { rp_v3 p = { a.x + (b.x - a.x) / 4 * k, a.y + (b.y - a.y) / 4 * k, a.z + (b.z - a.z) / 4 * k }; fx d;
    if (rpw_solid(u, p, r, n, &d)) { *t = RP_ONE / 4 * k - RP_ONE / 4; if (*t < 0) *t = 0; return 1; } }
  return 0;
}
const rp_world sf3_rpw = { 0, rpw_floor, rpw_solid, rpw_sweep };
/* the doll's colours: 0 shirt, 1 skin, 2 trousers, 3 shoes */
static const u8 rd_bone_ab[RP_BONES][2] = { {0,1},{1,2},{2,3},{2,4},{2,5},{0,10},{0,11},{4,6},{6,8},{5,7},{7,9},{10,12},{12,14},{14,16},{11,13},{13,15},{15,17} };
static const u8 rd_bone_cls[RP_BONES] = { 0, 0, 1, 0, 0, 2, 2, 0, 1, 0, 1, 2, 2, 3, 2, 2, 3 };
static const u8 rd_bone_r[RP_BONES] = { 8, 9, 6, 4, 4, 5, 5, 4, 3, 4, 3, 5, 4, 3, 5, 4, 3 };   /* radius in units (64 a metre): 13 cm .. 4 cm */
static void doll_draw(int di) {
  CV cv[RP_P]; for (int j = 0; j < RP_P; j++) { cpu_cam(rd_pos[di][j][0], rd_pos[di][j][1], rd_pos[di][j][2], 0, &cv[j]); if (cv[j].z < 60) return; }
  u32 cls[4] = { rd_shirt[di] & 0xffffff, 0x90B0E0, 0x483830, 0x181818 };         /* BGR order words for the GPU: 0xBBGGRR */
  for (int b = 0; b < RP_BONES; b++) {
    const CV *A = &cv[rd_bone_ab[b][0]], *B = &cv[rd_bone_ab[b][1]]; int za = A->z, zb = B->z, zm = (za + zb) >> 1;
    int ax = 160 + H_FOCAL * A->x / za, ay = 120 - H_FOCAL * A->y / za, bx = 160 + H_FOCAL * B->x / zb, by = 120 - H_FOCAL * B->y / zb;
    if ((ax < -64 && bx < -64) || (ax > 384 && bx > 384) || (ay < -64 && by < -64) || (ay > 304 && by > 304)) continue;
    int hw = H_FOCAL * (rd_bone_r[b] + 1) / zm; if (hw < 1) hw = 1;
    int dx = bx - ax, dy = by - ay, adx = dx < 0 ? -dx : dx, ady = dy < 0 ? -dy : dy, L = adx > ady ? adx + (ady >> 1) : ady + (adx >> 1);
    u32 col = cls[rd_bone_cls[b]]; u32 *p = pnew(5); if (!p) return;
    int nx, ny; if (L < 1) { nx = hw; ny = 0; } else { int f = (hw << 8) / L; nx = -(dy * f) >> 8; ny = (dx * f) >> 8; }
    p[1] = 0x28000000 | col; p[2] = XY(ax + nx, ay + ny); p[3] = XY(ax - nx, ay - ny); p[4] = XY(bx + nx, by + ny); p[5] = XY(bx - nx, by - ny);
    link_ot(bucket(zdepth((rd_pos[di][rd_bone_ab[b][0]][0] + rd_pos[di][rd_bone_ab[b][1]][0]) >> 1, (rd_pos[di][rd_bone_ab[b][0]][1] + rd_pos[di][rd_bone_ab[b][1]][1]) >> 1, (rd_pos[di][rd_bone_ab[b][0]][2] + rd_pos[di][rd_bone_ab[b][1]][2]) >> 1)), p, 5);
  }
  { const CV *H = &cv[3]; int r = H_FOCAL * 7 / H->z + 1, hx = 160 + H_FOCAL * H->x / H->z, hy = 120 - H_FOCAL * H->y / H->z; u32 *p = pnew(5);
    if (p) { p[1] = 0x28000000 | 0x90B0E0; p[2] = XY(hx - r, hy - r); p[3] = XY(hx + r, hy - r); p[4] = XY(hx - r, hy + r); p[5] = XY(hx + r, hy + r); link_ot(bucket(zdepth(rd_pos[di][3][0], rd_pos[di][3][1], rd_pos[di][3][2]) - 8), p, 5); } }
}
/* one frame of the city from the guest's player: position in units, heading in 65536 a turn (our convention), pkind 0 on foot 1 in a vehicle */
#ifdef TREETEST
/* TEST-ONLY (stage 17): fixed poses at Freedom City's park trees: the player stands d units before the tree at cell (cx, cz), looking along heading hd (the camera is 820 behind him) */
int sf3_treepose(int n, s32 *x, s32 *y, s32 *z, int *hd) {
  static const struct { u8 cx, cz; u16 d, hd; } P[] = { { 21, 61, 1500, 0x4000 }, { 23, 61, 1300, 0x0000 }, { 25, 63, 1300, 0x4000 }, { 25, 68, 1500, 0xC000 }, { 10, 56, 1800, 0x0000 }, { 23, 61, 3600, 0x8000 } };
  if (n >= (int)(sizeof P / sizeof P[0])) return 0;
  s32 tx = P[n].cx * 1024 + 512, tz = P[n].cz * 1024 + 512, ty = 0;
  for (int i = 0; i < ntree; i++) if (trees[i].kind < 2 && (trees[i].x >> 8) == P[n].cx && (trees[i].z >> 8) == P[n].cz) { tx = trees[i].x * 4; tz = trees[i].z * 4; ty = trees[i].base * 64; break; }
  s32 s = fsin(P[n].hd), c = fcos(P[n].hd);
  *x = tx - (s * P[n].d >> 14); *z = tz - (c * P[n].d >> 14); *y = ty; *hd = P[n].hd; sf3_hide_player = 1; return 1;
}
#endif
int sf3_frame(int oy, s32 px, s32 py, s32 pz, int heading, int pkind, const SfEnt *ents, int nents, int hud) {
  if (!sf3_have) return -1;
  u32 t0 = HLINES();
  car_x = px << 8; car_y = py << 8; car_z = pz << 8; car_h = heading & 0xffff;
    s32 s = fsin(car_h), c = fcos(car_h); int back = pkind ? 820 : 520, up = pkind ? 300 : 260;
  if (cam_first || iabs_(car_x - cpx) > (6000 << 8) || iabs_(car_z - cpz) > (6000 << 8)) {
    cpx = car_x - (s * back >> 14 << 8); cpz = car_z - (c * back >> 14 << 8); cpy = car_y + (up << 8); yaw = car_h; cam_first = 0; }
  { s32 tx = car_x - (s * back >> 14 << 8), tz = car_z - (c * back >> 14 << 8), ty = car_y + (up << 8);
    cpx += (tx - cpx) >> 1; cpz += (tz - cpz) >> 1; cpy += (ty - cpy) >> 1;
    for (int k = 0; k < 6; k++) {
      int gh = ground_at(cpx >> 8, cpz >> 8, cpy >> 8);
      if (gh < (cpy >> 8) - 60) break;
      cpx = car_x + ((cpx - car_x) >> 1); cpz = car_z + ((cpz - car_z) >> 1);
    }
    int dy = (short)(car_h - yaw); yaw = (yaw + (dy >> 1)) & 0xffff; pitch = -2300; }
  { static const s16 reachs[4] = { REACH, 11264, 10240, 8192 }; static const u8 errs[4] = { ERRPX, 3, 4, 6 }; 
#ifdef LODREACH
    reach = reachs[lod];
#else
    reach = REACH;   /* LOD never shortens the view (stage5 rule): only the subdivision error and the ground grid change */
#endif
    errpx = errs[lod]; }
  cam_from_angles(); cam_commit();
  list_begin(0);
#define PH(k) do { u32 t_ = PHT(); sf3_ph[k] = (t_ - tp_) & 0xffff; tp_ = t_; } while (0)
  u32 tp_ = PHT(); c_proj = 0; c_leaf = 0; c_clip = 0; t_cb = t_cr = t_ct = t_gc = t_clipt = t_rect = t_qoff = t_qf = t_wg = t_fw = t_top = t_pa = t_pb = t_pc = t_pd = t_pf = 0; c_box = c_rect = c_cells = c_cullcell = c_cleaf = c_wg = c_wcell = c_wq = c_wf = 0;
  sky_draw(); PH(0);
  island_draw(flat_col(1, 2, 0)); PH(1);
  city_draw(); PH(2);
ground_draw();
  PH(3);
#ifdef OLDMODELS
  if (pkind) car_draw(px, py, pz, car_h);
  else if (!sf3_hide_player) billboard(px, py, pz, 45, 0, 150, flat_col(7, 2, 0), zdepth(px, py, pz));
  for (int i = 0; i < nents; i++) {
    const SfEnt *e = &ents[i]; if (e->kind == 0) car_draw(e->x, e->y, e->z, e->yaw);
    else { CV cc; cpu_cam(e->x, e->y, e->z, 0, &cc); if (cc.z > 60 && cc.z < 5000) billboard(e->x, e->y, e->z, 40, 0, 140, flat_col(10, 1, 0), cc.z); }
  }
#else
  n_t0v = n_t0p = n_veh = n_ped = 0; t_vehl = t_pedl = 0;
  /* stage 17: the player first (always full detail), then the entities nearest first so the far ones get the cheap model when the primitive pool runs short */
  if (pkind) veh_draw(px, py, pz, car_h, sf3_plook, sf3_ppol, 0);
  else if (!sf3_hide_player) ped_draw(px, py, pz, car_h, 128, ROW_HERO, 0);
  { int n = nents > 40 ? 40 : nents;    /* two passes, near first (the cheap levels and the primitive pool check do the rest) */
    for (int pass = 0; pass < 2; pass++) for (int k = 0; k < n; k++) { const SfEnt *e = &ents[k]; int d = zdepth(e->x, e->y, e->z); if ((d < 1300) != (pass == 0) || d < -400 || d > 9000) continue;
      if (e->kind == 0) veh_draw(e->x, e->y, e->z, e->yaw, e->look, e->pol, d);
      else ped_draw(e->x, e->y, e->z, e->yaw, e->spare & 127, ped_row(e->spare & 127, e->pol, e->look == 0xFE), d); } }
#endif
  PH(4);
#ifdef SPINHASH
  { u32 h = 2166136261u; u32 lo = ADDR(pbs), hi = lo + PBW * 4, ol = ADDR(otc), oh = ol + OTN * 4;   /* link words that point at static variables (binary-layout dependent) are masked */
    for (const u32 *q = pbs; q < pb; ) { u32 n = q[0] >> 24, ad = q[0] & 0xFFFFFF; h = (h ^ (n << 24) ^ (((ad >= lo && ad < hi) || (ad >= ol && ad < oh)) ? ad : 0)) * 16777619u;
      for (u32 k = 1; k <= n; k++) h = (h ^ q[k]) * 16777619u; q += n + 1; }
    for (int k = 1; k < OTN; k++) h = (h ^ otc[k]) * 16777619u; sf3_hash = h; }
#endif
  for (int di = 0; di < 4; di++) if (rd_live[di]) doll_draw(di);
  if (hud) {
    char b[80], *e;
    e = fmt_s(b, "ENG "); e = fmt_int(e, sf3_stat_eng, 0); e = fmt_s(e, " Q "); e = fmt_int(e, nprim, 0); e = fmt_s(e, " OVF "); e = fmt_int(e, sf3_stat_ovf, 0); e = fmt_s(e, " LOD "); e = fmt_int(e, lod, 0); e = fmt_s(e, " MAP "); e = fmt_int(e, sf3_map_cur, 0); if (sf3_mt != 0xffff) { e = fmt_s(e, " MT "); e = fmt_int(e, sf3_mt, 0); }
    hud_box(4, 12, 232, 11); hud_str(6, 14, b, 0xC0FFC0);
    e = fmt_s(b, "SCORE "); e = fmt_int(e, sf3_score, 0); e = fmt_s(e, " HP "); e = fmt_int(e, sf3_hp, 0); e = fmt_s(e, " CLK "); e = fmt_int(e, sf3_clock, 0);
    hud_box(4, 24, 232, 11); hud_str(6, 26, b, 0xFFE080);
  }
  PH(5);
  gpu_idle();
  /* stage 19: the 3D view is drawn into lines 8..231 of the buffer, the area the 2D layer and its HUD use (ppu12.h PP_Y0/PP_H); same projection
     (centre 160,120, H 181, square pixels), so the view is not stretched, only its top and bottom 8 lines are not drawn */
  gp0c(0xE1000400 | TPAGE(320, 0, 1, 0)); gp0e(0xE3000000 | ((oy + 8) << 10)); gp0e(0xE4000000 | 319 | ((oy + 231) << 10)); gp0e(0xE5000000 | (oy << 11));
  list_send(); PH(6);
  sf3_cnt[0] = c_proj; sf3_cnt[1] = c_leaf; sf3_cnt[2] = c_clip; sf3_cnt[3] = t_cb / 268; sf3_cnt[4] = t_cr / 268; sf3_cnt[5] = t_ct / 268; sf3_cnt[6] = t_gc / 268; sf3_cnt[7] = t_clipt / 268; sf3_ph[7] = 0; sf3_cnt[8] = t_rect / 268; sf3_cnt[9] = t_qoff / 268; sf3_cnt[10] = t_qf / 268; sf3_cnt[11] = c_box; sf3_cnt[12] = c_rect; sf3_cnt[13] = c_cells; sf3_cnt[14] = c_cullcell; sf3_cnt[15] = c_cleaf; sf3_cnt[16] = t_wg / 268; sf3_cnt[17] = t_fw / 268; sf3_cnt[18] = t_top / 268; sf3_cnt[19] = c_wg; sf3_cnt[20] = c_wcell; sf3_cnt[21] = c_wq; sf3_cnt[22] = c_wf; sf3_cnt[23] = t_pa / 268; sf3_cnt[24] = t_pb / 268; sf3_cnt[25] = t_pc / 268; sf3_cnt[26] = t_pd / 268; sf3_cnt[27] = t_pf / 268;
#ifndef OLDMODELS
  sf3_cnt[28] = t_vehl; sf3_cnt[29] = t_pedl; sf3_cnt[30] = n_veh; sf3_cnt[31] = n_ped;
#endif
  u32 t1 = HLINES(); u32 eng = (t1 - t0) & 0xffff;
  sf3_stat_eng = eng; sf3_stat_prim = nprim; sf3_stat_ovf = ovf; sf3_stat_lod = lod; sf3_frames++; ovf = 0;
  { int budget = FIELDS * 263 - 70; static int calm;
    if ((int)eng > budget && lod < 3) { lod++; calm = 0; } else if ((int)eng < budget - LODCALM && lod > 0) { if (++calm > 45) { lod--; calm = 0; } } else calm = 0; }
#ifdef FIXLOD
  lod = FIXLOD;
#endif
  return 0;
}
