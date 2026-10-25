/* Payback for the PC: stands in for src/pbapi.h (it takes the include guard first, -include pbmock.h), so the engine's
   own source compiles for the host and runs against a model of the goal list, the command queue, the banner, the
   score and the entity list. The model follows what the build's probes measured: a command is applied once per
   tick, a goal is 9 words, an entity record has its tag at +0x14c. */
#ifndef PBAPI_H
#define PBAPI_H
#include "gba.h"

#define PB_NGOAL_MAX 100
#define PB_GOAL_SIZE 0x24
#define PB_CMD_SIZE 0x28
enum { PBG_LEVEL = 0, PBG_PHONE = 1, PBG_GOTO = 4, PBG_PHONE_RED = 7, PBG_HIDDEN_PICKUP = 47 };
#define PBG_ID 0
#define PBG_KIND 1
#define PBG_A 2
#define PBG_B 3
#define PBG_FLOOR 4
#define PBG_MARKER_BYTE 0x14

#define PBM_NENT 12
typedef struct {
    s32 goals[PB_NGOAL_MAX * 9];
    s16 ngoals;
    struct { s32 kind, id, a, b, floor, marker; } cmd[64];
    int ncmd;
    s16 level_end, respawn, mult;
    u32 clock;
    int score;
    char banners[64][24];
    int nbanner;
    u8 ent[PBM_NENT][0x160] __attribute__((aligned(8)));
    int spawn_calls, kill_calls, goal_reached_calls;
    s8 wanted;
    u8 me_rec[0x160] __attribute__((aligned(8)));
    int grid_ram;                                  /* 1: the cell the goal would sit on has a RAM copy */
    int sg_foes[16];
} PbMock;
extern PbMock pbm;

#define PB_NGOALS (pbm.ngoals)
#define PB_LEVEL_END (pbm.level_end)
#define PB_RESPAWN (pbm.respawn)
#define PB_MULT (pbm.mult)
#define PB_CLOCK (pbm.clock)
#define PB_BANNER_LEN 19
#define PB_BANNER_COMPLETE 0x7e6
#define PB_BANNER_FAILED 0x7ec
static inline volatile s32 *pb_goal_w(int i, int k) { return (volatile s32 *)pbm.goals + 9 * i + k; }
void pb_goal_add(int id, int kind, int a, int b, int floor, int marker);
void pb_goal_remove(int id);
static inline void pb_phones_readd(void) {}
static inline int pb_get_score(void) { return pbm.score; }
static inline void pb_add_score(int n) { pbm.score += n * pbm.mult; }
void pb_banner_raw(int slot, const char *s);
static inline void pb_banner_idx(int i) { (void)i; }

#define PBE_X 4
#define PBE_Y 8
#define PBE_Z 0xc
#define PBE_HEAD 0x12
#define PBE_DESC 0x1c
#define PBE_HEALTH 0x68
#define PBE_SCORE 0x90
#define PBE_WANTED 0x5a
#define PBE_STATE 0x10f
#define PBE_TAG 0x14c
#define PB_DESC_SIZE 0x3c
#define PBA_DESC0 0x08354af4
#define PB_DESC_K(d) (((u32)(d) - PBA_DESC0) / PB_DESC_SIZE)
static inline int pb_wanted(const u8 *me) { return me ? *(const s8 *)(me + PBE_WANTED) : 0; }
void pb_spawn_tagged(int tag, int type, int x, int y);
void pb_kill(int tag);
u8 *pb_ent_by_tag(int tag);
static inline void pb_hurt(int i, int by_man) { (void)i; (void)by_man; }
static inline u32 pb_col(int cx, int cz) { (void)cx; (void)cz; return pbm.grid_ram ? 0x02000000u : 0x08000000u; }
#define PB_IN_ROM(p) ((u32)(p) >= 0x08000000u)
static inline void pb_window_origin(s32 *ox8, s32 *oy8) { *ox8 = 0; *oy8 = 0; }
enum { B_UP = 0, B_DOWN = 1, B_SELECT = 2, B_LEFT = 4, B_RIGHT = 5, B_A = 6, B_B = 7, B_R = 8, B_START = 9, B_L = 10, B_SELECT2 = 11, B_N = 14 };
#endif
