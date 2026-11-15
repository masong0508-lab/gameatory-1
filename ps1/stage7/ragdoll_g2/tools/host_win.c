#include <stdio.h>
#include "../src/ragdoll_ps1.c"
#include "../src/scenario.inc"
int main(){ sc_reset(); long tot[4]={0},cnt[4]={0}; for(int f=0;f<SC_FRAMES;f++){ sc_script(); sc_step_dolls(); if(f>=170&&f<300){ if(f%12==0){ printf("t%3d:",f); for(int i=0;i<NACT;i++){ rp_doll*d=&act[i].d; if(!act[i].active){printf(" --");continue;} fx vm=0; for(int j=0;j<RP_P;j++){fx m=iabs(d->vel[j].x)+iabs(d->vel[j].y)+iabs(d->vel[j].z); if(m>vm)vm=m;} printf(" [s%d l%d n%d c%d v%.1f]",d->state,d->lod,d->nsub,d->contacts,vm/1048576.0);} printf("\n"); }
 for(int i=0;i<NACT;i++) if(act[i].active&&act[i].d.state!=RP_ASLEEP){ int l=act[i].d.lod; tot[l]+=act[i].d.nsub; cnt[l]++; } } }
 for(int l=0;l<4;l++) printf("lod%d: doll-ticks %ld substeps %ld\n",l,cnt[l],tot[l]); }
