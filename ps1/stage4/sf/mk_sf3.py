import re
s=open('sf_orig.c').read()
def rep(a,b,cnt=1):
    global s
    assert s.count(a)>=1,('missing',a[:60])
    s=s.replace(a,b) if cnt==0 else s.replace(a,b,cnt)
rep('extern const u8 world_blob[], atlas_blob[], clut_blob[], side_blob[], font_blob[];',
    '#include "sfmem.h"\nextern const u8 side_blob[];')
# world pointers
rep('static const Box *boxes; static const u8 *lots_; static const Ramp *ramps; static const u16 *sector, *items; static const Cell *cells;',
    'static const Box *boxes; static const Ramp *ramps; static const u16 *sector, *items; static const u16 *cellidx; static const Cell *celldict;')
rep('static const Tree *trees; static const u16 *ctex, *btex, *dtex; static const s8 *deck;','static const Tree *trees; static const u16 *ctex, *btex, *dtex; static const u8 *deckl; static int ndeck;')
rep('static const u8 *wall_;\n','')
a=s.index('static void world_init(void) {'); b=s.index('}\n',a)+2
s=s[:a]+'''static void world_init(void) {
  const u8 *b = (const u8 *)SF_WORLD; const u32 *h = (const u32 *)b;
  nbox = h[1]; nramp = h[2]; ntree = h[3]; ndeck = h[5];
  boxes = (const Box *)(b + h[6]); ramps = (const Ramp *)(b + h[7]); sector = (const u16 *)(b + h[8]); items = (const u16 *)(b + h[9]);
  trees = (const Tree *)(b + h[10]); ctex = (const u16 *)(b + h[11]); btex = (const u16 *)(b + h[12]); dtex = (const u16 *)(b + h[13]);
  cellidx = (const u16 *)(b + h[14]); celldict = (const Cell *)(b + h[15]); deckl = b + h[16];
  side = (const Side *)side_blob;
}
static const s8 zero4[4];
static const s8 *deck_get(int i) {   /* sparse deck table: sorted (u16 cell, s8 d[4]) records of 6 bytes */
  int lo = 0, hi = ndeck - 1;
  while (lo <= hi) { int m = (lo + hi) >> 1; const u8 *p = deckl + 6 * m; int k = p[0] | p[1] << 8; if (k == i) return (const s8 *)(p + 2); if (k < i) lo = m + 1; else hi = m - 1; }
  return zero4;
}
'''+s[b:]
rep('#define PBW 40000\nstatic u32 pbuf[2][PBW];\nstatic u32 otab[2][OTN];','#define PBW SF_PBW\n#define pbuf ((u32 (*)[PBW])SF_PBUF)\n#define otab ((u32 (*)[OTN])SF_OT)')
rep('static u16 st_box[3072], st_ramp[1024], st_tree[2304]; static u16 stamp;','#define st_box ((u16 *)SF_ST)\n#define st_ramp ((u16 *)(SF_ST + 6144))\n#define st_tree ((u16 *)(SF_ST + 8192))\nstatic u16 stamp;')
rep('cells[nx * 128 + nz].hi','celldict[cellidx[nx * 128 + nz]].hi')
rep('const Cell *c = &cells[i];','const Cell *c = &celldict[cellidx[i]];')
rep('const s8 *d = &deck[4 * i];','const s8 *d = deck_get(i);')
# cut everything from the vram upload section on
a=s.index('static void upload_all(void) {'); 
s=s[:a]
open('sf3_head.c','w').write(s)
print(len(s))
