/* Retain Start/A edges until the authoritative guest low KEYINPUT read
 * receives them. A native rendering read or a PADSPLIT-deferred press
 * must not acknowledge an edge. */
#ifndef B3_KEY_EDGES_H
#define B3_KEY_EDGES_H
typedef struct { unsigned pending,physical; } B3KeyEdges;
static inline void b3_key_observe(B3KeyEdges *s,unsigned k,int level){
    unsigned dn=(~k)&9u;
    if(level) s->pending|=dn&~s->physical;
    else s->pending=0;
    s->physical=dn;
}
static inline unsigned b3_key_before(B3KeyEdges *s,int level,int guest){
    if(!level) s->pending=0;
    return level&&guest?s->pending:0;
}
static inline void b3_key_after(B3KeyEdges *s,unsigned k,int level,int guest){
    if(!level) s->pending=0;
    else if(guest) s->pending&=k;
}
#endif
