/* In-game build mode: hold SELECT and press A (kicker ramp), B (platform), R (raise), L (clear).
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
extern const u32 cols[17 + 4 * 16];
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

enum { KA = 1, KB = 2, KSEL = 4, KR = 0x100, KL = 0x200 };

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

void editor(u8 *buttons)
{
    u16 keys = ~KEYS & 0x3ff, hit = keys & ~PREV;
    PREV = keys;
    maps_update();
    if (!(keys & KSEL))
        return;
    for (int i = 0; i < 8; i++)      /* the game sees no buttons while SELECT is held */
        buttons[i] = 0;
    if (!(hit & (KA | KB | KR | KL)))
        return;

    u8 *e = ENTS[CONTROLLED];
    int x = *(int *)(e + 4) >> 11, y = *(int *)(e + 8) >> 11;
    int a = *(s16 *)(e + 0x12) + 720, d = 0;               /* heading: 5760 per turn, 0 = +y */
    while (a >= 1440) a -= 1440, d++;
    d &= 3;                                                 /* 0 +y, 1 +x, 2 -y, 3 -x */
    int dx = d == 1 ? 1 : d == 3 ? -1 : 0, dy = d == 0 ? 1 : d == 2 ? -1 : 0;
    int tx = x + 2 * dx, ty = y + 2 * dy;
    int h = top(GRID[tx * 128 + ty]);

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
