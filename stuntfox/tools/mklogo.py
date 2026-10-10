"""Draws the STAR-FLYBACK title art at build time (our own letters; nothing comes from Payback).

Payback's title is a battered typewriter slab serif, white-hot letters in an orange fire glow.
This draws the new name the same way, from scratch: each capital is a few strokes with slab
serifs (GLYPHS, in units of the cap height), rendered from their distance field with inky,
worn edges, then lit with a heat ramp (white-hot core, yellow, orange, red, dark) from blurred
copies of the letters, rising flame noise and a burst behind the middle of the word.

Writes gen/logo.c with
    sf_title_card[240 * 160]   the title screen (mode 3, BGR555) that replaces Payback's intro film
    sf_menu_logo[LOGO_W * LOGO_H]   the menu and credits logo, as indices of Payback's own BG
                               palette; Payback's blitter mixes it into the picture through its
                               lighten table, so index 0 (black) leaves the picture alone
Payback's palette and that table are read from the player's ROM to choose the indices.
Pure Python (no numpy or PIL), so the build needs nothing new. `python3 mklogo.py ROM DIR`
also writes PNG previews into DIR.
"""
import math
import random
import struct
import sys
import zlib

TITLE = 'STAR-FLYBACK'
LOGO_W, LOGO_H = 200, 63            # menu logo (Payback's was 128 x 63)
PALETTE = 0x6367a8                  # Payback's BG palette (red and blue swapped)
LIGHTEN = 0x68dbaa                  # its 256 x 256 colour table the menu blits the logo through

HW = 0.085                          # half-width of a stem, cap height = 1
SW = 0.05                           # half-width of a serif


def arc(cx, cy, rx, ry, a0, a1, n=16):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def S(*pts):
    """a serif (thinner stroke)"""
    return (list(pts), SW)


def M(*pts):
    return (list(pts), HW)


# advance width, strokes ((points, half-width)); y grows downwards, stems run from 0.1 to 0.9
GLYPHS = {
    'S': (0.62, [(arc(0.31, 0.29, 0.24, 0.19, -25, -270), HW),
                 (arc(0.31, 0.7, 0.26, 0.2, -90, 155), HW),
                 S((0.55, 0.12), (0.55, 0.31)), S((0.07, 0.69), (0.07, 0.89))]),
    'T': (0.66, [M((0.05, 0.1), (0.61, 0.1)), M((0.33, 0.1), (0.33, 0.9)),
                 S((0.18, 0.9), (0.48, 0.9)), S((0.05, 0.1), (0.05, 0.27)), S((0.61, 0.1), (0.61, 0.27))]),
    'A': (0.76, [M((0.38, 0.1), (0.1, 0.9)), M((0.38, 0.1), (0.66, 0.9)), M((0.22, 0.6), (0.54, 0.6)),
                 S((0.0, 0.9), (0.22, 0.9)), S((0.55, 0.9), (0.77, 0.9)), S((0.26, 0.1), (0.4, 0.1))]),
    'R': (0.7, [M((0.13, 0.1), (0.13, 0.9)), M((0.03, 0.1), (0.38, 0.1)), (arc(0.38, 0.3, 0.2, 0.2, -90, 90), HW),
                M((0.13, 0.5), (0.38, 0.5)), M((0.36, 0.52), (0.6, 0.9)),
                S((0.02, 0.9), (0.26, 0.9)), S((0.52, 0.9), (0.71, 0.9))]),
    '-': (0.42, [M((0.08, 0.58), (0.33, 0.58))]),
    'F': (0.62, [M((0.13, 0.1), (0.13, 0.9)), M((0.03, 0.1), (0.58, 0.1)), S((0.58, 0.1), (0.58, 0.25)),
                 M((0.13, 0.53), (0.4, 0.53)), S((0.02, 0.9), (0.28, 0.9))]),
    'L': (0.62, [M((0.15, 0.1), (0.15, 0.9)), M((0.15, 0.9), (0.57, 0.9)), S((0.03, 0.1), (0.29, 0.1)),
                 S((0.57, 0.72), (0.57, 0.9))]),
    'Y': (0.72, [M((0.12, 0.1), (0.36, 0.52)), M((0.6, 0.1), (0.36, 0.52)), M((0.36, 0.52), (0.36, 0.9)),
                 S((0.0, 0.1), (0.24, 0.1)), S((0.49, 0.1), (0.72, 0.1)), S((0.22, 0.9), (0.5, 0.9))]),
    'B': (0.68, [M((0.13, 0.1), (0.13, 0.9)), M((0.03, 0.1), (0.37, 0.1)), (arc(0.37, 0.29, 0.19, 0.19, -90, 90), HW),
                 M((0.13, 0.48), (0.39, 0.48)), (arc(0.39, 0.69, 0.22, 0.21, -90, 90), HW),
                 M((0.03, 0.9), (0.39, 0.9))]),
    'C': (0.68, [(arc(0.37, 0.5, 0.28, 0.4, -42, -318, 24), HW),
                 S((0.6, 0.12), (0.6, 0.33)), S((0.6, 0.67), (0.6, 0.88))]),
    'K': (0.72, [M((0.13, 0.1), (0.13, 0.9)), M((0.15, 0.6), (0.58, 0.1)), M((0.31, 0.43), (0.61, 0.9)),
                 S((0.02, 0.1), (0.25, 0.1)), S((0.02, 0.9), (0.25, 0.9)),
                 S((0.47, 0.1), (0.71, 0.1)), S((0.5, 0.9), (0.73, 0.9))]),
}
TRACK = 0.09                        # space between letters


class Noise:
    """smooth value noise in -1..1"""
    def __init__(self, seed):
        r = random.Random(seed)
        self.p = [r.random() * 2 - 1 for _ in range(4096)]

    def __call__(self, x, y):
        i, j = math.floor(x), math.floor(y)
        fx, fy = x - i, y - j
        sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        p = self.p
        a = p[(i * 73856093 ^ j * 19349663) & 4095]
        b = p[((i + 1) * 73856093 ^ j * 19349663) & 4095]
        c = p[(i * 73856093 ^ (j + 1) * 19349663) & 4095]
        d = p[((i + 1) * 73856093 ^ (j + 1) * 19349663) & 4095]
        return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy


def text_width(text):
    return sum(GLYPHS[c][0] for c in text) + TRACK * (len(text) - 1)


def render_text(text, cap, w, h, cx, top, seed):
    """coverage (0..1) of the battered letters, centred on cx; the cap height is cap pixels"""
    mask = [0.0] * (w * h)
    edge = Noise(seed)              # inky, wobbly edges
    wear = Noise(seed + 1)          # worn patches inside the strokes
    jit = random.Random(seed + 2)
    x = cx - text_width(text) * cap / 2
    for ch in text:
        adv, strokes = GLYPHS[ch]
        dy = top + jit.uniform(-0.035, 0.035) * cap      # typewriter letters never sit quite level
        dx = x + jit.uniform(-0.02, 0.02) * cap
        segs = []
        for pts, hw in strokes:
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                segs.append((dx + ax * cap, dy + ay * cap, dx + bx * cap, dy + by * cap, hw * cap))
        x0 = max(0, int(dx - 0.15 * cap)); x1 = min(w, int(dx + (adv + 0.15) * cap) + 1)
        y0 = max(0, int(dy - 0.1 * cap)); y1 = min(h, int(dy + 1.1 * cap) + 1)
        for py in range(y0, y1):
            fy = py + 0.5
            for px in range(x0, x1):
                fx = px + 0.5
                best = -1e9
                for ax, ay, bx, by, hw in segs:
                    vx, vy = bx - ax, by - ay
                    ll = vx * vx + vy * vy
                    t = ((fx - ax) * vx + (fy - ay) * vy) / ll if ll else 0.0
                    t = 0.0 if t < 0 else 1.0 if t > 1 else t
                    ex, ey = fx - ax - t * vx, fy - ay - t * vy
                    v = hw - math.sqrt(ex * ex + ey * ey)
                    if v > best:
                        best = v
                u, v = fx / cap, fy / cap
                best += cap * (0.035 * edge(u * 9, v * 9) + 0.02 * edge(u * 23 + 40, v * 23))
                c = best + 0.5
                if c <= 0:
                    continue
                c = 1.0 if c > 1 else c
                n = wear(u * 14, v * 14) + 0.5 * wear(u * 37 + 9, v * 37)
                if n > 0.55:
                    c *= 0.62               # dry ink: darker pits in the white-hot letters
                k = py * w + px
                if c > mask[k]:
                    mask[k] = c
        x += (adv + TRACK) * cap
    return mask


def blur(src, w, h, rx, ry=None, passes=3):
    """box blur repeated (close to a gaussian); zero outside the picture"""
    ry = rx if ry is None else ry
    a = list(src)
    for _ in range(passes):
        if rx > 0:
            n = 2 * rx + 1
            out = [0.0] * (w * h)
            for y in range(h):
                row = a[y * w:(y + 1) * w]
                s = sum(row[:rx])
                for x in range(w):
                    if x + rx < w:
                        s += row[x + rx]
                    out[y * w + x] = s / n
                    if x - rx >= 0:
                        s -= row[x - rx]
            a = out
        if ry > 0:
            n = 2 * ry + 1
            out = [0.0] * (w * h)
            for x in range(w):
                col = a[x::w]
                s = sum(col[:ry])
                for y in range(h):
                    if y + ry < h:
                        s += col[y + ry]
                    out[y * w + x] = s / n
                    if y - ry >= 0:
                        s -= col[y - ry]
            a = out
    return a


HEAT = [(0.0, (0.0, 0.0, 0.0)), (0.16, (0.3, 0.02, 0.0)), (0.36, (0.75, 0.12, 0.01)),
        (0.56, (1.0, 0.38, 0.04)), (0.76, (1.0, 0.68, 0.2)), (0.92, (1.0, 0.9, 0.62)),
        (1.05, (1.0, 0.98, 0.9))]


def heat(t):
    if t <= 0:
        return HEAT[0][1]
    for (t0, c0), (t1, c1) in zip(HEAT, HEAT[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(a + (b - a) * f for a, b in zip(c0, c1))
    return HEAT[-1][1]


def fire(w, h, cap, cx, top, seed, burst=1.0, backdrop=True, hot=1.0, glow=1.0):
    """the lit title: rgb triples 0..1 per pixel"""
    m = render_text(TITLE, cap, w, h, cx, top, seed)
    inner = blur(m, w, h, max(1, cap // 16), passes=2)   # 1 deep inside a stroke, less at its edge
    g1 = blur(m, w, h, 1)
    g2 = blur(m, w, h, max(2, cap // 8))
    g3 = blur(m, w, h, max(4, cap // 3), max(3, cap // 5))
    flame = Noise(seed + 5)
    drip = Noise(seed + 6)
    ray = Noise(seed + 7)
    by = top + cap * 0.5
    out = []
    for y in range(h):
        for x in range(w):
            k = y * w + x
            # flames lick upwards: glow sampled from below, broken into tongues
            yy = min(h - 1, y + max(1, cap // 6))
            up = g3[yy * w + x]
            f = 0.55 + 0.45 * flame(x / (cap * 0.16), y / (cap * 0.7) + x * 0.01)
            f2 = 0.6 + 0.4 * flame(x / (cap * 0.07) + 50, y / (cap * 0.25))
            dx, dy = (x - cx) / (cap * 2.6), (y - by) / (cap * 0.9)
            r = math.sqrt(dx * dx + dy * dy)
            ang = math.atan2(dy, dx)
            rays = 0.5 + 0.5 * ray(ang * 5 + 20, 0.3)
            b = burst * (math.exp(-r * 1.6) * (0.3 + 0.7 * rays) +
                         0.5 * math.exp(-abs(y - by) / (cap * 0.12)) * math.exp(-abs(x - cx) / (cap * 3.2)) +
                         0.4 * math.exp(-r * 6) +       # the flare in the middle, and its light
                         0.3 * math.exp(-abs(x - cx) / (cap * 0.3)) * math.exp(-abs(y - by) / (cap * 1.4)))
            t = (m[k] * hot * (0.5 + 0.62 * inner[k] * inner[k]) + glow * (0.45 * g1[k] + 0.9 * g2[k] * f) +
                 min(0.7, 1.25 * up * f * f2 + 0.85 * b * f))   # (the glow never outshines the letters)
            rgb = heat(t)
            if backdrop:
                # the dark, streaky wall behind (fire-lit near the letters)
                d = drip(x / 3.1, y / 38.0 + 0.4 * drip(x / 17.0, 3.3))
                d = max(0.0, d) ** 1.5
                lit = 0.25 + 0.75 * min(1.0, up * 3 + b)
                fade = 1.0 - (abs(y - by) / (h * 0.75)) ** 2
                v = 0.2 * d * lit * max(0.0, fade)
                rgb = (rgb[0] + v * 0.9, rgb[1] + v * 0.5, rgb[2] + v * 0.25)
            out.append(rgb)
    return out


BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5]


def to_bgr555(rgb, w, h):
    px = []
    for k, (r, g, b) in enumerate(rgb):
        d = (BAYER[(k // w & 3) * 4 + (k % w & 3)] + 0.5) / 16
        c = [min(31, int(v * 31 + d)) if v > 0 else 0 for v in (r, g, b)]
        px.append(c[0] | c[1] << 5 | c[2] << 10)
    return px


def title_card():
    w, h = 240, 160
    rgb = fire(w, h, 26, 120, 62, 1977)
    return to_bgr555(rgb, w, h), rgb


def menu_logo(rom):
    """our logo in Payback's menu palette: the index whose blend best matches each pixel"""
    pal = []
    for i in range(256):
        c = struct.unpack_from('<H', rom, PALETTE + 2 * i)[0]
        pal.append((c >> 10 & 31, c >> 5 & 31, c & 31))
    lut = rom[LIGHTEN:LIGHTEN + 65536]
    darks = [t for t, c in enumerate(pal) if sum(c) <= 6]
    cand = []
    for s in range(1, 256):         # colours that come out as themselves over black
        c = pal[s]
        if c[2] > c[1] + 2 or c in [pal[k] for k in cand]:
            continue                # (and no blues or purples: they never appear in fire)
        if all(sum(abs(a - b) for a, b in zip(pal[lut[s * 256 + t]], c)) <= 3 for t in darks):
            cand.append(s)
    rgb = fire(LOGO_W, LOGO_H, 22, LOGO_W // 2, 20, 1984, burst=0.55, backdrop=False, hot=0.85, glow=0.7)
    out = []
    for k, (r, g, b) in enumerate(rgb):
        d = (BAYER[(k // LOGO_W & 3) * 4 + (k % LOGO_W & 3)] + 0.5) / 16 - 0.5
        c = (r * 31 + d, g * 31 + d, b * 31 + d)
        if max(c) < 4.5:            # (faint glow would only tint the picture)
            out.append(0)
            continue
        best, bi = 1e9, 0
        for s in cand:
            p = pal[s]
            e = 3 * (p[0] - c[0]) ** 2 + 4 * (p[1] - c[1]) ** 2 + 2 * (p[2] - c[2]) ** 2
            if e < best:
                best, bi = e, s
        out.append(bi)
    return out, pal


def png(path, w, h, rgb):
    raw = b''.join(b'\0' + bytes(min(255, int(v * 255)) for px in rgb[y * w:(y + 1) * w] for v in px)
                   for y in range(h))
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
                chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def main(rom, out_c, preview=None):
    card, card_rgb = title_card()
    logo, pal = menu_logo(rom)
    with open(out_c, 'w') as f:
        f.write('/* generated by tools/mklogo.py: the STAR-FLYBACK title art, drawn at build time */\n')
        f.write('#include "../../src/gba.h"\n')
        f.write('const u16 sf_title_card[240 * 160] = {\n')
        for i in range(0, len(card), 16):
            f.write(','.join('0x%04x' % v for v in card[i:i + 16]) + ',\n')
        f.write('};\nconst u8 sf_menu_logo[%d * %d] = {\n' % (LOGO_W, LOGO_H))
        for i in range(0, len(logo), 32):
            f.write(','.join('%d' % v for v in logo[i:i + 32]) + ',\n')
        f.write('};\n')
    if preview:
        import os
        png(os.path.join(preview, 'title_card.png'), 240, 160,
            [((v & 31) / 31, (v >> 5 & 31) / 31, (v >> 10 & 31) / 31) for v in card])
        png(os.path.join(preview, 'menu_logo.png'), LOGO_W, LOGO_H,
            [tuple(c / 31 for c in pal[i]) for i in logo])


if __name__ == '__main__':
    main(open(sys.argv[1], 'rb').read(), '/dev/null', sys.argv[2] if len(sys.argv) > 2 else None)
