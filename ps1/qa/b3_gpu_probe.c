#include "ps1.h"
#include "b3_gpu.h"
volatile u32 results[40];
static u32 nodes[128];
static const s16 quad[8]={192,192,1248,192,1248,960,192,960};
static const s16 hex[12]={2304,320,3008,320,3456,800,3008,1280,2304,1280,1856,800};
static void idle(void){while(D2_CHCR&0x01000000){} while((GP1&0x14000000)!=0x14000000){}}
static void draw(const s16*xy,int n,u16 color){
 int w=b3_flat_packet(nodes+1,127,xy,n,b3_rgb555(color)); if(w<0){results[1]++;return;}
 nodes[0]=((u32)w<<24)|0xffffff; idle(); D2_MADR=(u32)nodes&0xffffff; D2_BCR=0; D2_CHCR=0x01000401; idle();
}
static u16 pixel(int x,int y){gp0c(0xc0000000);gp0p(XY(x,y));gp0p(XY(2,1));while(!(GP1&0x08000000)){} return GP0&0x7fff;}
int main(void){
 results[0]=0x12340000;
 GP1=0; GP1=0x03000001; GP1=0x08000001;
 GP1=0x06000000|(0x260|((0x260+320*8)<<12)); GP1=0x07000000|(0x10|((0x10+240)<<10));
 GP1=0x04000002; DPCR|=0x800;
 gp0c(0xE1000400); gp0e(0xE3000000|(8u<<10));gp0e(0xE4000000|319u|(231u<<10));gp0e(0xE5000000);
 gp0c(0x02000000);gp0p(0);gp0p(XY(320,240));idle();
 draw(quad,4,0x03e0);draw(hex,6,0x001f);
 results[2]=pixel(50,40);results[3]=pixel(220,75);results[4]=pixel(4,4);results[5]=pixel(140,100);
 results[6]=pixel(18,27);results[7]=pixel(102,88);results[8]=pixel(220,120);
 // actual GTE matrix and projection, the same vertical row correction as sf3.c
 static const s16 pts[8][3]={{-90,50,160},{90,50,160},{-90,-50,160},{90,-50,160},{0,0,32},{100,-20,300},{-300,100,700},{300,120,850}};
 for(int f=0;f<2;f++){
   int focal=f?176:136,hx=b3_hx(focal),hy=b3_hy(focal);
   s32 m[9]={4096,0,0,0,-((16384*hy/hx)>>2),0,0,0,4096};
   gte_set_rot(m);gte_set_trans(0,0,0);CTC2(24,(160<<16)+0x8000);CTC2(25,(120<<16)+0x8000);CTC2(26,hx);
   CTC2(27,0);CTC2(28,0);
   for(int i=0;i<8;i++){
     MTC2(0,((u32)(u16)(pts[i][1]*4)<<16)|(u16)(pts[i][0]*4));MTC2(1,pts[i][2]*4);GTE(RTPS);
     results[10+f*8+i]=MFC2(14);
   }
 }
 GP1=0x05000000; GP1=0x03000000;
 results[0]=0xb3c0ffee; for(;;){}
}
