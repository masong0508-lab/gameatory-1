/* gte_rp.h: the few GTE operations the ragdoll solver uses, with three back ends.
   hardware (PS1 build): mtc2/ctc2 + COP2 commands.  RP_GTE_SIM (PC and the MIPS instruction-count model, which has no COP2):
   a C model of exactly the same operations, bit for bit on the used subset (16 bit vector registers, 16 bit rotation matrix,
   32 bit MAC readout), so the PC trace, the model and the console agree.
   Used: SQR (sf=0): MAC1..3 = IR1..3 squared (sum of squares of a 3-vector in two GTE instructions less than the CPU's three 64-bit multiplies);
         MVMVA (RT x V0, no translation, sf=1): the car's world -> local transform, one command for nine multiplies.
   The solver clobbers RT, TR (not touched), V0, IR, MAC: the caller sets its camera after rp_step (app.c does). */
#ifndef GTE_RP_H
#define GTE_RP_H
#if defined(PS1) && !defined(RP_GTE_SIM)
#define RPG_HW 1
#define RPG_MTC2(n,v) __asm__ volatile("mtc2 %0,$" #n :: "r"((uint32_t)(v)))
#define RPG_MFC2(n) ({uint32_t r_; __asm__ volatile("mfc2 %0,$" #n "\n nop" : "=r"(r_)); r_;})
#define RPG_CTC2(n,v) do{ register uint32_t t_ __asm__("$8")=(uint32_t)(v); __asm__ volatile(".word 0x48C80000|(" #n "<<11)" :: "r"(t_) : "memory"); }while(0)
#define RPG_CMD(cmd) __asm__ volatile("nop\n nop\n .word " #cmd)
static inline void rpg_rt(const int16_t *m)          /* m[9] row major, 1.3.12 */
{
    RPG_CTC2(0, ((uint32_t)(uint16_t)m[1] << 16) | (uint16_t)m[0]); RPG_CTC2(1, ((uint32_t)(uint16_t)m[3] << 16) | (uint16_t)m[2]);
    RPG_CTC2(2, ((uint32_t)(uint16_t)m[5] << 16) | (uint16_t)m[4]); RPG_CTC2(3, ((uint32_t)(uint16_t)m[7] << 16) | (uint16_t)m[6]);
    RPG_CTC2(4, (uint16_t)m[8]);
    RPG_CTC2(5, 0); RPG_CTC2(6, 0); RPG_CTC2(7, 0);
}
static inline uint32_t rpg_sqrsum(int a, int b, int c)   /* a,b,c fit 16 bits: a^2 + b^2 + c^2 (under 2^32) */
{
    RPG_MTC2(9, a); RPG_MTC2(10, b); RPG_MTC2(11, c);
    RPG_CMD(0x4A400028);
    uint32_t x = RPG_MFC2(25), y = RPG_MFC2(26), z = RPG_MFC2(27);
    return x + y + z;
}
static inline void rpg_mv(int a, int b, int c, int *x, int *y, int *z)
{
    RPG_MTC2(0, ((uint32_t)(uint16_t)b << 16) | (uint16_t)a); RPG_MTC2(1, (uint16_t)c);
    RPG_CMD(0x4A486012);
    *x = (int)RPG_MFC2(25); *y = (int)RPG_MFC2(26); *z = (int)RPG_MFC2(27);
}
#else
#define RPG_HW 0
#ifdef RP_GTE_NOINLINE
#define RPG_INL __attribute__((noinline))
#else
#define RPG_INL static inline
#endif
static int16_t rpg_m[9];
#ifdef RP_GTE_NOINLINE
__attribute__((noinline)) void gtesim_rt(const int16_t *m)
#else
RPG_INL void rpg_rt(const int16_t *m)
#endif
{ for (int i = 0; i < 9; i++) rpg_m[i] = m[i]; }
#ifdef RP_GTE_NOINLINE
void rpg_rt(const int16_t *m) { gtesim_rt(m); }
#endif
#define RPG_SAT(v) ((v) > 32767 ? 32767 : (v) < -32768 ? -32768 : (v))
#ifdef RP_GTE_NOINLINE
__attribute__((noinline)) uint32_t gtesim_sqrsum(int a, int b, int c)
#else
RPG_INL uint32_t rpg_sqrsum(int a, int b, int c)
#endif
{ a = RPG_SAT(a); b = RPG_SAT(b); c = RPG_SAT(c); return (uint32_t)(a * a) + (uint32_t)(b * b) + (uint32_t)(c * c); }
#ifdef RP_GTE_NOINLINE
static inline uint32_t rpg_sqrsum(int a, int b, int c) { return gtesim_sqrsum(a, b, c); }
#endif
#ifdef RP_GTE_NOINLINE
__attribute__((noinline)) void gtesim_mv(int a, int b, int c, int *x, int *y, int *z)
#else
RPG_INL void rpg_mv(int a, int b, int c, int *x, int *y, int *z)
#endif
{
    a = RPG_SAT(a); b = RPG_SAT(b); c = RPG_SAT(c);
    *x = (int)(((int64_t)rpg_m[0] * a + (int64_t)rpg_m[1] * b + (int64_t)rpg_m[2] * c) >> 12);
    *y = (int)(((int64_t)rpg_m[3] * a + (int64_t)rpg_m[4] * b + (int64_t)rpg_m[5] * c) >> 12);
    *z = (int)(((int64_t)rpg_m[6] * a + (int64_t)rpg_m[7] * b + (int64_t)rpg_m[8] * c) >> 12);
}
#ifdef RP_GTE_NOINLINE
static inline void rpg_mv(int a, int b, int c, int *x, int *y, int *z) { gtesim_mv(a, b, c, x, y, z); }
#endif
#endif
#endif
