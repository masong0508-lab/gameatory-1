"""ROM-free synthetic framebuffer tests for exact direct spans."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest
SRC=pathlib.Path(__file__).resolve().parents[1]/"merged"/"sfspan.c"
class FastSpanTest(unittest.TestCase):
    def test_reference_spans_and_rejection(self):
        cc=shutil.which("cc")
        if not cc: self.skipTest("C compiler unavailable")
        code=r'''
#define _GNU_SOURCE
#include <sys/mman.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdlib.h>
#include "sfspan.c"
static u8 *fb=(u8*)0x80181000u,*tile=(u8*)0x801d0000u;
static u8 ref[0x14000];
static unsigned polls;
void sf_fast_poll(void){polls++;}
void *sf_resolve(u32 a,u32 *av){(void)a;*av=0;return 0;}
static u32 seed=0x1357u;
static u32 rnd(void){seed=seed*1664525u+1013904223u;return seed;}
int main(void){
 assert(mmap(fb,0x80000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0)==fb);
 for(unsigned j=0;j<1024;j++)tile[j]=rnd()>>24;
 for(unsigned k=0;k<80;k++){
   for(unsigned j=0;j<sizeof(ref);j++)ref[j]=rnd()>>24;
   memcpy(fb,ref,sizeof(ref));
   unsigned off=(k&1?0xa000:0)+(rnd()%70)*240,x=rnd()%100;
   int rows=1+rnd()%40,l=x<<16,r=(x+100)<<16,sl=123,sr=-321,c=rnd()>>24;
   for(int i=0;i<rows;i++)for(int j=(l+i*sl+0x7fff)>>16;j<(r+i*sr+0x7fff)>>16;j++)ref[off+i*240+j]=c;
   assert(sf_fast_fill_trap((u8*)(uintptr_t)(0x06000000u+off),rows,l,sl,r,sr,c));
   assert(!memcmp(fb,ref,sizeof(ref)));
   unsigned uv=rnd(),duv=rnd(),a=uv;int count=50;
   for(int i=0;i<count;i++,a+=duv){u8 v=tile[TEXEL(a)];ref[off+i*2]=ref[off+i*2+1]=ref[off+240+i*2]=ref[off+241+i*2]=v;}
   assert(sf_fast_tex_hrun(fb+off,count,uv,duv,tile,240));
   assert(!memcmp(fb,ref,sizeof(ref)));
   assert(!sf_fast_fill_trap(fb+off,rows,-65536,0,r,0,c));
   assert(!sf_fast_tex_hrun(fb+38398,2,uv,duv,tile,240));
   assert(!sf_fast_tex_hrun(fb+off,2,uv,duv,(u8*)0x08000fffu,240));
   assert(!memcmp(fb,ref,sizeof(ref)));
 }
 assert(polls==160);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d); (p/"test.c").write_text(code)
            subprocess.run([cc,"-O2","-fno-strict-aliasing","-Wno-int-to-pointer-cast","-Wno-pointer-to-int-cast","-I",str(SRC.parent),str(p/"test.c"),"-o",str(p/"test")],check=True)
            subprocess.run([str(p/"test")],check=True)
if __name__=="__main__": unittest.main()
