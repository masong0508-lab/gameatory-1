/* unit check of distance_c's GTE/linear form against the exact form: residual violation after one application */
#include <stdio.h>
#include <math.h>
#include <stdlib.h>
#include "../src/ragdoll_ps1.c"
static double L(rp_v3 a, rp_v3 b){ double x=a.x-b.x,y=a.y-b.y,z=a.z-b.z; return sqrt(x*x+y*y+z*z)/1048576.0; }
int main(void){ init_tables(); srand(5);
  for(int ci=0;ci<3;ci++){ int n=ci==0?RP_BONES:ci==1?NBRACE:NRANGE; double worst=0,sum=0; int cnt=0;
   for(int i=0;i<n;i++){ Cons*c=ci==0?&c_bone[i]:ci==1?&c_brace[i]:&c_range[i]; int a=ci==0?bone_ab[i][0]:ci==1?braces[i][0]:ranges[i].a, b=ci==0?bone_ab[i][1]:ci==1?braces[i][1]:ranges[i].b;
    for(int t=0;t<2000;t++){ double rest=(c->lo+c->hi)/2.0/1048576.0; double sc=0.5+ (rand()%1500)/1000.0; /* 0.5..2.0 x */
      rp_v3 p[RP_P]; memset(p,0,sizeof p); double ux=rand()%2001-1000,uy=rand()%2001-1000,uz=rand()%2001-1000; double un=sqrt(ux*ux+uy*uy+uz*uz)+1;
      double len=rest*sc; p[a]=V(0,0,0); p[b]=V((fx)(ux/un*len*1048576),(fx)(uy/un*len*1048576),(fx)(uz/un*len*1048576));
      double l0=L(p[a],p[b]); double lo=c->lo/1048576.0, hi=c->hi/1048576.0; if(l0>=lo&&l0<=hi) continue; double tgt=l0<lo?lo:hi;
      distance_c(p,a,b,c); double l1=L(p[a],p[b]); double e0=fabs(l0-tgt)/tgt,e1=fabs(l1-tgt)/tgt; if(e0>0.01){ sum+=e1/e0; cnt++; if(e1/e0>worst) worst=e1/e0; } } }
   printf("%s: avg residual ratio %.3f worst %.3f (n=%d)\n",ci==0?"bones":ci==1?"braces":"ranges",sum/cnt,worst,cnt); }
  return 0; }
