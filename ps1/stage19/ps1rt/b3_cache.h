/* B3 optional ROM working-set cache. Pure C, shared by the PS1 runtime
   and ROM-free host tests. A compressed block is never exposed as a guest
   pointer: it must first restore a full, ordinary 4 KiB cache frame. */
#ifndef PS1_B3_CACHE_H
#define PS1_B3_CACHE_H
#define B3_PAGE_SIZE 4096u
#define B3_PAGE_COUNT 4096u
#define B3_HOT_MAX 56u

typedef struct { u16 page, bytes; const u8 *data; } B3CachePage;

/* Bounded LZ4 block decoder. Accept only a complete 4096-byte output.
   On failure the caller must overwrite the entire frame from the disc
   before publishing its mapping. Overlapping back-references are normal. */
static int b3_decode_page(const u8 *src, u32 size, u8 *dst)
{
    if (!size || size >= B3_PAGE_SIZE)
        return 0;
    const u8 *in = src, *end = src + size;
    u8 *out = dst, *limit = dst + B3_PAGE_SIZE;
    while (in < end) {
        u32 token = *in++, lit = token >> 4, match = token & 15u, v;
        if (lit == 15u) {
            do { if (in == end) return 0; v = *in++; lit += v; } while (v == 255u);
        }
        if (lit > (u32)(end - in) || lit > (u32)(limit - out))
            return 0;
        while (lit--) *out++ = *in++;
        if (in == end)
            return out == limit;
        if (end - in < 2)
            return 0;
        u32 distance = in[0] | ((u32)in[1] << 8);
        in += 2;
        if (!distance || distance > (u32)(out - dst))
            return 0;
        if (match == 15u) {
            do { if (in == end) return 0; v = *in++; match += v; } while (v == 255u);
        }
        match += 4u;
        if (match > (u32)(limit - out))
            return 0;
        const u8 *from = out - distance;
        while (match--) *out++ = *from++;
    }
    return 0;
}

/* 1 restored, 0 absent, -1 malformed. Entries are sorted by page ID. */
static int b3_restore_page(u32 pg, u8 *dst, const B3CachePage *pages, u32 count)
{
    u32 lo = 0, hi = count;
    while (lo < hi) {
        u32 mid = (lo + hi) >> 1, key = pages[mid].page;
        if (key < pg) lo = mid + 1;
        else if (key > pg) hi = mid;
        else return b3_decode_page(pages[mid].data, pages[mid].bytes, dst) ? 1 : -1;
    }
    return 0;
}

/* CLOCK continues to use the direct translated ROM mapping as its
   reference bit. Prefer non-hot frames for two bounded sweeps; if all
   are hot, fall back to the original CLOCK. No frame is pinned forever,
   and no owner or reverse map is changed by this chooser. */
static u32 b3_clock_victim(u32 n, u32 *hand, const u16 *owners,
                           const u8 **mapped, const u8 *preferred, int active)
{
    u32 f = *hand;
    if (active) {
        for (u32 i = 0; i < 2u * n; i++) {
            u32 owner = owners[f], next = f + 1 < n ? f + 1 : 0;
            if (!owner || !(preferred[(owner - 1u) >> 3] & (1u << ((owner - 1u) & 7u)))) {
                if (!owner || !mapped[owner - 1u]) { *hand = next; return f; }
                mapped[owner - 1u] = 0;
            }
            f = next;
        }
    }
    for (;;) {
        u32 owner = owners[f];
        *hand = f + 1 < n ? f + 1 : 0;
        if (!owner || !mapped[owner - 1u])
            return f;
        mapped[owner - 1u] = 0;
        f = *hand;
    }
}
#endif
