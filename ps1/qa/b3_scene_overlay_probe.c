typedef unsigned char u8; typedef unsigned int u32;
#include "scene_overlay.h"
extern const u8 flight_blob[], station_blob[];
volatile u32 results[20];
static SOState state;
static u8 scratch[SO_SECTOR] __attribute__((aligned(4)));
static u32 failmode, reads, claims, flushes;
static int rd(void *ctx,u32 lba,u32 n,u8 *dst){
 (void)ctx; reads++; const u8 *src;
 if(lba>=10 && lba+n<=12) src=flight_blob+(lba-10)*SO_SECTOR;
 else if(lba>=20 && lba+n<=22) src=station_blob+(lba-20)*SO_SECTOR;
 else return 0;
 for(u32 i=0;i<n*SO_SECTOR;i++) dst[i]=src[i];
 if(failmode==1 && n==1 && lba==20) dst[4]^=1;
 if(failmode==2 && lba==21) dst[0]^=1;
 return 1;
}
static int claim(void *ctx,u32 a,u32 n){(void)ctx;claims++;return a==0x800ab800u && n==0x22000u;}
static int sync_code(void *ctx){
 (void)ctx;flushes++;
 register u32 t1 __asm__("$9")=0x44;
 __asm__ volatile("addiu $29,$29,-16\n li $8,0xA0\n jalr $8\n nop\n addiu $29,$29,16":"+r"(t1)::"$1","$2","$3","$4","$5","$6","$7","$8","$10","$11","$12","$13","$14","$15","$24","$25","$31","hi","lo","memory");
 return 1;
}
static int tick(u32 scene,u32 id,int v){
 u8 *p=so_enter(&state,scene,id); if(!p) return -999;
 int out=((int(*)(int))p)(v); so_leave(&state); return out;
}
int main(void){
 SOOps op={rd,claim,sync_code,0}; u8 *slot=(u8*)0x800ab800u;
 results[0]=0x55555555; slot[-1]=0x73; slot[0x22000]=0x4d; slot[0x21fff]=0xa5;
 results[1]=so_init(&state,slot,0x800ab800u,0x22000u);
 results[2]=so_select(&state,&op,scratch,SO_FLIGHT,10,0);
 results[3]=tick(SO_FLIGHT,1,100); results[4]=tick(SO_FLIGHT,2,7);
 u8 *p=so_enter(&state,SO_FLIGHT,1);
 results[5]=(p!=0 && !so_select(&state,&op,scratch,SO_STATION,20,0) && so_leave(&state));
 results[6]=!so_select(&state,&op,scratch,SO_STATION,20,1);
 failmode=1;results[7]=!so_select(&state,&op,scratch,SO_STATION,20,0) && tick(SO_FLIGHT,1,100)==117;
 failmode=2;results[8]=!so_select(&state,&op,scratch,SO_STATION,20,0) && state.active==0 && !so_enter(&state,SO_FLIGHT,1);
 failmode=0;results[9]=so_select(&state,&op,scratch,SO_STATION,20,0);
 results[10]=tick(SO_STATION,1,100);results[11]=tick(SO_STATION,2,7);
 results[12]=so_select(&state,&op,scratch,SO_FLIGHT,10,0);
 results[13]=tick(SO_FLIGHT,1,100);results[14]=state.generation;
 results[15]=reads;results[16]=claims;results[17]=flushes;
 results[18]=slot[-1]==0x73 && slot[0x22000]==0x4d && slot[0x21fff]==0;
 results[0]=0xb30f1a9e;for(;;){}
}
