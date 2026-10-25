/* People sent flying (MERGE build): a body of 12 points joined by sticks that tumbles, bounces
   and settles in the city as drawn, in the colours of the person it was. Only a picture:
   Payback's own record of that person is never moved (see merge.c, rag_scan). */
#ifndef RAGDOLL_H
#define RAGDOLL_H
#include "physics.h"

#define RAG_N 5                    /* bodies at once (the oldest makes way) */
#define RAG_P 12                   /* points of a body */

typedef struct {
    s16 x[RAG_P][3];               /* points, units / 8 from o */
    s16 v[RAG_P][3];               /* their velocity, units / 8 a tick */
    s32 o[3];                      /* where the body is (units) */
    const u8 *rec;                 /* Payback's record it stands for while that lies there, or 0 */
    s32 kx, kz;                    /* where that went down (units) */
    u8 body, legs, hero;           /* clothes (materials), and the player's own jacket and jeans */
    u8 state;                      /* RAG_FREE, RAG_FLY (moving), RAG_REST (settled) */
    u8 quiet;                      /* steps it has hardly moved */
    u8 bounces;                    /* times it came down hard (for the bounce gate) */
    u8 fine;                       /* fast and near the city: stepped a tick at a time */
    u8 own;                        /* the player's own, bailing out: merge.c runs it, our car never knocks it */
    u8 land;                       /* how fast it last came down hard on a floor (units a tick; merge.c
                                      takes it for fall damage) */
    u16 age;                       /* ticks since it was thrown (getting up: since that began) */
    u8 far;                        /* drawn small or not at all last frame (rag_draw) */
    u8 held;                       /* ticks put off to the next frame (a far body, when others fly too) */
    u8 due;                        /* knocked down by a car still short of them (merge.c): it throws them as it
                                      goes by, even off to its side */
} Rag;
enum { RAG_FREE, RAG_FLY, RAG_REST, RAG_RISE, RAG_UP };

extern Rag rags[RAG_N];
extern u8 rag_on;                  /* the option: ragdolls at all */
extern u8 rag_wacky;               /* the secret: superballs on the moon */
extern u8 rag_fall;                /* the option: a fall from a height costs the player health */
extern u8 rag_unlock;              /* the cheat has been entered: the RAGDOLLS option is there to set */

/* a body standing at feet (units) facing yaw (65536 a turn), thrown with vel (units << 8 a tick)
   and spin (an axis whose length is the turn rate, 1.14 radians a tick); returns its slot, or -1 for
   nobody (its feet inside something our city has solid) */
int rag_throw(V3 feet, s32 yaw, V3 vel, V3 spin, int body, int legs, int hero, const u8 *rec);
void rag_tick(int ticks);          /* moves every body that is not at rest */
void rag_draw(void);               /* draws them all, with the scene */
Rag *rag_of(const u8 *rec);        /* the body standing for Payback's record rec, or 0 */
V3 rag_pelvis(const Rag *r);       /* (units) */
s32 rag_floor(s32 x, s32 z, s32 y);   /* the floor a body at (x, y, z) lies on: a bridge deck it is over, a roof,
                                         a ramp, the water's surface (units) */
/* a body at rest gets up, facing yaw, its feet on the floor under it: RAG_RISE, then RAG_UP
   (standing as the person models stand) a third of a second later; age 0 the frame it stands
   (drawn standing once before a person model takes its place) */
void rag_rise(Rag *r, s32 yaw);
s32 rag_yaw(const Rag *r);         /* which way it would face standing up (its chest, or its legs lying down) */
void rag_clear(void);
/* spacewalk.c's figure, posed (not simulated): the body turned by m with its pelvis at `at` (units),
   the limbs spread s/16 of the way out (0 standing .. 16 floating). It stays RAG_UP, so nothing moves it */
void rag_pose(Rag *r, const M3 *m, V3 at, int s);
/* our car while it is driven or rolls on empty (merge.c, else 0): bodies it runs into are
   knocked on */
extern const Body *rag_car;

#endif
