/* Milestone B (PS1): stands in for stuntfox/src/gba.h when Stunt Fox is compiled natively for MIPS-I (ps1/merged/natbuild.py copies the
   sources into a build directory and puts this file over theirs; stuntfox/src is not changed).  Same types and register names; what differs:
   no ARM/IWRAM placement (HOT*, IWRAM_CODE are plain functions), SCRATCH/SCRATCH2 keep their own sections (the linker puts them on the host
   images of merge.ld's scr/scr2), and the memory accesses stay guest-addressed C: natbuild.py routes every load and store through the
   runtime's guest memory model (ps1/merged/sfmem.h), so REG_* and Payback's addresses mean what they mean on the GBA. */
#ifndef GBA_H
#define GBA_H

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed char s8;
typedef short s16;
typedef int s32;
typedef long long s64;
typedef unsigned long long u64;

#define IWRAM_CODE __attribute__((noinline))
#define IWRAM_DATA
#define COLD
#define EWRAM_BSS __attribute__((section(".sbss")))
#define HOT
#define HOT2
#define HOT3
#define HOT4
#define HOT5
#define HOT6
#define HOT6B
#define HOT7
#define HOT8
#define HOT9
#define HOT10
#define HOT11
#define SCRATCH __attribute__((section(".scratch")))
#define SCRATCH2 __attribute__((section(".scratch2")))

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
#define OBJ_TILES ((volatile u32 *)0x06014000)
#define OAM ((volatile u16 *)0x07000000)

enum {
    KEY_A = 1, KEY_B = 2, KEY_SELECT = 4, KEY_START = 8, KEY_RIGHT = 16, KEY_LEFT = 32,
    KEY_UP = 64, KEY_DOWN = 128, KEY_R = 256, KEY_L = 512
};

static inline void vblank_wait(void) {}        /* Payback owns the frame loop in the merged game */

static inline void cycles_init(void) { REG_TM3CNT_H = 0x84; REG_TM2CNT_H = 0x80; }
static inline u32 cycles(void)
{
    u32 hi = REG_TM3D, lo = REG_TM2D;
    if (REG_TM3D != hi) { hi = REG_TM3D; lo = REG_TM2D; }
    return hi << 16 | lo;
}

void *memset(void *d, int c, unsigned n);
void *memcpy(void *d, const void *s, unsigned n);
void *memmove(void *d, const void *s, unsigned n);
int memcmp(const void *a, const void *b, unsigned n);

#endif
