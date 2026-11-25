/* B3 fixed-address scene overlays. Include after the runtime's u8/u32 types.
   The controller, scratch sector, callbacks and executing stack must be
   resident outside the slot. Only the resident scene dispatcher may call it. */
#ifndef SF_B3_SCENE_OVERLAY_H
#define SF_B3_SCENE_OVERLAY_H
#define SO_SECTOR 2048u
#define SO_MAGIC 0x31564f53u /* SOV1 */
#define SO_MAX_ENTRY 64u
#define SO_FLIGHT 1u
#define SO_STATION 2u
#define SO_MAX_SLOT 0x22000u

typedef struct { u32 id, offset; } SOEntry;
typedef struct {
    u8 *slot;
    u32 address, capacity, active, count, held, busy, generation;
    SOEntry entries[SO_MAX_ENTRY];
} SOState;
typedef struct {
    /* Synchronous sector read; false on failure. No asynchronous writers. */
    int (*read)(void *ctx,u32 lba,u32 sectors,u8 *dst);
    /* Drain previous GPU/DMA work, then invalidate translated dispatch entries.
       False means no write may occur. This must not flip or blank the screen. */
    int (*claim)(void *ctx,u32 address,u32 capacity);
    /* Flush executable cache after complete verified load; false on failure. */
    int (*sync)(void *ctx);
    void *ctx;
} SOOps;

static inline u32 so_word(const u8 *p){
    return (u32)p[0]|((u32)p[1]<<8)|((u32)p[2]<<16)|((u32)p[3]<<24);
}
static u32 so_crc(const u8 *p,u32 n){
    u32 c=0xffffffffu;
    while(n--){ c^=*p++; for(int i=0;i<8;i++) c=(c>>1)^(0xedb88320u & (0u-(c&1u))); }
    return ~c;
}
static inline int so_scene(u32 scene){ return scene==SO_FLIGHT || scene==SO_STATION; }
/* Subtract ordered addresses rather than adding unchecked lengths. */
static inline int so_disjoint(const void *a,u32 an,const void *b,u32 bn){
    __UINTPTR_TYPE__ x=(__UINTPTR_TYPE__)a,y=(__UINTPTR_TYPE__)b;
    return x<=y ? y-x>=an : x-y>=bn;
}
static inline int so_init(SOState *s,u8 *slot,u32 address,u32 capacity){
    if(!s || !slot || address<0x80010000u || address>=0x801f8000u ||
       (address&(SO_SECTOR-1u)) || !capacity || (capacity&(SO_SECTOR-1u)) ||
       capacity>SO_MAX_SLOT || capacity>0x801f8000u-address ||
       !so_disjoint(s,sizeof(*s),slot,capacity)) return 0;
#ifdef __mips__
    if((u32)slot!=address) return 0; /* reject an alias or incorrectly linked slot */
#endif
    s->slot=slot; s->address=address; s->capacity=capacity;
    s->active=s->count=s->held=s->busy=s->generation=0;
    return 1;
}
/* Header validation does not alter current residency. All sizes and offsets
   are checked before the first payload read. The 2K header CRC covers the
   entry table as well as the payload CRC. */
static int so_header(const SOState *s,const u8 *h,u32 scene,u32 lba){
    if(!so_scene(scene) || so_word(h)!=SO_MAGIC || so_word(h+4)!=1u ||
       so_word(h+8)!=scene || so_word(h+12)!=s->address ||
       so_word(h+16)!=s->capacity || so_crc(h,SO_SECTOR-4)!=so_word(h+SO_SECTOR-4)) return 0;
    u32 bytes=so_word(h+20), sectors=so_word(h+24), count=so_word(h+32);
    if(!bytes || (bytes&3u) || bytes>s->capacity || !sectors ||
       sectors!=(bytes+SO_SECTOR-1u)/SO_SECTOR || sectors>s->capacity/SO_SECTOR ||
       !count || count>SO_MAX_ENTRY || lba>0xffffffu-sectors || so_word(h+36)) return 0;
    u32 prev=0;
    for(u32 i=0;i<count;i++){
        u32 id=so_word(h+40+8*i),off=so_word(h+44+8*i);
        if(id<=prev || (off&3u) || off>=bytes) return 0;
        prev=id;
    }
    return 1;
}
/* 1 ready, 0 refused/failed. native_depth must be zero at the resident
   transition boundary (including callbacks into guest code). If a payload
   read or CRC fails, the slot becomes invalid: never run the old or partial
   code. Caller keeps displaying the previous frame and uses resident recovery.
   Scratch must be a separate resident sector and cannot overlap the slot. */
static int so_select(SOState *s,const SOOps *op,u8 *scratch,u32 scene,u32 lba,u32 native_depth){
    if(!s || !op || !op->read || !op->claim || !op->sync || !scratch ||
       !s->slot || !s->capacity || s->busy || s->held || native_depth ||
       !so_scene(scene) || lba>0xffffffu ||
       !so_disjoint(scratch,SO_SECTOR,s->slot,s->capacity) ||
       !so_disjoint(scratch,SO_SECTOR,s,sizeof(*s)) ||
       !so_disjoint(scratch,SO_SECTOR,op,sizeof(*op)) ||
       !so_disjoint(op,sizeof(*op),s->slot,s->capacity)) return 0;
    if(s->active==scene) return 1;
    s->busy=1;
    if(!op->read(op->ctx,lba,1,scratch) || !so_header(s,scratch,scene,lba) ||
       !op->claim(op->ctx,s->address,s->capacity)){ s->busy=0; return 0; }
    u32 sectors=so_word(scratch+24),count=so_word(scratch+32),crc=so_word(scratch+28);
    s->active=0; s->count=0; s->generation++;
    if(!op->read(op->ctx,lba+1,sectors,s->slot) ||
       so_crc(s->slot,sectors*SO_SECTOR)!=crc){ s->busy=0; return 0; }
    /* No stale bytes from a larger previous overlay. */
    for(u32 i=sectors*SO_SECTOR;i<s->capacity;i++) s->slot[i]=0;
    if(!op->sync(op->ctx)){ s->busy=0; return 0; }
    for(u32 i=0;i<count;i++){
        s->entries[i].id=so_word(scratch+40+8*i);
        s->entries[i].offset=so_word(scratch+44+8*i);
    }
    s->count=count; s->active=scene; s->busy=0;
    return 1;
}
/* The resident dispatcher must call the returned address synchronously,
   and release only after it returns. Never cache/export a raw slot pointer. */
static u8 *so_enter(SOState *s,u32 scene,u32 id){
    if(!s || s->busy || s->held || !s->active || s->active!=scene || !id) return 0;
    u32 lo=0,hi=s->count;
    while(lo<hi){
        u32 mid=(lo+hi)>>1,key=s->entries[mid].id;
        if(key<id) lo=mid+1; else if(key>id) hi=mid;
        else{ s->held=1; return s->slot+s->entries[mid].offset; }
    }
    return 0;
}
static inline int so_leave(SOState *s){
    if(!s || !s->held || s->busy) return 0;
    s->held=0; return 1;
}
#endif
