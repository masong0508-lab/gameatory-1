"""ROM-free radio-range and camera-math regression checks."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class AudioGte(unittest.TestCase):
    def compile_run(self,source,flags=()):
        cc=shutil.which("cc") or shutil.which("clang")
        if not cc:self.skipTest("host compiler unavailable")
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)
            (p/"probe.c").write_text(source)
            subprocess.run([cc,"-std=c99","-O2",*flags,str(p/"probe.c"),"-o",str(p/"probe")],check=True)
            subprocess.run([str(p/"probe")],check=True)
    def test_compact_disc_bounds(self):
        code=r'''
#include <assert.h>
typedef unsigned int u32;typedef unsigned char u8;typedef unsigned short u16;
static u32 cdda_last=5,cdda_playing,track;
static u32(*cdda_nextfn)(u32);
static void dbg(const char*p){(void)p;}static void dec(u32 n){(void)n;}
static void cdda_play(u32 t){assert(t>=2&&t<=cdda_last);track=t;cdda_playing=1;}
static void cdda_stop(void){cdda_playing=0;}
#define B3_AUDIO_ORIGINALS
#include "hw_radio.h"
int main(void){
 assert(radio_lo_()==3&&radio_hi_()==5);
 assert(radio_next(5)==3&&radio_prev(3)==5);
 radio_poll1(1,1u<<15);assert(radio_mode==1&&track==2);
 radio_poll1(1,1u<<15);assert(radio_mode==2&&track==2);
 assert(radio_next(2)==2&&radio_prev(2)==2);
 radio_poll1(1,1u<<15);assert(radio_mode==0&&track==3);
 cdda_last=2;assert(radio_lo_()==2&&radio_hi_()==2);
 radio_poll1(1,1u<<11);assert(track==2);
 cdda_last=1;radio_go(2,"test");assert(track==2);
 return 0;
}
'''
        self.compile_run(code,["-I",str(ROOT/"stage16/merge/ps1rt")])
    def test_camera_range_and_wrapped_math(self):
        code=r'''
#include <assert.h>
#include "gtecam.h"
int main(void){
 M3 m={ {16384,0,0},{0,16384,0},{0,0,16384} };
 V3 d={-32768,32767,-123},p=sf_gte_project(&m,d);
 assert(sf_gte_range(&m,d)<65536u);
 assert(p.x==d.x&&p.y==d.y&&p.z==d.z);
 d.x=32768;assert(sf_gte_range(&m,d)>=65536u);
 d.x=-32769;assert(sf_gte_range(&m,d)>=65536u);
 d.x=(s32)0x80000000u;assert(sf_gte_range(&m,d)>=65536u);
 m.r.x=32768;d.x=1;assert(sf_gte_range(&m,d)>=65536u);
 p=sf_gte_project(&m,d);assert(p.x==2);
 return 0;
}
'''
        self.compile_run(code,["-I",str(ROOT/"merged/include"),"-I",str(ROOT.parent/"stuntfox/src")])
    def test_mips_camera_compile(self):
        cc=shutil.which("clang")
        if not cc:self.skipTest("clang unavailable")
        if "mips" not in subprocess.check_output([cc,"--print-targets"],text=True):self.skipTest("MIPS unavailable")
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)
            (p/"probe.c").write_text('#include "gtecam.h"\nV3 project(const M3*m,V3 d){return sf_gte_project(m,d);}\n')
            subprocess.run([cc,"--target=mipsel-none-elf","-march=mips1","-mabi=32","-mfp32","-msoft-float","-ffreestanding","-fno-pic","-mno-abicalls","-mno-check-zero-division","-G0","-Os","-I",str(ROOT/"merged/include"),"-I",str(ROOT.parent/"stuntfox/src"),"-c",str(p/"probe.c"),"-o",str(p/"probe.o")],check=True)
if __name__=="__main__":unittest.main()
