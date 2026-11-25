#include "ps1.h"
volatile u32 results[8];
static u16 src[240*160], readout[240*160], clut[256];
static u32 rgb(u16 a){return ((a&31)<<3)|((a&0x3e0)<<6)|((a&0x7c00)<<9);}
static void quad(int x0,int x1,int u0,int u1,int tp,int v){
 gp0c(0x2d000000);GP0=XY(x0,0);GP0=u0|(v<<8)|((0u|496u<<6)<<16);
 GP0=XY(x1,0);GP0=u1|(v<<8)|(tp<<16);GP0=XY(x0,160);GP0=u0|((v+160)<<8);GP0=XY(x1,160);GP0=u1|((v+160)<<8);
}
int main(void){
 GP1=0;GP1=0x03000001;GP1=0x08000001;GP1=0x04000002;DPCR|=0x800;
 results[0]=0x1234;
 for(int i=0;i<256;i++)clut[i]=0x8000|i*73%32768;
 for(int y=0;y<160;y++)for(int x=0;x<240;x++)src[y*240+x]=0x0100|((x*7+y*13)&255);
 gpu_idle();vram_load(0,496,256,1,clut);
 vram_load(320,0,240,160,src);gpu_idle();
 gp0e(0xe3000000);gp0e(0xe4000000|239u|(159u<<10));gp0e(0xe5000000);gp0e(0xe1000400);gp0e(0xe2000000);gp0e(0xe6000000);
 quad(0,120,0,240,5|128,0);quad(120,128,112,128,6|128,0);quad(128,240,0,224,7|128,0);gpu_idle();
 gp0c(0xc0000000);GP0=0;GP0=XY(240,160);
 for(int i=0;i<240*160/2;i++){while(!(GP1&0x08000000)){}((u32*)readout)[i]=GP0;}
 u32 bad=0;for(int i=0;i<240*160;i++)if((readout[i]&0x7fff)!=(clut[src[i]&255]&0x7fff))bad++;
 results[1]=bad;results[2]=readout[0];results[3]=readout[1];results[4]=readout[119];results[5]=readout[120];results[6]=readout[128];results[7]=readout[239];results[0]=0xb300beef;for(;;){}
}
