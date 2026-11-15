/* PC check: the same scenario against (a) the reference solver (-DRP_REF) or (b) the port at RP_LEVEL n; prints a trace.
   gcc -O2 -DRP_REF  -Iref tools/host_test.c -o host_ref ;  gcc -O2 -DRP_LEVEL=1 -Isrc tools/host_test.c -o host_l1 */
#include <stdio.h>
#include <stdlib.h>
#ifdef RP_REF
#include "../ref/ragdoll_ps1_ref.c"
#else
#include "../src/ragdoll_ps1.c"
#endif
#include "../src/scenario.inc"
int main(int argc, char **argv)
{
    int nf = argc > 1 ? atoi(argv[1]) : SC_FRAMES;
    sc_reset();
    long steps = 0;
    for (int f = 0; f < nf; f++) {
        sc_script(); sc_step_dolls();
        if (f % 10 == 9) {
            printf("F %d car %d %d |", f + 1, car.pos.y, car.pos.z);
            for (int i = 0; i < NACT; i++) if (act[i].active) printf(" %d:%08x(%d,%d,%d,s%d)", i, rp_hash(&act[i].d), act[i].d.pos[0].x, act[i].d.pos[0].y, act[i].d.pos[0].z, act[i].d.state);
            printf("\n");
        }
    }
    for (int i = 0; i < NACT; i++) steps += act[i].d.steps;
    printf("STEPS %ld\n", steps);
    { unsigned h = 0; for (int i = 0; i < NACT; i++) h = h * 31 + rp_hash(&act[i].d); printf("COMBINED %08x\n", h); }
    return 0;
}
