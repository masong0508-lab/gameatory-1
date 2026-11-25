/* Star-FlyBack B3 GPU bridge: exact game camera and clipped flat polygons.
   This header is independent of the GPU and of any private game data. */
#ifndef SF3_B3_GPU_H
#define SF3_B3_GPU_H
#define B3_ONE 16384
#define B3_MAX_VERTS 32

typedef struct {
    s32 pos[3], right[3], up[3], forward[3], focal;
} B3Camera;

static inline s32 b3_dot(const s32 *a, const s32 *b)
{
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}

/* B3 city accepts the mirrored outdoor camera only. Banked, inverted or
   extreme-height scenes retain the software renderer until B4. Never
   silently replace the game's camera with a second chase camera. */
static inline int b3_camera_ok(const B3Camera *c)
{
    if (!c || c->focal < 136 || c->focal > 176 ||
        c->pos[0] < -8192 || c->pos[0] > 139264 ||
        c->pos[2] < -8192 || c->pos[2] > 139264 ||
        c->pos[1] < -8192 || c->pos[1] > 12000 ||
        c->right[1] < -32 || c->right[1] > 32 || c->up[1] < 4096)
        return 0;
    const s32 *a[3] = {c->right,c->up,c->forward};
    for (int i=0;i<3;i++) {
        for (int j=0;j<3;j++)
            if (a[i][j] < -16448 || a[i][j] > 16448) return 0;
        s32 norm=b3_dot(a[i],a[i]);
        if (norm < 260000000 || norm > 277000000) return 0;
    }
    for (int i=0;i<3;i++) for (int j=i+1;j<3;j++) {
        s32 d=b3_dot(a[i],a[j]);
        if (d < -4000000 || d > 4000000) return 0;
    }
    s32 cross[3];
    for (int i=0;i<3;i++) {
        int j=(i+1)%3,k=(i+2)%3;
        cross[i]=(a[0][j]*a[1][k]-a[0][k]*a[1][j]) / B3_ONE;
    }
    return b3_dot(cross,a[2]) < -250000000;
}

/* L1 is scaled from 240x160 to 320x224 at y=8; use the same lens for
   the city and its native additions. GTE H is horizontal; the vertical
   row is scaled by Hy/Hx. Focal values are rounded only once. */
static inline int b3_hx(int focal) { return (4*focal+1)/3; }
static inline int b3_hy(int focal) { return (7*focal+2)/5; }

/* Input from r_poly/r_polyn is a clipped ring in 28.4 GBA pixels.
   Coordinates at 240 or 160 are valid exclusive viewport boundaries.
   Drawing area clips those boundary vertices, rather than shrinking
   the picture or distorting its right/bottom edge. */
static inline u32 b3_xy(s16 x,s16 y)
{
    u32 sx=(x+6)/12, sy=8+(7*y+40)/80;
    return sx | (sy<<16);
}
static inline int b3_flat_words(int n)
{
    if(n<3 || n>B3_MAX_VERTS) return -1;
    return n==4 ? 5 : 4*(n-2);
}

/* Opaque palette RGB, ring order. One linked-list node holds the whole
   convex polygon: either F4 in GPU Z order or a triangle fan. No partial
   packet on invalid input/short capacity. Max 120 GP0 words (<255). */
static inline int b3_flat_packet(u32 *out,u32 capacity,const s16 *xy,int n,u32 rgb)
{
    int words=b3_flat_words(n);
    if(words<0 || !out || !xy || (u32)words>capacity) return -1;
    for(int i=0;i<n;i++)
        if(xy[2*i]<0 || xy[2*i]>3840 || xy[2*i+1]<0 || xy[2*i+1]>2560)
            return -1;
    rgb &= 0xffffffu;
    if(n==4){
        out[0]=0x28000000u|rgb;
        out[1]=b3_xy(xy[0],xy[1]); out[2]=b3_xy(xy[2],xy[3]);
        out[3]=b3_xy(xy[6],xy[7]); out[4]=b3_xy(xy[4],xy[5]);
    }else{
        u32 first=b3_xy(xy[0],xy[1]);
        for(int i=1;i<n-1;i++){
            *out++=0x20000000u|rgb; *out++=first;
            *out++=b3_xy(xy[2*i],xy[2*i+1]);
            *out++=b3_xy(xy[2*i+2],xy[2*i+3]);
        }
    }
    return words;
}

/* GBA palette is BGR555; GP0 is 0x00BBGGRR. Bit 15 is ignored. */
static inline u32 b3_rgb555(u16 color)
{
    return ((u32)(color&31)<<3) | ((u32)(color&0x3e0)<<6) | ((u32)(color&0x7c00)<<9);
}

#ifdef SF3_B3_BRIDGE
int sf3_b3_begin(int oy,u32 map,const B3Camera *camera);
int sf3_b3_flat(const s16 *xy,int n,u16 color,int key,int bg);
int sf3_b3_end(void);
void sf3_b3_abort(void);
#endif
#endif
