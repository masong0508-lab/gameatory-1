/* Exact Q14 camera transforms using the PS1 GTE MAC registers.
 * This is a native-software renderer math optimization, not a GPU
 * geometry list. Only enable where this renderer owns COP2 (sf3 off).
 * All values outside signed 16-bit input range take the original
 * low-32-bit dot-product path; no truncation or IR saturation.
 */
#ifndef SF_GTECAM_H
#define SF_GTECAM_H
#include "fx.h"
static inline s32 sf_gte_dot(V3 a,V3 b){
    return (s32)((u32)a.x*(u32)b.x+(u32)a.y*(u32)b.y+(u32)a.z*(u32)b.z)>>14;
}
static inline V3 sf_gte_cpu(const M3*m,V3 d){
    return v3(sf_gte_dot(m->r,d),sf_gte_dot(m->u,d),sf_gte_dot(m->f,d));
}
static inline u32 sf_gte_range(const M3*m,V3 d){
    V3 r=m->r,u=m->u,f=m->f;
    return ((u32)d.x+32768u)|((u32)d.y+32768u)|((u32)d.z+32768u)|
           ((u32)r.x+32768u)|((u32)r.y+32768u)|((u32)r.z+32768u)|
           ((u32)u.x+32768u)|((u32)u.y+32768u)|((u32)u.z+32768u)|
           ((u32)f.x+32768u)|((u32)f.y+32768u)|((u32)f.z+32768u);
}
#ifdef __mips__
#define SFC_CTC(n,v) do{register u32 t __asm__("$8")=(u32)(v); __asm__ volatile(".word 0x48C80000|(" #n "<<11)"::"r"(t));}while(0)
#define SFC_MTC(n,v) __asm__ volatile("mtc2 %0,$" #n::"r"((u32)(v)))
#define SFC_MFC(n) ({u32 r; __asm__ volatile("mfc2 %0,$" #n "\n nop":"=r"(r));r;})
static inline u32 sf_gte_pair(s32 a,s32 b){return ((u32)b<<16)|((u32)a&65535u);}
static inline V3 sf_gte_project(const M3*m,V3 d){
    V3 r=m->r,u=m->u,f=m->f;
    if(sf_gte_range(m,d)>=65536u) return sf_gte_cpu(m,d);
    SFC_CTC(0,sf_gte_pair(r.x,r.y)); SFC_CTC(1,sf_gte_pair(r.z,u.x));
    SFC_CTC(2,sf_gte_pair(u.y,u.z)); SFC_CTC(3,sf_gte_pair(f.x,f.y));
    SFC_CTC(4,(u32)f.z&65535u);
    SFC_MTC(0,sf_gte_pair(d.x,d.y)); SFC_MTC(1,d.z);
    /* MVMVA rotation*V0, no translation, sf=0. Read MAC1..3, not IR. */
    __asm__ volatile("nop\n nop\n .word 0x4a406012");
    return v3((s32)SFC_MFC(25)>>14,(s32)SFC_MFC(26)>>14,(s32)SFC_MFC(27)>>14);
}
#undef SFC_CTC
#undef SFC_MTC
#undef SFC_MFC
#else
static inline V3 sf_gte_project(const M3*m,V3 d){return sf_gte_cpu(m,d);}
#endif
#endif
