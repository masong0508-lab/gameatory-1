/* Projective wall planner for the optional native PS1 indexed renderer.
 * Inputs are a convex, screen-clipped ring (28.4) and the public TexWall
 * projective plane coefficients. No guest reads or GPU writes occur here.
 * Clip texture boundaries in homogeneous space, then bound the difference
 * between projective and affine UV interpolation before emitting triangles.
 * Rejection is atomic: callers must keep the ordinary span renderer.
 */
#ifndef SF_PROJECTIVE_H
#define SF_PROJECTIVE_H
#define SFP_VERT 24
#define SFP_TRIS 64
#define SFP_DEPTH 9
#define SFP_FLAT 4
#define SFP_UV_RANGE (96*256)
#define SFP_ERROR 256 /* one texel before integer GPU raster quantization */
typedef struct { s16 x,y; } SfpPoint;
typedef struct { SfpPoint p; s32 w,u,v; } SfpVertex;
typedef struct { s16 xy[6]; u16 uv[3]; u8 tile; } SfpTri;
typedef struct { SfpTri tri[SFP_TRIS]; unsigned n; } SfpPlan;
/* W, A and B are evaluated at 28.4 coordinates, with a common factor 16. */
typedef struct { s32 w[3],a[3],b[3],wlim; unsigned mask; } SfpPlane;
static s64 sfp_eval(const s32 *c,SfpPoint p){return (s64)c[0]*16+(s64)c[1]*p.x+(s64)c[2]*p.y;}
static u32 sfp_abs(s32 x){return x<0?0u-(u32)x:(u32)x;}
/* Half-space distances. For tile boundaries U=512*A/W. */
static s64 sfp_distance(const SfpPlane*t,SfpPoint p,int sign,int kind,int boundary){
 s64 w=sfp_eval(t->w,p)*sign;
 if(kind==0)return w-boundary;
 return sfp_eval(t->a,p)*sign*512-(s64)boundary*w;
}
static int sfp_equal(SfpPoint a,SfpPoint b){return a.x==b.x&&a.y==b.y;}
/* Canonical endpoint order gives identical rounded intersections on both
 * sides of a tile boundary. Scale both distances to fit a native u32 divide. */
static SfpPoint sfp_intersect(SfpPoint a,SfpPoint b,s64 da,s64 db){
 if(a.x>b.x||(a.x==b.x&&a.y>b.y)){SfpPoint q=a;a=b;b=q;s64 d=da;da=db;db=d;}
 u64 na=da<0?(u64)-da:(u64)da,nb=db<0?(u64)-db:(u64)db;
 while((na|nb)>32767u){na>>=1;nb>>=1;}
 u32 den=(u32)(na+nb),f=den?((u32)na<<16)/den:32768u;
 SfpPoint p={(s16)(a.x+(((s32)(b.x-a.x)*(s32)f+32768)>>16)),(s16)(a.y+(((s32)(b.y-a.y)*(s32)f+32768)>>16))};return p;
}
static int sfp_append(SfpPoint*out,int n,SfpPoint p){if(n&&sfp_equal(out[n-1],p))return n;if(n>=SFP_VERT)return -1;out[n]=p;return n+1;}
static int sfp_clip(const SfpPlane*t,const SfpPoint*in,int n,SfpPoint*out,int sign,int kind,int boundary,int positive){
 if(n<=0)return n;int m=0;SfpPoint a=in[n-1];s64 da=sfp_distance(t,a,sign,kind,boundary);int ia=positive?da>=0:da<=0;
 for(int i=0;i<n;i++){SfpPoint b=in[i];s64 db=sfp_distance(t,b,sign,kind,boundary);int ib=positive?db>=0:db<=0;
  if(ia!=ib){m=sfp_append(out,m,sfp_intersect(a,b,da,db));if(m<0)return -1;}
  if(ib){m=sfp_append(out,m,b);if(m<0)return -1;}a=b;da=db;ia=ib;
 }
 if(m>1&&sfp_equal(out[0],out[m-1]))m--;return m;
}
/* Signed 17-bit fixed-point ratio, with a native 32-bit division. The
 * fractional denominator is normalized to <= 32767 before shifting.
 * Bound outputs to prevent overflow in later interpolation/error checks. */
static int sfp_ratio(s32 a,u32 w,s32*out){
 if(!w)return 0;u32 n=sfp_abs(a),q=n/w,r=n-q*w;if(q>31)return 0;
 while(w>32767u){w>>=1;r>>=1;}
 u32 frac=(r<<17)/w;if(frac>=131072u)frac=131071u;
 s32 v=(s32)((q<<17)+frac);*out=a<0?-v:v;return 1;
}
static int sfp_vertex(const SfpPlane*t,SfpPoint p,int sign,SfpVertex*out){
 s64 w=sfp_eval(t->w,p)*sign,a=sfp_eval(t->a,p)*sign,b=sfp_eval(t->b,p)*sign;
 if(w<=0||w>0x7fffffffu||a>0x7fffffffll||a<(-2147483647ll-1)||b>0x7fffffffll||b<(-2147483647ll-1))return 0;
 out->p=p;out->w=(s32)w;return sfp_ratio((s32)a,(u32)w,&out->u)&&sfp_ratio((s32)b,(u32)w,&out->v);
}
static s32 sfp_area(SfpPoint a,SfpPoint b,SfpPoint c){return (s32)(b.x-a.x)*(c.y-a.y)-(s32)(b.y-a.y)*(c.x-a.x);}
static int sfp_emit(SfpPlan*plan,const SfpVertex*v,int tile){
 if(plan->n>=SFP_TRIS)return 0;
 /* Screen coordinates use the original renderer's (x+7)>>4 rounding. */
 SfpPoint p[3];for(int i=0;i<3;i++){p[i].x=(v[i].p.x+7)>>4;p[i].y=(v[i].p.y+7)>>4;}
 if(!sfp_area(p[0],p[1],p[2]))return 1;
 SfpTri*q=&plan->tri[plan->n];s32 u0=v[0].u>>8,v0=v[0].v>>8;
 for(int i=0;i<3;i++){q->xy[2*i]=p[i].x;q->xy[2*i+1]=p[i].y;
  s32 u=96+(u0&31)+(v[i].u>>8)-u0,z=96+(v0&31)+(v[i].v>>8)-v0;
  if(tile!=SFP_FLAT&&(u<0||u>255||z<0||z>255))return 0;
  q->uv[i]=tile==SFP_FLAT?0:(u16)(u|(z<<8));
 }
 q->tile=(u8)tile;plan->n++;return 1;
}
/* For barycentric weights lambda, the difference is
 * sum_{i<j} lambda_i lambda_j (ui-uj)(wj-wi) / sum lambda_i wi.
 * sum_{i<j} lambda_i lambda_j <= 1/3; therefore max pair product <=
 * 3*epsilon*minW bounds the affine error over the complete triangle.
 * The planner splits the offending edge, not a screen-space column. */
static int sfp_split(const SfpPlane*t,SfpPlan*plan,const SfpVertex*v,int tile,int sign,int depth){
 if(!sfp_area(v[0].p,v[1].p,v[2].p))return 1;
 s32 lo=v[0].w;for(int i=1;i<3;i++)if(v[i].w<lo)lo=v[i].w;
 u64 lim=(u64)(u32)lo*(3*SFP_ERROR),worst=0;int edge=-1;
 for(int i=0;i<3;i++){int j=(i+1)%3;u32 du=sfp_abs(v[i].u-v[j].u),dv=sfp_abs(v[i].v-v[j].v),d=du>dv?du:dv;
  u64 e=(u64)d*sfp_abs(v[i].w-v[j].w);
  if(d>SFP_UV_RANGE)e+=lim+((u64)d<<16);
  if(e>lim&&e>worst){worst=e;edge=i;}
 }
 if(edge<0)return sfp_emit(plan,v,tile);
 if(depth>=SFP_DEPTH||plan->n>=SFP_TRIS)return 0;
 int j=(edge+1)%3,k=(edge+2)%3;SfpPoint p={(s16)((v[edge].p.x+v[j].p.x+1)>>1),(s16)((v[edge].p.y+v[j].p.y+1)>>1)};
 if(sfp_equal(p,v[edge].p)||sfp_equal(p,v[j].p))return 0;
 SfpVertex mid;if(!sfp_vertex(t,p,sign,&mid))return 0;
 SfpVertex a[3]={v[edge],mid,v[k]},b[3]={mid,v[j],v[k]};
 return sfp_split(t,plan,a,tile,sign,depth+1)&&sfp_split(t,plan,b,tile,sign,depth+1);
}
static int sfp_polygon(const SfpPlane*t,SfpPlan*plan,const SfpPoint*p,int n,int tile,int sign){
 if(n<3)return 1;SfpVertex v[SFP_VERT];
 for(int i=0;i<n;i++){if(tile==SFP_FLAT){v[i].p=p[i];v[i].u=v[i].v=0;v[i].w=1;}else if(!sfp_vertex(t,p[i],sign,&v[i]))return 0;}
 for(int i=1;i+1<n;i++){SfpVertex a[3]={v[0],v[i],v[i+1]};if(tile==SFP_FLAT){if(!sfp_emit(plan,a,tile))return 0;}else if(!sfp_split(t,plan,a,tile,sign,0))return 0;}
 return 1;
}
static int sfp_plan(const SfpPlane*t,const s16*xy,int n,SfpPlan*out){
 out->n=0;if(n<3||n>16||t->wlim<0||t->wlim>0x07ffffff)return 0;
 SfpPoint ring[SFP_VERT],near[SFP_VERT],a[SFP_VERT],b[SFP_VERT];int sign=0;
 for(int i=0;i<n;i++){SfpPoint p={xy[2*i],xy[2*i+1]};if(p.x<0||p.x>3840||p.y<0||p.y>2560)return 0;
  s64 w=sfp_eval(t->w,p);if(!w)return 0;if(!sign)sign=w<0?-1:1;else if(w*sign<0)return 0;ring[i]=p;}
 /* Clip near/far separately. Flat triangles retain the original distant
  * material index; each textured tile has its own source and shade LUT. */
 int threshold=t->wlim>0?t->wlim*16:1;
 int m=sfp_clip(t,ring,n,near,sign,0,threshold,1),f=sfp_clip(t,ring,n,a,sign,0,threshold,0);
 if(m<0||f<0||!sfp_polygon(t,out,a,f,SFP_FLAT,sign))goto bad;
 for(int tile=0;tile<4;tile++){
  int k=m;const SfpPoint*src=near;if(tile){k=sfp_clip(t,near,m,a,sign,1,tile*32,1);src=a;}
  if(k<0)goto bad;if(tile<3){k=sfp_clip(t,src,k,b,sign,1,(tile+1)*32,0);src=b;}
  if(k<0||!sfp_polygon(t,out,src,k,(t->mask&(1u<<tile))?tile:SFP_FLAT,sign))goto bad;
 }
 return 1;
bad:out->n=0;return 0;
}
#endif
