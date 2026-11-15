/* app.c: Stage 5 ragdoll test disc. Scripted car jump off a ramp, bail-out and five pedestrians hit, drawn with the GTE.
   One translation unit, no SDK. Build: ./build.sh TAG [-DRP_LEVEL=n -DHOLD_AT=frame ...]. */
#define PS1 1
#include "ps1.h"
#include "ragdoll_ps1.c"
#include "rt.inc"

#ifndef LOGFROM
#define LOGFROM 100
#endif
#ifndef LOD_FULL
#define LOD_FULL 2
#endif
#ifndef FIELDS
#define FIELDS 1                       /* 1 = shown at 60 fps if a frame fits 263 hblank lines */
#endif
#ifndef HFOCAL
#define HFOCAL 300
#endif
#define OTN2 1024
#define PBW 24000
static u32 otb[2][OTN2], pbuf[2][PBW];
static u32 *otc, *pbp, *pbe;
static int nprim, ovf;
static void list_begin(int c)
{
    otc = otb[c]; pbp = pbuf[c]; pbe = pbuf[c] + PBW - 64; nprim = 0;
    D6_MADR = (u32)&otc[OTN2 - 1] & 0xFFFFFF; D6_BCR = OTN2; D6_CHCR = 0x11000002; while (D6_CHCR & 0x01000000) {}
}
static void list_send(void)
{
    while (!(GP1 & 0x04000000)) {}
    D2_MADR = (u32)&otc[OTN2 - 1] & 0xFFFFFF; D2_BCR = 0; D2_CHCR = 0x01000401;
}
#define BGR(c) ((((c) & 0xFF) << 16) | ((c) & 0xFF00) | (((c) >> 16) & 0xFF))
static inline u32 *np(int w) { u32 *p = pbp; if (p >= pbe) { ovf++; return 0; } pbp = p + w + 1; nprim++; return p; }
static inline void lk(int z, u32 *p, int w) { if (z < 0) z = 0; if (z > OTN2 - 1) z = OTN2 - 1; p[0] = ((u32)w << 24) | otc[z]; otc[z] = (u32)p & 0xFFFFFF; }
static inline void F4(int z, u32 rgb, u32 a, u32 b, u32 c, u32 d) { u32 *p = np(5); if (!p) return; p[1] = 0x28000000 | BGR(rgb); p[2] = a; p[3] = b; p[4] = c; p[5] = d; lk(z, p, 5); }
static inline void G4(int z, u32 a, u32 ca, u32 b, u32 cb, u32 c, u32 cc, u32 d, u32 cd) { u32 *p = np(8); if (!p) return;
    p[1] = 0x38000000 | BGR(ca); p[2] = a; p[3] = BGR(cb); p[4] = b; p[5] = BGR(cc); p[6] = c; p[7] = BGR(cd); p[8] = d; lk(z, p, 8); }
static inline void FILL(int z, int y, u32 rgb) { u32 *p = np(3); if (!p) return; p[1] = 0x02000000 | BGR(rgb); p[2] = XY(0, y); p[3] = XY(320, 240); lk(z, p, 3); }

/* ---- timing: root counter 2 = sysclk/8 (16 bit), counter 1 = hblank */
static u32 tot_sol_ticks, sol_ticks, sol_worst, sol_t0, step_count, sub_sum, sol_ticks_frame;
static u32 sol_h0;
/* a step can take longer than the 16-bit sysclk/8 counter's 524288 cycles: the hblank counter says how many wraps */
static inline u32 elapsed8(u32 t0, u32 h0) { u32 tk = (TICKS8() - t0) & 0xffff, hl = (HLINES() - h0) & 0xffff, est = hl * 268; u32 k = est > tk ? (est - tk + 32768) >> 16 : 0; return tk + (k << 16); }
#define SC_T0() (sol_t0 = TICKS8(), sol_h0 = HLINES())
#define SC_T1(i) do { u32 dt_ = elapsed8(sol_t0, sol_h0); sol_ticks_frame += dt_; tot_sol_ticks += dt_; step_count++; sub_sum += act[i].d.nsub; if (dt_ > sol_worst) sol_worst = dt_; } while (0)
#include "scenario.inc"

/* ---- camera and projection */
static rp_v3 cam;                                  /* tgt (the camera target) lives in scenario.inc: the budget governor ranks dolls by it */
static int proj_ok;
static inline int proj(rp_v3 p, int *sx, int *sy)       /* returns depth (1/256 m units) or 0 when unusable */
{
    s32 dx = (p.x - cam.x) >> 12, dy = (p.y - cam.y) >> 12, dz = (p.z - cam.z) >> 12;
    if (dx > 32000 || dx < -32000 || dy > 32000 || dy < -32000 || dz > 32000 || dz < -32000) return 0;     /* must fit the GTE's 16-bit vector */
    MTC2(0, (dx & 0xffff) | ((u32)dy << 16)); MTC2(1, dz);
    GTE(RTPS);
    u32 sxy = MFC2(14), sz = MFC2(19);
    *sx = (s16)sxy; *sy = (s16)(sxy >> 16);
    return (int)(sz & 0xffff);
}
#define INSCR(x, y) ((x) > -700 && (x) < 1000 && (y) > -700 && (y) < 900)
static int horizon_y;
static void cam_setup(void)
{
    const int yawc = 4400, pitch = 3300;                 /* 24 deg to the right of the road's axis, 18 deg down */
    fx sy = rsin(yawc) >> 8, cy = rcos(yawc) >> 8, sp = rsin(pitch) >> 8, cp = rcos(pitch) >> 8;   /* Q12 */
    s32 m[9] = { cy, 0, -sy,   -((sy * sp) >> 12), -cp, -((cy * sp) >> 12),   (sy * cp) >> 12, -sp, (cy * cp) >> 12 };
    gte_set_rot(m); gte_set_trans(0, 0, 0);
    CTC2(24, (160 << 16) + 0x8000); CTC2(25, (120 << 16) + 0x8000); CTC2(26, HFOCAL);
    fx D = MM(10000), Hc = MM(3400);
    cam.x = tgt.x - mul(D, rsin(yawc)); cam.z = tgt.z - mul(D, rcos(yawc)); cam.y = tgt.y + Hc;
    horizon_y = 120 - (HFOCAL * sp) / cp;
}

/* ---- the ground: a lattice of 4 m cells, the ramp is part of it */
#define LC 9
#define LR 15
static fx ground_h(fx x, fx z) { if (iabs(x) < RAMP_HW + 1 && z > RAMP_Z0 && z <= RAMP_Z1 && iabs(x) <= RAMP_HW) return mul(z - RAMP_Z0, RAMP_SLOPE); return 0; }
static u32 shade(u32 rgb, int k)      /* k/256 */
{ u32 r = (rgb >> 16) & 255, g = (rgb >> 8) & 255, b = rgb & 255; r = r * k >> 8; g = g * k >> 8; b = b * k >> 8; if (r > 255) r = 255; if (g > 255) g = 255; if (b > 255) b = 255; return (r << 16) | (g << 8) | b; }
static void draw_ground(void)
{
    static int px[LR][LC], py[LR][LC], pz[LR][LC];
    fx z0 = ((cam.z - MM(4000)) >> 20) & ~3; z0 = z0 << 20;             /* first lattice row, a multiple of 4 m, just behind the camera */
    fx xc = ((cam.x) >> 20) & ~3; xc <<= 20;
    for (int r = 0; r < LR; r++)
        for (int c = 0; c < LC; c++) {
            fx x = xc + (c - 4) * MM(4000), z = z0 + r * MM(4000);
            pz[r][c] = proj(V(x, ground_h(x, z), z), &px[r][c], &py[r][c]);
        }
#ifdef GDBG
    { static int once; if (!once++) { dbg("G cam "); ddec(cam.x >> 10); ddec(cam.y >> 10); ddec(cam.z >> 10); dbg("z0 "); ddec(z0 >> 10); dbg("pz "); for (int r = 0; r < 6; r++) for (int c = 0; c < LC; c += 4) { ddec(pz[r][c]); ddec(px[r][c]); ddec(py[r][c]); dbg("|"); } dbg("\n"); } }
#endif
    for (int r = 0; r < LR - 1; r++)
        for (int c = 0; c < LC - 1; c++) {
            int z00 = pz[r][c], z10 = pz[r][c + 1], z01 = pz[r + 1][c], z11 = pz[r + 1][c + 1];
            if (z00 < 300 || z10 < 300 || z01 < 300 || z11 < 300) continue;
            if (!INSCR(px[r][c], py[r][c]) || !INSCR(px[r][c + 1], py[r][c + 1]) || !INSCR(px[r + 1][c], py[r + 1][c]) || !INSCR(px[r + 1][c + 1], py[r + 1][c + 1])) continue;
            fx x = xc + (c - 4) * MM(4000), z = z0 + r * MM(4000);
            int xi = (x >> 20) >> 2, zi = (z >> 20) >> 2;
            int chk = (xi + zi) & 1;
            u32 col;
            if (iabs(x + MM(2000)) < RAMP_HW + 1 && z >= RAMP_Z0 && z < RAMP_Z1) col = chk ? 0xC89030 : 0xB88028;
            else if (x >= MM(-8000) && x < MM(8000)) col = (x >= MM(-1) && x < MM(3999) + 1 && 0) ? 0 : (chk ? 0x666670 : 0x585862);
            else col = chk ? 0x3E8236 : 0x36742E;
            if (z >= MM(88000) - MM(4000) && z < MM(92000)) col = shade(col, 230);
            int zz = ((z00 + z10 + z01 + z11) >> 6) + 12;
            F4(zz, col, XY(px[r][c], py[r][c]), XY(px[r][c + 1], py[r][c + 1]), XY(px[r + 1][c], py[r + 1][c]), XY(px[r + 1][c + 1], py[r + 1][c + 1]));
        }
}

/* ---- boxes (building, wall, car) */
static const u8 face_v[6][4] = { {0, 4, 2, 6}, {1, 5, 3, 7}, {0, 1, 4, 5}, {2, 3, 6, 7}, {0, 1, 2, 3}, {4, 5, 6, 7} };
static const u16 face_k[6] = { 170, 170, 90, 256, 140, 140 };
static void draw_box8(const rp_v3 *v, u32 col, int zbias)
{
    int sx[8], sy[8], sz[8];
    for (int i = 0; i < 8; i++) { sz[i] = proj(v[i], &sx[i], &sy[i]); if (sz[i] < 200 || !INSCR(sx[i], sy[i])) return; }
    for (int f = 0; f < 6; f++) {
        const u8 *q = face_v[f];
        int z = ((sz[q[0]] + sz[q[1]] + sz[q[2]] + sz[q[3]]) >> 6) + zbias;
        F4(z, shade(col, face_k[f]), XY(sx[q[0]], sy[q[0]]), XY(sx[q[1]], sy[q[1]]), XY(sx[q[2]], sy[q[2]]), XY(sx[q[3]], sy[q[3]]));
    }
}
static void draw_static_box(const rp_box *b, u32 col)
{
    rp_v3 v[8];
    for (int i = 0; i < 8; i++) v[i] = V(i & 1 ? b->hi.x : b->lo.x, i & 2 ? b->hi.y : b->lo.y, i & 4 ? b->hi.z : b->lo.z);
    draw_box8(v, col, 4);
}
static void draw_car(void)
{
    rp_v3 v[8];
    for (int i = 0; i < 8; i++) {
        rp_v3 l = V(i & 1 ? car.half_x : -car.half_x, i & 2 ? car.half_y : -car.half_y, i & 4 ? car.half_z : -car.half_z);
        v[i] = add(car.pos, V(mul(l.x, car.m[0]) + mul(l.y, car.m[3]) + mul(l.z, car.m[6]), mul(l.x, car.m[1]) + mul(l.y, car.m[4]) + mul(l.z, car.m[7]), mul(l.x, car.m[2]) + mul(l.y, car.m[5]) + mul(l.z, car.m[8])));
    }
    draw_box8(v, 0xD03828, 0);
}

/* ---- dolls */
static const u8 bone_ab_[RP_BONES][2] = {
    {RP_PELVIS, RP_SPINE}, {RP_SPINE, RP_CHEST}, {RP_CHEST, RP_HEAD}, {RP_CHEST, RP_SHL}, {RP_CHEST, RP_SHR}, {RP_PELVIS, RP_HPL},
    {RP_PELVIS, RP_HPR}, {RP_SHL, RP_ELL}, {RP_ELL, RP_HDL}, {RP_SHR, RP_ELR}, {RP_ELR, RP_HDR}, {RP_HPL, RP_KNL}, {RP_KNL, RP_ANL},
    {RP_ANL, RP_TOL}, {RP_HPR, RP_KNR}, {RP_KNR, RP_ANR}, {RP_ANR, RP_TOR},
};
/* which colour a bone gets: 0 shirt, 1 skin, 2 trousers, 3 shoes */
static const u8 bone_cls[RP_BONES] = { 0, 0, 1, 0, 0, 2, 2, 0, 1, 0, 1, 2, 2, 3, 2, 2, 3 };
static void draw_doll(const rp_doll *d, int who)
{
    int sx[RP_P], sy[RP_P], sz[RP_P];
    for (int i = 0; i < RP_P; i++) { sz[i] = proj(d->pos[i], &sx[i], &sy[i]); if (sz[i] < 200) return; }
    u32 cls[4] = { (u32)ped_shirt[who], 0xE0B090, 0x303848, 0x181818 };
    for (int b = 0; b < RP_BONES; b++) {
        int a = bone_ab_[b][0], c = bone_ab_[b][1];
        int z = (sz[a] + sz[c]) >> 5;
        int dx = sx[c] - sx[a], dy = sy[c] - sy[a];
        if (!INSCR(sx[a], sy[a]) || !INSCR(sx[c], sy[c])) continue;
        int hw = ((bone_r_mm[b] * 256 / 1000) * HFOCAL) / (((sz[a] + sz[c]) >> 1) + 1);     /* half width in pixels */
        if (hw < 1) hw = 1;
        int adx = dx < 0 ? -dx : dx, ady = dy < 0 ? -dy : dy, L = adx > ady ? adx + (ady >> 1) : ady + (adx >> 1);
        u32 col = cls[bone_cls[b]];
        if (L < 1) { F4(z, col, XY(sx[a] - hw, sy[a] - hw), XY(sx[a] + hw, sy[a] - hw), XY(sx[a] - hw, sy[a] + hw), XY(sx[a] + hw, sy[a] + hw)); continue; }
        int f = (hw << 8) / L, nx = -(dy * f) >> 8, ny = (dx * f) >> 8;
        F4(z, col, XY(sx[a] + nx, sy[a] + ny), XY(sx[a] - nx, sy[a] - ny), XY(sx[c] + nx, sy[c] + ny), XY(sx[c] - nx, sy[c] - ny));
        if (bone_cls[b] != 3 && hw > 1) F4(z - 1, col, XY(sx[c] - hw + 1, sy[c] - hw + 1), XY(sx[c] + hw - 1, sy[c] - hw + 1), XY(sx[c] - hw + 1, sy[c] + hw - 1), XY(sx[c] + hw - 1, sy[c] + hw - 1));
    }
    /* head: an octagon from two squares */
    { int h = RP_HEAD, r = (110 * 256 / 1000 * HFOCAL) / (sz[h] + 1) + 1, r2 = r * 7 / 10 + 1; int z = (sz[h] >> 4) - 2;
      F4(z, 0xE0B090, XY(sx[h] - r, sy[h] - r2), XY(sx[h] + r, sy[h] - r2), XY(sx[h] - r, sy[h] + r2), XY(sx[h] + r, sy[h] + r2));
      F4(z, 0xE0B090, XY(sx[h] - r2, sy[h] - r), XY(sx[h] + r2, sy[h] - r), XY(sx[h] - r2, sy[h] + r), XY(sx[h] + r2, sy[h] + r));
      F4(z - 1, 0x403020, XY(sx[h] - r2, sy[h] - r), XY(sx[h] + r2, sy[h] - r), XY(sx[h] - r2 + 1, sy[h] - r2), XY(sx[h] + r2 - 1, sy[h] - r2)); }
    /* a blob shadow under the pelvis on the ground */
    { fx gx = d->pos[0].x, gz = d->pos[0].z; int ax_, ay_, bx_, by_, cx_, cy_, dx_, dy_; fx rr = MM(700); fx gh = ground_h(gx, gz);
      int z1 = proj(V(gx - rr, gh, gz - rr), &ax_, &ay_), z2 = proj(V(gx + rr, gh, gz - rr), &bx_, &by_), z3 = proj(V(gx - rr, gh, gz + rr), &cx_, &cy_), z4 = proj(V(gx + rr, gh, gz + rr), &dx_, &dy_);
      if (z1 > 200 && z2 > 200 && z3 > 200 && z4 > 200 && INSCR(ax_, ay_) && INSCR(dx_, dy_)) F4(((z1 + z2 + z3 + z4) >> 6) + 8, 0x2C2C30, XY(ax_, ay_), XY(bx_, by_), XY(cx_, cy_), XY(dx_, dy_)); }
}

/* ---- the bars: top row = solver, second row = rest of the engine; 1 px = 2 hblank lines, white tick = one field (263 lines) */
static void draw_bars(u32 sol_lines, u32 ren_lines)
{
    u32 a = sol_lines / 2, b = ren_lines / 2; if (a > 300) a = 300; if (b > 300) b = 300;
    F4(3, 0xE08030, XY(4, 4), XY(4 + a, 4), XY(4, 9), XY(4 + a, 9));
    F4(3, 0x40C0E0, XY(4, 11), XY(4 + b, 11), XY(4, 16), XY(4 + b, 16));
    F4(2, 0xFFFFFF, XY(4 + 131, 2), XY(4 + 132, 2), XY(4 + 131, 18), XY(4 + 132, 18));
}

static void gpu_setup_draw(int oy)
{
    gp0(0xE1000400 | TPAGE(320, 0, 1, 0)); gp0(0xE3000000 | (oy << 10)); gp0(0xE4000000 | 319 | ((oy + 239) << 10)); gp0(0xE5000000 | (oy << 11));
}
static u32 pbits(u32 v) { return v; }

void main(void)
{
    gpu_init(); timers_init();
    dbg("RAGDOLL STAGE5 level "); ddec(RP_LEVEL); dbg("\n");
    sc_reset();
    tgt = V(0, MM(1500), MM(8000));
    int frame = 0, cl = 0, prev_oy = -1; u32 flip_t = HLINES();
    u32 tot_sol = 0, max_sol = 0, tot_ren = 0, max_ren = 0, tot_fr = 0, max_fr = 0, nover = 0, nfr = 0, last_sol = 0, last_ren = 0;
    u32 peak_act = 0;
    for (;;) {
        u32 t0 = HLINES();
        sol_ticks_frame = 0;
        int hold = 0;
#ifdef HOLD_AT
        if (sc_frame_no >= HOLD_AT) hold = 1;
#endif
        if (!hold) {
            sc_script();
#if !defined(NO_LOD) && !defined(POLICY)
            /* detail by rank: the two dolls nearest the camera target get the full solver, the next two drop hinges and self contact,
               the rest also one pass and the bone-ball contacts. Only dolls moving faster than 2 m/s are ranked. */
            { int idx[NACT], n = 0;
              for (int i = 0; i < NACT; i++) if (act[i].active && act[i].d.state != RP_ASLEEP) {
                  const rp_v3 *pv = &act[i].d.vel[RP_PELVIS];
                  if (iabs(pv->x) + iabs(pv->y) + iabs(pv->z) > 2 * RP_ONE) idx[n++] = i;      /* only the fast ones are ranked; a settling doll gets the full solver so it comes to rest and sleeps */
                  else act[i].d.lod = 0; }
              for (int a = 1; a < n; a++) { int k = idx[a], j = a - 1; fx dk = iabs(act[k].d.pos[0].z - tgt.z) + iabs(act[k].d.pos[0].x - tgt.x);
                  while (j >= 0 && iabs(act[idx[j]].d.pos[0].z - tgt.z) + iabs(act[idx[j]].d.pos[0].x - tgt.x) > dk) { idx[j + 1] = idx[j]; j--; } idx[j + 1] = k; }
              for (int a = 0; a < n; a++) act[idx[a]].d.lod = a < LOD_FULL ? 0 : a < LOD_FULL + 2 ? 1 : 2; }
#endif
            sc_step_dolls();
        }
        u32 sol_lines = (sol_ticks_frame * 8) / 2146;           /* emulated cycles -> hblank lines */
        u32 nact = 0; for (int i = 0; i < NACT; i++) nact += act[i].active;
        if (nact > peak_act) peak_act = nact;
        u32 r0 = TICKS8(), rh0 = HLINES();
        list_begin(cl);
        cam_setup();
        FILL(OTN2 - 1, cl ? 240 : 0, 0x5C6A60);
        { int hy = horizon_y; if (hy < 2) hy = 2; if (hy > 238) hy = 238;
          G4(OTN2 - 2, XY(0, 0), 0x6C4A20, XY(320, 0), 0x6C4A20, XY(0, hy), 0xE0C890, XY(320, hy), 0xE0C890); }
        draw_ground();
        draw_static_box(&sc_box[0], 0xB4A488); draw_static_box(&sc_box[1], 0x8A6A4A);
        draw_car();
        for (int i = 0; i < NACT; i++) draw_doll(&act[i].d, i);
        draw_bars(last_sol, last_ren);
        u32 ren_ticks = elapsed8(r0, rh0); u32 ren_lines = (ren_ticks * 8) / 2146;
        u32 t1 = HLINES(); u32 frame_lines = (t1 - t0) & 0xffff;
        if (prev_oy >= 0) { gpu_idle(); frame_flip(prev_oy, FIELDS); }
        gpu_idle();
        gpu_setup_draw(cl ? 240 : 0);
        list_send();
        prev_oy = cl ? 240 : 0; cl ^= 1; frame++;
        last_sol = sol_lines; last_ren = ren_lines;
        if (!hold) {
            tot_sol += sol_lines; if (sol_lines > max_sol) max_sol = sol_lines; tot_ren += ren_lines; if (ren_lines > max_ren) max_ren = ren_lines;
            u32 fl = sol_lines + ren_lines; tot_fr += fl; if (fl > max_fr) max_fr = fl; if (fl > 263 - 20) nover++; nfr++;
        }
#ifdef LOGALL
        if (!hold && sc_frame_no >= LOGFROM && sc_frame_no < LOGFROM + 30) { dbg("L "); ddec(sc_frame_no); ddec(sol_lines); ddec(ren_lines); ddec(nact); dbg("\n"); }
#endif
        if ((frame % 30) == 0 && !hold) { dbg("F "); ddec(sc_frame_no); dbg("act "); ddec(nact); dbg("sol_lines "); ddec(sol_lines); dbg("ren_lines "); ddec(ren_lines); dbg("prims "); ddec(nprim); dbg("ovf "); ddec(ovf); dbg("\n"); }
        if (!hold && sc_frame_no >= SC_FRAMES) {
            dbg("SUMMARY frames "); ddec(nfr);
            dbg("solver_lines_avg_x10 "); ddec(tot_sol * 10 / nfr); dbg("max "); ddec(max_sol);
            dbg("render_lines_avg_x10 "); ddec(tot_ren * 10 / nfr); dbg("max "); ddec(max_ren);
            dbg("total_avg_x10 "); ddec(tot_fr * 10 / nfr); dbg("max "); ddec(max_fr); dbg("over_budget "); ddec(nover);
            dbg("steps "); ddec(step_count); dbg("avg_kcycles_per_step "); ddec(step_count ? tot_sol_ticks * 8 / step_count / 1000 : 0);
            dbg("sub_avg_x10 "); ddec(step_count ? sub_sum * 10 / step_count : 0); dbg("worst_step_ticks8 "); ddec(sol_worst); dbg("peak_active "); ddec(peak_act);
            dbg("hash "); { u32 h = 0; for (int i = 0; i < NACT; i++) h = h * 31 + rp_hash(&act[i].d); dhex(h); } dbg("\n");
            tot_sol = max_sol = tot_ren = max_ren = tot_fr = max_fr = nover = nfr = 0; step_count = sub_sum = sol_worst = tot_sol_ticks = 0; peak_act = 0;
            sc_reset(); tgt = V(0, MM(1500), MM(8000));
        }
        ovf = 0; (void)pbits; (void)flip_t;
    }
}
