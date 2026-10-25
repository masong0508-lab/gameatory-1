/* The PC side of the engine's world: Payback's goal list and queue, the banner, the entity list, K's foes, and the
   frame state; see pbmock.h. The queue is applied once per Payback tick, as the real one is. */
#include "stage2.h"
#include "mission.h"
#include "draw2d.h"
#include <string.h>
#include <stdio.h>

PbMock pbm;
S2Frame s2f;
u16 s2_phones;
S2Dbg s2_dbg;
u8 s2_blob_store[1 << 16] __attribute__((aligned(4)));
extern const u8 s2_blob[1 << 16] __attribute__((alias("s2_blob_store")));
int pbm_job, pbm_bad;                  /* K's job on; a rule the engine broke (the driver prints it) */
int pbm_evs[EV_N], pbm_puts;
struct { int tag, n; } pbm_foe[8];
char pbm_text[8][64];                  /* what d_text drew: the line, the card */
int pbm_ntext;

void pbm_reset(void)
{
    memset(&pbm, 0, sizeof pbm);
    memset(&s2f, 0, sizeof s2f);
    memset(pbm_evs, 0, sizeof pbm_evs);
    for (int i = 0; i < PBM_NENT; i++)
        *(s32 *)(pbm.ent[i] + PBE_TAG) = -1;
    pbm.mult = 1;
    pbm_job = pbm_bad = pbm_puts = 0;
    s2_phones = 0;
    for (int i = 0; i < 8; i++)
        pbm_foe[i].tag = -1, pbm_foe[i].n = 0;
    s2f.me = pbm.me_rec;
    s2f.map = 0;
}

static void add_goal(int id, int kind, int a, int b, int floor, int marker)
{
    if (pbm.ngoals >= PB_NGOAL_MAX)
        return;
    s32 *g = pbm.goals + 9 * pbm.ngoals++;
    g[0] = id, g[1] = kind, g[2] = a, g[3] = b, g[4] = floor, g[5] = marker & 255, g[6] = g[7] = -1, g[8] = 0;
}
static void del_goal(int id)
{
    for (int i = 0; i < pbm.ngoals; i++)
        if (pbm.goals[9 * i] == id) {
            memmove(pbm.goals + 9 * i, pbm.goals + 9 * (i + 1), (pbm.ngoals - i - 1) * 36);
            pbm.ngoals--;
            return;
        }
}

void pb_goal_add(int id, int kind, int a, int b, int floor, int marker)
{
    /* a goal on the floor 0x7f must have marker 0 (a marker byte on it makes Payback write into a cell by floor) */
    if (floor == 0x7f && marker != 0)
        pbm_bad |= 1;
    if (pbm.ncmd < 64)
        pbm.cmd[pbm.ncmd++] = (typeof(pbm.cmd[0])){0, id, a, b, floor, marker};
    pbm.cmd[pbm.ncmd - 1].kind = kind;
}
void pb_goal_remove(int id)
{
    if (pbm.ncmd < 64)
        pbm.cmd[pbm.ncmd++] = (typeof(pbm.cmd[0])){-1, id, 0, 0, 0, 0};
}
/* one Payback tick: the clock, the queue */
void pbm_tick(void)
{
    pbm.clock++;
    for (int i = 0; i < pbm.ncmd; i++) {
        if (pbm.cmd[i].kind == -1)
            del_goal(pbm.cmd[i].id);
        else
            add_goal(pbm.cmd[i].id, pbm.cmd[i].kind, pbm.cmd[i].a, pbm.cmd[i].b, pbm.cmd[i].floor, pbm.cmd[i].marker);
    }
    pbm.ncmd = 0;
}
/* a goal of Payback's own */
void pbm_add_own(int id, int kind) { add_goal(id, kind, 0, 0, 0, 0); }
void pbm_del_own(int id) { del_goal(id); }

void pb_banner_raw(int slot, const char *s)
{
    (void)slot;
    if (strlen(s) > PB_BANNER_LEN)
        pbm_bad |= 2;
    if (pbm.nbanner < 64)
        snprintf(pbm.banners[pbm.nbanner++], 24, "%s", s);
}

void pb_spawn_tagged(int tag, int type, int x, int y)
{
    pbm.spawn_calls++;
    for (int i = 0; i < PBM_NENT; i++)
        if (*(s32 *)(pbm.ent[i] + PBE_TAG) == -1 && !*(s16 *)(pbm.ent[i] + PBE_HEALTH)) {
            *(s32 *)(pbm.ent[i] + PBE_TAG) = tag;
            *(s32 *)(pbm.ent[i] + PBE_X) = x, *(s32 *)(pbm.ent[i] + PBE_Y) = y;
            *(s16 *)(pbm.ent[i] + PBE_HEALTH) = 100;
            *(u32 *)(pbm.ent[i] + PBE_DESC) = PBA_DESC0 + type * PB_DESC_SIZE;
            return;
        }
}
void pb_kill(int tag)
{
    pbm.kill_calls++;
    pbm_bad |= 4;                      /* the engine must not call it (untried in Payback's image) */
    (void)tag;
}
u8 *pb_ent_by_tag(int tag)
{
    if (tag < 0)
        return 0;
    for (int i = 0; i < PBM_NENT; i++)
        if (*(s32 *)(pbm.ent[i] + PBE_TAG) == tag)
            return pbm.ent[i];
    return 0;
}

int s2_put_player(V3 p, int heading, int mode)
{
    (void)heading;
    pbm_puts++;
    s2f.pos = p;
    s2f.mode = mode;
    return 1;
}
void s2_ev(int ev, int a, int b)
{
    if (ev >= 0 && ev < EV_N)
        pbm_evs[ev]++;
    ms_ev(ev, a, b);
}

int sg_job_active(void) { return pbm_job; }
int sg_foe_spawn(int kind, V3 p, V3 home, int hp, int tag)
{
    (void)kind; (void)p; (void)home; (void)hp;
    for (int i = 0; i < 8; i++)
        if (pbm_foe[i].tag == tag || pbm_foe[i].tag == -1) {
            pbm_foe[i].tag = tag;
            pbm_foe[i].n++;
            return i;
        }
    return -1;
}
int sg_foe_alive(int tag)
{
    for (int i = 0; i < 8; i++)
        if (pbm_foe[i].tag == tag && pbm_foe[i].n > 0)
            return 1;
    return 0;
}
void sg_foe_clear(int tag)
{
    for (int i = 0; i < 8; i++)
        if (pbm_foe[i].tag == tag)
            pbm_foe[i].tag = -1, pbm_foe[i].n = 0;
}
void sg_foe_hold(int tag, int on) { (void)tag; (void)on; }
int sg_boss_spawn(int boss, V3 p, int tag) { return sg_foe_spawn(boss, p, p, 100, tag) >= 0; }
int sg_boss_alive(int tag) { return sg_foe_alive(tag); }
int bigmap_enter(int arg) { (void)arg; return 0; }

/* the page (hudline.c writes it a word at a time, as the device's takes nothing smaller) and the 2D calls it uses */
u8 pbm_page[240 * 160] __attribute__((aligned(4)));
u8 *r_target(void) { return pbm_page; }
int d_pal(int c) { return c >= 0x100 ? c & 0xff : (c * 5 + 17) & 0xff; }          /* (any map that keeps colours apart) */
void d_text(int x, int y, const char *s, int color)
{
    (void)x; (void)color;
    if (pbm_ntext < 8)
        snprintf(pbm_text[pbm_ntext++], 64, "%d:%s", y, s);
}
void d_fill(int x, int y, int w, int h, int color)       /* (draw2d.c's, minus the DMA) */
{
    int c = d_pal(color);
    x &= ~3;
    w = (w + 3) & ~3;
    if (x < 0) w += x, x = 0;
    if (x + w > 240) w = 240 - x;
    if (y < 0) h += y, y = 0;
    if (y + h > 160) h = 160 - y;
    for (int j = 0; j < h && w > 0; j++)
        memset(pbm_page + (y + j) * 240 + x, c, w);
}
char *d_num(char *b, int v) { return b + sprintf(b, "%d", v); }
char *d_time(char *b, int s) { return b + sprintf(b, "%d:%02d", s / 60, s % 60); }
char *d_cat(char *b, const char *s) { while (*s) *b++ = *s++; *b = 0; return b; }
