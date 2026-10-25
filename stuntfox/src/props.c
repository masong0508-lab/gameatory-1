/* Payback's street objects as they are now (MERGE build): phones, crates, rocks, crossing
   beacons, chimneys, traffic lights, the radar, alarms and pickups, read every frame from the
   column records of Payback's live map (byte 1 of a record is the object, byte 0 turns it), near
   the camera. So the crate a mission puts down shows where Payback put it (a copy of that column
   in RAM) and goes when it is opened, and a phone is a phone. Trees, lamps and benches are in
   the world data (tools/mkworld.py, citydraw.c). On every map: Payback's live map is the one it
   has loaded, at that map's street level (world.yoff), and each object stands where Payback has
   it, at the circle it pushes people and cars out of (as tools/mkworld.py puts it for our car,
   car_posts, which asks prop_live whether it is still there).

   The models are boxes that share one face list and one set of normals (any box has the same
   ones), all in ROM: no RAM. Payback's "flashing" frames (a ringing phone's object byte flips
   every tick, so do crossing beacons and alarms) are drawn as their steady selves. */
#include "gba.h"
#include "fx.h"
#include "render.h"
#include "model.h"
#include "palette.h"
#include "world.h"
#include "stage2.h"

#define PB_OBJ ((const u8 *)0x08353f00)                     /* object descriptors, 0x3c a type */
#define PB_SIN ((const s16 *)0x08666daa)                    /* Payback's sine and cosine: 5760 a turn, x 256 */
#define PB_COS ((const s16 *)0x08669aaa)

#define F4(m, fl, a, b, c, d) {4, m, fl, {a, b, c, d}}
#define BOX(x0, x1, y0, y1, z0, z1) \
    {x0, y0, z0}, {x1, y0, z0}, {x1, y0, z1}, {x0, y0, z1}, {x0, y1, z0}, {x1, y1, z0}, {x1, y1, z1}, {x0, y1, z1}
/* sides in model_body's paint, the top in model_hull's; front (+z) is the way Payback turns it */
static const MFace box_f[] = {
    F4(M_CAR, 0, 0, 1, 5, 4), F4(M_CAR, 0, 1, 2, 6, 5), F4(M_CAR, 0, 2, 3, 7, 6), F4(M_CAR, 0, 3, 0, 4, 7),
    F4(M_SHIP, 0, 4, 5, 6, 7),
};
static const N3 box_n[] = {{0, 0, -16384}, {16384, 0, 0}, {0, 0, 16384}, {-16384, 0, 0}, {0, 16384, 0}};
#define PART(name, r, ...) \
    static const MVert name##_v[] = {BOX(__VA_ARGS__)}; \
    static const Model name = {name##_v, box_f, 8, 5, r, (N3 *)box_n}

PART(pole, 520, -9, 9, 0, 520, -9, 9);                  /* a traffic light's */
PART(lights, 600, -32, 32, 420, 600, -26, 26);
PART(stand, 210, -14, 14, 0, 190, -40, -12);           /* a payphone: post, box and hood, in */
PART(phone, 320, -70, 70, 160, 300, -60, 16);           /* Payback's blue and red, behind the caller */
PART(hood, 340, -96, 96, 300, 330, -84, 60);
PART(crate, 170, -100, 100, 0, 130, -100, 100);           /* Payback's size: people stop at its face */
PART(post, 520, -14, 14, 0, 420, -14, 14);              /* a crossing beacon's */
PART(globe, 540, -50, 50, 420, 520, -50, 50);
PART(chimney, 330, -90, 90, 0, 320, -90, 90);
PART(mast, 200, -24, 24, 0, 180, -24, 24);             /* the radar's */
PART(alarm, 140, -50, 50, 0, 90, -40, 40);
PART(pickup, 120, -70, 70, 40, 90, -35, 35);
PART(case_, 110, -60, 60, 0, 90, -18, 18);
PART(sign, 340, -80, 80, 200, 330, -10, 10);
PART(column, 1500, -140, 140, 0, 1400, -140, 140);      /* a monument */
PART(bollard, 420, -40, 40, 0, 400, -40, 40);
PART(barrier, 340, -140, 140, 0, 170, -260, 260);       /* (red, white on top) */
PART(block, 380, -170, 170, 0, 330, -110, 110);
PART(box_, 200, -84, 84, 0, 170, -84, 84);
PART(plank, 60, -40, 40, -6, 6, -14, 14);              /* a crate's, flying (puff_draw) */
PART(dust, 200, -80, 80, 0, 160, -80, 80);

#define FAR 4600                   /* objects nearer than this (units), ... */
#define SMALL_FAR 3000             /* ... small ones than this */

static void lamp(const Place *pl, s32 x0, s32 x1, s32 y0, s32 y1, s32 z, int color)
{
    MVert q[4] = {{x0, y0, z}, {x1, y0, z}, {x1, y1, z}, {x0, y1, z}};
    model_poly(pl, q, 4, color);
}

static void prop(int type, s32 x, s32 y, s32 z, int turn)
{
    M3 m;
    Place pl;
    s32 ex = x - cam.pos.x, ez = z - cam.pos.z;
    if (ex < 300 && ex > -300 && ez < 300 && ez > -300 && cam.pos.y < y + 600)
        return;                                       /* (the camera in it) */
    int spin = type == 20 || (type >= 9 && type <= 13) || type == 27 || type == 28 || type == 34;
    myaw(&m, spin ? (s32)frame_count * (type == 20 ? 150 : 250) : turn << 8);   /* (slow and smooth) */
    if (!model_place(&pl, v3(x, y, z), &m, 256, 0, type == 4 ? 1500 : 600) || pl.t.z < 200)
        return;                                       /* (or right at the lens) */
    int f = pl.fog, near = pl.t.z < 1600;             /* (the small parts only near) */
    switch (type) {
    case 1:                                           /* traffic light: red, steady */
        model_body = model_hull = M_STEEL;
        model_draw(&pole, &pl);
        model_body = model_hull = M_ROAD;
        model_draw(&lights, &pl);
        lamp(&pl, -18, 18, 552, 586, 27, COLOR(M_STUNT, 3, 0));
        if (near) {
            lamp(&pl, -18, 18, 512, 546, 27, COLOR(M_ACCENT, 1, f));
            lamp(&pl, -18, 18, 472, 506, 27, COLOR(M_GRASS, 1, f));
        }
        break;
    case 3:                                           /* rock, half sunk */
        if (model_place(&pl, v3(x, y + 60, z), &m, 110, 0, 130))
            model_draw(&mdl_rock, &pl);
        break;
    case 4:
        model_body = M_CONCRETE, model_hull = M_PLAZA;
        model_draw(&column, &pl);
        break;
    case 6:                                           /* crate: planks, two braces */
        model_body = model_hull = M_PLAZA;
        model_draw(&crate, &pl);
        if (near) {
            lamp(&pl, -100, 100, 56, 74, 104, COLOR(M_BRICK, 0, f));
            lamp(&pl, -100, 100, 56, 74, -104, COLOR(M_BRICK, 0, f));
        }
        break;
    case 14: case 19:                                 /* phone (ringing or not: the same) */
        model_body = model_hull = M_STEEL;
        model_draw(&stand, &pl);
        model_body = M_CAR, model_hull = M_STUNT;
        model_draw(&phone, &pl);
        model_body = model_hull = M_STUNT;
        model_draw(&hood, &pl);
        if (near) {
            lamp(&pl, -44, 44, 190, 280, 26, COLOR(M_ROAD, 1, f));         /* the handset's panel */
            lamp(&pl, -30, 30, 252, 270, 30, COLOR(M_SHIP, 3, 0));
        }
        break;
    case 15: case 16:                                 /* crossing beacon: amber, steady */
        model_body = model_hull = M_CREAM;
        model_draw(&post, &pl);
        model_body = model_hull = M_ACCENT;
        model_draw(&globe, &pl);
        break;
    case 17:
        model_body = M_BRICK, model_hull = M_ROAD;
        model_draw(&chimney, &pl);
        break;
    case 20: {                                        /* radar: a dish turning slowly on its mast */
        model_body = model_hull = M_STEEL;
        model_draw(&mast, &pl);
        MVert d0[4] = {{-150, 330, -40}, {0, 180, 20}, {0, 330, 60}, {-150, 420, 0}};
        MVert d1[4] = {{150, 330, -40}, {0, 180, 20}, {0, 330, 60}, {150, 420, 0}};
        model_poly(&pl, d0, 4, COLOR(M_CREAM, 2, f));
        model_poly(&pl, d1, 4, COLOR(M_CREAM, 1, f));
        break;
    }
    case 21: case 22:                                 /* alarm: a box with a red lamp, steady */
        model_body = M_CREAM, model_hull = M_STUNT;
        model_draw(&alarm, &pl);
        break;
    case 23:
        model_body = model_hull = M_ROAD;
        model_draw(&case_, &pl);
        break;
    case 24: case 35:
        model_body = model_hull = M_STEEL;
        model_draw(&post, &pl);
        model_body = model_hull = M_SHIP;
        model_draw(&sign, &pl);
        break;
    case 26:
        model_body = M_CONCRETE, model_hull = M_ROAD;
        model_draw(&block, &pl);
        break;
    case 29:
        model_body = model_hull = M_ROAD;
        model_draw(&bollard, &pl);
        break;
    case 30:
        model_body = M_STUNT, model_hull = M_CREAM;
        model_draw(&barrier, &pl);
        break;
    case 31:
        model_body = model_hull = M_PLAZA;
        model_draw(&box_, &pl);
        break;
    default:                                          /* a weapon or a pickup, turning */
        model_body = M_ROAD, model_hull = M_ACCENT;
        model_draw(&pickup, &pl);
        break;
    }
}

/* which objects are drawn here, a bit each (the rest are in the world data or not drawn; tools/
   mkworld.py OBJ_LIVE) */
#define OURS (1u << 1 | 1u << 3 | 1u << 4 | 1u << 6 | 0x1ffu << 9 | 0x3fu << 19 | 0x3fu << 26)
static int ours(u32 t) { return (t < 32 && OURS >> t & 1) || t == 34 || t == 35; }

/* where Payback has the object of type t turned turn in the cell whose middle is (x, z): its
   descriptor's offset, turned as Payback turns it (0x08000e10; tools/mkworld.py the same) */
static void place_of(u32 t, int turn, s32 *x, s32 *z)
{
    const s16 *o = (const s16 *)(PB_OBJ + t * 0x3c - 0x14);
    int a = turn * 45 >> 1;
    s32 c = PB_COS[a], s = PB_SIN[a];
    *x += (c * o[0] + s * o[1]) >> 9;
    *z += (c * o[1] - s * o[0]) >> 9;
}

/* is a street object of ours still in the cell under (x, z) (units) on Payback's live map:
   car.c stops our car at one only while it is */
int prop_live(s32 x, s32 z)
{
    const u32 *g = PB_GRID;
    int cx = x >> 10, cz = z >> 10;
    if ((u32)g < 0x02000000 || (u32)g >= 0x0203c000 || cx < 0 || cz < 0 || cx >= CITY || cz >= CITY)
        return 1;
    const u8 *c = (const u8 *)g[cx * CITY + cz];
    if ((u32)c < 0x02000000)
        return 1;                                     /* (in ROM: as built) */
    for (int k = 0; k < 3; k++, c += 20)
        if (c[1] && c[8] && ours(c[1]))
            return 1;
    return 0;
}

/* ---- what hits them: the Arwing's bolts (spacegame.c shots_tick) ----
   Payback's crate_break (0x08003480) opens the crate in record k of cell (cx, cy) as its own
   fist and guns do (z: the floor's Payback height, 19904 at street level); the burst it spawns
   is a call we take over (build.py redirects the bl at 0x080034f6 to sf_crate_fx), so a crate
   opened by anyone, a traffic car or the man's fist too, bursts in a puff of ours: Payback's own
   effect records are not drawn by our renderer. */
#define PB_CRATE_BREAK ((void (*)(int cx, int cy, int k, int z))0x08003481)
#define PB_BURST ((void (*)(int, int, int, int, int, int, int))0x08075641)

/* each kind of object as drawn (the parts above, citydraw.c draw_prop for the benches and lamps
   in the world data), what a bolt meets of it: boxes in its own frame, turned as it is drawn
   (x across it, half width hx; z0..z1 front to back; y0..y1 up from its foot), or ROUND ones
   (a post, a turning dish: hx its radius). A thin post or board is met at least 24 units out,
   the bolt's own width. Trees (IS_TREE) are a crown and a trunk, as citydraw.c draw_tree. */
typedef struct { s16 hx, z0, z1, y0, y1; u8 round, more; } HitBox;
static const HitBox hitbox[] = {
    {24, 0, 0, 0, 420, 1, 1}, {32, -26, 26, 420, 600, 0, 0},       /* 1 traffic light: pole, lights */
    {90, 0, 0, 0, 170, 1, 0},                                      /* 3 rock */
    {140, -140, 140, 0, 1400, 0, 0},                               /* 4 monument */
    {100, -100, 100, 0, 130, 0, 0},                                /* 6 crate */
    {40, -40, 40, 0, 400, 0, 1}, {96, -84, 60, 160, 330, 0, 0},    /* 14 19 phone: its post, the booth */
    {24, 0, 0, 0, 420, 1, 1}, {50, -50, 50, 420, 520, 0, 0},       /* 15 16 beacon: post, globe */
    {90, -90, 90, 0, 320, 0, 0},                                   /* 17 chimney */
    {24, 0, 0, 0, 180, 1, 1}, {150, 0, 0, 180, 420, 1, 0},         /* 20 radar: mast, the dish turning */
    {50, -40, 40, 0, 90, 0, 0},                                    /* 21 22 alarm */
    {60, -24, 24, 0, 90, 0, 0},                                    /* 23 case */
    {24, 0, 0, 0, 420, 1, 1}, {80, -24, 24, 200, 330, 0, 0},       /* 24 35 sign: post, board */
    {170, -110, 110, 0, 330, 0, 0},                                /* 26 block */
    {40, -40, 40, 0, 400, 0, 0},                                   /* 29 bollard */
    {140, -260, 260, 0, 170, 0, 0},                                /* 30 barrier */
    {84, -84, 84, 0, 170, 0, 0},                                   /* 31 box */
    {24, 0, 0, 0, 780, 1, 1}, {34, -200, 20, 760, 800, 0, 0},      /* 2 33 36 street lamp: post, arm */
    {140, -45, 45, 0, 110, 0, 1}, {140, -46, -26, 110, 240, 0, 0}, /* 18 bench: seat, backrest */
};
/* each type's first box (+ 1; 0: a pickup, never in the way) */
static const u8 hitbox_of[37] = {0, 1, 21, 3, 4, 0, 5, 0, 0, 0, 0, 0, 0, 0, 6, 8, 8, 10, 23, 6,
                                 11, 13, 13, 14, 15, 0, 17, 0, 0, 18, 19, 20, 0, 21, 0, 15, 21};
#define IS_TREE(t) ((t) == 5 || (t) == 7 || (t) == 8 || (t) == 25 || (t) == 32)
/* a tree's height (units), as tools/mkworld.py OBJ_TREES (index t - 5, the trees only) */
static const u16 tree_h[28] = {650, 0, 800, 450, [20] = 800, [27] = 450};

/* the puffs, at most two at once: cell << 2 | record, where it stood (units) and its age in
   frames; PENDING: a bolt hit the crate this frame, and props_send opens it after our frame */
#define NPUFF 2
#define PENDING 0xff
#define PUFF_LIFE 12
static u16 puff_at[NPUFF];
static s16 puff_y[NPUFF];
static u8 puff_t[NPUFF];

/* where record k of column c stands (units): the records stand on each other (mkworld.py stack) */
static s32 column_y(const u8 *c, int k)
{
    s32 base = 0;
    for (int i = 0; i < k; i++, c += 20)
        base += *(const s16 *)(c + 4);
    s32 h0 = *(const s16 *)(c + 4), h1 = *(const s16 *)(c + 6);
    return (base + (h0 > h1 ? h0 : h1) - 0x100) * 8 + world.yoff;
}

static void puff_put(u32 at, s32 y, int t)
{
    int k = 0;
    for (int i = 0; i < NPUFF; i++)
        if (puff_t[i] && puff_at[i] == at) {          /* the same crate: on with it */
            k = i;
            goto put;
        }
    for (int i = 1; i < NPUFF; i++) {                 /* a free slot, else the oldest puff */
        int a = !puff_t[i] ? 256 : puff_t[i] == PENDING ? 0 : puff_t[i];
        int b = !puff_t[k] ? 256 : puff_t[k] == PENDING ? 0 : puff_t[k];
        if (a > b)
            k = i;
    }
put:
    puff_at[k] = at, puff_y[k] = y, puff_t[k] = t;
}

/* The objects near the camera that props_draw draws, found by a sweep over the cells round it
   that looks at one or two columns a frame (a whole frame's look costs more than drawing them;
   there are at most 10 in any 9 x 9 cells of the city, 28 of another map's, where pickups lie in
   heaps). The sweep goes over the map's own columns, one of each nine a frame (two from the air),
   so however fast the camera flies every column round it is looked at again within nine frames
   (five). Each is looked up again in the live map when drawn, so a crate opened goes at once,
   and one put down shows within nine frames. */
#define NSEEN 32
static u16 seen[NSEEN];            /* cell << 2 | record */
static s16 seen_y[NSEEN];          /* where it stands (units) */
static u8 seen_at[2];              /* how many there are, and the column the sweep is at */
#define nseen seen_at[0]           /* (one array, laid out together whichever is used first) */
#define sweep seen_at[1]

/* A bolt's tick against the street objects: from (x, y, z) by (dx, dy, dz), its box, and the
   nearest meeting so far (s: the fraction of the step, 0..256, NONE for none) */
#define NONE 0x1000
typedef struct {
    s32 x, y, z, dx, dy, dz, x0, x1, z0, z1, y0, y1, s;
    u32 crate;                     /* (cell << 2 | record of a crate met, or NONE) */
} Bolt;

/* narrow the step's part [*s0, *s1] (fractions, 0..256) to where p + d s / 256 is in lo..hi */
static int slab(s32 p, s32 d, s32 lo, s32 hi, s32 *s0, s32 *s1)
{
    if (!d)
        return p >= lo && p <= hi;
    s32 a = (lo - p) * 256 / d, b = (hi - p) * 256 / d;
    if (d < 0) {
        s32 t = a;
        a = b, b = t;
    }
    if (a > *s0)
        *s0 = a;
    if (b < *s1)
        *s1 = b;
    return *s0 <= *s1;
}

/* where the step (from p by d, relative to the middle of a round part, or of a ball when y0 > y1)
   comes nearest that middle inside y0..y1: the fraction if that is within r, else NONE */
static s32 round_hit(s32 px, s32 py, s32 pz, s32 dx, s32 dy, s32 dz, s32 r, s32 y0, s32 y1)
{
    s32 s0 = 0, s1 = 256, ball = y0 > y1;
    if (!ball && !slab(py, dy, y0, y1, &s0, &s1))
        return NONE;
    s32 dd = dx * dx + dz * dz + (ball ? dy * dy : 0), t = s0;
    if (dd)
        t = -((px * dx + pz * dz + (ball ? py * dy : 0)) * 256 / dd);
    t = t < s0 ? s0 : t > s1 ? s1 : t;
    s32 qx = px + dx * t / 256, qz = pz + dz * t / 256, qy = ball ? py + dy * t / 256 : 0;
    return qx * qx + qz * qz + qy * qy <= r * r ? t : NONE;
}

/* is that sorted list of cell << 2 | record (tools/mkworld.py: what the world data leaves out)
   holding key */
static int listed(const u16 *l, u32 key)
{
    int lo = 1, hi = l[0];
    while (lo <= hi) {
        int m = (lo + hi) >> 1;
        if (l[m] == key)
            return 1;
        if (l[m] < key)
            lo = m + 1;
        else
            hi = m - 1;
    }
    return 0;
}

/* Is record k of cell (cx, cz), of type t, standing at (ox, y, oz), drawn from where the player
   looks: by props_draw (in its list, then its own tests and prop's), or by citydraw.c (in the
   world data, its sector drawn, near enough and in front: draw_tree's and draw_prop's tests). A
   bolt never stops at what he cannot see. */
static int drawn(u32 t, s32 cx, s32 cz, int k, s32 ox, s32 y, s32 oz)
{
    u32 key = (cx * CITY + cz) << 2 | k;
    V3 d = v3(ox - cam.pos.x, y - cam.pos.y, oz - cam.pos.z);
    s32 pz = vdot(cam.m.f, d), px = vdot(cam.m.r, d);
    if (ours(t)) {
        int i = 0;
        while (i < nseen && seen[i] != key)
            i++;
        s32 ex = cx * CELL + CELL / 2 - cam.pos.x, ez = cz * CELL + CELL / 2 - cam.pos.z;
        s32 far = t <= 6 || (t >= 14 && t <= 19) ? FAR : SMALL_FAR;
        return i < nseen && cam.pos.y <= 9000 && y <= cam.pos.y + 400 &&
               ex * (cam.m.f.x >> 4) + ez * (cam.m.f.z >> 4) > -1100 * 1024 &&
               ex > -far && ex < far && ez > -far && ez < far &&
               !(d.x < 300 && d.x > -300 && d.z < 300 && d.z > -300 && d.y > -600) && pz >= 200;
    }
    if (listed((const u16 *)(world.tree + world.ntree), key))
        return 0;                  /* (not in the world data: on a floor nobody gets to) */
    s32 view = world_view() - 4096;
    s32 sx = (ox >> 13) * 8192 + 4096 - cam.pos.x, sz = (oz >> 13) * 8192 + 4096 - cam.pos.z;
    if (sx > view || sx < -view || sz > view || sz < -view)
        return 0;                  /* (its sector is not drawn) */
    s32 far = IS_TREE(t) ? TREE_FAR : PROP_FAR, halfw = IS_TREE(t) ? 360 : t == 2 || t == 33 || t == 36 ? 140 : 0;
    return d.x >= -far && d.x <= far && d.z >= -far && d.z <= far && (pz <= TREE_FAR || !IS_TREE(t)) &&
           !(pz < 420 || (pz < 760 && px < halfw && px > -halfw));
}

/* The bolt against the street objects of column c, cell (cx, cz): the nearest it meets of what
   is drawn there, if nearer than b->s */
static __attribute__((noinline)) void hit_cell(Bolt *b, s32 cx, s32 cz, const u8 *c)
{
    s32 base = 0;
    for (int k = 0; k < 3; k++, base += *(const s16 *)(c + 4), c += 20) {
        u32 t = c[1];
        if (!t || !c[8] || t > 36 || (!hitbox_of[t] && !IS_TREE(t)))
            continue;
        s32 h0 = *(const s16 *)(c + 4), h1 = *(const s16 *)(c + 6), y;
        if (ours(t)) {             /* (props_draw: on the record's top) */
            y = (base + (h0 > h1 ? h0 : h1) - 0x100) * 8 + world.yoff;
        } else {                   /* (citydraw: at TREE_BASE, mkworld.py's base, the slope's middle in units / 64) */
            s32 t0 = base + h0, t1 = base + h1;
            s32 top = (c[11] & 0x70) == 0x40 ? t1 : c[8] == 1 ? t0 :
                      c[8] == 2 || c[8] == 3 ? t0 + (1024 * (t1 - t0) >> 11) : t1 + (1024 * (t0 - t1) >> 11);
            y = ((top - 0x100) * 8 + world.yoff + 32) >> 6;
            y = (y < -128 ? -128 : y > 127 ? 127 : y) << 6;
        }
        s32 ox = cx * CELL + CELL / 2, oz = cz * CELL + CELL / 2;
        place_of(t, c[0], &ox, &oz);
        s32 bound, top, r = 0, h = 0;
        const HitBox *hb = hitbox;
        if (IS_TREE(t)) {          /* (draw_tree: a crown as wide as Payback's circle, mkworld.py) */
            s32 pr = *(const s16 *)(PB_OBJ + t * 0x3c - 0x10) >> 4;
            pr = pr > 255 ? 255 : pr;
            h = tree_h[t - 5] > 8 * pr ? tree_h[t - 5] : 8 * pr;
            h &= ~7;
            r = h * 3 >> 3 > pr << 2 ? h * 3 >> 3 : pr << 2;
            bound = r, top = h;
        } else {
            bound = 0, top = 0, hb += hitbox_of[t] - 1;
            for (const HitBox *q = hb;; q++) {
                s32 e = q->hx + (q->z0 < -q->z1 ? -q->z0 : q->z1);
                bound = e > bound ? e : bound;
                top = q->y1 > top ? q->y1 : top;
                if (!q->more)
                    break;
            }
        }
        if (b->x1 < ox - bound || b->x0 > ox + bound || b->z1 < oz - bound || b->z0 > oz + bound ||
            b->y1 < y || b->y0 > y + top)
            continue;              /* (the most of them: nowhere near) */
        s32 px = b->x - ox, py = b->y - y, pz = b->z - oz, s = NONE;
        if (IS_TREE(t)) {          /* a crown facing the camera (a ball) on a trunk h / 16 wide */
            s32 tw = h >> 4 < 24 ? 24 : h >> 4;
            s = round_hit(px, py - (h - r), pz, b->dx, b->dy, b->dz, r, 1, 0);
            s32 s2 = round_hit(px, py, pz, b->dx, b->dy, b->dz, tw, 0, h - r);
            s = s2 < s ? s2 : s;
        } else {                   /* (into its own frame: x across, z its front) */
            s32 a = c[0] << 8, co = fcos(a), si = fsin(a);
            s32 lx = (co * px - si * pz) >> 14, lz = (si * px + co * pz) >> 14;
            s32 ldx = (co * b->dx - si * b->dz) >> 14, ldz = (si * b->dx + co * b->dz) >> 14;
            for (const HitBox *q = hb;; q++) {
                s32 s0 = 0, s1 = 256;
                if (q->round)
                    s0 = round_hit(lx, py, lz, ldx, b->dy, ldz, q->hx, q->y0, q->y1);
                else if (!slab(lx, ldx, -q->hx, q->hx, &s0, &s1) || !slab(py, b->dy, q->y0, q->y1, &s0, &s1) ||
                         !slab(lz, ldz, q->z0, q->z1, &s0, &s1))
                    s0 = NONE;
                s = s0 < s ? s0 : s;
                if (!q->more)
                    break;
            }
        }
        if (s >= b->s || !drawn(t, cx, cz, k, ox, y, oz))
            continue;
        b->s = s;
        b->crate = t == 6 ? (u32)(cx * CITY + cz) << 2 | k : NONE;
    }
}

/* the column of cell (cx, cz) if anything stands in it */
static const u8 *column_of(const u32 *g, s32 cx, s32 cz)
{
    if ((u32)cx >= CITY || (u32)cz >= CITY)
        return 0;
    const u8 *c = (const u8 *)g[cx * CITY + cz];
    return (u32)c >= 0x02000000 && (c[1] | c[21] | c[41]) ? c : 0;
}

static __attribute__((noinline)) int prop_hit2(V3 *p, V3 step, const u32 *g)
{
    /* the cell it ends in, the one it starts in, and across a corner both beside (the most
       have nothing on them) */
    s32 cx = p->x >> 10, cz = p->z >> 10, bx = (p->x - step.x) >> 10, bz = (p->z - step.z) >> 10;
    const u8 *c0 = column_of(g, cx, cz), *c1 = 0, *c2 = 0, *c3 = 0;
    if (bx != cx || bz != cz) {
        c1 = column_of(g, bx, bz);
        if (bx != cx && bz != cz)
            c2 = column_of(g, bx, cz), c3 = column_of(g, cx, bz);
    }
    if (!c0 && !c1 && !c2 && !c3)
        return 0;
    Bolt b;
    b.dx = step.x, b.dy = step.y, b.dz = step.z;
    b.x = p->x - step.x, b.y = p->y - step.y, b.z = p->z - step.z;
    b.x0 = b.x < p->x ? b.x : p->x, b.x1 = b.x ^ p->x ^ b.x0;
    b.y0 = b.y < p->y ? b.y : p->y, b.y1 = b.y ^ p->y ^ b.y0;
    b.z0 = b.z < p->z ? b.z : p->z, b.z1 = b.z ^ p->z ^ b.z0;
    b.s = NONE;
    if (c0)
        hit_cell(&b, cx, cz, c0);
    if (c1)
        hit_cell(&b, bx, bz, c1);
    if (c2)
        hit_cell(&b, bx, cz, c2);
    if (c3)
        hit_cell(&b, cx, bz, c3);
    if (b.s == NONE)
        return 0;
    *p = v3(b.x + b.dx * b.s / 256, b.y + b.dy * b.s / 256, b.z + b.dz * b.s / 256);
    if (b.crate != NONE)
        puff_put(b.crate, column_y((const u8 *)g[b.crate >> 2], b.crate & 3), PENDING);
    return 1;
}

/* A bolt's step, from p - step to p, against the street objects drawn in the cells it starts
   and ends in: 1 when it meets one, and p is moved to where it first does. Most cells have
   nothing on them, and a step mostly stays in its cell: one look at a column, about 80 cycles
   (the 2 to 16 bolts alive look 2 to 16 times a tick). */
int prop_hit(V3 *p, V3 step)
{
    u32 g = (u32)PB_GRID, x = p->x, z = p->z, cx = x >> 10, cz = z >> 10;
    if (g - 0x02000000 >= 0x3c000)
        return 0;
    if (!(((x ^ (x - step.x)) | (z ^ (z - step.z))) >> 10)) {
        if ((cx | cz) >= CITY)
            return 0;
        const u8 *c = ((const u8 *const *)g)[cx * CITY + cz];
        if ((u32)c < 0x02000000 || !(c[1] | c[21] | c[41]))
            return 0;                      /* (the most of them: nothing there) */
    }
    return prop_hit2(p, step, (const u32 *)g);
}

/* Payback's burst for a crate opened (its arguments: the effect descriptor, record + 1, the
   cell middle's Payback x and y, its z, the turn and 5), from crate_break for whoever opened
   it. A puff of ours where the crate stood, then Payback's effect as before. The section puts
   it among the hooks merge.ld keeps. */
__attribute__((section(".text.sf_hook_crate_fx")))
void sf_crate_fx(int desc, int k1, int px, int py, int z, int ang, int n)
{
    const u32 *g = PB_GRID;
    int cx = px >> 11, cz = py >> 11, k = k1 - 1;
    if ((u32)g >= 0x02000000 && (u32)g < 0x0203c000 && (u32)cx < CITY && (u32)cz < CITY && (u32)k < 3) {
        const u8 *c = (const u8 *)g[cx * CITY + cz];
        if ((u32)c >= 0x02000000) {
            puff_put((cx * CITY + cz) << 2 | k, column_y(c, k), 1);
            s2_ev(EV_KILL, cx << 7 | cz, EVK_BOX);
        }
    }
    PB_BURST(desc, k1, px, py, z, ang, n);
}

/* after our frame (merge.c, with Payback's code back in IWRAM): open the crates bolts hit */
void props_send(void)
{
    for (int i = 0; i < NPUFF; i++)
        if (puff_t[i] == PENDING) {
            int cell = puff_at[i] >> 2;
            PB_CRATE_BREAK(cell >> 7, cell & 127, puff_at[i] & 3, 19904 - 2 * (puff_y[i] - world.yoff));
            if (puff_t[i] == PENDING)                 /* (sf_crate_fx has started it; if not, now) */
                puff_t[i] = 1;
        }
}

/* a crate bursting: four planks flung up and out, and a low cloud of dust no bigger than the
   crate that billows out and settles, in the crate's own steady colours (not with the camera
   near: the man who opened it is beside it, and it would hide him) */
static void puff_draw(V3 at, int t)
{
    M3 m;
    Place pl;
    s32 ex = at.x - cam.pos.x, ez = at.z - cam.pos.z;
    myaw(&m, 0);                                     /* (still: a turning cloud flickers at its edges) */
    if ((ex > 400 || ex < -400 || ez > 400 || ez < -400) &&
        model_place(&pl, at, &m, t < 4 ? 128 + t * 32 : 256 - (t - 4) * 20, 0, 300)) {
        model_body = model_hull = M_CREAM;
        model_draw(&dust, &pl);
    }
    s32 d = 28 + t * 14, h = 90 + t * 32 - t * t * 3;
    for (int i = 0; i < 4; i++) {
        myaw(&m, t * 1500 + i * 16384);
        V3 q = v3(at.x + (i & 1 ? d : -d), at.y + h, at.z + (i & 2 ? d : -d));
        if (model_place(&pl, q, &m, 256, 0, 60)) {
            model_body = model_hull = M_PLAZA;
            model_draw(&plank, &pl);
        }
    }
}

void props_draw(void)
{
    const u32 *g = PB_GRID;
    for (int i = 0; i < NPUFF; i++)
        if (puff_t[i] && puff_t[i] != PENDING && ++puff_t[i] > PUFF_LIFE)
            puff_t[i] = 0;
    if ((u32)g < 0x02000000 || (u32)g >= 0x0203c000 || cam.pos.y > 9000)
        return;
    int cx = cam.pos.x >> 10, cz = cam.pos.z >> 10, r = FAR >> 10, xs[2];
    int n = cam.pos.y - world.yoff > 700 ? 2 : 1;      /* (two columns a frame from the air, where it flies fast) */
    for (int j = 0; j < 2; j++) {                     /* (the map's every ninth, in turn) */
        if (j < n && ++sweep > 2 * r)
            sweep = 0;
        xs[j] = cx - r + ((u32)(sweep - (cx - r) + 2 * (2 * r + 1) * CITY) % (2 * r + 1));
    }
    for (int i = 0; i < nseen;) {                     /* (forget what is out of reach, and what it finds again) */
        int sx = seen[i] >> 9, dx = sx - cx, dz = (seen[i] >> 2 & 127) - cz;
        if (sx == xs[0] || sx == xs[1] || dx < -r || dx > r || dz < -r || dz > r)
            --nseen, seen[i] = seen[nseen], seen_y[i] = seen_y[nseen];
        else
            i++;
    }
    for (int j = 0; j < n; j++) {
        int x = xs[j];
        if (x < 0 || x >= CITY)
            continue;
        const u32 *gx = g + x * CITY;
        for (int z = cz - r < 0 ? 0 : cz - r, z1 = cz + r < CITY ? cz + r : CITY - 1; z <= z1; z++) {
            const u8 *c = (const u8 *)gx[z];
            if ((u32)c < 0x02000000 || !(c[1] | c[21] | c[41]))
                continue;                             /* (most cells have nothing on them) */
            for (int k = 0, base = 0; k < 3 && nseen < NSEEN; base += *(const s16 *)(c + 4), k++, c += 20)
                if (c[1] && c[8] && ours(c[1])) {     /* (records stand on each other, see mkworld.py stack) */
                    s32 h0 = *(const s16 *)(c + 4), h1 = *(const s16 *)(c + 6);
                    seen_y[nseen] = (base + (h0 > h1 ? h0 : h1) - 0x100) * 8 + world.yoff;
                    seen[nseen++] = (x * CITY + z) << 2 | k;
                }
        }
    }
    s32 fx = cam.m.f.x >> 4, fz = cam.m.f.z >> 4;     /* (1.10) */
    for (int i = 0; i < nseen; i++) {
        int cell = seen[i] >> 2;
        s32 y = seen_y[i], wx = (cell >> 7) * CELL + CELL / 2, wz = (cell & 127) * CELL + CELL / 2;
        s32 dx = wx - cam.pos.x, dz = wz - cam.pos.z;
        if (y > cam.pos.y + 400 || dx * fx + dz * fz <= -1100 * 1024)
            continue;                                 /* (behind, or on a roof above the camera: its edge hides it) */
        const u8 *c = (const u8 *)g[cell];
        if ((u32)c < 0x02000000)
            continue;
        c += 20 * (seen[i] & 3);
        u32 t = c[1];
        if (!t || !c[8] || !ours(t))
            continue;                                 /* (gone since: opened, or flipped) */
        s32 far = t <= 6 || (t >= 14 && t <= 19) ? FAR : SMALL_FAR;
        if (dx > -far && dx < far && dz > -far && dz < far) {
            place_of(t, c[0], &wx, &wz);
            prop(t, wx, y, wz, c[0]);
        }
    }
    for (int i = 0; i < NPUFF; i++)
        if (puff_t[i] && puff_t[i] != PENDING) {
            int cell = puff_at[i] >> 2;
            puff_draw(v3((cell >> 7) * CELL + CELL / 2, puff_y[i], (cell & 127) * CELL + CELL / 2), puff_t[i]);
        }
    model_body = M_CAR;
    model_hull = M_SHIP;
}
