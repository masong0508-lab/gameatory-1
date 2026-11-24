/* Milestone B (PS1): the memory helpers that ps1/merged/irmem.py puts in place of Stunt Fox's loads and stores (and memcpy & co.) when its C is
   compiled natively.  They are linked into the one Stunt Fox module (natbuild.py: llvm-link, then opt) and inlined there.
   Memory model (t2m 'P', as translated Payback): a value >= 0x80000000 is a host address and is used as it is (Stunt Fox's own variables, its
   stack, and every RAM pointer Payback hands over); anything else is a guest address (ROM 0x08.., IO 0x04.., a guest RAM address built at run
   time) and goes to the runtime (sfglue.h: sf_rd / sf_wr, the same paths translated Payback's slow accesses take).
   No Payback code or data here. */
typedef unsigned int u32; typedef int s32; typedef unsigned short u16; typedef unsigned char u8; typedef unsigned long long u64;
u32 sf_rd(u32 a, u32 kind);                 /* kind: 0 u8, 2 u16, 4 u32 (h_memrd's) */
void sf_wr(u32 a, u32 size, u32 v);
void *sf_resolve(u32 a, u32 *avail);        /* host pointer of a guest address and how many bytes follow it in the same window or page, 0 if none */
void *sf_native_of(u32 a);                  /* the native function compiled from the Stunt Fox function at guest address a, 0 if none */
extern u32 sf_gtarget; u64 sf_gthunk();
#define AI __attribute__((always_inline))
#define HOST(a) ((s32)(a) < 0)
typedef struct __attribute__((packed)) { u16 v; } P16;
typedef struct __attribute__((packed)) { u32 v; } P32;

AI u32 __sf_ld8(const void *p) { u32 a = (u32)p; return HOST(a) ? *(const u8 *)p : sf_rd(a, 0); }
AI u32 __sf_ld16(const void *p) { u32 a = (u32)p; return HOST(a) ? *(const u16 *)p : sf_rd(a, 2); }
AI u32 __sf_ld32(const void *p) { u32 a = (u32)p; return HOST(a) ? *(const u32 *)p : sf_rd(a, 4); }
AI u32 __sf_ld16u(const void *p) { u32 a = (u32)p; return HOST(a) ? ((const P16 *)p)->v : sf_rd(a, 0) | sf_rd(a + 1, 0) << 8; }
AI u32 __sf_ld32u(const void *p) { u32 a = (u32)p; return HOST(a) ? ((const P32 *)p)->v : __sf_ld16u(p) | __sf_ld16u((const u8 *)p + 2) << 16; }
AI u64 __sf_ld64(const void *p) { return __sf_ld32u(p) | (u64)__sf_ld32u((const u8 *)p + 4) << 32; }
AI void __sf_st8(void *p, u32 v) { u32 a = (u32)p; if (HOST(a)) *(u8 *)p = v; else sf_wr(a, 1, v); }
AI void __sf_st16(void *p, u32 v) { u32 a = (u32)p; if (HOST(a)) *(u16 *)p = v; else sf_wr(a, 2, v); }
AI void __sf_st32(void *p, u32 v) { u32 a = (u32)p; if (HOST(a)) *(u32 *)p = v; else sf_wr(a, 4, v); }
AI void __sf_st16u(void *p, u32 v) { u32 a = (u32)p; if (HOST(a)) ((P16 *)p)->v = v; else { sf_wr(a, 1, v); sf_wr(a + 1, 1, v >> 8); } }
AI void __sf_st32u(void *p, u32 v) { u32 a = (u32)p; if (HOST(a)) ((P32 *)p)->v = v; else { __sf_st16u(p, v); __sf_st16u((u8 *)p + 2, v >> 16); } }
AI void __sf_st64(void *p, u64 v) { __sf_st32u(p, (u32)v); __sf_st32u((u8 *)p + 4, (u32)(v >> 32)); }

/* pointer <-> number (irmem.py: ptrtoint / inttoptr): numbers are guest addresses, pointers host ones, for the plain RAM windows
   (the runtime's layout, rt.c g2h: EWRAM, IWRAM, PAL, OAM, VRAM; IO, ROM and everything else keep their value) */
AI u32 __sf_h2g(const void *p)
{
    u32 a = (u32)p;
    if (a - 0x801b0000u < 0x40000u) return a - 0x801b0000u + 0x02000000u;
    if (a - 0x801f0000u < 0x8000u) return a - 0x801f0000u + 0x03000000u;
    if (a - 0x80180000u < 0x400u) return a - 0x80180000u + 0x05000000u;
    if (a - 0x80180400u < 0x400u) return a - 0x80180400u + 0x07000000u;
    if (a - 0x80181000u < 0x18000u) return a - 0x80181000u + 0x06000000u;
    return a;
}
AI void *__sf_g2h(u32 a)
{
    switch (a >> 24) {
    case 2: return (void *)(0x801b0000u + (a & 0x3ffffu));
    case 3: return (void *)(0x801f0000u + (a & 0x7fffu));
    case 5: return (void *)(0x80180000u + (a & 0x3ffu));
    case 7: return (void *)(0x80180400u + (a & 0x3ffu));
    case 6: { u32 o = a & 0x1ffffu; if (o >= 0x18000u) o -= 0x8000u; return (void *)(0x80181000u + o); }
    }
    return (void *)a;
}

/* the same out of line, for the code that is not hot (irmem.py --outline): a call is smaller than the inline test and slow path */
#define NI __attribute__((noinline))
NI u32 __sf_ld8_o(const void *p) { return __sf_ld8(p); }
NI u32 __sf_ld16_o(const void *p) { return __sf_ld16(p); }
NI u32 __sf_ld32_o(const void *p) { return __sf_ld32(p); }
NI u32 __sf_ld16u_o(const void *p) { return __sf_ld16u(p); }
NI u32 __sf_ld32u_o(const void *p) { return __sf_ld32u(p); }
NI u64 __sf_ld64_o(const void *p) { return __sf_ld64(p); }
NI void __sf_st8_o(void *p, u32 v) { __sf_st8(p, v); }
NI void __sf_st16_o(void *p, u32 v) { __sf_st16(p, v); }
NI void __sf_st32_o(void *p, u32 v) { __sf_st32(p, v); }
NI void __sf_st16u_o(void *p, u32 v) { __sf_st16u(p, v); }
NI void __sf_st32u_o(void *p, u32 v) { __sf_st32u(p, v); }
NI void __sf_st64_o(void *p, u64 v) { __sf_st64(p, v); }

/* a function pointer: native as it is, a Stunt Fox function by its guest address, else a guest call (the thunk takes the target from sf_gtarget) */
AI void *__sf_fnmap(void *f)
{
    u32 a = (u32)f;
    if (HOST(a))
        return f;
    void *n = sf_native_of(a);
    if (n)
        return n;
    sf_gtarget = a;
    return (void *)sf_gthunk;
}

/* the copies: host to host as plain loops, else window by window (a ROM page at a time) through sf_resolve, else byte by byte */
static void *span(void *d, u32 n, u32 *got)
{
    u32 a = (u32)d;
    if (HOST(a)) { *got = n; return d; }
    u32 av; void *p = sf_resolve(a, &av);
    if (!p) { *got = 1; return 0; }
    *got = av < n ? av : n;
    return p;
}
__attribute__((noinline)) void *__sf_memcpy(void *d, const void *s, u32 n)
{
    u8 *dd = d; const u8 *ss = s;
    if (HOST((u32)d) && HOST((u32)s) && !(((u32)d | (u32)s | n) & 3)) {
        u32 *a = d; const u32 *b = s;
        for (n >>= 2; n; n--) *a++ = *b++;
        return d;
    }
    while (n) {
        u32 g1, g2; u8 *p = span(dd, n, &g1); const u8 *q = span((void *)ss, n, &g2);
        u32 k = g1 < g2 ? g1 : g2;
        if (p && q) { for (u32 i = 0; i < k; i++) p[i] = q[i]; }
        else { k = 1; u32 v = q ? *q : sf_rd((u32)ss, 0); if (p) *p = v; else sf_wr((u32)dd, 1, v); }
        dd += k; ss += k; n -= k;
    }
    return d;
}
__attribute__((noinline)) void *__sf_memmove(void *d, const void *s, u32 n)
{
    if ((u32)d <= (u32)s || (u32)d >= (u32)s + n)
        return __sf_memcpy(d, s, n);
    u8 *dd = d; const u8 *ss = s;
    while (n--) __sf_st8(dd + n, __sf_ld8(ss + n));
    return d;
}
__attribute__((noinline)) void *__sf_memset(void *d, u32 c, u32 n)
{
    u8 *dd = d;
    c &= 0xff;
    if (HOST((u32)d) && !(((u32)d | n) & 3)) {
        u32 w = c * 0x01010101u, *a = d;
        for (n >>= 2; n; n--) *a++ = w;
        return d;
    }
    while (n) {
        u32 g; u8 *p = span(dd, n, &g);
        if (p) { for (u32 i = 0; i < g; i++) p[i] = c; }
        else { g = 1; sf_wr((u32)dd, 1, c); }
        dd += g; n -= g;
    }
    return d;
}
__attribute__((noinline)) int __sf_memcmp(const void *a, const void *b, u32 n)
{
    const u8 *p = a, *q = b;
    for (; n; n--, p++, q++) {
        int x = __sf_ld8(p), y = __sf_ld8(q);
        if (x != y) return x - y;
    }
    return 0;
}
__attribute__((noinline)) u32 __sf_strlen(const char *s)
{
    u32 n = 0;
    while (__sf_ld8(s + n)) n++;
    return n;
}
