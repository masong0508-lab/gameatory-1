/* The radio's stream encoder (tools/mkradio.py loads it with ctypes; src/radiodec.s decodes).

   Mono 16-bit samples (8-bit full scale = +-32768) at Payback's mixing rate, in segments of 480
   samples, one per sound interrupt. A segment is 15 frames of 32 samples at 2 or 4 bits each:
       u8 bits, u8 head[15] (predictor << 6 | step), codes (frame by frame, 32-bit words, first
       sample in the lowest bits), 136 or 256 bytes in all
   Sample i of a frame: v = pred(k, a, b) + c * STEP[s], c the signed code; a, b the last two v.
   The levels include zero (silence stays silent). The predictors have whole coefficients, so
   the decoder can run on v * volume throughout (the same sums, scaled) and needs no multiply
   per sample for the volume; the steps go in quarter octaves.
   The encoder tries every predictor and the steps near the frame's level, and keeps the least
   squared error; mkradio.py chooses 2 or 4 bits per segment for the whole budget at once. */
#include <stdint.h>
#include <string.h>
#include <math.h>
typedef int16_t s16; typedef uint8_t u8; typedef int64_t s64;
#define SEG 480
#define FL 32
#define NFR (SEG / FL)
#define NS 64
static int STEP[NS];

static void init(void)
{
    for (int s = 0; s < NS; s++)
        STEP[s] = (int)floor(pow(2.0, (s + 2) / 4.0) + 0.5);
}

static inline int pred(int k, int a, int b)
{
    return k == 0 ? 0 : k == 1 ? a : k == 2 ? 2 * a - b : a - b;
}

typedef struct { int a, b; } St;

/* one frame from st with predictor k, step s: squared error (or INT64_MAX past bail / no fit) */
static s64 frame(const s16 *x, St *st, int k, int s, int bits, u8 *codes, s64 bail)
{
    int a = st->a, b = st->b, st_ = STEP[s], lo = -(1 << (bits - 1)), hi = (1 << (bits - 1)) - 1;
    s64 e = 0;
    for (int i = 0; i < FL; i++) {
        int p = pred(k, a, b), d = x[i] - p;
        int c = d >= 0 ? (d + st_ / 2) / st_ : -((-d + st_ / 2 - 1) / st_);
        c = c < lo ? lo : c > hi ? hi : c;
        int v = p + c * st_;
        while (v > 32767 && c > lo) v = p + --c * st_;
        while (v < -32768 && c < hi) v = p + ++c * st_;
        if (v > 32767 || v < -32768)
            return INT64_MAX;
        if (codes)
            codes[i] = c & ((1 << bits) - 1);
        s64 r = x[i] - v;
        e += r * r;
        if (e >= bail)
            return INT64_MAX;
        b = a;
        a = v;
    }
    st->a = a;
    st->b = b;
    return e;
}

/* a segment at 'bits' from st: its squared error; head and codes when asked */
static s64 segment(const s16 *x, St *st, int bits, u8 *head, u8 *codes)
{
    s64 D = 0;
    for (int f = 0; f < NFR; f++) {
        const s16 *xf = x + f * FL;
        s64 ss = 0;
        int pa = st->a;
        for (int i = 0; i < FL; i++) {
            int r = xf[i] - pa;
            ss += (s64)r * r;
            pa = xf[i];
        }
        /* the step that would spread this frame's first-difference level over the codes, +-6 */
        int c = (int)floor(4 * log2((sqrt((double)ss / FL) + 1) / (1 << (bits - 1)) + 1e-9)) - 2;
        int s0 = c - 6 < 0 ? 0 : c - 6 > NS - 1 ? NS - 1 : c - 6, s1 = c + 6 > NS - 1 ? NS - 1 : c + 6;
        s64 be = INT64_MAX;
        int bk = 0, bs = 0;
        for (int pass = 0; pass < 2 && be == INT64_MAX; pass++, s0 = 0, s1 = NS - 1)
            for (int k = 0; k < 4; k++)
                for (int s = s0; s <= s1; s++) {
                    St t = *st;
                    s64 e = frame(xf, &t, k, s, bits, 0, be);
                    if (e < be)
                        be = e, bk = k, bs = s;
                }
        frame(xf, st, bk, bs, bits, codes ? codes + f * FL : 0, INT64_MAX);
        if (head)
            head[f] = bk << 6 | bs;
        D += be;
    }
    return D;
}

static void seg_in(const s16 *x, int n, int g, s16 *xb)
{
    int m = n - g * SEG < SEG ? n - g * SEG : SEG;
    memcpy(xb, x + g * SEG, m * 2);
    memset(xb + m, 0, (SEG - m) * 2);
}

/* the squared error of every segment at 2 and at 4 bits (D[2g], D[2g+1]), each from the state
   that 4 bits would leave (a close stand-in for the state the final choice leaves) */
void radenc_errors(const s16 *x, int n, s64 *D)
{
    init();
    St st = {0, 0};
    s16 xb[SEG];
    for (int g = 0; g * SEG < n; g++) {
        seg_in(x, n, g, xb);
        St t = st;
        D[2 * g] = segment(xb, &t, 2, 0, 0);
        D[2 * g + 1] = segment(xb, &st, 4, 0, 0);
    }
}

/* the stream for the given bits per segment; returns its bytes. rec: the decoded samples */
long radenc_encode(const s16 *x, int n, const u8 *bits, u8 *out, s16 *rec)
{
    init();
    St st = {0, 0};
    s16 xb[SEG];
    u8 head[NFR], codes[SEG];
    long o = 0;
    for (int g = 0; g * SEG < n; g++) {
        int b = bits[g];
        seg_in(x, n, g, xb);
        St t = st;
        segment(xb, &st, b, head, codes);
        for (int f = 0; f < NFR; f++)       /* (what the decoder will make of it) */
            for (int i = 0; i < FL; i++) {
                int c = codes[f * FL + i], j = g * SEG + f * FL + i;
                c = c >= 1 << (b - 1) ? c - (1 << b) : c;
                int v = pred(head[f] >> 6, t.a, t.b) + c * STEP[head[f] & 63];
                if (j < n)
                    rec[j] = v;
                t.b = t.a;
                t.a = v;
            }
        out[o++] = b;
        memcpy(out + o, head, NFR);
        o += NFR;
        for (int f = 0; f < NFR; f++)
            for (int w = 0; w < FL * b / 32; w++) {
                uint32_t word = 0;
                for (int i = 0; i < 32 / b; i++)
                    word |= (uint32_t)codes[f * FL + w * (32 / b) + i] << (i * b);
                for (int k = 0; k < 4; k++)
                    out[o++] = word >> (8 * k);
            }
    }
    return o;
}
