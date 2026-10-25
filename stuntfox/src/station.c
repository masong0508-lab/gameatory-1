/* Fox Station (stage 2, S; station.h): the walker, the cameras, the doors, the crew's talk, the terminals and the quick menu. The
   hangar is room 0 and stays the docked view it always was (spacegame.c's menu and hangar_draw); the STATION line of its menu (or B)
   walks out to the hub, and from then on this file has the keys (st_tick) and the picture (st_view, stationdraw.c's st_draw_room).
   What the rooms are and what the crew say is ROM data (st_blob, tools/content/station.py); nothing of it is kept in RAM but the
   60-byte StState and a few statics. Nothing here prints on Payback's ticker: news is a line over the picture. */
#include "stage2.h"
#include "station.h"
#include "campaign.h"
#include "mission.h"
#include "spacegame.h"
#include "draw2d.h"
#include "render.h"
#include "palette.h"

#define INK COLOR(M_CREAM, 3, 0)
#define HI COLOR(M_ACCENT, 3, 0)
#define TITLE COLOR(M_GLOW, 3, 0)
#define DIM COLOR(M_STEEL, 1, 0)
#define PANEL COLOR(M_ROAD, 0, 0)
#define HELP COLOR(M_STEEL, 3, 0)
#define GOOD COLOR(M_GRASS, 3, 0)

#define WALK 22                    /* units a tick: 1300 a second */
#define RUN 35                     /* 2100 a second (R) */
#define BODY 130                   /* how close to a wall or a box the walker's middle comes */
#define CREWR 200                  /* ... and to a crew member */
#define TALKR 330                  /* how near one must be to be spoken to */
#define DWELL 30                   /* ticks (half a second) a camera node holds before the next cut */
#define HYST 256                   /* a node holds its walker this far outside its own region */
#define DOOR_CD 40                 /* ticks after a room change before a door may be taken */
#define MSG_TICKS 180
#define PAN 12                     /* ticks a page stays as it is (no more than two or three flashes a second at the fastest button) */
#define ROWS 7                     /* lines a list shows */

StState stw;
static u8 blob_ok;
static s32 iabs(s32 v) { return v < 0 ? -v : v; }                 /* 0 not looked at yet, 1 good, 2 not there or wrong */

extern int cp_travel(int c);
extern void cp_open_at(int line);  /* campaign.c: the quick menu, at one of its lines */

/* ---- the blob ---- */
static const StHead *hd(void) { return (const StHead *)st_blob; }
const StHead *st_head(void) { return hd(); }
int st_ok(void)
{
    if (!blob_ok) {
        const StHead *h = hd();
        blob_ok = 2;
        if (!((unsigned long)h & 3) && h->magic == ST_MAGIC && h->ver == ST_VER && h->nroom == R_N && h->size >= sizeof(StHead) &&
            h->size < 0x100000 && h->off_text < h->size)
            blob_ok = 1;
    }
    return blob_ok == 1;
}
const StRoom *st_room(int r) { return (const StRoom *)(st_blob + hd()->off_room) + r; }
const StCam *st_cams(const StRoom *rm) { return (const StCam *)(st_blob + rm->off_cam); }
const StUse *st_uses(const StRoom *rm) { return (const StUse *)(st_blob + rm->off_use); }
const StCrew *st_crews(const StRoom *rm) { return (const StCrew *)(st_blob + rm->off_crew); }
typedef struct { s16 x0, z0, x1, z1; } Box;
static const Box *boxes(const StRoom *rm) { return (const Box *)(st_blob + rm->off_box); }
static const StNode *node(int i) { return (const StNode *)(st_blob + hd()->off_node) + i; }
static const StEnt *ent(int i) { return (const StEnt *)(st_blob + hd()->off_ent) + i; }
const char *st_text(int id)
{
    const u8 *t = st_blob + hd()->off_text;
    return id < hd()->ntext ? (const char *)t + ((const u16 *)t)[id] : "";
}

/* ---- what the campaign says (cond bytes: tools/content/station.py) ---- */
static int chap_done(int k)
{
    if (k >= ms_nchap())
        return 0;
    int n = ms_chap(k)->nact;
    n = n > 8 ? 8 : n;
    int m = (1 << n) - 1;
    return n && (cp_prog.acts[k] & m) == m;
}

static int cond_ok(int c)
{
    int r, neg = c & 0x80;
    c &= 0x7f;
    if (!c)
        r = 1;
    else if (c < 0x30)
        r = cp_prog.chap_unlocked >= c - 0x10;
    else if (c < 0x50)
        r = chap_done(c - 0x30);
    else if (c < 0x58)
        r = cp_flag(c - 0x50);
    else if (c < 0x60)
        r = cp_unlocked(c - 0x58);
    else
        r = c == 0x60 && cp_ace();
    return neg ? !r : r;
}

/* the chapter this level is of (the one playing, else the first of this map) */
static int cur_chap(void)
{
    if (cp_active() && cp_prog.chap_cur < ms_nchap())
        return cp_prog.chap_cur;
    for (int c = 0; c < ms_nchap(); c++)
        if (ms_chap(c)->map == s2f.map && !(ms_chap(c)->flags & CH_RESERVED))
            return c;
    return -1;
}

static void news(const char *s)
{
    stw.msg = s;
    stw.msg_end = s2f.ticks + MSG_TICKS;
}
static int news_up(void) { return stw.msg && s2f.ticks < stw.msg_end; }

/* ---- rooms ---- */
static int in_box(const StRoom *rm, int x, int z, int pad)
{
    const Box *b = boxes(rm);
    for (int i = 0; i < rm->nbox; i++)
        if (x > b[i].x0 - pad && x < b[i].x1 + pad && z > b[i].z0 - pad && z < b[i].z1 + pad)
            return 1;
    return 0;
}

static int free_at(const StRoom *rm, int x, int z)
{
    if (x < -rm->hx + 140 || x > rm->hx - 140 || z < rm->zmin || z > rm->hz - 140 || in_box(rm, x, z, BODY))
        return 0;
    const StCrew *c = st_crews(rm);
    for (int i = 0; i < rm->ncrew; i++) {
        s32 dx = x - c[i].x, dz = z - c[i].z;
        if (dx * dx + dz * dz < CREWR * CREWR)
            return 0;
    }
    return 1;
}

static int cam_in(const StCam *c, int x, int z, int pad)
{
    return x >= c->x0 - pad && x <= c->x1 + pad && z >= c->z0 - pad && z <= c->z1 + pad;
}

/* the camera node for the walker: his own node while he is within its region and the hysteresis band, else the first that holds him
   (or the nearest by x) */
static int want_node(const StRoom *rm)
{
    const StCam *c = st_cams(rm);
    if (stw.node < rm->ncam && cam_in(&c[stw.node], stw.x, stw.z, HYST))
        return stw.node;
    int best = 0, bd = 1 << 30;
    for (int i = 0; i < rm->ncam; i++) {
        if (cam_in(&c[i], stw.x, stw.z, 0))
            return i;
        int d = stw.x < c[i].x0 ? c[i].x0 - stw.x : stw.x > c[i].x1 ? stw.x - c[i].x1 : 0;
        if (d < bd)
            bd = d, best = i;
    }
    return best;
}

static void snap_cam(void)
{
    const StRoom *rm = st_room(stw.room);
    const StCam *c = &st_cams(rm)[stw.node];
    stw.bx = c->px, stw.by = c->py, stw.bz = c->pz, stw.bty = c->ty, stw.btz = c->tz;
}

static int ease(int v, int t)                            /* a quarter of the way, and the last few units in one */
{
    int d = t - v;
    return v + (d >> 2) + (d > 0 && d < 4 ? d : 0);
}

static void cam_tick(void)
{
    const StRoom *rm = st_room(stw.room);
    if (stw.dwell)
        stw.dwell--;
    int want = want_node(rm);
    if (want != stw.node && !stw.dwell)
        stw.node = want, stw.dwell = DWELL;
    const StCam *c = &st_cams(rm)[stw.node];
    /* it glides to its node (a cut is a quick pan, not a jump: nothing on the screen changes all at once) */
    stw.bx = ease(stw.bx, c->px), stw.by = ease(stw.by, c->py), stw.bz = ease(stw.bz, c->pz);
    stw.bty = ease(stw.bty, c->ty), stw.btz = ease(stw.btz, c->tz);
}

/* walk into room `to` from room `from` (from = to when he arrives out of the hangar): at the door that leads back, clear of its trigger */
static void go_room(int to, int from)
{
    if (to == R_HANGAR) {
        stw.room = R_HANGAR;
        stw.term = stw.dent = 0;
        stw.sway = 128, stw.idle = 0, stw.same = 0;
        stw.cd = DOOR_CD;                                /* (the way back in waits too: hub and hangar do not swap faster than a flicker) */
        return;
    }
    const StRoom *rm = st_room(to);
    const StUse *u = st_uses(rm);
    int sx = 0, sz = 0;
    for (int i = 0; i < rm->nuse; i++)
        if (u[i].kind == U_DOOR && u[i].arg == from)
            sx = u[i].sx, sz = u[i].sz;
    stw.room = to;
    stw.x = sx, stw.z = sz;
    stw.yaw = 0;
    stw.term = stw.dent = stw.cur = stw.top = stw.page = stw.confirm = stw.near = 0;
    stw.cd = DOOR_CD;
    stw.node = 0;
    stw.node = want_node(rm);
    stw.dwell = DWELL;
    snap_cam();
    stw.same = 0;
}

int st_enter(void)
{
    if (!st_ok())
        return 0;
    if (!stw.cd)
        go_room(R_HUB, R_HANGAR);
    return 1;
}

int st_active(void) { return stw.room != R_HANGAR; }

/* ---- the talk ---- */
static int heard(int id) { return id < 64 && (stw.heard[id >> 5] >> (id & 31) & 1); }

static int pick_entry(int crew)
{
    const StHead *h = hd();
    int n = 0;
    for (int i = 0; i < h->nent; i++) {
        const StEnt *e = ent(i);
        if (e->crew != crew || (e->flags & (E_MSG | E_LOG)) || !cond_ok(e->cond))
            continue;
        if (e->flags & E_REPEAT)
            n++;
        else if (!heard(e->id))
            return i;
    }
    if (!n)
        return -1;
    int k = stw.chat++ % n;                              /* all said: the chatter, in turn */
    for (int i = 0; i < h->nent; i++) {
        const StEnt *e = ent(i);
        if (e->crew == crew && (e->flags & E_REPEAT) && cond_ok(e->cond) && !k--)
            return i;
    }
    return -1;
}

static void start_talk(int crew)
{
    int i = pick_entry(crew);
    if (i < 0)
        return;
    stw.dcrew = crew;
    stw.dent = ent(i)->id;
    stw.dnode = ent(i)->node;
}

/* contract k of this chapter, or 0 */
static int contract_at(int c, int k)
{
    if (c < 0)
        return 0;
    const Chapter *ch = ms_chap(c);
    for (int m = ch->mis0; m < ch->mis0 + ch->nmis; m++) {
        const MisDef *d = ms_def(m);
        if (d && d->kind == MK_CONTRACT && !k--)
            return m + 1;
    }
    return 0;
}

static int contract_n(int c)
{
    int n = 0;
    while (contract_at(c, n))
        n++;
    return n;
}

static void take_contract(int m)
{
    if (ms_state() == MS_RUN || ms_state() == MS_PAUSED) {
        news("FINISH YOUR MISSION FIRST");
        return;
    }
    ms_start(m);
    news("CONTRACT TAKEN. LAUNCH WHEN READY");
}

static void do_act(int act)
{
    int a = act >> 3;
    switch (act & 7) {
    case A_UNLOCK: cp_unlock(a); break;
    case A_SET: cp_set(a, 1); break;
    case A_START: {
        int m = contract_at(cur_chap(), a);
        if (m)
            take_contract(m - 1);
        break;
    }
    case A_OPEN:
        stw.term = a;
        stw.cur = stw.top = stw.page = stw.confirm = 0;
        break;
    }
}

static void talk_key(u16 hit)
{
    if (hit & KEY_B) {
        stw.dent = 0;                                    /* (cut short: not heard, nothing raised) */
        return;
    }
    if (!(hit & KEY_A))
        return;
    const StNode *n = node(stw.dnode);
    int act = n->act;
    if (n->next) {
        stw.dnode = n->next;
        do_act(act);
        return;
    }
    int id = stw.dent, crew = stw.dcrew;
    stw.dent = 0;
    if (id < 64)
        stw.heard[id >> 5] |= 1u << (id & 31);
    s2_ev(EV_TALK, crew, id);
    do_act(act);
}

/* ---- terminals: lists ---- */
static int list_n(void)
{
    int c = cur_chap(), n = 0;
    switch (stw.term) {
    case T_CONTRACT: return contract_n(c);
    case T_TRAVEL: case T_MAP: case T_RECAP: n = cp_prog.chap_unlocked + 1; return n > ms_nchap() ? ms_nchap() : n;
    case T_SHOP: return 5;
    case T_PAINT: { const char *const *nm; return sg_paints(&nm); }
    case T_COMMS: return 5;
    case T_QUICK: return 6;
    case T_MSGS: case T_LOG: {
        int f = stw.term == T_MSGS ? E_MSG : E_LOG;
        for (int i = 0; i < hd()->nent; i++)
            n += (ent(i)->flags & f) && cond_ok(ent(i)->cond);
        return n;
    }
    }
    return 0;
}

static int nth_ent(int flag, int k)                      /* the k-th entry of that sort that holds now */
{
    for (int i = 0; i < hd()->nent; i++)
        if ((ent(i)->flags & flag) && cond_ok(ent(i)->cond) && !k--)
            return i;
    return -1;
}

static void term_close(void)
{
    stw.term = stw.cur = stw.top = stw.page = stw.confirm = 0;
}

static void term_enter(int t)
{
    stw.term = t;
    stw.cur = stw.top = stw.page = stw.confirm = 0;
    if (t == T_MAP || t == T_TRAVEL)
        stw.cur = cur_chap() >= 0 && cur_chap() < list_n() ? cur_chap() : 0;
}

static void quick_pick(int i)
{
    switch (i) {
    case 0:
        term_close();
        stw.room = R_HANGAR;
        sg_launch();
        break;
    case 1: term_enter(T_CONTRACT); break;
    case 2: term_enter(T_TRAVEL); break;
    case 3: term_close(); cp_open_at(2); break;
    case 4: term_enter(T_MAP); break;
    default: term_close();
    }
}

static void term_key(u16 hit, u16 keys)
{
    (void)keys;
    int n = list_n(), t = stw.term;
    if (hit & KEY_B || (t == T_QUICK && hit & KEY_L)) {
        if ((t == T_MSGS || t == T_LOG || t == T_RECAP || t == T_BRIEF) && stw.page) {
            stw.page = 0;
        } else if (t == T_MSGS) {
            term_enter(T_COMMS);
            stw.cur = 3;
        } else
            term_close();
        return;
    }
    if (n) {
        if (hit & KEY_UP)
            stw.cur = stw.cur ? stw.cur - 1 : n - 1, stw.confirm = 0;
        if (hit & KEY_DOWN)
            stw.cur = stw.cur + 1 < n ? stw.cur + 1 : 0, stw.confirm = 0;
        stw.top = stw.cur < stw.top ? stw.cur : stw.cur >= stw.top + ROWS ? stw.cur - ROWS + 1 : stw.top;
    }
    if (t == T_TROPHY) {
        if (hit & KEY_RIGHT) stw.page = stw.page < 2 ? stw.page + 1 : 0;
        if (hit & KEY_LEFT) stw.page = stw.page ? stw.page - 1 : 2;
    }
    if (!(hit & KEY_A))
        return;
    switch (t) {
    case T_QUICK:
        quick_pick(stw.cur);
        break;
    case T_CONTRACT: {
        int m = contract_at(cur_chap(), stw.cur);
        if (m)
            take_contract(m - 1);
        break;
    }
    case T_TRAVEL: case T_MAP: {
        if (!cp_active()) {
            news("START THE CAMPAIGN FIRST");
            break;
        }
        int r = cp_travel(stw.cur);
        news(r == 1 ? "TRAVELLING..." : r == 2 ? "BOOKED: GO WHEN THIS LEVEL ENDS" : "NOT YET OPEN");
        if (r == 1)
            term_close();
        break;
    }
    case T_SHOP: {
        int p = sg_price(stw.cur);
        if (p > 0 && stw.confirm != stw.cur + 1 && sg_credits() >= p) {
            stw.confirm = stw.cur + 1;                   /* (one A must not spend every credit: it asks first) */
        } else {
            stw.confirm = 0;
            news(p <= 0 ? "ALREADY THE BEST" : sg_credits() < p ? "NOT ENOUGH CREDITS" : sg_buy(stw.cur) ? "FITTED!" : "NOT NOW");
        }
        break;
    }
    case T_PAINT:
        if (sg_paint_unlocked(stw.cur) && sg_buy(SGB_PAINT + stw.cur))
            news("PAINT ON");
        else
            news("NOT UNLOCKED YET");
        break;
    case T_COMMS:
        if (stw.cur == 3)
            term_enter(T_MSGS);
        else if (stw.cur == 4)
            term_close();
        else
            term_close(), cp_open_at(2 + stw.cur);
        break;
    case T_MSGS: case T_LOG:
        stw.page = !stw.page;
        break;
    case T_RECAP: case T_BRIEF:
        stw.page = !stw.page;
        break;
    }
}

/* ---- the walker ---- */
static void near_scan(void)
{
    const StRoom *rm = st_room(stw.room);
    const StCrew *c = st_crews(rm);
    const StUse *u = st_uses(rm);
    stw.near = 0;
    for (int i = 0; i < rm->ncrew; i++) {
        s32 dx = stw.x - c[i].x, dz = stw.z - c[i].z;
        if (dx * dx + dz * dz < TALKR * TALKR) {
            stw.near = U_TALK << 5 | (i + 1);
            return;
        }
    }
    for (int i = 0; i < rm->nuse; i++)
        if (u[i].kind == U_TERM && iabs(stw.x - u[i].x) < u[i].r4 * 4 && iabs(stw.z - u[i].z) < u[i].r4 * 4) {
            stw.near = U_TERM << 5 | (i + 1);
            return;
        }
}

static void door_scan(void)
{
    const StRoom *rm = st_room(stw.room);
    const StUse *u = st_uses(rm);
    if (stw.cd)
        return;
    for (int i = 0; i < rm->nuse; i++)
        if (u[i].kind == U_DOOR && iabs(stw.x - u[i].x) < u[i].r4 * 4 && iabs(stw.z - u[i].z) < u[i].r4 * 4) {
            if (u[i].arg == R_QUARTERS && !cp_unlocked(CP_UNLOCK_QUARTERS)) {
                news("LOCKED. KESTREL HAS THE KEY");     /* (the door waits for the story) */
                stw.cd = DOOR_CD * 4;
                return;
            }
            go_room(u[i].arg, stw.room);
            return;
        }
}

static void walk(u16 keys)
{
    const StRoom *rm = st_room(stw.room);
    int dx = !!(keys & KEY_RIGHT) - !!(keys & KEY_LEFT), dz = !!(keys & KEY_UP) - !!(keys & KEY_DOWN);
    stw.moving = 0;
    if (!(dx | dz))
        return;
    int sp = keys & KEY_R ? RUN : WALK;
    if (dx && dz)
        sp = sp * 181 >> 8;
    int nx = stw.x + dx * sp, nz = stw.z + dz * sp;
    if (free_at(rm, nx, stw.z))
        stw.x = nx, stw.moving = 1;
    if (free_at(rm, stw.x, nz))
        stw.z = nz, stw.moving = 1;
    u16 want = fatan2(dx, dz);
    stw.yaw += (s16)(want - stw.yaw) >> 1;
    if (stw.moving)
        stw.phase++;
}

static int tick2(u16 hit, u16 keys)
{
    if (stw.cd)
        stw.cd--;
    if (stw.dent) {
        talk_key(hit);
        cam_tick();
        return 1;
    }
    if (stw.term) {
        term_key(hit, keys);
        cam_tick();
        return 1;
    }
    if (hit & KEY_L) {
        term_enter(T_QUICK);
        return 1;
    }
    if (hit & KEY_B && !stw.cd) {                        /* back: out of a room into the hub, out of the hub into the hangar (not at once after a change: no flicker) */
        go_room(stw.room == R_HUB ? R_HANGAR : R_HUB, stw.room);
        return 1;
    }
    walk(keys);
    near_scan();
    if (hit & KEY_A && stw.near) {
        const StRoom *rm = st_room(stw.room);
        int k = (stw.near & 31) - 1;
        if (stw.near >> 5 == U_TALK)
            start_talk(st_crews(rm)[k].crew);
        else
            term_enter(st_uses(rm)[k].arg);
    }
    door_scan();
    cam_tick();
    return 1;
}

/* a full-screen page that comes and goes at the speed of a mashed button would flash: a page is held for PAN ticks, and the keys that
   would open, close or choose in it wait (the D-pad inside it does not) */
int st_tick(u16 hit, u16 keys)
{
    if (!st_ok() || stw.room == R_HANGAR || !s2f.docked)
        return 0;
    int open = stw.term != 0;
    if (stw.pan) {
        stw.pan--;
        hit &= open ? ~(KEY_A | KEY_B | KEY_L) : ~(KEY_A | KEY_L);
    }
    int r = tick2(hit, keys);
    if ((stw.term != 0) != open)
        stw.pan = PAN;
    return r;
}

/* ---- events and the frame ---- */
void st_ev(int ev, int a, int b)
{
    (void)a;
    (void)b;
    if (ev == EV_DOCK || ev == EV_LAUNCH) {              /* (a fresh dock is the hangar; a launch leaves any room) */
        stw.room = R_HANGAR;
        stw.term = stw.dent = 0;
    }
}

static void sprites(int want_hidden)                     /* Payback's sprites (its HUD and map) off for a room's picture: the options page does the same */
{
    if (want_hidden && !stw.hid)
        REG_DISPCNT &= ~0x1000, stw.hid = 1;
    else if (!want_hidden && stw.hid)
        REG_DISPCNT |= 0x1000, stw.hid = 0;
}

/* the hangar: the camera's sway settles once nothing has changed on the menu for a second, and then the view can be left as it is */
int st_sway(void) { return stw.sway << 1; }

static int hangar_view(void)
{
    u32 s = sg_menu_sig() ^ (u32)cam.pos.x * 31 ^ (u32)cam.pos.y * 7 ^ (u32)cam.pos.z * 17 ^ (u32)cam.m.f.x ^ (u32)cam.m.f.z * 3;
    if (s != stw.sig)
        stw.sig = s, stw.idle = 0, stw.same = 0;
    else if (stw.idle < 255)
        stw.idle++;
    int target = stw.idle > 45 ? 0 : 128;
    stw.sway = stw.sway < target ? (stw.sway + 3 > target ? target : stw.sway + 3) : stw.sway > target ? (stw.sway < 3 ? 0 : stw.sway - 3) : stw.sway;
    if (stw.sway)
        return 0;
    if (stw.same >= 2)
        return 2;                                        /* (both pages hold it) */
    stw.same++;
    return 0;
}

int st_view(void)
{
    if (!st_ok())
        return 0;
    if (!s2f.docked) {
        if (stw.room != R_HANGAR || stw.dent || stw.term)
            go_room(R_HANGAR, R_HANGAR);
        sprites(0);
        stw.sway = 128;
        return 0;
    }
    if (stw.room == R_HANGAR) {
        sprites(0);
        if (s2f.paused)
            return 0;
        if (stw.cd)
            stw.cd--;
        return hangar_view();
    }
    sprites(!s2f.paused);
    if (s2f.paused)
        return 1;
    u32 sg = st_sig();
    if (sg != stw.sig)
        stw.sig = sg, stw.same = 0;
    if (stw.same >= 2)
        return 2;
    stw.same++;
    return 1;
}

void st_draw(void)
{
    st_draw_room();
}

u32 st_sig(void)
{
    u32 h = stw.room ^ stw.node << 4 ^ stw.term << 8 ^ stw.cur << 13 ^ stw.top << 17 ^ stw.page << 21 ^ stw.confirm << 24 ^ stw.near << 27;
    h = h * 0x01000193 ^ (u16)stw.x ^ (u32)(u16)stw.z << 16;
    h = h * 0x01000193 ^ (u16)stw.bx ^ (u32)(u16)stw.by << 16;
    h = h * 0x01000193 ^ (u16)stw.bz ^ (u32)(u16)stw.bty << 16;
    h = h * 0x01000193 ^ (u16)stw.btz ^ (u32)(stw.moving ? 1 + (stw.phase >> 3 & 1) : 0) << 16 ^ (u32)(stw.yaw >> 11) << 20;
    h = h * 0x01000193 ^ stw.dnode ^ (u32)stw.dent << 16;
    h = h * 0x01000193 ^ (u32)sg_credits() ^ cp_sig() << 3 ^ (u32)news_up() << 30 ^ ((u32)stw.msg & 0xffff);
    return h;
}

/* ---- the screens ---- */
static void panel(int x, int y, int w, int h)
{
    d_fill(x, y, w, h, PANEL);
    d_hline(x, x + w - 1, y, DIM);
    d_hline(x, x + w - 1, y + h - 1, DIM);
    d_vline(x, y, y + h - 1, DIM);
    d_vline(x + w - 1, y, y + h - 1, DIM);
}

static void line(int x, int y, int sel, const char *s)
{
    if (sel)
        d_text(x - 8, y, ">", HI);
    d_text(x, y, s, sel ? HI : INK);
}

static void help(const char *s) { d_text(10, 128, s, HELP); }

static char *num(char *p, int v) { return d_num(p, v); }

static const char *const shop_name[5] = {"LASERS", "SHIELD", "ENGINE", "MISSILES", "MISSILE RACK"};
static const char *const quick_name[6] = {"LAUNCH", "CONTRACTS", "TRAVEL", "SAVE...", "MAP", "BACK"};
static const char *const comms_name[5] = {"SAVE...", "SHOW CODE", "ENTER CODE", "MESSAGES", "BACK"};
const char *const st_crew_name[8] = {"", "ROOK", "PIP", "NOVA", "DUSTY", "QUILL", "JUNO", "KESTREL"};
#define crew_name st_crew_name

static void screen_list(const char *title, int n)
{
    panel(8, 14, 224, 112);
    d_text(14, 18, title, TITLE);
    d_hline(9, 230, 28, DIM);
    char b[16], *p = d_cat(b, "CR ");
    p = num(p, sg_credits());
    d_text(228 - TEXT_W * (int)(p - b), 18, b, HELP);
    (void)n;
}

static void act_dots(int c, int x, int y)                /* a chapter's acts as boxes: done, or not */
{
    const Chapter *ch = ms_chap(c);
    int n = ch->nact > 8 ? 8 : ch->nact;
    for (int i = 0; i < n; i++)
        d_fill(x + i * 6, y, 5, 5, cp_prog.acts[c] >> i & 1 ? GOOD : DIM);
}

static int popc(u32 v)
{
    int n = 0;
    for (; v; v &= v - 1)
        n++;
    return n;
}

static void screen_map(int c)                            /* the holo table: the city's 128 x 128 cells on 64 x 64, where the station hangs and the acts */
{
    const int x = 160, y = 34;
    const Chapter *ch = ms_chap(c);
    d_fill(x - 1, y - 1, 66, 66, DIM);
    d_fill(x, y, 64, 64, COLOR(M_ROAD, 1, 0));
    int ok = 0, kk[4] = {0, 0, 0, 0};
    for (int m = ch->mis0; m < ch->mis0 + ch->nmis; m++) {
        const MisDef *d = ms_def(m);
        if (!d || d->start == NOPLACE || !ms_place(d->start))
            continue;
        const MsPlace *p = ms_place(d->start);
        int px = p->x8 >> 4, py = 63 - (p->y8 >> 4), done = 0;
        if (d->kind == MK_ACT)
            done = d->act >= 1 && d->act <= 8 && (cp_prog.acts[c] >> (d->act - 1) & 1);
        else if (d->kind == MK_CHAL)
            done = kk[MK_CHAL] < 16 && (cp_prog.chal[c] >> kk[MK_CHAL] & 1);
        else if (d->kind == MK_MEDAL)
            done = kk[MK_MEDAL] < 8 && (cp_prog.medals[c] >> kk[MK_MEDAL] & 1);
        kk[d->kind & 3]++;
        if (px < 0 || px > 62 || py < 0 || py > 62)
            continue;
        int big = d->kind == MK_ACT;
        d_fill(x + px, y + py, big ? 3 : 2, big ? 3 : 2, done ? GOOD : d->kind == MK_ACT ? HI : d->kind == MK_MEDAL ? TITLE : INK);
        ok++;
    }
    int hx = ch->hx2 >> 2, hy = 63 - (ch->hy2 >> 2);     /* the station: a cross over the cell */
    d_hline(x + hx - 3, x + hx + 3, y + hy, INK);
    d_vline(x + hx, y + hy - 3, y + hy + 3, INK);
    (void)ok;
}

static void screen(void)
{
    char b[40], *p;
    int c = cur_chap(), n = list_n();
    switch (stw.term) {
    case T_QUICK:
        panel(8, 20, 110, 90);
        d_text(14, 24, "FOX STATION", TITLE);
        for (int i = 0; i < 6; i++)
            line(22, 38 + i * 10, i == stw.cur, quick_name[i]);
        help("A: PICK   B: BACK");
        break;
    case T_BRIEF:
    case T_RECAP: {
        int k = stw.term == T_RECAP ? stw.cur : c;
        screen_list(stw.term == T_RECAP ? "STORY SO FAR" : "BRIEFING", n);
        if (stw.term == T_RECAP && !stw.page) {
            for (int i = stw.top; i < n && i < stw.top + ROWS; i++) {
                p = num(b, i + 1);
                p = d_cat(p, " ");
                d_cat(p, ms_text(ms_chap(i)->title));
                line(24, 34 + (i - stw.top) * 10, i == stw.cur, b);
            }
            help("A: READ   B: BACK");
            break;
        }
        if (k < 0 || k >= ms_nchap()) {
            d_text(14, 40, "NO CAMPAIGN DATA IN THIS ROM", INK);
            help("B: BACK");
            break;
        }
        const Chapter *ch = ms_chap(k);
        d_text(14, 32, ms_text(ch->title), HI);
        const char *t = ms_text(ch->brief);
        int row = 0;
        char l[40];
        for (const char *s = t; *s && row < 2; row++) {
            int w = 0;
            while (*s && *s != '\n' && w < 38)
                l[w++] = *s++;
            l[w] = 0;
            if (*s == '\n')
                s++;
            d_text(14, 44 + row * 9, l, INK);
        }
        d_text(14, 66, "ACTS", HELP);
        act_dots(k, 50, 67);
        int shown = 0;
        for (int m = ch->mis0; m < ch->mis0 + ch->nmis && shown < 5; m++) {
            const MisDef *d = ms_def(m);
            if (!d || d->kind != MK_ACT)
                continue;
            int done = d->act >= 1 && d->act <= 8 && (cp_prog.acts[k] >> (d->act - 1) & 1);
            p = num(b, d->act);
            p = d_cat(p, " ");
            d_cat(p, ms_text(d->title));
            d_text(14, 78 + shown * 9, b, done ? GOOD : INK);
            if (done)
                d_text(190, 78 + shown * 9, "DONE", GOOD);
            shown++;
        }
        help(stw.term == T_RECAP ? "B: BACK" : "B: BACK  TALK TO ROOK FOR MORE");
        break;
    }
    case T_CONTRACT:
        screen_list("CONTRACTS", n);
        if (!n)
            d_text(14, 40, "NO CONTRACTS ON THIS MAP", INK);
        for (int i = stw.top; i < n && i < stw.top + ROWS; i++) {
            const MisDef *d = ms_def(contract_at(c, i) - 1);
            p = d_cat(b, ms_text(d->title));
            line(24, 34 + (i - stw.top) * 10, i == stw.cur, b);
            p = num(b, d->pay);
            d_cat(p, " CR");
            d_text(180, 34 + (i - stw.top) * 10, b, GOOD);
        }
        if (c >= 0) {
            p = d_cat(b, "DONE ");
            p = num(p, cp_prog.contracts[c]);
            d_text(150, 18, b, HELP);
        }
        help("A: TAKE   B: BACK");
        break;
    case T_TRAVEL:
    case T_MAP:
        screen_list(stw.term == T_MAP ? "HOLO MAP" : "TRAVEL", n);
        if (!n) {
            d_text(14, 40, "NO CAMPAIGN DATA IN THIS ROM", INK);
            help("B: BACK");
            break;
        }
        for (int i = stw.top; i < n && i < stw.top + ROWS; i++) {
            p = num(b, i + 1);
            p = d_cat(p, " ");
            d_cat(p, ms_text(ms_chap(i)->title));
            if (stw.term == T_MAP && p - b > 21)
                b[21] = 0;                               /* (the map takes the right half) */
            line(24, 34 + (i - stw.top) * 10, i == stw.cur, b);
            if (stw.term == T_TRAVEL)
                act_dots(i, 170, 36 + (i - stw.top) * 10);
        }
        if (stw.term == T_MAP) {
            screen_map(stw.cur);
            p = d_cat(b, "ACTS ");
            p = num(p, popc(cp_prog.acts[stw.cur]));
            p = d_cat(p, " MEDALS ");
            num(p, popc(cp_prog.medals[stw.cur]));
            d_text(130, 102, b, HELP);
        }
        help(cp_active() ? "A: TRAVEL   B: BACK" : "START THE CAMPAIGN TO TRAVEL");
        break;
    case T_SHOP:
        screen_list("UPGRADES", n);
        for (int i = 0; i < 5; i++) {
            int pr = sg_price(i);
            line(24, 36 + i * 11, i == stw.cur, shop_name[i]);
            if (pr > 0) {
                p = num(b, pr);
                d_cat(p, " CR");
                d_text(150, 36 + i * 11, stw.confirm == i + 1 ? "A AGAIN" : b, stw.confirm == i + 1 ? HI : sg_credits() >= pr ? GOOD : DIM);
            } else
                d_text(150, 36 + i * 11, i == 3 ? "FULL" : "BEST", HELP);
        }
        help("A: BUY   B: BACK");
        break;
    case T_PAINT: {
        const char *const *nm;
        int np = sg_paints(&nm);
        screen_list("PAINT RACK", n);
        for (int i = stw.top; i < np && i < stw.top + ROWS; i++) {
            line(24, 34 + (i - stw.top) * 10, i == stw.cur, nm[i]);
            if (!sg_paint_unlocked(i))
                d_text(170, 34 + (i - stw.top) * 10, "LOCKED", DIM);
        }
        help("A: PAINT IT ON   B: BACK");
        break;
    }
    case T_TROPHY: {
        static const char *const pg[3] = {"MEDALS", "BEST TIMES", "CITY TROPHIES"};
        screen_list(pg[stw.page], 0);
        d_text(150, 18, "< >", HELP);
        if (stw.page == 0) {
            int tot = 0;
            for (int i = 0; i < ms_nchap() && i < 11; i++) {
                int x = 14 + (i >= 6) * 110, y = 34 + (i % 6) * 10;
                tot += popc(cp_prog.medals[i]);
                p = num(b, i + 1);
                d_text(x, y, b, i <= cp_prog.chap_unlocked ? INK : DIM);
                for (int k = 0; k < 8; k++)
                    d_fill(x + 24 + k * 8, y + 1, 6, 6, cp_prog.medals[i] >> k & 1 ? HI : DIM);
            }
            SgProgress sp;
            sg_get_progress(&sp);
            p = d_cat(b, "CITY MEDALS ");
            p = num(p, tot);
            p = d_cat(p, "   FOX MEDALS ");
            p = num(p, popc(sp.medals));
            d_cat(p, "/12");
            d_text(14, 100, b, TITLE);
        } else if (stw.page == 1) {
            for (int i = 0; i < ms_nchap() && i < 11; i++) {
                int t = cp_prog.best[i * 5], x = 14 + (i >= 6) * 110, y = 34 + (i % 6) * 10;
                p = num(b, i + 1);
                p = d_cat(p, " ");
                d_cat(p, ms_text(ms_chap(i)->title));
                b[9] = 0;
                d_text(x, y, b, t ? INK : DIM);
                if (t)
                    d_time(b, t / 10), d_text(x + 60, y, b, GOOD);
                else
                    d_text(x + 60, y, "--:--", DIM);
            }
        } else {
            d_text(14, 34, "THE CITY KEEPS ITS OWN SCORE.", INK);
            for (int i = 0; i < 6; i++) {
                p = d_cat(b, "TROPHY ");
                p = num(p, i + 1);
                p = d_cat(p, ": ");
                num(p, PB_TROPHIES[i]);
                d_text(14, 48 + i * 10, b, INK);
            }
        }
        help("LEFT RIGHT: PAGE   B: BACK");
        break;
    }
    case T_COMMS:
        screen_list("COMMS", n);
        for (int i = 0; i < 5; i++)
            line(24, 36 + i * 11, i == stw.cur, comms_name[i]);
        d_text(14, 96, cp_active() ? "SAVING KEEPS THE CAMPAIGN SAFE" : "START THE CAMPAIGN TO SAVE", HELP);
        help("A: PICK   B: BACK");
        break;
    case T_MSGS:
    case T_LOG: {
        int f = stw.term == T_MSGS ? E_MSG : E_LOG;
        screen_list(stw.term == T_MSGS ? "MESSAGES" : "KESTREL'S LOG", n);
        if (stw.page) {
            int i = nth_ent(f, stw.cur);
            if (i >= 0) {
                d_text(14, 34, crew_name[ent(i)->crew], HI);
                const char *t = st_text(node(ent(i)->node)->text);
                int row = 0;
                char l[40];
                for (const char *s = t; *s && row < 4; row++) {
                    int w = 0;
                    while (*s && *s != '\n' && w < 38)
                        l[w++] = *s++;
                    l[w] = 0;
                    if (*s == '\n')
                        s++;
                    d_text(14, 48 + row * 10, l, INK);
                }
            }
            help("B: BACK");
            break;
        }
        if (!n)
            d_text(14, 40, "NOTHING YET", INK);
        for (int i = stw.top; i < n && i < stw.top + ROWS; i++) {
            int e = nth_ent(f, i);
            p = d_cat(b, crew_name[ent(e)->crew]);
            p = d_cat(p, ": ");
            const char *t = st_text(node(ent(e)->node)->text);
            for (int k = 0; t[k] && t[k] != '\n' && p - b < 26; k++)
                *p++ = t[k];
            *p = 0;
            line(24, 34 + (i - stw.top) * 10, i == stw.cur, b);
        }
        if (stw.term == T_LOG)
            d_text(14, 108, cp_ace() ? "ACE MODE: ON" : "ACE MODE: OFF (WIN THE FINALE)", cp_ace() ? GOOD : HELP);
        help("A: READ   B: BACK");
        break;
    }
    }
}

/* the dialogue: the speaker's name and two lines over the lower picture */
static void talk_panel(void)
{
    const StNode *nd = node(stw.dnode);
    panel(6, 94, 228, 40);
    d_text(12, 98, crew_name[stw.dcrew], HI);
    const char *t = st_text(nd->text);
    char l[40];
    for (int row = 0; *t && row < 2; row++) {
        int w = 0;
        while (*t && *t != '\n' && w < 37)
            l[w++] = *t++;
        l[w] = 0;
        if (*t == '\n')
            t++;
        d_text(12, 108 + row * 10, l, INK);
    }
    d_text(214, 124, nd->next ? ">>" : "OK", HELP);
}

void st_hud(void)
{
    if (s2f.paused)
        return;
    const StRoom *rm = st_room(stw.room);
    st_draw_labels();
    d_text(8, 6, st_text(rm->title), TITLE);
    if (!stw.term && !stw.dent) {
        char b[24], *p = d_cat(b, "CR ");
        p = num(p, sg_credits());
        d_text(234 - TEXT_W * (int)(p - b), 6, b, HELP);
        if (stw.near) {
            int k = (stw.near & 31) - 1;
            char t[32];
            if (stw.near >> 5 == U_TALK)
                d_cat(d_cat(t, "A: TALK TO "), crew_name[st_crews(rm)[k].crew]);
            else
                d_cat(d_cat(t, "A: "), st_text(st_uses(rm)[k].label));
            d_fill(4, 126, TEXT_W * 32 + 4, 11, PANEL);
            d_text(8, 128, t, HI);
        } else {
            d_text(8, 142, "L: MENU   B: BACK   R: RUN", HELP);
        }
    }
    if (stw.dent)
        talk_panel();
    else if (stw.term)
        screen();
    if (news_up()) {
        int w = 0;
        while (stw.msg[w])
            w++;
        d_fill(4, 142, w * TEXT_W + 8, 12, PANEL);
        d_text(8, 144, stw.msg, INK);
    }
}

/* ---- the debug mailbox (stage2.h 32..47): 32 enter, 33 look (0 room 1 x 2 z 3 node 4 term | cur << 8 5 dialogue entry 6 near 7 same
   8 sprites hidden 9 the picture's hash 10 dialogue node 11 camera x 12 y 13 z 14 heard 0 15 heard 1 16 chat 17 the keep's size of the state),
   34 go to room arg (from the hub), 35 x := arg, 36 z := arg, 37 talk to crew arg, 38 clear what is heard, 39 open terminal arg,
   40 blob numbers (nent | nnode << 8 | nroom << 16), 41 an entry's id and node (arg = index), 42 raise the talk of entry arg,
   43 the cond arg as the campaign holds it ---- */
int st_dbg(int cmd, int arg)
{
    switch (cmd) {
    case 32:
        return st_enter() ? stw.room : -1;
    case 33:
        switch (arg) {
        case 0: return stw.room;
        case 1: return stw.x;
        case 2: return stw.z;
        case 3: return stw.node;
        case 4: return stw.term | stw.cur << 8 | stw.page << 16;
        case 5: return stw.dent;
        case 6: return stw.near;
        case 7: return stw.same;
        case 8: return stw.hid;
        case 9: return (int)stw.sig;
        case 10: return stw.dnode;
        case 11: return stw.bx;
        case 12: return stw.by;
        case 13: return stw.bz;
        case 14: return (int)stw.heard[0];
        case 15: return (int)stw.heard[1];
        case 16: return stw.chat;
        case 17: return sizeof(StState);
        case 18: return stw.cd | stw.dwell << 8;
        case 19: return stw.sway | stw.idle << 8;
        }
        return -1;
    case 34:
        if (!st_ok() || arg < 0 || arg >= R_N)
            return -1;
        go_room(arg, R_HUB);
        return stw.room;
    case 35: stw.x = arg; return stw.x;
    case 36: stw.z = arg; return stw.z;
    case 37: start_talk(arg); return stw.dent;
    case 38: stw.heard[0] = stw.heard[1] = 0; stw.chat = 0; return 0;
    case 39: term_enter(arg); return stw.term;
    case 40: return st_ok() ? hd()->nent | hd()->nnode << 8 | hd()->nroom << 16 : -1;
    case 41: return arg >= 0 && arg < hd()->nent ? ent(arg)->id | ent(arg)->node << 16 : -1;
    case 42: return pick_entry(arg);
    case 43: return cond_ok(arg);
    }
    return -1;
}
