/* doll.c: stage 7 glue between the live level and the stage 5 ragdoll solver (ragdoll_ps1.c, RP_FAST).  One translation unit with its own tiny runtime header (rd/ps1.h).
   Units at the interface: renderer units (64 per metre, y up, heading 65536 a turn, 0 = +z).  Inside: Q20 metres.
   Events come from rt.c (bail-out when the driver leaves a moving car, a pedestrian run down by the player's car); the renderer (sf3.c) supplies the world (floor / solid / sweep). */
#define PS1 1
#define RD_NOLIBC 1
#include "ps1.h"
#include "ragdoll_ps1.c"
#include "rt.inc"
#define ND 4
typedef struct { rp_doll d; int active; int id; u32 age; u32 shirt; } Slot;
static Slot D[ND];
static rp_car car; static int car_on;
s32 rd_pos[ND][RP_P][3]; u8 rd_live[ND]; u32 rd_shirt[ND];
u32 rd_spawned, rd_steps, rd_hurt_max, rd_rejected;
static void export_doll(int i){ const rp_doll *d = &D[i].d; for (int j = 0; j < RP_P; j++) { rd_pos[i][j][0] = d->pos[j].x >> 14; rd_pos[i][j][1] = d->pos[j].y >> 14; rd_pos[i][j][2] = d->pos[j].z >> 14; } }
/* the player's car as the solver's oriented box (units -> metres), pos = box centre, vel in m/s Q20 */
void rd_set_car(int on, s32 ux, s32 uy, s32 uz, int h16, s32 vx, s32 vy, s32 vz)
{
    car_on = on; if (!on) return;
    car.pos.x = ux << 14; car.pos.y = (uy + 38) << 14; car.pos.z = uz << 14; car.vel.x = vx; car.vel.y = vy; car.vel.z = vz;
    car.half_x = 943718; car.half_y = 629145; car.half_z = 2306867; car.mass = RP_ONE * 1200;
    fx s = rsin(h16), c = rcos(h16);                     /* Q20 */
    /* local->world rows (right, up, along): along = (sin h, 0, cos h); right = (cos h, 0, -sin h) */
    car.m[0] = c; car.m[1] = 0; car.m[2] = -s;
    car.m[3] = 0; car.m[4] = RP_ONE; car.m[5] = 0;
    car.m[6] = s; car.m[7] = 0; car.m[8] = c;
}
/* a standing doll with its feet at (ux,uy,uz), facing yaw, with velocity (vx,vy,vz) in m/s Q20 plus a spin about its middle; returns the slot or -1 */
int rd_spawn(s32 ux, s32 uy, s32 uz, int yaw, s32 vx, s32 vy, s32 vz, int id, u32 shirt)
{
    int k = -1; u32 oldest = 0;
    for (int i = 0; i < ND; i++) if (!D[i].active) { k = i; break; }
    if (k < 0) { for (int i = 0; i < ND; i++) if (D[i].age >= oldest) { oldest = D[i].age; k = i; } if (oldest < 240) { rd_rejected++; return -1; } }
    rp_v3 feet = { ux << 14, uy << 14, uz << 14 }, v = { vx, vy, vz }, w = { 0, (int)(2 * RP_ONE), (int)(3 * RP_ONE) / 2 };
    rp_spawn(&D[k].d, feet, yaw, v, w); D[k].d.lod = 0; D[k].d.dtf = 2;
    D[k].active = 1; D[k].id = id; D[k].age = 0; D[k].shirt = shirt; rd_live[k] = 1; rd_shirt[k] = shirt; rd_spawned++; export_doll(k);
    return k;
}
/* rc7: release the dolls of one id (the player's after a few seconds of game time), or all of them and the car (the guest left the level) */
void rd_drop(int id){ for (int i = 0; i < ND; i++) if (D[i].active && D[i].id == id) { D[i].active = 0; rd_live[i] = 0; } }
void rd_clear(void){ for (int i = 0; i < ND; i++) { D[i].active = 0; rd_live[i] = 0; } car_on = 0; }
int rd_id(int i){ return D[i].active ? D[i].id : -1; }
int rd_has(int id){ for (int i = 0; i < ND; i++) if (D[i].active && D[i].id == id) return 1; return 0; }
int rd_active(void){ int n = 0; for (int i = 0; i < ND; i++) n += D[i].active; return n; }
/* one 30 fps frame (two 60 Hz ticks in one step): the nearest two live dolls at full detail, the others lod 1; a doll asleep for 4 s (240 ticks) is released.
   (cx,cz) = the camera target in units, for the ranking. */
void rd_step_all(const rp_world *w, s32 cx, s32 cz)
{
    int rank[ND], n = 0;
    for (int i = 0; i < ND; i++) if (D[i].active) { rank[n++] = i; }
    for (int a = 0; a < n; a++) for (int b = a + 1; b < n; b++) {
        s32 da = iabs((D[rank[a]].d.pos[0].x >> 14) - cx) + iabs((D[rank[a]].d.pos[0].z >> 14) - cz), db = iabs((D[rank[b]].d.pos[0].x >> 14) - cx) + iabs((D[rank[b]].d.pos[0].z >> 14) - cz);
        if (db < da) { int t = rank[a]; rank[a] = rank[b]; rank[b] = t; } }
    for (int r = 0; r < n; r++) {
        int i = rank[r]; rp_doll *d = &D[i].d;
        d->lod = r < 2 ? 0 : 1; d->dtf = 2;
        rp_step(d, w, car_on ? &car : 0); rd_steps++;
        if (d->hurt > (int32_t)rd_hurt_max) rd_hurt_max = d->hurt;
        D[i].age += 2; export_doll(i);
        if (d->state == RP_ASLEEP && D[i].age > 600) { D[i].active = 0; rd_live[i] = 0; }
        if (D[i].age > 3600) { D[i].active = 0; rd_live[i] = 0; }
    }
}
