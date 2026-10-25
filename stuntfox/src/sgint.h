/* The space game's insides that sgx.c (the city's foes, bosses and escape pods) shares with spacegame.c. Nothing
   else includes this. spacegame.c keeps the players' side (the Arwing, its shots, the jobs, the hangar) and the
   old raiders and carrier; the newer kinds of foe, and anything with a tag, are sgx.c's. */
#ifndef SGINT_H
#define SGINT_H
#include "spacegame.h"
#include "stage2.h"
#include "model.h"

/* the kinds of foe. F_RAIDER and F_CARRIER are the job board's; a tagged one of either is a mission's. F_HULL is a
   boss's body; a boss may also be a carrier, an ace or a courier (boss_tab in sgx.c). F_TURRET and F_BAY are parts */
enum { F_NONE, F_RAIDER, F_CARRIER, F_TURRET, F_ACE, F_COURIER, F_HULL, F_BAY };
/* fl: bit 0 held (stands still), 1 gone (a courier in space), 2 fixed (a part that stays where it was put down, a roof
   turret), 3 spare; the high nibble 1 + the boss_tab row, for a boss's body and its parts */
#define FL_HOLD 1
#define FL_GONE 2
#define FL_FIXED 4
#define FL_BOSS(f) ((f)->fl >> 4)
typedef struct {
    V3 p, v, home;                 /* a part's home is where it sits on its body, in the body's frame */
    s16 hp;
    u8 kind, cool, ai, fl;         /* ai: a part's body (its slot); a raider's break-off count; an ace's (low 5 bits) and her burst (high 3) */
    u16 tag;                       /* 0: the job board's, else a mission's (ours: 0x5000 and up) */
    s16 flo;                       /* a mission's foe: the least height it may fly at, looked up every few ticks (-32768: not yet) */
} Foe;
#define NFOE 8
extern Foe sg_foes[NFOE];
/* the newer foes and the stage-2 enemy shots are worked on every other tick, two ticks' worth at a go (staggered by slot):
   the dogfight's frame rate is what the upkeep of eight foes and their shots costs, tick after tick */
extern u8 sgx_par;
#define SGX_DUE(i) (!((sgx_par + (i)) & 1))
/* ... a boss's guns and bays, which have only a countdown to keep, every eighth tick (eight ticks' worth) */
#define SGX_WORK(f, i) ((f)->kind == F_TURRET || (f)->kind == F_BAY ? !((sgx_par + (i)) & 7) : SGX_DUE(i))

enum { S_LASER, S_MISSILE, S_ENEMY };
typedef struct {
    V3 p;
    s16 vx, vy, vz;
    u8 life, who;
    s8 tgt, pad;                   /* an enemy shot: pad is the harm it does (0: the job board's 6 + 2 a level) */
} Shot;
#define NSHOT 16
extern Shot sg_shots[NSHOT];

/* ---- spacegame.c, for sgx.c ---- */
void sgi_boom(V3 p, int big);      /* 0..3 fireballs (3 the biggest), 4..5 smoke, 6 a spark */
void sgi_enemy_shot(V3 p, V3 v, int harm, int life);
s32 sgi_dist(V3 d);
V3 sgi_dir(V3 d);
s32 sgi_rnd(s32 lo, s32 hi);
s32 sgi_rand(void);                /* 16 random bits (no division: sgi_rnd's modulus is a BIOS call) */
s32 sgi_roof(s32 x, s32 z);        /* the top of what is there: a block, a floor, a deck over it */
int sgi_seen(V3 a, V3 b);          /* can a see b: no ground, roof or deck between */
void sgi_place(const Model *md, V3 p, const M3 *m, s32 scale);
int sgi_near(V3 p, s32 r);         /* within r of the camera, each way */
void sgi_pay(int credits);
int sgi_tier(void);                /* how far the player has got: 1 + jobs done / 3, at most 3 */
void sgi_note(const char *s);
void sgi_foe_killed(int i);        /* foe i is destroyed, as a shot would (the job's end, credits, events) */
int sgi_free_foe(void);            /* a free slot, or -1 */

/* ---- sgx.c, for spacegame.c ---- */
void sgx_reset(void);              /* a new level: the foes (all of them), pods and bosses go */
int sgx_foes(void);                /* how many foes there are, of any kind */
int sgx_tagged(void);              /* is any of them a mission's */
void sgx_tick_foe(int i, const Ship *s);   /* one foe of the newer kinds, a tick */
void sgx_tick(void);               /* after the foes: pods, a boss's phases */
s32 sgx_floor(Foe *f);             /* how low a tagged foe may fly (it looks ahead over the city; the answer is kept a few ticks) */
int sgx_steer(int i);              /* is it foe i's turn to steer (one tick in four: the rest only fly on and count down) */
s32 sgx_radius(const Foe *f);      /* how far from its middle a shot hits it, each way */
s32 sgx_size(const Foe *f);        /* ... and how big its HUD brackets are */
int sgx_damage(int i, int dm);     /* a hit: 1 it is destroyed, 0 hurt, -1 shielded */
int sgx_shielded(int i);           /* a boss's body or bay that its guns still shield: a shot goes through it to them */
void sgx_killed(int i);            /* foe i has no health left: it goes, with its parts, credits, events and maybe a pod */
void sgx_draw(void);               /* the foes (at most what the frame can draw, the nearest) and the pods */
extern u8 sgx_shed;                /* 0: all of it; 1, 2: the frames are coming slower than 18 a second (the HUD and the shots look at it): the extras go */
int sgx_pickups(V3 p);             /* the Arwing at p, pods taken */
int sgx_boss_text(char *b);        /* the HUD line for a boss fight: 1 if there is one */
void sgx_boss_bar(void);           /* its health, over the picture */

#endif
