/* ARMv4T (Thumb + ARM) interpreter, freestanding C, no 64-bit types, no libc.  Used as the last-resort fallback of the Star-FlyBack PS1 runtime:
   guest code that is in neither the hot blob nor the cold overlay set runs here instead of halting at RT_MISS.
   Code only: no Payback code or data. */
#ifndef INTERP_H
#define INTERP_H
typedef unsigned int u32; typedef int s32; typedef unsigned short u16; typedef short s16; typedef unsigned char u8; typedef signed char s8;
#define IF_N 0x80000000u
#define IF_Z 0x40000000u
#define IF_C 0x20000000u
#define IF_V 0x10000000u
typedef struct IS {
  u32 r[16];     /* r0-r12, sp (r13), lr (r14), r15 unused */
  u32 f;         /* CPSR flag bits N Z C V (bits 31..28) */
  u32 pc;        /* address of the next instruction, bit 0 = Thumb state */
  u32 ev;        /* out of interp_step: 0 plain, 1 call (bl), 2 swi (r[15] = number), 3 branch/jump (pc is a transfer target) */
  u32 pad[2];
} IS;            /* 19 words, padded to 32 in the asm slabs */
/* embedding callbacks */
extern u32 ip_rd(u32 ea,u32 size);              /* guest read (size 1,2,4, aligned by the caller), zero-extended */
extern void ip_wr(u32 ea,u32 size,u32 val);
extern u32 ip_res_push(u32 sp,u32 lr);   /* record a pending guest return address (keyed by the guest sp); returns the host-form lr to hand to translated code */
extern u32 ip_map(u32 v);                       /* literal / pc-relative constant -> the translator's host-pointer form (identity if not a region address) */
extern u32 ip_lookup(u32 target);               /* translated host entry for a guest function entry, 0 if none (cold groups are loaded here) */
extern void ip_call(IS*s,u32 host);             /* run translated code at host with guest regs r0-r12,sp from s (lr = return trampoline); s updated on return */
extern void ip_swi(IS*s,u32 num);
extern u32 ip_is_host_iw(u32 a);                /* if a is a host address inside the IWRAM window: the guest 0x03xxxxxx address, else 0 */
extern u32 ip_arm_code(u32 a);                  /* 1 if the (even) guest address starts ARM-state code */
extern u32 ip_hle(IS*s,u32 target);            /* 1 if the embedding performed the guest routine at target natively (s->pc = return address) */
u32 interp_step(IS*s);
u32 interp_run(IS*s);                           /* runs from s->pc until control leaves to a host address (returned) */
extern unsigned int ip_stat_steps, ip_stat_calls, ip_stat_undef;
#endif
