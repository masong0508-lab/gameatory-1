/* rt.inc: the 64-bit helpers clang calls on mips1 (no libgcc here). Level 0 builds divide bit by bit (what a naive port costs). */
typedef unsigned long long ull_;
static ull_ udivmod_loop(ull_ n, ull_ d, ull_ *rem)
{
    ull_ q = 0, r = 0;
    for (int i = 63; i >= 0; i--) { r = (r << 1) | ((n >> i) & 1); if (r >= d) { r -= d; q |= (ull_)1 << i; } }
    if (rem) *rem = r;
    return q;
}
static ull_ udivmod(ull_ n, ull_ d, ull_ *rem)
{
#if RP_LEVEL >= 1
    if (!(d >> 32)) { ull_ q = udiv64_32(n, (uint32_t)d); if (rem) *rem = n - q * d; return q; }
#endif
    return udivmod_loop(n, d, rem);
}
ull_ __udivdi3(ull_ n, ull_ d) { return udivmod(n, d, 0); }
ull_ __umoddi3(ull_ n, ull_ d) { ull_ r; udivmod(n, d, &r); return r; }
long long __divdi3(long long n, long long d) { int neg = (n < 0) ^ (d < 0); ull_ q = udivmod(n < 0 ? -n : n, d < 0 ? -d : d, 0); return neg ? -(long long)q : (long long)q; }
long long __moddi3(long long n, long long d) { ull_ r; udivmod(n < 0 ? -n : n, d < 0 ? -d : d, &r); return n < 0 ? -(long long)r : (long long)r; }
ull_ __muldi3(ull_ a, ull_ b)
{
    uint32_t al = (uint32_t)a, ah = (uint32_t)(a >> 32), bl = (uint32_t)b, bh = (uint32_t)(b >> 32);
    return (ull_)al * bl + (((ull_)(al * bh + ah * bl)) << 32);
}
