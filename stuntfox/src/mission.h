/* The mission engine (stage 2): runs one mission at a time from the ROM blob (misdata.h) on Payback's goal
   list, the arrow, the banner and the score, and on s2f and the events. The campaign (P) decides which act is
   armed; challenges and medals are armed here by walking up to their beacon. All entry points the frame
   hooks reach are ms_tick, ms_ev, ms_draw3d, ms_level_enter and ms_dbg (stage2.h); this is the rest. */
#ifndef MISSION_H
#define MISSION_H
#include "gba.h"
#include "misdata.h"

enum { MS_IDLE, MS_ARMED, MS_RUN, MS_DONE, MS_FAIL, MS_PAUSED };
enum { RF_ROAM = 1, RF_GOAL = 2, RF_HELD = 4, RF_CARD = 8, RF_QUIET = 16 };   /* flags: a beacon armed by walking up; our arrow goal is pushed;
                                                                  foes held for a phone mission; the retry card was shown; the armed
                                                                  beacon and line are off (a job, a talk or a Payback mission on) */

typedef struct {                   /* 64 bytes, in keep */
    u16 mis, obj;                  /* the MisDef, the MisObj (an index into the blob's objectives) */
    u8 state, retries;
    u8 ckpt, carry;                /* the last MO_CKPT objective reached + 1 (0: none); carrying (DELIVER, CRATES) */
    u16 count, need;               /* progress in the op (DEFEND: the asset's hp); need: Payback's phone count at the step's start */
    u16 tag, group;                /* the tags of its spawns and foes; GROUP's members done */
    s32 t_start, t_step;           /* PB_CLOCK at the start of the act and of the step */
    s32 timer;                     /* ticks left of a TIMER scope (0: none) */
    s32 score0;                    /* Payback's score at the start of the step (SCORE) */
    u16 ceil_h, ceil_zone, zone;   /* CEIL: height and its zone's MsPlace + 1; ZONE: its MsPlace + 1 */
    u16 pts;                       /* STUNT points so far */
    u8 flags, evm;                 /* RF_*; the events since the last tick (EVM_*) */
    u16 goal;                      /* the id of our arrow goal (0: none) */
    u8 dwell, ap;                  /* ticks standing in the start beacon; autopilot (dbg) */
    u8 spawned, pad;               /* tags of ours on the street (bit i: tag + i) */
    s32 v[3];                      /* the op's scratch: [0] the side of a plane / the spawns up / DEFEND's ticks left, [1] the pickups taken / the
                                      kills / the foes' wear, [2] a time limit / the poll clock */
    u16 rr;                        /* the roam scan's next mission */
    u8 ndone, nfail;               /* missions finished and failed since the level began (the harness reads them) */
} MisRun;
#ifdef __arm__
_Static_assert(sizeof(MisRun) == 64, "MisRun");
#endif
extern MisRun ms_run;
enum { EVM_DEATH = 1, EVM_SPACE = 2, EVM_DOCK = 4, EVM_TALK = 8, EVM_JUMP = 16, EVM_FORCE = 32, EVM_FAIL = 64 };   /* (the last two: the debug mailbox) */

/* start rules, the engine side */
void ms_arm(int mis);              /* show the start beacon; it starts when the player stands in it (or flies through it) */
void ms_start(int mis);            /* start now (the Ops board, a talk, the debug mailbox); a run in progress is dropped */
void ms_abort(void);               /* drop the run: our goals out, our spawns and foes gone */
int ms_state(void);                /* MS_* */
int ms_current(void);              /* the MisDef index running or armed, -1 none */
int ms_retries(void);              /* fails of the current mission since it was first started */
const MisDef *ms_def(int i);
const Chapter *ms_chap(int i);
const MsPlace *ms_place(int i);
const MisObj *ms_obj(int i);
const char *ms_text(int id);
int ms_target(void);               /* the MsPlace of the objective now (the arrow, the beacon), -1 none */
int ms_count(void);
int ms_nchap(void);

/* what the engine asks of the other packages, each weak in mission.c (nothing there: no effect) */
void sg_give(int credits);                  /* K: credits */
int sg_foe_near(V3 p, s32 r, int tag);      /* K: foes of this tag within r of p */
int cp_mis_done(int mis);                   /* P: this mission is done (medals found are not armed again) */
void cp_unlock(int what);                   /* P: OP_UNLOCK */
void cp_set(int flag, int value);           /* P: OP_SET */

/* msn_draw.c */
#endif
