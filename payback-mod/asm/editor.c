/* In-game build mode: hold SELECT and press A (kicker ramp), B (platform), R (raise), L (clear),
   UP (loop plate) or DOWN (dash plate).
   Edits the decoded level grid in RAM, so changes show at once and last until the level reloads. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef short s16;
typedef unsigned int u32;

#define KEYS (*(volatile u16 *)0x04000130)
#define PREV (*(volatile u16 *)0x0203fff8)      /* cleared by the game at level load */
#define GRID (*(u32 **)0x03000d60)              /* 128*128 column pointers, index x*128+y */
#define ENTS ((u8 **)0x03000c60)
#define CONTROLLED (*(s16 *)0x02001db8)          /* entity the player controls: 0 on foot, else the vehicle */

/* Filled in by build.py: flat columns for heights 0x100 + 0x20*i (i < 17), then ramps
   rising toward +y, +x, -y, -x from 0x100 + 0x20*k (k < 16). */
extern const u32 cols[17 + 4 * 16 + 2];       /* + loop pad, boost pad */
#define LOOP_PAD cols[81]
#define BOOST_PAD cols[82]
/* Also filled in by build.py: full column-pointer grids for space, Mute City (level 0) as the
   story uses it, and Neo Mute City, the free-roam city built on the same streets. */
extern const u32 *const maps[3];
#define SPACE_MAP maps[0]
#define CITY_MAP maps[1]
#define NEO_MAP maps[2]
#define IN_SPACE (*(volatile u8 *)0x0203fffa)   /* these two are cleared by the game at level load */
#define IN_NEO (*(volatile u8 *)0x0203fffb)
#define FREE_ROAM (*(u8 *)0x02001d39)           /* 1 in Rampage (free roam), 0 in the story */
#define ARWING_DESC 0x08354ef0                   /* the helicopter, renamed Arwing */
#define CAR_DESC_FIRST 0x08354af4                /* road vehicles run from here to the Arwing */

static void load_map(const u32 *src)
{
    u32 *g = GRID;
    for (int i = 0; i < 128 * 128; i++)
        if ((g[i] >> 24) != 0x02)             /* keep the few columns the game builds in RAM */
            g[i] = src[i];
}

static int is_city(void)
{
    u32 *g = GRID;
    for (int i = 300; i < 128 * 128; i += 997)
        if ((g[i] >> 24) != 0x02 && g[i] != CITY_MAP[i])
            return 0;
    return 1;
}

/* Free roam in Mute City loads Neo Mute City. Getting into the Arwing swaps the map for space;
   getting out swaps back to whichever city you came from. */
static void maps_update(void)
{
    if (!IN_SPACE && !IN_NEO && FREE_ROAM == 1 && is_city()) {
        load_map(NEO_MAP);
        IN_NEO = 1;
    }
    u8 *e = ENTS[CONTROLLED];
    int flying = *(u32 *)(e + 0x1c) == ARWING_DESC;
    if (flying && !IN_SPACE && (IN_NEO || is_city())) {
        load_map(SPACE_MAP);
        IN_SPACE = 1;
    } else if (!flying && IN_SPACE) {
        load_map(IN_NEO ? NEO_MAP : CITY_MAP);
        IN_SPACE = 0;
    }
}

enum { KA = 1, KB = 2, KSEL = 4, KUP = 0x40, KDOWN = 0x80, KR = 0x100, KL = 0x200 };

static int top(u32 col)
{
    const u16 *r = (const u16 *)col;
    int h0 = r[2], h1 = r[3];
    return h0 > h1 ? h0 : h1;
}

static void put(int x, int y, u32 col)
{
    if (x >= 1 && x < 127 && y >= 1 && y < 127)
        GRID[x * 128 + y] = col;
}

static int level(int h)
{
    int i = (h - 0x100) >> 5;
    return i < 0 ? 0 : i > 16 ? 16 : i;
}

/* Hard Drivin' loops, run as physics rather than an animation. A loop pad starts a vertical
   circle of radius LOOP_R ahead of the car. While on it the car is a point held to the track by
   the normal force:
     - speed along the track changes with gravity (g * sin of the angle), the throttle and brake,
     - LEFT/RIGHT steer across the track, which is LOOP_W wide,
     - the track can only push, never pull: when v^2/R is less than the part of gravity pulling the
       car off (near the top, when too slow) the car leaves the track,
     - steering past the edge also leaves the track.
   Leaving hands the car back to the game's own physics with its full 3D velocity (forward,
   sideways and vertical), so overshooting or falling off really flies or drops you off the loop.
   The screen rolls with the car's angle on the loop and rights itself afterwards. */
#define LOOP_ON (*(volatile u8 *)0x0203fffc)       /* 0 idle, 1 on the loop, 0xff wait to leave pad */
#define LOOP_D (*(volatile u8 *)0x0203fffd)        /* direction 0 +y, 1 +x, 2 -y, 3 -x */
#define LOOP_X (*(volatile int *)0x0203ffe0)       /* loop entry point */
#define LOOP_Y (*(volatile int *)0x0203ffe4)
#define LOOP_V (*(volatile int *)0x0203ffe8)       /* speed along the track, x16 */
#define LOOP_P (*(volatile int *)0x0203ffec)       /* angle round the loop, 256 per 1/24 turn */
#define LOOP_L (*(volatile int *)0x0203fff0)       /* sideways offset across the track */
#define ROLL (*(volatile int *)0x0203fff4)         /* screen roll, same units as LOOP_P */
#define FULL (24 * 256)
#define LOOP_R 4096                                /* 2 cells */
#define LOOP_W 3072                                /* half the track width */
#define LOOP_G 220                                 /* gravity, speed x16 per tick */
#define GAS 12
#define BRAKE 160
#define REG16(a) (*(volatile u16 *)(a))
#define REG32(a) (*(volatile u32 *)(a))
enum { KRIGHT = 0x10, KLEFT = 0x20 };

static const short sin24[25] = {                   /* 256 * sin(2*pi*i/24) */
    0, 66, 128, 181, 222, 247, 256, 247, 222, 181, 128, 66, 0,
    -66, -128, -181, -222, -247, -256, -247, -222, -181, -128, -66, 0};

static int heading4(u8 *e)
{
    int a = *(s16 *)(e + 0x12) + 720, d = 0;      /* heading: 5760 per turn, 0 = +y */
    while (a >= 1440) a -= 1440, d++;
    return d & 3;
}

static int wrap(int p)
{
    if (p < 0) p += FULL;                           /* callers stay within one turn either side */
    if (p >= FULL) p -= FULL;
    return p;
}

static int sinp(int p)
{
    p = wrap(p);
    int i = p >> 8, f = p & 255;
    return sin24[i] + (((sin24[i + 1] - sin24[i]) * f) >> 8);
}

static int cosp(int p) { return sinp(p + 6 * 256); }

#define CAR_SX 120                                 /* screen centre: the car is drawn into the same */
#define CAR_SY 80                                  /* bitmap, so it rolls with the world */
static void roll_screen(int p)                     /* rotate the 3D view (mode 4, BG2) */
{
    int c = cosp(p), s = sinp(p);
    REG16(0x04000020) = (u16)c;
    REG16(0x04000022) = (u16)-s;
    REG16(0x04000024) = (u16)s;
    REG16(0x04000026) = (u16)c;
    REG32(0x04000028) = (u32)((CAR_SX << 8) - (c * CAR_SX - s * CAR_SY));
    REG32(0x0400002c) = (u32)((CAR_SY << 8) - (s * CAR_SX + c * CAR_SY));
}

/* leave the track: hand the car to the game with its velocity in all three axes */
static void fly_off(u8 *e, int fx, int fy, int sx, int sy)
{
    s16 *v = (s16 *)(e + 0x40);
    int p = LOOP_P, V = LOOP_V >> 4, fwd = (V * cosp(p)) >> 8, up = (V * sinp(p)) >> 8;
    int side = 0;
    if (LOOP_L > LOOP_W) side = 96;
    else if (LOOP_L < -LOOP_W) side = -96;
    v[0] = (s16)(fx * fwd + sx * side);
    v[1] = (s16)(fy * fwd + sy * side);
    v[2] = (s16)-up;                                /* the game's vertical speed is positive down */
    if (fwd < 0)                                    /* thrown backwards off the top: face the way you fly */
        *(s16 *)(e + 0x12) = (s16)(((LOOP_D + 2) & 3) * 1440);
    LOOP_ON = 0xff;
}

static void stunts(void)
{
    if (ROLL) {                                     /* right the view after a loop */
        if (LOOP_ON != 1) {
            int r = ROLL;
            r = r < FULL / 2 ? r - 224 : r + 224;
            ROLL = r <= 0 || r >= FULL ? 0 : r;
        }
        roll_screen(ROLL);
    }
    if (CONTROLLED < 0)
        return;
    u8 *e = ENTS[CONTROLLED];
    u32 desc = *(u32 *)(e + 0x1c);
    if (desc < CAR_DESC_FIRST || desc >= ARWING_DESC)  /* cars only (index 0 can be a car too) */
        return;
    s16 *v = (s16 *)(e + 0x40);
    int *x = (int *)(e + 4), *y = (int *)(e + 8), *z = (int *)(e + 0xc);
    u32 col = GRID[(*x >> 11) * 128 + (*y >> 11)];
    int speed = (v[0] < 0 ? -v[0] : v[0]) + (v[1] < 0 ? -v[1] : v[1]);
    if (LOOP_ON == 0xff && col != LOOP_PAD)
        LOOP_ON = 0;
    if (LOOP_ON == 0 && col == BOOST_PAD) {        /* F-Zero dash plate: a kick along your heading */
        int d = heading4(e), s = speed < 340 ? 520 : speed + (speed >> 1);
        if (s > 700) s = 700;
        v[0] = d == 1 ? s : d == 3 ? -s : 0;
        v[1] = d == 0 ? s : d == 2 ? -s : 0;
    }
    if (LOOP_ON == 0 && col == LOOP_PAD && speed >= 60 && *z >= 19904 - 64) {   /* wheels on the plate */
        int d = heading4(e);
        LOOP_D = d;
        LOOP_X = *x;
        LOOP_Y = *y;
        LOOP_L = (d == 1 || d == 3) ? (*y & 2047) - 1024 : (*x & 2047) - 1024;
        if (d == 1 || d == 2) LOOP_L = -LOOP_L;     /* positive is to the driver's right */
        LOOP_V = speed << 4;
        LOOP_P = 0;
        LOOP_ON = 1;
    }
    if (LOOP_ON != 1)
        return;

    int d = LOOP_D;
    int fx = d == 1 ? 1 : d == 3 ? -1 : 0, fy = d == 0 ? 1 : d == 2 ? -1 : 0;
    int sx = fy, sy = -fx;                          /* driver's right */
    u16 keys = ~KEYS & 0x3ff;
    int p = LOOP_P, Vs = LOOP_V;
    Vs -= (LOOP_G * sinp(p)) >> 8;                  /* gravity along the track */
    if (keys & KA) Vs += GAS;
    if (keys & KB) Vs -= BRAKE;
    Vs -= Vs >> 9;                                  /* rolling drag */
    LOOP_V = Vs;
    int V = Vs >> 4;
    if (keys & KRIGHT) LOOP_L += 120 + (V >> 2);
    if (keys & KLEFT) LOOP_L -= 120 + (V >> 2);
    p += (V * 98) >> 8;                             /* distance travelled per tick (about 1.6 V) -> angle */
    LOOP_P = p;
    ROLL = wrap(p);

    /* off the track: past either edge, or not enough speed to stay pressed on (v^2/R < g inward) */
    int c = cosp(p);
    if (LOOP_L > LOOP_W || LOOP_L < -LOOP_W || (c < 0 && V * V < -137 * c)) {
        fly_off(e, fx, fy, sx, sy);
        return;
    }
    if (p >= FULL || p < 0) {                       /* round and out (or rolled back down the way in) */
        int fwd = p < 0 ? 0 : 2 * LOOP_R;
        *x = LOOP_X + fx * fwd + sx * LOOP_L;
        *y = LOOP_Y + fy * fwd + sy * LOOP_L;
        *z = 19904;
        v[0] = (s16)(fx * V);
        v[1] = (s16)(fy * V);
        v[2] = 0;
        LOOP_ON = 0xff;
        ROLL = p < 0 ? 0 : ROLL;
        return;
    }
    int fwd = ((LOOP_R * sinp(p)) >> 8) + ((p * 21) >> 4);   /* the loop drifts 2R forward so it exits ahead */
    *x = LOOP_X + fx * fwd + sx * LOOP_L;
    *y = LOOP_Y + fy * fwd + sy * LOOP_L;
    *z = 19904 - 16 * ((LOOP_R - ((LOOP_R * c) >> 8)) >> 4);
    *(s16 *)(e + 0x12) = (s16)(d * 1440);
    v[0] = v[1] = 0;
    v[2] = 0;
}

void editor(u8 *buttons)
{
    u16 keys = ~KEYS & 0x3ff, hit = keys & ~PREV;
    PREV = keys;
    maps_update();
    stunts();
    if (!(keys & KSEL))
        return;
    for (int i = 0; i < 8; i++)      /* the game sees no buttons while SELECT is held */
        buttons[i] = 0;
    if (!(hit & (KA | KB | KR | KL | KUP | KDOWN)))
        return;

    u8 *e = ENTS[CONTROLLED];
    int x = *(int *)(e + 4) >> 11, y = *(int *)(e + 8) >> 11;
    int d = heading4(e);
    int dx = d == 1 ? 1 : d == 3 ? -1 : 0, dy = d == 0 ? 1 : d == 2 ? -1 : 0;
    int tx = x + 2 * dx, ty = y + 2 * dy;
    int h = top(GRID[tx * 128 + ty]);

    if (hit & (KUP | KDOWN)) {        /* three-wide plate across your path: UP loop, DOWN dash */
        for (int w = -1; w <= 1; w++)
            put(tx + w * dy, ty + w * dx, hit & KUP ? LOOP_PAD : BOOST_PAD);
        return;
    }
    if (hit & KA)                     /* four-cell kicker ahead, rising away from you */
        for (int k = 0; k < 4; k++)
            put(tx + k * dx, ty + k * dy, cols[17 + d * 16 + k]);
    else if (hit & KB)
        put(tx, ty, cols[level(h + 0x40)]);
    else if (hit & KR)
        put(tx, ty, cols[level(h + 0x20)]);
    else
        put(tx, ty, cols[0]);
}
