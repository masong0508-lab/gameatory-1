/* host-side harness for the fuzz: flat arena at 0x02000000 (256 KiB) + code window at 0x08000000 (4 KiB) */
#include "interp.h"


static unsigned char arena[0x40000]; static unsigned char code[0x1000];
int fault; unsigned int last_wr[64][3]; int nwr;
static unsigned char* loc(u32 ea,u32 size){
  if(ea-0x02000000u<=0x40000u-size) return arena+(ea-0x02000000u);
  if(ea-0x08000000u<=0x1000u-size) return code+(ea-0x08000000u);
  return 0;
}
u32 ip_rd(u32 ea,u32 size){ unsigned char*p=loc(ea,size); if(!p){ fault=1; return 0; } u32 v=0; for(u32 k=0;k<size;k++) v|=(u32)p[k]<<(8*k); return v; }
void ip_wr(u32 ea,u32 size,u32 v){ unsigned char*p=loc(ea,size); if(!p||ea>=0x08000000u){ fault=1; return; } for(u32 k=0;k<size;k++) p[k]=v>>(8*k); if(nwr<64){ last_wr[nwr][0]=ea; last_wr[nwr][1]=size; last_wr[nwr][2]=v; nwr++; } }
u32 ip_map(u32 v){ return v; }
u32 ip_res_push(u32 sp,u32 lr){ return lr; }
u32 ip_lookup(u32 t){ return 0; }
void ip_call(IS*s,u32 h){}
void ip_swi(IS*s,u32 n){}
u32 ip_is_host_iw(u32 a){ return 0; }
u32 ip_arm_code(u32 a){ return 0; }
unsigned char* t_arena(void){ return arena; } unsigned char* t_code(void){ return code; }
int t_step(IS*s){ fault=0; nwr=0; u32 u=interp_step(s); return u?2:(fault?1:0); }
int t_nwr(void){ return nwr; } unsigned int* t_wr(void){ return &last_wr[0][0]; }

extern unsigned int ip_unal; unsigned int t_unal(void){ unsigned int v=ip_unal; ip_unal=0; return v; }
