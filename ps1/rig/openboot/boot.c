/* boot.c: the openboot loader.  Runs once from RAM (KSEG0) on the boot stack: installs the call/exception vectors,
   brings the CD-ROM controller up, reads the ISO9660 volume descriptor and the root directory, SYSTEM.CNF, the
   PS-X EXE, sets the machine state and starts the game.
   Own work from the public hardware documentation (psx-spx: cdromdrive, kernelbios, interrupts, iomap,
   graphicsprocessingunitgpu).  No Sony code or data.  Every "documented" below refers to those pages; every
   assumption is listed in BOOTROM.md. */
#include "ob.h"

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

#define R32(a)  (*(volatile u32 *)(a))
#define R8(a)   (*(volatile u8 *)(a))
#define TR(o)   R32(0x80000000u + OB_TRACE + (o))

#define I_STAT  R32(0x1F801070)
#define I_MASK  R32(0x1F801074)
#define DPCR    R32(0x1F8010F0)
#define DICR    R32(0x1F8010F4)
#define GP0     R32(0x1F801810)
#define GP1     R32(0x1F801814)
#define CD_IDX  R8(0x1F801800)      /* read: HSTS (bit 5 result ready, 6 data request, 7 busy); write: register bank */
#define CD_1    R8(0x1F801801)      /* write bank 0: command; read: result FIFO */
#define CD_2    R8(0x1F801802)      /* write bank 0: parameter, bank 1: HINTMSK; read: data FIFO */
#define CD_3    R8(0x1F801803)      /* write bank 0: HCHPCTL (bit 7 BFRD), bank 1: HCLRCTL; read bank 1: HINTSTS */

#define T_FIRST   6000000u          /* polling loop turns: first response of a command */
#define T_SECOND  30000000u         /* second response (Init, Pause), first sector after a seek */

extern void ob_launch(u32 pc0, u32 sp, u32 gp, u32 flags) __attribute__((noreturn));
extern void ob_flush_now(void);
extern const u32 ob_vec_exc[4], ob_vec_a[4], ob_vec_b[4], ob_vec_c[4];

void *memcpy(void *d, const void *s, u32 n) { u8 *a = d; const u8 *b = s; while (n--) *a++ = *b++; return d; }
void *memset(void *d, int c, u32 n) { u8 *a = d; while (n--) *a++ = (u8)c; return d; }

/* ---- failure: a colour on the screen (GPU reset, 320x240, one fill), the code in the trace table, stop */
static void ob_panic(u32 code) __attribute__((noreturn));
static void ob_panic(u32 code)
{
    static const u32 colour[8] = { 0x000000, 0x0000c0, 0x0080ff, 0x00c0c0, 0xc0c000, 0xc00000, 0xc000c0, 0x808080 };
    TR(TR_ERROR) = code;
    GP1 = 0x00000000;                           /* reset */
    GP1 = 0x08000001;                           /* 320 wide, NTSC, 15 bit */
    GP1 = 0x06c60260;                           /* horizontal display range (the documented default) */
    GP1 = 0x07040010;                           /* vertical display range 10h..100h */
    GP1 = 0x05000000;                           /* display start 0,0 */
    GP0 = 0x02000000 | colour[code & 7];        /* fill rectangle */
    GP0 = 0x00000000;
    GP0 = (240u << 16) | 320u;
    GP1 = 0x03000000;                           /* display on */
    for (;;) { }
}

/* ---- CD-ROM controller, polled */
static u32 cd_flags(void)
{
    u32 f;
    CD_IDX = 1;
    f = CD_3 & 7;
    if (f) f = CD_3 & 7;                        /* documented: the first non-zero read may be unstable, read again */
    return f;
}
static u32 cd_wait(u32 turns)
{
    while (turns--) { u32 f = cd_flags(); if (f) return f; }
    return 0;
}
static void cd_result(u8 *r)
{
    u32 n = 0;
    while ((CD_IDX & 0x20) && n < 16) { u8 b = CD_1; if (n < 8) r[n] = b; n++; }
    if (n) TR(TR_CD_STAT) = r[0];
}
static void cd_ack(void) { CD_IDX = 1; CD_3 = 0x1f; }
/* boot log of the first 63 CD-ROM events (TR_CDLOG): count, then command << 16 | first result byte << 8 | INT */
static u32 cd_last_cmd;
static void cd_log(u32 f, u32 stat)
{
    u32 n = TR(TR_CDLOG);
    if (n < 63) { TR(TR_CDLOG + 4 + 4 * n) = (cd_last_cmd << 16) | ((stat & 0xff) << 8) | f; TR(TR_CDLOG) = n + 1; }
}
/* the response after the command's own first one, or the first one itself: data-ready interrupts of sectors
   that were still on their way are dropped */
static u32 cd_response(u8 *r, u32 turns)
{
    for (;;) {
        u32 f = cd_wait(turns);
        r[0] = 0xff;
        cd_result(r);
        cd_log(f, r[0]);
        cd_ack();
        if (f != 1) return f;
    }
}
/* the second response of Init / Pause: INT2 (or INT5).  A further INT3 before it is tolerated and counted in
   TR_EXTRA_INT3: SwanStation answers Init with INT3, INT3, INT2 (the documentation says INT3, INT2). */
static u32 cd_complete(u8 *r)
{
    for (;;) {
        u32 f = cd_response(r, T_SECOND);
        if (f != 3) return f;
        TR(TR_EXTRA_INT3)++;
    }
}
static u32 cd_cmd(u32 c, const u8 *p, u32 np, u8 *r)
{
    u32 t, i;
    for (t = 0; (CD_IDX & 0x80) && t < 4000000; t++) { }       /* BUSYSTS */
    CD_IDX = 0;
    for (i = 0; i < np; i++) CD_2 = p[i];
    CD_1 = (u8)c;
    cd_last_cmd = c;
    return cd_response(r, T_FIRST);
}
static void delay(u32 turns) { volatile u32 n = turns; while (n) n--; }

static int cd_init(void)
{
    u8 r[8], m;
    u32 f;
    cd_ack();                                   /* documented "To init the CD": flush all IRQs */
    CD_IDX = 0; CD_3 = 0x00;                    /* HCHPCTL = 0 */
    CD_IDX = 1; CD_2 = 0x1f;                    /* HINTMSK = 1Fh ("typically set to 1Fh") */
    R32(0x1F801020) = 0x00001325;               /* COM_DELAY */
    f = cd_cmd(0x01, 0, 0, r); TR(TR_CDI_STEP) = 0x100 | f;   /* two Nop (Getstat) */
    f = cd_cmd(0x01, 0, 0, r); TR(TR_CDI_STEP) = 0x200 | f;
    f = cd_cmd(0x0a, 0, 0, r); TR(TR_CDI_STEP) = 0x300 | f;   /* Init: INT3, then INT2 */
    if (f != 3) return -1;
    f = cd_complete(r); TR(TR_CDI_STEP) = 0x400 | f;
    if (f != 2) return -1;
    f = cd_cmd(0x0c, 0, 0, r); TR(TR_CDI_STEP) = 0x500 | f;   /* Demute */
    m = 0xa0;                                   /* Setmode: double speed, 924h bytes per sector (header + data) */
    f = cd_cmd(0x0e, &m, 1, r); TR(TR_CDI_STEP) = 0x600 | f;
    if (f != 3) return -1;
    return 0;
}

static u32 bcd(u32 v) { return ((v / 10) << 4) | (v % 10); }

/* one Setloc/ReadN run; *done = sectors stored.  Every sector's own address header is checked, so a sector the
   drive skipped or delivered late is noticed and read again by the caller. */
static int cd_try_read(u32 lba, u32 n, u8 *dst, u32 *done)
{
    u8 p[3], r[8], h[12];
    u32 a = lba + 150, s, i, t, f;
    p[0] = (u8)bcd(a / 4500); p[1] = (u8)bcd((a / 75) % 60); p[2] = (u8)bcd(a % 75);
    if (cd_cmd(0x02, p, 3, r) != 3) return -1;                  /* Setloc */
    if (cd_cmd(0x06, 0, 0, r) != 3) return -1;                  /* ReadN: INT3, then INT1 per sector */
    for (s = 0; s < n; s++) {
        u8 *d = dst + s * 2048;
        f = cd_wait(T_SECOND);
        cd_result(r);
        if (f != 1) { cd_ack(); return -1; }
        CD_IDX = 0; CD_3 = 0x00; CD_3 = 0x80;                   /* BFRD: reset the data FIFO, then request the sector */
        for (t = 0; !(CD_IDX & 0x40) && t < 200000; t++) { }    /* documented: wait until DRQSTS is set */
        cd_ack();                                               /* documented order: request, acknowledge, copy */
        for (i = 0; i < 12; i++) h[i] = CD_2;                   /* MM SS FF mode, then (mode 2) the sub-header */
        a = lba + s + 150;
        if (h[0] != bcd(a / 4500) || h[1] != bcd((a / 75) % 60) || h[2] != bcd(a % 75)) return -2;
        if (h[3] == 2) {
            for (i = 0; i < 2048; i++) d[i] = CD_2;
            for (i = 0; i < 280; i++) (void)CD_2;               /* EDC/ECC: drained, the FIFO is left empty */
        } else {                                                /* mode 1: the data starts right behind the header */
            for (i = 0; i < 8; i++) d[i] = h[4 + i];
            for (i = 8; i < 2048; i++) d[i] = CD_2;
            for (i = 0; i < 288; i++) (void)CD_2;
        }
        CD_IDX = 0; CD_3 = 0x00;
        TR(TR_BOOT_SECTORS)++;
        *done = s + 1;
    }
    return 0;
}
static void cd_read(u32 lba, u32 n, u8 *dst)
{
    u8 r[8];
    u32 tries = 0;
    while (n) {
        u32 done = 0;
        int e = cd_try_read(lba, n, dst, &done);
        if (cd_cmd(0x09, 0, 0, r) == 3) cd_complete(r);             /* Pause: INT3, then INT2 */
        else delay(200000);
        lba += done; dst += done * 2048; n -= done;
        if (done) tries = 0;
        if (e) {
            TR(TR_BOOT_RETRIES)++;
            if (++tries > 12) ob_panic(OBE_CD_READ);
            delay(400000);
        }
    }
}

/* ---- ISO9660 */
static u8 *const secbuf = (u8 *)OB_SCRATCH;                     /* one sector */
static u32 le32(const u8 *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((u32)p[3] << 24); }
static u32 upc(u32 c) { return (c >= 'a' && c <= 'z') ? c - 32 : c; }
/* directory identifier against a path component; a ";version" suffix on either side is ignored */
static int name_eq(const u8 *id, u32 idlen, const u8 *nm, u32 nmlen)
{
    u32 i;
    for (i = 0; i < idlen; i++) if (id[i] == ';') { idlen = i; break; }
    for (i = 0; i < nmlen; i++) if (nm[i] == ';') { nmlen = i; break; }
    if (idlen != nmlen) return 0;
    for (i = 0; i < idlen; i++) if (upc(id[i]) != upc(nm[i])) return 0;
    return 1;
}
struct ent { u32 lba, size, flags; };
static int dir_find(const struct ent *dir, const u8 *nm, u32 nmlen, struct ent *out)
{
    u32 lba = dir->lba, left = dir->size;
    while (left) {
        u32 p = 0;
        cd_read(lba, 1, secbuf);
        while (p < 2048) {
            u32 len = secbuf[p];
            if (!len || p + len > 2048) break;                  /* records do not cross sectors */
            if (name_eq(secbuf + p + 33, secbuf[p + 32], nm, nmlen)) {
                out->lba = le32(secbuf + p + 2); out->size = le32(secbuf + p + 10); out->flags = secbuf[p + 25];
                return 1;
            }
            p += len;
        }
        lba++;
        left = left > 2048 ? left - 2048 : 0;
    }
    return 0;
}
/* "cdrom:\DIR\NAME.EXT;1": the device name and leading separators are skipped, directories are walked */
static int path_find(const struct ent *root, const u8 *path, u32 len, struct ent *out)
{
    struct ent cur = *root;
    u32 i, s;
    for (i = 0; i < len; i++) if (path[i] == ':') { path += i + 1; len -= i + 1; break; }
    i = 0;
    for (;;) {
        while (i < len && (path[i] == '\\' || path[i] == '/')) i++;
        if (i >= len) return 0;
        s = i;
        while (i < len && path[i] != '\\' && path[i] != '/') i++;
        if (!dir_find(&cur, path + s, i - s, out)) return 0;
        if (i >= len) return 1;
        if (!(out->flags & 2)) return 0;                        /* more path follows: must be a directory */
        cur = *out;
    }
}

/* ---- SYSTEM.CNF: "KEY = value" lines; TCB, EVENT and STACK are hexadecimal (documented) */
static int is_sp(u32 c) { return c == ' ' || c == '\t'; }
static u32 hexval(const u8 *p, u32 n)
{
    u32 v = 0, i;
    for (i = 0; i < n; i++) {
        u32 c = upc(p[i]);
        if (c >= '0' && c <= '9') v = (v << 4) | (c - '0');
        else if (c >= 'A' && c <= 'F') v = (v << 4) | (c - 'A' + 10);
        else break;
    }
    return v;
}
struct cnf { u8 boot[64]; u32 bootlen, tcb, event, stack; };
static void cnf_parse(const u8 *t, u32 len, struct cnf *c)
{
    u32 i = 0;
    while (i < len && t[i]) {
        u32 ks, ke, vs, ve, e;
        while (i < len && (is_sp(t[i]) || t[i] == '\r' || t[i] == '\n')) i++;
        ks = i;
        while (i < len && t[i] != '=' && t[i] != '\r' && t[i] != '\n' && t[i]) i++;
        ke = i;
        while (ke > ks && is_sp(t[ke - 1])) ke--;
        if (i >= len || t[i] != '=') continue;
        i++;
        while (i < len && is_sp(t[i])) i++;
        vs = i;
        while (i < len && t[i] != '\r' && t[i] != '\n' && t[i]) i++;
        ve = i;
        while (ve > vs && is_sp(t[ve - 1])) ve--;
        if (name_eq(t + ks, ke - ks, (const u8 *)"BOOT", 4)) {
            volatile u8 *arg = (volatile u8 *)0x80000180;       /* documented: the argument of "BOOT = fname argument" */
            u32 k = 0;
            for (e = vs; e < ve && !is_sp(t[e]); e++) { }
            c->bootlen = e - vs < 63 ? e - vs : 63;
            memcpy(c->boot, t + vs, c->bootlen);
            while (e < ve && is_sp(t[e])) e++;
            while (e < ve && k < 0x7f) arg[k++] = t[e++];
            arg[k] = 0;
        } else if (name_eq(t + ks, ke - ks, (const u8 *)"TCB", 3)) c->tcb = hexval(t + vs, ve - vs);
        else if (name_eq(t + ks, ke - ks, (const u8 *)"EVENT", 5)) c->event = hexval(t + vs, ve - vs);
        else if (name_eq(t + ks, ke - ks, (const u8 *)"STACK", 5)) c->stack = hexval(t + vs, ve - vs);
    }
}

void ob_main(void) __attribute__((noreturn));
void ob_main(void)
{
    static const u8 defboot[] = "cdrom:PSX.EXE;1";
    struct ent root, f;
    struct cnf c;
    u32 flags = TR(TR_FLAGS), i, pc0, gp0, taddr, tsize, baddr, bsize, sp, sr, tries;
    volatile u32 *v;

    TR(TR_STAGE) = 1;
    /* documented kernel RAM words: memory size, and the four vectors */
    R32(0x80000060) = 2; R32(0x80000064) = 0; R32(0x80000068) = 0xff;
    v = (volatile u32 *)0x80000080; for (i = 0; i < 4; i++) v[i] = ob_vec_exc[i];
    v = (volatile u32 *)0x800000a0; for (i = 0; i < 4; i++) v[i] = ob_vec_a[i];
    v = (volatile u32 *)0x800000b0; for (i = 0; i < 4; i++) v[i] = ob_vec_b[i];
    v = (volatile u32 *)0x800000c0; for (i = 0; i < 4; i++) v[i] = ob_vec_c[i];
    ob_flush_now();
    TR(TR_STAGE) = 2;

    for (tries = 0; cd_init(); tries++) {
        if (!TR(TR_CDI_FAIL)) TR(TR_CDI_FAIL) = TR(TR_CDI_STEP);
        TR(TR_BOOT_RETRIES)++;
        if (tries >= 8) ob_panic(OBE_CD_INIT);
        delay(2000000);
    }
    TR(TR_STAGE) = 3;

    cd_read(16, 1, secbuf);                                     /* primary volume descriptor */
    if (secbuf[0] != 1 || secbuf[1] != 'C' || secbuf[2] != 'D' || secbuf[3] != '0' || secbuf[4] != '0' || secbuf[5] != '1')
        ob_panic(OBE_NO_PVD);
    root.lba = le32(secbuf + 156 + 2); root.size = le32(secbuf + 156 + 10); root.flags = 2;
    TR(TR_STAGE) = 4;

    memset(&c, 0, sizeof c);
    c.tcb = 4; c.event = 0x10; c.stack = 0x801fff00;            /* documented defaults */
    memcpy(c.boot, defboot, sizeof defboot - 1); c.bootlen = sizeof defboot - 1;
    if (path_find(&root, (const u8 *)"SYSTEM.CNF;1", 12, &f)) {
        cd_read(f.lba, 1, secbuf);
        cnf_parse(secbuf, f.size < 2048 ? f.size : 2048, &c);
    } else TR(TR_ERROR) = OBE_NO_CNF;                           /* not fatal: PSX.EXE is tried */
    TR(TR_CNF_TCB) = c.tcb; TR(TR_CNF_EVENT) = c.event; TR(TR_CNF_STACK) = c.stack;
    TR(TR_STAGE) = 5;

    if (!path_find(&root, c.boot, c.bootlen, &f)) ob_panic(OBE_NO_EXE);
    cd_read(f.lba, 1, secbuf);                                  /* 800h byte header */
    if (secbuf[0] != 'P' || secbuf[1] != 'S' || secbuf[2] != '-' || secbuf[3] != 'X' || secbuf[4] != ' ' ||
        secbuf[5] != 'E' || secbuf[6] != 'X' || secbuf[7] != 'E') ob_panic(OBE_BAD_EXE);
    pc0 = le32(secbuf + 0x10); gp0 = le32(secbuf + 0x14); taddr = le32(secbuf + 0x18); tsize = le32(secbuf + 0x1c);
    baddr = le32(secbuf + 0x28); bsize = le32(secbuf + 0x2c);
    sp = c.stack ? c.stack : le32(secbuf + 0x30) + le32(secbuf + 0x34);
    /* the body must lie in main RAM above the kernel's 64 KiB and fit the file */
    if ((taddr & 0x1fffffff) < 0x10000 || (taddr & 0x1fffffff) + tsize > 0x200000 || tsize + 0x800 > ((f.size + 0x7ff) & ~0x7ffu))
        ob_panic(OBE_BAD_EXE);
    TR(TR_PC0) = pc0; TR(TR_GP) = gp0; TR(TR_TADDR) = taddr; TR(TR_TSIZE) = tsize; TR(TR_EXELBA) = f.lba; TR(TR_SP) = sp;
    TR(TR_STAGE) = 6;

    if (flags & OBF_DIRTY) {                                    /* RAM is not zero when a real console starts a game */
        volatile u32 *q = (volatile u32 *)0x80010000;
        u32 x = 0x9e3779b9;
        while (q < (volatile u32 *)0x80200000) { x = x * 1664525u + 1013904223u; *q++ = x | 0x01010101u; }
    }
    cd_read(f.lba + 1, (tsize + 2047) >> 11, (u8 *)taddr);
    if (bsize) memset((void *)baddr, 0, bsize);                 /* Exec: the header's memfill region */
    TR(TR_STAGE) = 7;

    {   /* drive: paused (cd_read), double speed, 800h byte sectors */
        u8 r[8], m = 0x80;
        cd_cmd(0x0e, &m, 1, r);
    }
    ob_flush_now();                                             /* Load: FlushCache after the body is in RAM */
    if (flags & OBF_KIRQ) {
        /* what the documentation says of the kernel that loads the boot file: _96_init has run, IRQ2 (CD-ROM) and
           IRQ3 (DMA) are enabled, DMA3 is enabled with its interrupt, interrupts are on (ExitCriticalSection) */
        DPCR = DPCR | 0x00008000;
        DICR = (DICR & 0x00ffffff) | 0x00880000;
        I_MASK = (flags & OBF_KVBL) ? 0x0d : 0x0c;
        sr = 0x00000401;
    } else {
        I_MASK = 0;
        sr = 0;
    }
    TR(TR_ISTAT_BOOT) = I_STAT;
    I_STAT = 0;
    TR(TR_SR_ENTRY) = sr;
    TR(TR_STAGE) = 8;
    ob_launch(pc0, sp, gp0, flags);
}
