/* PC check of a solver configuration on the scenario: stretch of the bones, ground/box/car penetration, speeds, sleep, where the bodies end.
   gcc -O2 -DRP_LEVEL=2 -DRP_ITER=2 ... -Isrc tools/host_quality.c   (or -DRP_REF -Iref for the reference) */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#ifdef RP_REF
#include "../ref/ragdoll_ps1_ref.c"
#else
#include "../src/ragdoll_ps1.c"
#endif
#include "../src/scenario.inc"
static const int ba[RP_BONES][2] = {{0,1},{1,2},{2,3},{2,4},{2,5},{0,10},{0,11},{4,6},{6,8},{5,7},{7,9},{10,12},{12,14},{14,16},{11,13},{13,15},{15,17}};
int main(int argc, char **argv)
{
    sc_reset();
    double maxstretch = 0, maxpen = 0, maxspeed = 0, maxcar = 0; int inside_box = 0, tunnel = 0; long steps = 0; double e0 = 0;
    for (int f = 0; f < SC_FRAMES; f++) {
        sc_script(); sc_step_dolls();
        for (int i = 0; i < NACT; i++) if (act[i].active) {
            rp_doll *d = &act[i].d;
            for (int b = 0; b < RP_BONES; b++) {
                rp_v3 a = d->pos[ba[b][0]], c = d->pos[ba[b][1]];
                double l = sqrt(pow((double)a.x - c.x, 2) + pow((double)a.y - c.y, 2) + pow((double)a.z - c.z, 2));
                double r = (double)rest_bone[b]; if (fabs(l - r) / r > maxstretch) maxstretch = fabs(l - r) / r;
            }
            for (int j = 0; j < RP_P; j++) {
                rp_v3 p = d->pos[j]; fx h; rp_v3 n; int m;
                sc_floor(0, p.x, p.z, p.y, &h, &n, &m);
                double pen = ((double)h + radius[j] - p.y) / 1048576.0 * 100; if (pen > maxpen) maxpen = pen;   /* cm below the floor-touching height */
                for (int k = 0; k < 2; k++) { const rp_box *x = &sc_box[k];
                    if (p.x > x->lo.x + radius[j] && p.x < x->hi.x - radius[j] && p.y > x->lo.y + radius[j] && p.y < x->hi.y - radius[j] && p.z > x->lo.z + radius[j] && p.z < x->hi.z - radius[j]) inside_box++; }
                double sp = (fabs((double)d->vel[j].x) + fabs((double)d->vel[j].y) + fabs((double)d->vel[j].z)) / 1048576.0; if (sp > maxspeed) maxspeed = sp;
            }
        }
    }
    printf("stretch_max %.4f  below_floor_max_cm %.1f  inside_box_samples %d  speed_max_L1 %.1f m/s  substeps %ld\n", maxstretch, maxpen, inside_box, maxspeed, ({ long s = 0; for (int i = 0; i < NACT; i++) s += act[i].d.steps; s; }));
    for (int i = 0; i < NACT; i++) printf("  doll %d: end pelvis x %.2f y %.2f z %.2f  state %d\n", i, act[i].d.pos[0].x / 1048576.0, act[i].d.pos[0].y / 1048576.0, act[i].d.pos[0].z / 1048576.0, act[i].d.state);
    return 0;
}
