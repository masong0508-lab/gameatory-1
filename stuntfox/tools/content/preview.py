"""Atlas pictures for the authors (sfc preview): the map's cells by kind and height with places drawn over it. Host tools only."""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import atlas  # noqa: E402

S = 6                                         # pixels a cell


def _shade(h):
    """Building and deck tops: darker low, lighter high."""
    v = max(0, min(255, 70 + h * 150 // 10240))
    return (v, v, min(255, v + 25))


def render(a, places=(), routes=(), path=None):
    """places: [(name, x, y, kind)] in cells; routes: [[(x, y), ...]]."""
    im = Image.new('RGB', (atlas.N * S, atlas.N * S), (20, 24, 28))
    d = ImageDraw.Draw(im)
    for i in range(atlas.N * atlas.N):
        x, y = divmod(i, atlas.N)
        k = a.kind[i]
        if a.water[i]:
            c = (30, 70, 140)
        elif k == 'building':
            c = _shade(a.hi[i])
        elif k == 'road':
            c = (60, 60, 64)
        elif k == 'kerb':
            c = (90, 90, 80)
        elif k == 'ramp':
            c = (140, 110, 60)
        else:
            c = (55, 110, 60) if a.lo[i] == 0 else (40, 90, 50)
        if i in a.deck and k != 'building':
            c = tuple(min(255, v + 60) for v in _shade(a.deck[i][1]))
        d.rectangle([x * S, y * S, x * S + S - 1, y * S + S - 1], fill=c)
    for r in routes:
        d.line([(x * S, y * S) for x, y in r], fill=(255, 220, 0), width=2)
    col = {2: (255, 80, 80), 3: (255, 80, 80), 4: (255, 80, 255), 1: (80, 255, 255), 7: (255, 255, 80)}
    for name, x, y, kind in places:
        c = col.get(kind, (255, 255, 255))
        d.ellipse([x * S - 3, y * S - 3, x * S + 3, y * S + 3], outline=c)
    for g in range(0, atlas.N, 16):
        d.line([(g * S, 0), (g * S, atlas.N * S)], fill=(0, 0, 0))
        d.line([(0, g * S), (atlas.N * S, g * S)], fill=(0, 0, 0))
        d.text((g * S + 2, 2), str(g), fill=(255, 255, 255))
        d.text((2, g * S + 2), str(g), fill=(255, 255, 255))
    if path:
        im.save(path)
    return im
