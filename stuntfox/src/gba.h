/* Stunt Fox: GBA hardware definitions and basic types. */
#ifndef GBA_H
#define GBA_H

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed char s8;
typedef short s16;
typedef int s32;
typedef long long s64;

#define IWRAM_CODE __attribute__((section(".iwram"), target("arm"), noinline))
#define IWRAM_DATA __attribute__((section(".iwram_data")))
#define EWRAM_BSS __attribute__((section(".sbss")))

#define REG_DISPCNT (*(volatile u16 *)0x04000000)
#define REG_DISPSTAT (*(volatile u16 *)0x04000004)
#define REG_VCOUNT (*(volatile u16 *)0x04000006)
#define REG_BG2PA (*(volatile s16 *)0x04000020)
#define REG_BG2PB (*(volatile s16 *)0x04000022)
#define REG_BG2PC (*(volatile s16 *)0x04000024)
#define REG_BG2PD (*(volatile s16 *)0x04000026)
#define REG_BG2X (*(volatile s32 *)0x04000028)
#define REG_BG2Y (*(volatile s32 *)0x0400002c)
#define REG_BLDCNT (*(volatile u16 *)0x04000050)
#define REG_BLDY (*(volatile u16 *)0x04000054)
#define REG_KEYINPUT (*(volatile u16 *)0x04000130)
#define REG_IE (*(volatile u16 *)0x04000200)
#define REG_IF (*(volatile u16 *)0x04000202)
#define REG_WAITCNT (*(volatile u16 *)0x04000204)
#define REG_IME (*(volatile u16 *)0x04000208)
#define REG_SOUNDCNT_X (*(volatile u16 *)0x04000084)
#define REG_TM0CNT (*(volatile u32 *)0x04000100)
#define REG_TM0D (*(volatile u16 *)0x04000100)
#define REG_TM1D (*(volatile u16 *)0x04000104)
#define REG_TM0CNT_H (*(volatile u16 *)0x04000102)
#define REG_TM1CNT_H (*(volatile u16 *)0x04000106)
#define REG_TM2D (*(volatile u16 *)0x04000108)
#define REG_TM2CNT_H (*(volatile u16 *)0x0400010a)
#define REG_TM3D (*(volatile u16 *)0x0400010c)
#define REG_TM3CNT_H (*(volatile u16 *)0x0400010e)
#define BIOS_IFLAGS (*(volatile u16 *)0x03007ff8)
#define IRQ_HANDLER (*(void (*volatile *)(void))0x03007ffc)

#define PAL_BG ((volatile u16 *)0x05000000)
#define PAL_OBJ ((volatile u16 *)0x05000200)
#define VRAM ((volatile u16 *)0x06000000)
#define OBJ_TILES ((volatile u32 *)0x06014000)      /* mode 4: OBJ tiles 512.. */
#define OAM ((volatile u16 *)0x07000000)

enum {
    KEY_A = 1, KEY_B = 2, KEY_SELECT = 4, KEY_START = 8, KEY_RIGHT = 16, KEY_LEFT = 32,
    KEY_UP = 64, KEY_DOWN = 128, KEY_R = 256, KEY_L = 512
};

/* BIOS VBlankIntrWait. ARM state takes the call number from bits 16..23. */
#if !defined(__arm__)
static inline void vblank_wait(void) {}     /* host-side tests */
#elif defined(__thumb__)
static inline void vblank_wait(void) { __asm__ volatile("swi 0x05" ::: "r0", "r1", "r2", "r3", "memory"); }
#else
static inline void vblank_wait(void) { __asm__ volatile("swi 0x050000" ::: "r0", "r1", "r2", "r3", "memory"); }
#endif

/* free-running CPU cycle counter on timers 2 and 3 (call cycles_init once) */
static inline void cycles_init(void) { REG_TM3CNT_H = 0x84; REG_TM2CNT_H = 0x80; }
static inline u32 cycles(void)
{
    u32 hi = REG_TM3D, lo = REG_TM2D;
    if (REG_TM3D != hi) { hi = REG_TM3D; lo = REG_TM2D; }
    return hi << 16 | lo;
}

#ifdef __arm__
void *memset(void *d, int c, unsigned n);
void *memcpy(void *d, const void *s, unsigned n);
#else
#include <string.h>                         /* host-side tests (tools/sim) */
#endif

#endif
