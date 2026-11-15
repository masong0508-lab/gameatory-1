/* ------------------------------------------------------------------------------------------- vram upload (streamed from SF3A.BIN) */
extern void sf3_cd_read(u32 lba, u32 nsec, u8 *dst);
extern const u32 CD_SF3W_LBA, CD_SF3W_SECS, CD_SF3A_LBA;
static u8 *const sf_tmp = (u8 *)SF_TMP;      /* the primitive buffer doubles as the upload buffer at start */
static void upload_all(void) {
  u32 lba = CD_SF3A_LBA;
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
typedef struct { s32 x, y, z; u16 yaw; u8 kind, spare; } SfEnt;     /* units (1024 a cell); kind 0 car, 1 person */
s32 sf3_score, sf3_hp, sf3_clock; u32 sf3_stat_eng, sf3_stat_prim, sf3_stat_ovf, sf3_stat_lod, sf3_frames, sf3_stat_gpu;
static int sf3_have;
int sf3_init(void) {
  dbg("sf3_init a\n"); timers_init(); GP1 = 0x04000002; DPCR |= 0x08000800;
  sf3_cd_read(CD_SF3W_LBA, CD_SF3W_SECS, (u8 *)SF_WORLD);
  if (*(const u32 *)SF_WORLD != 0x57334653) { dbg("SF3W bad magic\n"); return -1; }
  dbg("sf3_init b\n"); world_init(); dbg("sf3_init c\n"); upload_all(); dbg("sf3_init d\n");
  for (u32 i = 0; i < 3072 + 1024 + 2304; i++) ((volatile u16 *)SF_ST)[i] = 0;
  dbg("sf3 init ok\n"); sf3_have = 1; return 0;
}
/* one frame of the city from the guest's player: position in units, heading in 65536 a turn (our convention), pkind 0 on foot 1 in a vehicle */
int sf3_frame(int oy, s32 px, s32 py, s32 pz, int heading, int pkind, const SfEnt *ents, int nents, int hud) {
  if (!sf3_have) return -1;
  u32 t0 = HLINES();
  car_x = px << 8; car_y = py << 8; car_z = pz << 8; car_h = heading & 0xffff;
  static int first = 1;
  s32 s = fsin(car_h), c = fcos(car_h); int back = pkind ? 820 : 520, up = pkind ? 300 : 260;
  if (first || iabs_(car_x - cpx) > (6000 << 8) || iabs_(car_z - cpz) > (6000 << 8)) {
    cpx = car_x - (s * back >> 14 << 8); cpz = car_z - (c * back >> 14 << 8); cpy = car_y + (up << 8); yaw = car_h; first = 0; }
  { s32 tx = car_x - (s * back >> 14 << 8), tz = car_z - (c * back >> 14 << 8), ty = car_y + (up << 8);
    cpx += (tx - cpx) >> 1; cpz += (tz - cpz) >> 1; cpy += (ty - cpy) >> 1;
    for (int k = 0; k < 6; k++) {
      int gh = ground_at(cpx >> 8, cpz >> 8, cpy >> 8);
      if (gh < (cpy >> 8) - 60) break;
      cpx = car_x + ((cpx - car_x) >> 1); cpz = car_z + ((cpz - car_z) >> 1);
    }
    int dy = (short)(car_h - yaw); yaw = (yaw + (dy >> 1)) & 0xffff; pitch = -2300; }
  { static const s16 reachs[4] = { REACH, 11264, 10240, 8192 }; static const u8 errs[4] = { ERRPX, 3, 4, 6 }; reach = reachs[lod]; errpx = errs[lod]; }
  cam_from_angles(); cam_commit();
  list_begin(0);
  sky_draw();
  island_draw(flat_col(1, 2, 0));
  city_draw(); ground_draw();
  if (pkind) car_draw(px, py, pz, car_h);
  else billboard(px, py, pz, 45, 0, 150, flat_col(7, 2, 0), zdepth(px, py, pz));
  for (int i = 0; i < nents; i++) {
    const SfEnt *e = &ents[i]; if (e->kind == 0) car_draw(e->x, e->y, e->z, e->yaw);
    else { CV cc; cpu_cam(e->x, e->y, e->z, 0, &cc); if (cc.z > 60 && cc.z < 5000) billboard(e->x, e->y, e->z, 40, 0, 140, flat_col(10, 1, 0), cc.z); }
  }
  if (hud) {
    char b[80], *e;
    e = fmt_s(b, "ENG "); e = fmt_int(e, sf3_stat_eng, 0); e = fmt_s(e, " Q "); e = fmt_int(e, nprim, 0); e = fmt_s(e, " OVF "); e = fmt_int(e, sf3_stat_ovf, 0); e = fmt_s(e, " LOD "); e = fmt_int(e, lod, 0);
    hud_box(4, 4, 232, 11); hud_str(6, 6, b, 0xC0FFC0);
    e = fmt_s(b, "SCORE "); e = fmt_int(e, sf3_score, 0); e = fmt_s(e, " HP "); e = fmt_int(e, sf3_hp, 0); e = fmt_s(e, " CLK "); e = fmt_int(e, sf3_clock, 0);
    hud_box(4, 16, 232, 11); hud_str(6, 18, b, 0xFFE080);
  }
  gpu_idle();
  gp0(0xE1000400 | TPAGE(320, 0, 1, 0)); gp0(0xE3000000 | (oy << 10)); gp0(0xE4000000 | 319 | ((oy + 239) << 10)); gp0(0xE5000000 | (oy << 11));
  list_send();
  u32 t1 = HLINES(); u32 eng = (t1 - t0) & 0xffff;
  sf3_stat_eng = eng; sf3_stat_prim = nprim; sf3_stat_ovf = ovf; sf3_stat_lod = lod; sf3_frames++; ovf = 0;
  { int budget = 3 * 263 - 70; static int calm;
    if ((int)eng > budget && lod < 3) { lod++; calm = 0; } else if ((int)eng < budget - 190 && lod > 0) { if (++calm > 45) { lod--; calm = 0; } } else calm = 0; }
  return 0;
}
