/* bench.c: the solver + scenario with no hardware, for instruction counting on a MIPS-I model (tools/mipsprof.py).
   mark() is called at the start of each frame, so the harness can bin instructions per frame / per function. */
#define PS1 1
typedef unsigned char u8;
typedef unsigned int u32;
void *memset(void *d,int c,unsigned n){ char*p=d; u32 w=(u8)c; w|=w<<8; w|=w<<16;
  if(!((u32)p&3)){ u32*q=(u32*)p; while(n>=16){ q[0]=w;q[1]=w;q[2]=w;q[3]=w; q+=4; n-=16; } while(n>=4){ *q++=w; n-=4; } p=(char*)q; }
  while(n--) *p++=c; return d; }
void *memcpy(void *d,const void*s,unsigned n){ char*p=d; const char*q=s;
  if(!(((u32)p|(u32)q)&3)){ u32*a=(u32*)p; const u32*b=(const u32*)q; while(n>=16){ u32 x0=b[0],x1=b[1],x2=b[2],x3=b[3]; a[0]=x0;a[1]=x1;a[2]=x2;a[3]=x3; a+=4;b+=4;n-=16; } while(n>=4){ *a++=*b++; n-=4; } p=(char*)a; q=(const char*)b; }
  while(n--) *p++=*q++; return d; }
#include "ragdoll_ps1.c"
#include "rt.inc"
#include "scenario.inc"
volatile int bench_frame, bench_sum;
void __attribute__((noinline)) mark(void) { __asm__ volatile("" ::: "memory"); }
int main(void)
{
    sc_reset();
    for (bench_frame = 0; bench_frame < SC_FRAMES; bench_frame++) { mark(); sc_script(); sc_step_dolls(); }
    mark();
    bench_sum = rp_hash(&act[0].d) ^ rp_hash(&act[1].d);
    return 0;
}
