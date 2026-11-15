#include "ps1.h"
void main(void){ gpu_init(); timers_init();
  for(int rep=0;rep<3;rep++){
  volatile u32 acc=0; u32 t0=TICKS8(), h0=HLINES();
  for(volatile int i=0;i<20000;i++){ acc+=i; }
  u32 t1=TICKS8(), h1=HLINES(); dbg("CAL loop20000 ticks8 "); ddec((t1-t0)&0xffff); dbg("hlines "); ddec((h1-h0)&0xffff); dbg("\n");
  u32 a=12345, b=7; t0=TICKS8(); h0=HLINES();
  for(int i=0;i<2000;i++){ a=a/b+i; b=(a&15)+3; }
  t1=TICKS8(); h1=HLINES(); dbg("CAL 2000 divs ticks8 "); ddec((t1-t0)&0xffff); dbg("hlines "); ddec((h1-h0)&0xffff); dbg("\n"); }
  for(;;){}
}
