#include <stdio.h>
#include <stdlib.h>
#include "../src/ragdoll_ps1.c"
#include "../src/scenario.inc"
int main(void){ sc_reset(); for(int f=0;f<SC_FRAMES;f++){ sc_script(); sc_step_dolls(); for(int i=0;i<NACT;i++) if(act[i].active){ rp_doll*d=&act[i].d; fx vm=0; for(int j=0;j<RP_P;j++){fx m=iabs(d->vel[j].x)+iabs(d->vel[j].y)+iabs(d->vel[j].z); if(m>vm)vm=m;} if(vm>45*RP_ONE) printf("tick %d doll %d vmax %.1f state %d lod %d dtf %d nsub %d contacts %d air %d\n",f,i,vm/1048576.0,d->state,d->lod,d->dtf,d->nsub,d->contacts,d->air);} } return 0; }
