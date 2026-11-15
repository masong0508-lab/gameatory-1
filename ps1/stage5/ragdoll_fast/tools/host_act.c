/* PC: per 10 ticks, per doll: state, substeps last tick, contacts, pelvis speed (m/s). Used to see where the cost sits. */
#include <stdio.h>
#include <stdlib.h>
#include "../src/ragdoll_ps1.c"
#include "../src/scenario.inc"
int main(void){ sc_reset(); for(int f=0;f<SC_FRAMES;f++){ sc_script(); sc_step_dolls(); if(f%10==9&&f>100&&f<420){ printf("%3d",f+1); for(int i=0;i<NACT;i++){ if(!act[i].active){printf(" |   -        ");continue;} rp_doll*d=&act[i].d; fx v=iabs(d->vel[0].x)+iabs(d->vel[0].y)+iabs(d->vel[0].z); printf(" | s%d n%d c%2d v%5.1f",d->state,d->nsub,d->contacts,v/1048576.0);} printf("\n"); } } return 0; }
