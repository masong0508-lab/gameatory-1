/* Execute the production assignment state machine. Physical beacon contact is
   exercised separately in mGBA; these cases cover gating, rewards and receipts. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../src/spacewalk.c"

Prog cp_prog;
S2Frame s2f;
u8 sw_pack;
int sg_state;
u32 frame_count;
static int mission_state, other_job, wallet, events, checks;

int cp_active(void) { return cp_prog.flags & CPF_ON; }
int ms_state(void) { return mission_state; }
int sg_job_active(void) { return other_job; }
int sg_credit(int amount) { return wallet += amount; }
void s2_ev(int event, int a, int b) { (void)event; (void)a; (void)b; events++; }

#define CHECK(test, label) do { checks++; if (!(test)) { fprintf(stderr, "FAIL: %s\n", label); exit(1); } } while (0)

static void reset(void)
{
    memset(&cp_prog, 0, sizeof cp_prog);
    memset(&s2f, 0, sizeof s2f);
    cp_prog.flags = CPF_ON;
    s2f.docked = 1;
    sw_pack = 1;
    sg_state = SG_DOCKED;
    mission_state = MS_IDLE;
    other_job = wallet = events = 0;
    sw_reset();
}

static void policy(void)
{
    reset();
    CHECK(sw_job_take(0) == SWJ_BAD && sw_job_take(4) == SWJ_BAD, "invalid assignment rejected");
    cp_prog.flags = 0;
    CHECK(sw_job_take(1) == SWJ_CAMPAIGN, "campaign required");
    cp_prog.flags = CPF_ON;
    sw_pack = 0;
    CHECK(sw_job_take(1) == SWJ_PACK, "jet pack required");
    sw_pack = 1;
    mission_state = MS_RUN;
    CHECK(sw_job_take(1) == SWJ_BUSY, "active campaign mission preserved");
    mission_state = MS_PAUSED;
    CHECK(sw_job_take(1) == SWJ_BUSY, "paused mission preserved");
    mission_state = MS_IDLE;
    other_job = 1;
    CHECK(sw_job_take(1) == SWJ_BUSY, "active flight job preserved");
    other_job = 0;
    s2f.docked = 0;
    CHECK(sw_job_take(1) == SWJ_DOCK, "cannot accept from outside station");
    s2f.docked = 1;
    sg_state = SG_LAUNCH;
    CHECK(sw_job_take(1) == SWJ_DOCK, "cannot accept during launch transition");
    sg_state = SG_DOCKED;
    CHECK(sw_job_take(1) == SWJ_READY, "eligible player accepts");
    CHECK(sw_job_take(2) == SWJ_BUSY && sw_obj(0, 0) == 1, "new selection cannot erase live assignment");
    sw_job_cancel();
    CHECK(!sw_obj(0, 0) && !wallet && !cp_prog.spare[CP_SPARE_EVA], "cancellation awards nothing");
}

static void rewards(void)
{
    reset();
    for (int i = 1; i <= 8; i++) cp_prog.spare[i] = 0x91 + i;
    CHECK(sw_job_pay(-1) == 0 && sw_job_pay(4) == 0, "invalid reward query is safe");
    CHECK(sw_job_take(1) == SWJ_READY, "first patrol accepted");
    obj_reached();
    CHECK(wallet == 150 && !sw_obj(0, 0) && sw_job_done(1), "first patrol pays and records completion");
    obj_reached(); obj_finish(); obj_boarded();
    CHECK(wallet == 150, "repeated contact cannot duplicate reward");
    CHECK(sw_job_pay(1) == 50 && sw_job_pay(2) == 300, "only cleared assignment changes replay reward");
    CHECK(sw_job_take(1) == SWJ_READY, "patrol can be replayed");
    obj_reached();
    CHECK(wallet == 200, "replay remains useful but cannot farm first-clear pay");
    CHECK(sw_job_take(2) == SWJ_READY, "moon survey accepted");
    obj_reached();
    CHECK(wallet == 500 && sw_job_done(2) && sw_job_pay(2) == 75, "moon survey first-clear and replay pay");
    for (int i = 1; i <= 8; i++) CHECK(cp_prog.spare[i] == 0x91 + i, "crew dialogue receipts preserved");
    prog_seal(&cp_prog);
    CHECK(prog_ok(&cp_prog), "receipt uses existing valid campaign layout");
    Prog stored = cp_prog;
    reset();
    cp_prog = stored;
    CHECK(sw_job_done(1) && sw_job_done(2) && sw_job_pay(1) == 50, "saved image restores first-clear receipts");
}

static void relay(void)
{
    reset();
    CHECK(sw_job_take(3) == SWJ_READY, "relay accepted");
    obj_boarded();
    CHECK(!wallet && sw_obj(0, 0) == 3, "boarding early does not complete relay");
    obj_reached();
    CHECK(obj_s == 1 && !wallet, "first beacon is partial progress");
    obj_boarded();
    CHECK(!wallet && obj_s == 1, "one beacon is insufficient");
    obj_reached();
    CHECK(obj_s == 2 && !wallet, "both beacons still require safe reboarding");
    obj_reached();
    CHECK(obj_s == 2 && !wallet, "repeated second contact does not skip boarding");
    obj_boarded();
    CHECK(wallet == 500 && sw_job_done(3) && !sw_obj(0, 0), "safe reboarding pays relay once");
    obj_boarded();
    CHECK(wallet == 500 && sw_job_pay(3) == 100, "no duplicate board reward");
    /* The walk can also end in a fall to the city; the Arwing is then boarded on the street (merge.c board()). */
    CHECK(sw_job_take(3) == SWJ_READY, "relay accepted again");
    sw_job_boarded();
    CHECK(wallet == 500 && sw_obj(0, 0) == 3 && obj_s == 0, "boarding on the street early does not complete relay");
    obj_reached();
    sw_job_boarded();
    CHECK(wallet == 500 && obj_s == 1, "one beacon and a street boarding is insufficient");
    obj_reached();
    swk.on = 0;                        /* (he fell out of space: the walk is over, the relay is not) */
    CHECK(wallet == 500 && sw_obj(0, 0) == 3 && obj_s == 2, "a fall keeps the finished relay waiting for the Arwing");
    sw_job_boarded();
    CHECK(wallet == 600 && !sw_obj(0, 0) && sw_job_done(3), "boarding on the street after the fall pays the relay");
    sw_job_boarded();
    CHECK(wallet == 600, "no duplicate street-boarding reward");
}

static void interruption(void)
{
    reset();
    CHECK(sw_job_take(3) == SWJ_READY, "relay accepted before interruption");
    obj_reached();
    sw_reset();
    CHECK(!sw_obj(0, 0) && !wallet && !sw_job_done(3), "death or map reset clears unfinished work without payment");
    CHECK(sw_job_take(3) == SWJ_READY && obj_s == 0, "retry starts at first beacon");
    obj_reached(); sw_job_cancel(); obj_boarded();
    CHECK(!wallet && !sw_job_done(3), "cancelled partial progress cannot be cashed in");
    CHECK(sw_job_take(1) == SWJ_READY, "patrol accepted before campaign stop");
    cp_prog.spare[CP_SPARE_EVA] = 1;
    cp_prog.flags &= ~CPF_ON;
    obj_reached();
    CHECK(!wallet && !sw_obj(0, 0) && cp_prog.spare[CP_SPARE_EVA] == 1,
          "stopping campaign cannot pay or erase an existing first-clear record");
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    if (!strcmp(argv[1], "policy")) policy();
    else if (!strcmp(argv[1], "rewards")) rewards();
    else if (!strcmp(argv[1], "relay")) relay();
    else if (!strcmp(argv[1], "interruption")) interruption();
    else return 2;
    printf("PASS %s: %d production-state checks\n", argv[1], checks);
    return 0;
}
