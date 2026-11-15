/* Tiny headless libmgba shim for emu.py (ctypes). Build: gcc -O2 -shared -fPIC gbashim.c -o libgbashim.so -lmgba */
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <stdint.h>
#include <mgba/core/core.h>
#include <mgba/core/blip_buf.h>
#include <mgba/gba/core.h>
#include <mgba-util/vfs.h>
#include <mgba/core/log.h>

static void quiet_log(struct mLogger *l, int cat, enum mLogLevel lv, const char *fmt, va_list ap) { (void)l; (void)cat; (void)lv; (void)fmt; (void)ap; }
static struct mLogger quiet = { quiet_log, NULL };

typedef struct {
    struct mCore *core;
    uint32_t *fb;
    unsigned w, h;
    void *state;
    size_t statesz;
} Gba;

void *gba_open(const char *rom, int *err)
{
    Gba *g = calloc(1, sizeof *g);
    mLogSetDefaultLogger(&quiet);
    g->core = GBACoreCreate();
    if (!g->core) { *err = 1; return 0; }
    g->core->init(g->core);
    mCoreInitConfig(g->core, NULL);
    g->core->desiredVideoDimensions(g->core, &g->w, &g->h);
    g->fb = calloc(g->w * g->h, 4);
    g->core->setVideoBuffer(g->core, g->fb, g->w);
    g->core->setAudioBufferSize(g->core, 1024);
    if (!mCoreLoadFile(g->core, rom)) { *err = 2; return 0; }
    /* the save lives in memory only: nothing is written next to the ROM */
    struct VFile *sv = VFileMemChunk(NULL, 0);
    g->core->loadSave(g->core, sv);
    g->core->reset(g->core);
    g->statesz = g->core->stateSize(g->core);
    g->state = malloc(g->statesz);
    *err = 0;
    return g;
}

void gba_close(Gba *g) { g->core->deinit(g->core); free(g->fb); free(g->state); free(g); }

static void drain(Gba *g)
{
    /* the audio is never played: empty the blip buffers so they do not fill */
    blip_t *l = g->core->getAudioChannel(g->core, 0), *r = g->core->getAudioChannel(g->core, 1);
    if (l) blip_clear(l);
    if (r) blip_clear(r);
}

void gba_run(Gba *g, int n) { while (n-- > 0) { g->core->runFrame(g->core); drain(g); } }
void gba_keys(Gba *g, uint32_t m) { g->core->setKeys(g->core, m); }
uint32_t gba_r8(Gba *g, uint32_t a) { return g->core->busRead8(g->core, a); }
uint32_t gba_r16(Gba *g, uint32_t a) { return g->core->busRead16(g->core, a); }
uint32_t gba_r32(Gba *g, uint32_t a) { return g->core->busRead32(g->core, a); }
void gba_w8(Gba *g, uint32_t a, uint32_t v) { g->core->busWrite8(g->core, a, v); }
void gba_w16(Gba *g, uint32_t a, uint32_t v) { g->core->busWrite16(g->core, a, v); }
void gba_w32(Gba *g, uint32_t a, uint32_t v) { g->core->busWrite32(g->core, a, v); }
/* bulk read through the bus (a byte at a time keeps ROM/IO side effects out of the way: raw reads) */
void gba_read(Gba *g, uint32_t a, uint8_t *out, uint32_t n)
{ for (uint32_t i = 0; i < n; i++) out[i] = g->core->busRead8(g->core, a + i); }
void gba_write(Gba *g, uint32_t a, const uint8_t *in, uint32_t n)
{ for (uint32_t i = 0; i < n; i++) g->core->busWrite8(g->core, a + i, in[i]); }
/* 240x160 RGBA bytes (R,G,B,A in memory order) */
void gba_fb(Gba *g, uint8_t *out)
{
    unsigned n = g->w * g->h;
    for (unsigned i = 0; i < n; i++) {
        uint32_t p = g->fb[i];             /* mCOLOR_32: 0xAABBGGRR on little-endian hosts */
        out[4 * i] = p & 255; out[4 * i + 1] = p >> 8 & 255; out[4 * i + 2] = p >> 16 & 255; out[4 * i + 3] = 255;
    }
}
uint32_t gba_pc(Gba *g) { uint32_t v = 0; g->core->readRegister(g->core, "pc", &v); return v; }
uint32_t gba_reg(Gba *g, int i)
{
    char nm[8]; uint32_t v = 0;
    if (i == 16) strcpy(nm, "cpsr"); else { nm[0] = 'r'; nm[1] = 0; if (i > 9) { nm[1] = '1'; nm[2] = '0' + i - 10; nm[3] = 0; } else { nm[1] = '0' + i; nm[2] = 0; } }
    g->core->readRegister(g->core, nm, &v);
    return v;
}
uint32_t gba_frames(Gba *g) { return g->core->frameCounter(g->core); }
size_t gba_statesize(Gba *g) { return g->statesz; }
int gba_savestate(Gba *g, void *buf) { return g->core->saveState(g->core, buf); }
int gba_loadstate(Gba *g, const void *buf) { return g->core->loadState(g->core, buf); }
void gba_reset(Gba *g) { g->core->reset(g->core); }

/* stage 3: instruction-level block coverage of the ROM (halfword bitmap over 0x08000000..0x08800000) while running nframes frames */
void gba_cover(Gba *g, int nframes, uint8_t *bitmap)
{
    uint32_t f0 = g->core->frameCounter(g->core);
    while (g->core->frameCounter(g->core) - f0 < (uint32_t)nframes) {
        uint32_t pc = 0; g->core->readRegister(g->core, "pc", &pc);
        if (pc >= 0x08000000 && pc < 0x08800000) { uint32_t h = (pc - 0x08000000) >> 1; bitmap[h >> 3] |= 1 << (h & 7); }
        else if (pc >= 0x03000000 && pc < 0x03008000) { uint32_t h = 0x400000 + ((pc - 0x03000000) >> 1); bitmap[h >> 3] |= 1 << (h & 7); }   /* stage 4: IWRAM (ARM hot code) after the ROM bitmap */
        g->core->step(g->core);
    }
    drain(g);
}

/* stage 4: cycle cost of one guest function (stepped instruction by instruction, emulator-only).  Every time pc == entry the call is timed until pc returns to the
   caller (lr at entry).  Cycles spent with the CPU halted (a step that leaves pc unchanged: halt / IRQ wait) are counted as idle and left out of the busy figure.
   out[0]=calls, out[1]=busy cycles inside, out[2]=max busy cycles of one call, out[3]=frames run, out[4]=busiest frame (sum of its calls), out[5]=idle cycles inside, out[6]=elapsed (busy+idle) */
void gba_prof(Gba *g, int nframes, uint32_t entry, uint64_t *out, uint64_t *bk)
{
    struct mCore *c = g->core; uint32_t f0 = c->frameCounter(c), cur = f0, ret = 0; int in = 0; uint64_t cs = 0, fsum = 0;
    for (int k = 0; k < 7; k++) out[k] = 0;
    while (c->frameCounter(c) - f0 < (uint32_t)nframes) {
        uint32_t pc = 0, lr = 0, pc2 = 0;
        c->readRegister(c, "pc", &pc);
        uint64_t t = (uint64_t)c->frameCounter(c) * 280896u + (uint64_t)c->frameCycles(c);
        if (c->frameCounter(c) != cur) { if (fsum > out[4]) out[4] = fsum; fsum = 0; cur = c->frameCounter(c); }
        if (!in && (pc == entry || pc == entry + 2 || pc == entry + 4)) { c->readRegister(c, "lr", &lr); ret = lr & ~1u; in = 1; cs = 0; out[0]++; }
        else if (in && (pc == ret || pc == ret + 2 || pc == ret + 4)) { out[1] += cs; fsum += cs; if (cs > out[2]) out[2] = cs; in = 0; }
        c->step(c);
        if (in) {
            c->readRegister(c, "pc", &pc2);
            uint64_t t2 = (uint64_t)c->frameCounter(c) * 280896u + (uint64_t)c->frameCycles(c);
            if (t2 >= t) { if (pc2 == pc) out[5] += t2 - t; else cs += t2 - t; out[6] += t2 - t;
                if (bk) { if (pc >= 0x08000000 && pc < 0x08800000) bk[(pc - 0x08000000) >> 6] += t2 - t; else if (pc >= 0x03000000 && pc < 0x03008000) bk[0x20000 + ((pc - 0x03000000) >> 6)] += t2 - t; else bk[0x20600] += t2 - t; } }
        }
    }
    out[3] = c->frameCounter(c) - f0; drain(g);
}
