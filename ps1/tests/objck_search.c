/* objck_search.c (rc10.2): host search for misses of the OBJ tile change check (ppu12.h pp_objck: checks A and B of each block of 512 of
   the 4096 tile words; pp_obj compares the blocks the sprites use).
   ROM-free: synthetic tile data only.  Built and run by objck_search.py, which cuts the PP_OBJCK block out of ppu12.h into objck_cut.h, so
   the search runs the C that defines the check (PP_OBJCK_STEP, the seeds) and calls pp_objck itself for every miss and for samples.

   A miss is a changed buffer with the same (A,B) as the base in every block (so the search treats every block as used).  Every step of A
   and of B is a bijection of its state for a fixed word, so a change spanning words lo..hi of a block gives the same result exactly when
   the states after word hi are the same: each try runs the steps over the changed part of each block only, from the base's states (and a
   sample of the tries is checked against pp_objck of every block).
   Per class: tries (changed buffers), full misses (A and B equal: must be 0), A-only and B-only equalities (32-bit: about tries/2^32 by
   chance; classes built to cancel one check say so and that check's count is then every try).

   usage: objck_search TRIES_PER_CLASS [SEED] [CLASS (-1: all)] [DUMPFILE K]   prints one line per class and "TOTAL ... misses N"; exit 1 when a class has a miss
   or the windowed model disagrees with pp_objck.  DUMPFILE K: up to K changed buffers per class are written as (class, base[4096],
   changed[4096]) little-endian words, for test_objhash.py to run through the MIPS loop. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
typedef uint32_t u32;
#include "objck_cut.h"
#define N 4096
static uint64_t rs;
static u32 rnd(void){ rs^=rs<<13; rs^=rs>>7; rs^=rs<<17; return (u32)(rs>>11)^(u32)(rs>>43); }
static u32 rn(u32 n){ return (u32)(((uint64_t)rnd()*n)>>32); }
static u32 base[N+2], x[N+2];
#define BW 512                                /* words per block (pp_objck) */
static u32 PA[N+1], PB[N+1], QA[N], QB[N];    /* states before / after word i, inside its block */
static u32 H0[N/BW][2];
static const u32 KA=PP_OBJCK_KA, KB=PP_OBJCK_KB;
static u32 inv(u32 k){ u32 v=k; for(int i=0;i<5;i++) v*=2u-k*v; return v; }

/* ---- bases */
#define NBASE 8
static const char*bname[NBASE]={"zeros","random","sparse 4bpp sprites","dense 4bpp sprites","sparse 8bpp sprites","4bpp few colours",
  "half random","font-like 1bpp in 4bpp"};
static u32 nib4(int dens){ u32 w=0; for(int n=0;n<8;n++){ u32 c=(rn(100)<(u32)dens)?1+rn(15):0; w|=c<<(4*n); } return w; }
static void mkbase(int k){
  memset(base,0,sizeof base);
  switch(k){
  case 0: break;
  case 1: for(int i=0;i<N;i++) base[i]=rnd(); break;
  case 2: for(int t=0;t<512;t++) if(rn(4)==0) for(int r=0;r<8;r++) base[t*8+r]=nib4(40); break;
  case 3: for(int i=0;i<N;i++) base[i]=nib4(70); break;
  case 4: for(int t=0;t<256;t++) if(rn(4)==0) for(int r=0;r<16;r++){ u32 w=0; for(int n=0;n<4;n++) w|=(rn(2)?1+rn(255):0)<<(8*n); base[t*16+r]=w; } break;
  case 5: for(int i=0;i<N;i++){ u32 w=0; for(int n=0;n<8;n++) w|=(rn(3)?0:1+rn(3))<<(4*n); base[i]=w; } break;
  case 6: for(int i=0;i<N/2;i++) base[i]=rnd(); break;
  case 7: for(int t=0;t<512;t++) if(rn(2)) for(int r=0;r<8;r++){ u32 w=0; for(int n=0;n<8;n++) if(rn(3)==0) w|=1u<<(4*n); base[t*8+r]=w*(1+rn(15)); } break;
  }
  u32 a=0, b=0;
  for(int i=0;i<N;i++){ if(i%BW==0){ a=PP_OBJCK_A0; b=PP_OBJCK_B0; } PA[i]=a; PB[i]=b; PP_OBJCK_STEP(a,b,base[i]); QA[i]=a; QB[i]=b;
    if(i%BW==BW-1){ pp_objck(base+i-(BW-1),H0[i/BW]); if(H0[i/BW][0]!=a||H0[i/BW][1]!=b){ printf("MODEL MISMATCH base %d\n",k); exit(2); } } }
  PA[N]=PP_OBJCK_A0; PB[N]=PP_OBJCK_B0;
  memcpy(x,base,sizeof x);
}

/* ---- one try: the words of x differ from base only inside [lo,hi]; returns 1 for a full miss */
#define NCLS 40
static const char*cname[NCLS];
static long tries[NCLS], miss[NCLS], aeq[NCLS], beq[NCLS], nsame[NCLS], nverify; static int bad;
static FILE*dumpf; static int dumpk; static long ndump[NCLS];
static int cur, curbase, built[NCLS], nshown[NCLS];
static int eval(int lo,int hi){
  if(lo>hi){ int t=lo; lo=hi; hi=t; }
  if(lo<0) lo=0; if(hi>N-1) hi=N-1;
  int ch=0; for(int i=lo;i<=hi;i++) if(x[i]!=base[i]){ ch=1; break; }
  if(!ch){ nsame[cur]++; return 0; }
  int ea=1, eb=1;
  for(int k=lo/BW;k<=hi/BW;k++){ int l=k*BW>lo?k*BW:lo, h=k*BW+BW-1<hi?k*BW+BW-1:hi;
    while(l<=h&&x[l]==base[l]) l++; while(h>=l&&x[h]==base[h]) h--; if(l>h) continue;
    u32 a=PA[l], b=PB[l]; for(int i=l;i<=h;i++) PP_OBJCK_STEP(a,b,x[i]); ea&=(a==QA[h]); eb&=(b==QB[h]); }
  tries[cur]++; aeq[cur]+=ea; beq[cur]+=eb;
  if(dumpf&&ndump[cur]<dumpk&&(tries[cur]%997)==1){ u32 c=(u32)cur; fwrite(&c,4,1,dumpf); fwrite(base,4,N,dumpf); fwrite(x,4,N,dumpf); ndump[cur]++; }
  if((ea||eb)&&!built[cur]&&nshown[cur]<3){ nshown[cur]++; printf("  note class %d base %d: %s equal, words",cur,curbase,ea?"A":"B"); int k=0; for(int i=lo;i<=hi&&k<6;i++) if(x[i]!=base[i]){ printf(" %d:%08x->%08x",i,base[i],x[i]); k++; } printf("\n"); }
  if(ea&&eb||((tries[cur]&0xffff)==1)){        /* every miss, and one try in 65536: the full check of the whole buffer */
    int full=1; nverify++; for(int k=0;k<N/BW;k++){ u32 h[2]; pp_objck(x+k*BW,h); if(h[0]!=H0[k][0]||h[1]!=H0[k][1]) full=0; }
    if(full!=(ea&&eb)){ printf("WINDOW/FULL DISAGREE class %d\n",cur); bad=1; }
    if(full){ miss[cur]++;
      if(miss[cur]<=3){ printf("MISS class %d (%s): words",cur,cname[cur]); int k=0; for(int i=0;i<N&&k<8;i++) if(x[i]!=base[i]){ printf(" %d:%08x->%08x",i,base[i],x[i]); k++; } printf("\n"); } }
  }
  return ea&&eb;
}
static void undo(int lo,int hi){ if(lo>hi){ int t=lo; lo=hi; hi=t; } if(lo<0) lo=0; if(hi>N-1) hi=N-1; memcpy(x+lo,base+lo,4*(hi-lo+1)); }
#define TRY(lo,hi) do{ eval(lo,hi); undo(lo,hi); }while(0)

/* ---- the classes */
/* the state of A and B before word j of x, when x differs from base only from word i0 on (block aware) */
static void before(int i0,int j,u32*pa,u32*pb){ int s0=j-j%BW; if(s0<i0) s0=i0; u32 a=PA[s0], b=PB[s0]; for(int q=s0;q<j;q++) PP_OBJCK_STEP(a,b,x[q]); *pa=a; *pb=b; }
static u32 rbits(void){ switch(rn(6)){ case 0: return 1u<<rn(32); case 1: return (1u<<rn(32))|(1u<<rn(32)); case 2: return rnd(); case 3: return rn(16)<<(4*rn(8));
  case 4: return (1u+rn(255))<<(8*rn(4)); default: return 1u<<(27+rn(5)); } }
static u32 nib(u32 w,int c){ return (w>>(4*c))&15; }
static u32 setnib(u32 w,int c,u32 v){ return (w&~(15u<<(4*c)))|((v&15)<<(4*c)); }
static u32 byt(u32 w,int c){ return (w>>(8*c))&255; }
static u32 setbyt(u32 w,int c,u32 v){ return (w&~(255u<<(8*c)))|((v&255)<<(8*c)); }

static void cls_sparse(long n,int kmax,int span){   /* 2..kmax words changed (random value, bit flips, nibble/byte edits) within span words */
  for(long it=0;it<n;it++){ int k=2+rn(kmax-1), p0=rn(N), lo=N, hi=-1;
    for(int j=0;j<k;j++){ int p=span>=N?(int)rn(N):p0+(int)rn(span); if(p>=N) p=N-1; u32 r=rbits(); if(!r) r=1;
      if(rn(3)==0) x[p]=rnd(); else x[p]^=r; if(p<lo) lo=p; if(p>hi) hi=p; }
    TRY(lo,hi); } }
static void cls_col4(long n){        /* 4 bpp: a pixel of column c moved to another row, same column; every column; inside a tile and across tiles */
  for(long it=0;it<n;it++){ int c=it&7, i=rn(N), d=1+rn(it&8?64:7), j=i+d; if(j>=N) continue;
    u32 vi=nib(x[i],c), vj=nib(x[j],c);
    if(rn(2)){ x[i]=setnib(x[i],c,vj); x[j]=setnib(x[j],c,0); if(vj==0){ x[j]=setnib(x[j],c,1+rn(15)); } }   /* move j -> i (or put a dot) */
    else { x[i]=setnib(x[i],c,vj); x[j]=setnib(x[j],c,vi); if(vi==vj){ x[i]=setnib(x[i],c,(vi+1+rn(15))&15); } }  /* swap the two pixels */
    TRY(i,j); } }
static void cls_col8(long n){        /* 8 bpp: a pixel of column c (row = 2 words) moved to another row; every column */
  for(long it=0;it<n;it++){ int c=it&7, r=rn(N/2), d=1+rn(it&8?32:7); int i=2*r+(c>>2), j=i+2*d, bb=c&3; if(j>=N) continue;
    u32 vi=byt(x[i],bb), vj=byt(x[j],bb);
    if(rn(2)){ x[i]=setbyt(x[i],bb,vj); x[j]=setbyt(x[j],bb,0); if(vj==0) x[j]=setbyt(x[j],bb,1+rn(255)); }
    else { x[i]=setbyt(x[i],bb,vj); x[j]=setbyt(x[j],bb,vi); if(vi==vj) x[i]=setbyt(x[i],bb,(vi+1+rn(255))&255); }
    TRY(i,j); } }
static void cls_topsum(long n,int bits){   /* zero-sum pairs in the top nibble (bits=4) or top byte (bits=8): +c<<s at i, -c<<s at i+D, every D 1..64 */
  int s=32-bits; u32 m=(1u<<bits)-1;
  for(long it=0;it<n;it++){ int d=1+(int)(it%64), i=rn(N-d), j=i+d; u32 c=1+rn(m);
    switch((it/64)%3){ case 0: x[i]+=c<<s; x[j]-=c<<s; break;                 /* additive, carry out of bit 31 dropped */
      case 1: x[i]^=c<<s; x[j]^=c<<s; break;                                     /* the same bits flipped in both */
      default: { u32 vi=x[i]>>s, vj=x[j]>>s; if(vi==vj) vj=(vj+c)&m; x[i]=(x[i]&~(m<<s))|(vj<<s); x[j]=(x[j]&~(m<<s))|(vi<<s); } }  /* top part swapped */
    TRY(i,j); } }
static void cls_kd(long n){          /* two words: +d at i, -d*k^e at i+D for multiplier relations k (old and new checks), every D 1..64 */
  static u32 K[16]; int nk=0; K[nk++]=1; K[nk++]=0xffffffffu; K[nk++]=33; K[nk++]=65599; K[nk++]=0x9e3779b1u; K[nk++]=KA; K[nk++]=KB; K[nk++]=inv(KA);
  K[nk++]=inv(KB); K[nk++]=KA*KB; K[nk++]=inv(KA*KB); K[nk++]=KA*inv(KB); K[nk++]=KB*inv(KA); K[nk++]=0x80000001u; K[nk++]=3; K[nk++]=0x7fffffffu;
  for(long it=0;it<n;it++){ int d=1+(int)(it%64), i=rn(N-d), j=i+d; u32 k=K[(it/64)%nk], dd=rbits(); if(!dd) dd=1;
    u32 m=k; if((it/(64*nk))&1){ m=1; for(int e=0;e<d;e++) m*=k; }       /* k, or k^D (the djb2-style relation over D words) */
    if(rn(4)==0){ x[i]^=dd; x[j]^=dd*m; } else { x[i]+=dd; x[j]-=dd*m; }
    TRY(i,j); } }
static void cls_cancelA(long n,int far){   /* built: a change at i, and word i+1 (or a later word) set so that A is exactly the same again; B must see it */
  for(long it=0;it<n;it++){ int i=rn(N-1-far), j=i+1+(far?rn(far):0); u32 dd=rbits(); if(!dd) dd=1;
    x[i]^=dd; u32 a, b; before(i,j,&a,&b);
    /* A before word j is a; the base has PA[j]; choose x[j] so that a+x[j] = PA[j]+base[j] */
    x[j]=PA[j]+base[j]-a; TRY(i,j); } }
static void cls_cancelB(long n,int far){   /* built: B made the same again by the word after the change (xor input); A must see it */
  for(long it=0;it<n;it++){ int i=rn(N-1-far), j=i+1+(far?rn(far):0); u32 dd=rbits(); if(!dd) dd=1;
    x[i]^=dd; u32 a, b; before(i,j,&a,&b);
    x[j]=PB[j]^base[j]^b; TRY(i,j); } }
static void cls_four(long n){        /* the 4-word construction generalised: two places p<q (any distance), each a sparse change of two words
                                         built so that one check (A at p, B at q, or the same check at both) is cancelled locally; the other
                                         check's difference from p must then be undone at q by chance */
  for(long it=0;it<n;it++){ int p, q; if(it&4){ p=rn(N-4); q=p+2+rn(N-2-p-2+1); } else { int k=rn(N/BW); p=k*BW+rn(BW-4); q=p+2+rn(k*BW+BW-2-p-2); }
    if(q>N-2) q=N-2; if((p+1)/BW!=p/BW||(q+1)/BW!=q/BW) continue; int mode=it&3; u32 d1=rbits(), d2=rbits(); if(!d1) d1=1; if(!d2) d2=2;
    u32 a, b; before(p,p,&a,&b);
    x[p]^=d1; PP_OBJCK_STEP(a,b,x[p]);
    if(mode==0||mode==2) x[p+1]=PA[p+1]+base[p+1]-a; else x[p+1]=PB[p+1]^base[p+1]^b;
    before(p,q,&a,&b);
    x[q]^=d2; { u32 a2=a, b2=b; PP_OBJCK_STEP(a2,b2,x[q]);
      if(mode==0||mode==3) x[q+1]=PB[q+1]^base[q+1]^b2;      /* B cancelled at q */
      else x[q+1]=PA[q+1]+base[q+1]-a2; }                     /* A cancelled at q */
    TRY(p,q+1);
    /* the rc10.1 F3 shape: bit 31 of w_p and of w_q flipped, w_p+1 and w_q+1 moved by 2^31 +- 2^16 */
    if((it&15)==0){ int pp=rn(BW/4)*2+BW*rn(N/BW), qq=pp+BW/2; if(qq+1<N){ int s1=rn(2), s2=rn(2); x[pp]^=0x80000000u; x[pp+1]+=s1?0x80010000u:0x7fff0000u;
        x[qq]^=0x80000000u; x[qq+1]+=s2?0x80010000u:0x7fff0000u; TRY(pp,qq+1); } } } }
static void cls_tiles(long n){       /* tile moves and swaps: 4 bpp (8 words) and 8 bpp (16 words) tiles, sprites of 1..16 tiles, copies, swaps */
  static u32 tmp[N];
  for(long it=0;it<n;it++){ int tw=(it&1)?16:8, nt=1+rn(it&2?16:2), len=tw*nt; if(len>N/2) len=N/2;
    int s=rn((N-len)/tw+1)*tw, t=rn((N-len)/tw+1)*tw; if(s==t) continue;
    int lo=s<t?s:t, hi=(s<t?t:s)+len-1;
    switch((it>>2)%3){
    case 0: memmove(x+t,base+s,4*len); break;                                       /* copy (the target's old tiles are gone) */
    case 1: if((s<t?t-s:s-t)<len) continue; memcpy(tmp,base+s,4*len); memcpy(x+s,base+t,4*len); memcpy(x+t,tmp,4*len); break;   /* swap */
    default: memmove(x+t,base+s,4*len); for(int i=0;i<len;i++) if(s+i<t||s+i>=t+len) x[s+i]=0; break;     /* move: source cleared */
    }
    TRY(lo,hi); } }
static void cls_intile(long n){      /* edits of one tile: row rotation, vertical/horizontal flip, palette index +k (4 and 8 bpp), one pixel shift */
  for(long it=0;it<n;it++){ int b8=it&1, tw=b8?16:8, t=rn(N/tw)*tw, k=1+rn(b8?255:15);
    switch((it>>1)%5){
    case 0: { int c=1+rn(tw-1); for(int w=0;w<tw;w++) x[t+w]=base[t+(w+c)%tw]; } break;
    case 1: for(int w=0;w<tw;w++) x[t+w]=base[t+tw-1-w]; if(b8) for(int r=0;r<8;r++){ x[t+2*r]=base[t+2*(7-r)]; x[t+2*r+1]=base[t+2*(7-r)+1]; } break;
    case 2: for(int w=0;w<tw;w++){ u32 v=base[t+w], r=0; if(b8) for(int q=0;q<4;q++) r|=((v>>(8*q))&255)<<(8*(3-q)); else for(int q=0;q<8;q++) r|=((v>>(4*q))&15)<<(4*(7-q)); x[t+w]=r; } break;
    case 3: for(int w=0;w<tw;w++){ u32 v=base[t+w], r=0; if(b8) for(int q=0;q<4;q++) r|=(((v>>(8*q))+k)&255)<<(8*q); else for(int q=0;q<8;q++) r|=(((v>>(4*q))+k)&15)<<(4*q); x[t+w]=r; } break;
    default: for(int w=0;w<tw;w++) x[t+w]=(it&2)?(base[t+w]<<(b8?8:4)):(base[t+w]>>(b8?8:4)); break;
    }
    TRY(t,t+tw-1); } }
static void cls_bitpairs(long n){    /* the same bit flipped in two words at every distance 1..64 and at the rc10 review's 32 */
  for(long it=0;it<n;it++){ int d=1+(int)(it%64), i=rn(N-d), j=i+d, bb=(it/64)%32; x[i]^=1u<<bb; x[j]^=1u<<bb; if((it/2048)&1) x[j]^=1u<<rn(32); TRY(i,j); } }

int main(int argc,char**argv){
  long n=argc>1?atol(argv[1]):100000; uint64_t seed=argc>2?strtoull(argv[2],0,0):1; int only=argc>3?atoi(argv[3]):-1;
  if(argc>5){ dumpf=fopen(argv[4],"wb"); dumpk=atoi(argv[5]); }
  struct { const char*nm; int id; } L[]={
    {"random sparse edits, 2..8 words anywhere",0},{"random sparse edits, 2..6 words within 64",1},
    {"4bpp pixel moved/swapped along a column, every column, rows 1..64 apart",2},{"8bpp pixel moved/swapped along a column, every column",3},
    {"top-nibble zero-sum / flip / swap pairs, every distance 1..64",4},{"top-byte zero-sum / flip / swap pairs, every distance 1..64",5},
    {"two words +d / -d*k (k, k^D) for 16 multiplier relations, D 1..64",6},
    {"built: A cancelled by the next word (B must see it)",7},{"built: A cancelled up to 64 words later",8},
    {"built: B cancelled by the next word (A must see it)",9},{"built: B cancelled up to 64 words later",10},
    {"4-word construction generalised (two places, each cancelling one check) + the F3 shape",11},
    {"tile/sprite moves, copies and swaps (4 and 8 bpp, 1..16 tiles)",12},{"in-tile edits: rotate, flips, index +k, pixel shift",13},
    {"the same bit in two words, every bit, distance 1..64",14}};
  int nl=sizeof L/sizeof*L;
  for(int c=0;c<nl;c++) cname[c]=L[c].nm;
  built[7]=built[8]=built[9]=built[10]=built[11]=1;
  for(int c=0;c<nl;c++){ if(only>=0&&c!=only) continue; cur=c;
    for(int bi=0;bi<NBASE;bi++){ rs=seed*0x9e3779b97f4a7c15ull+(uint64_t)(c*131+bi*7+1); if(!rs) rs=1; mkbase(bi); curbase=bi;
      long want=n*(bi+1)/NBASE;                    /* a base on which a class makes few changes (tile moves on zeros) leaves the rest to the next */
      for(int stall=0;tries[c]<want&&stall<4;){ long m=want-tries[c], t0=tries[c]; if(bi<NBASE-1&&m>n/NBASE) m=n/NBASE;
        if(bi==NBASE-1) stall=0;
        switch(c){ case 0: cls_sparse(m,8,N); break; case 1: cls_sparse(m,6,64); break; case 2: cls_col4(m); break; case 3: cls_col8(m); break;
          case 4: cls_topsum(m,4); break; case 5: cls_topsum(m,8); break; case 6: cls_kd(m); break;
          case 7: cls_cancelA(m,0); break; case 8: cls_cancelA(m,64); break; case 9: cls_cancelB(m,0); break; case 10: cls_cancelB(m,64); break;
          case 11: cls_four(m); break; case 12: cls_tiles(m); break; case 13: cls_intile(m); break; case 14: cls_bitpairs(m); break; }
        if(tries[c]-t0<m/4) stall++; } }
    printf("class %2d %-92s tries %10ld misses %ld  A-equal %ld  B-equal %ld  (unchanged skipped %ld)\n",c,cname[c],tries[c],miss[c],aeq[c],beq[c],nsame[c]);
    fflush(stdout); }
  long T=0,M=0; for(int c=0;c<nl;c++){ T+=tries[c]; M+=miss[c]; }
  printf("TOTAL tries %ld misses %ld full-check samples %ld%s\n",T,M,nverify,bad?" DISAGREE":"");
  return (M||bad)?1:0;
}
