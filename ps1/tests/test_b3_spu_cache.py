"""ROM-free SPU cache metadata selection and MIPS-I compile gate."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
HEADER=ROOT/"stage19"/"ps1rt"/"b3_spu_cache.h"

class SpuCacheTest(unittest.TestCase):
    def test_exclusive_metadata(self):
        cc=shutil.which("cc") or shutil.which("clang")
        if not cc: self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)
            c=p/"test.c"
            c.write_text('typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8;\n'
              '#include "b3_spu_cache.h"\n'
              'int main(void){\n'
              'if(b3_spu_pick(7,8)>=B3_SPU_N) return 1;\n'
              'for(u32 j=0;j<B3_SPU_N;j++) b3_spu_owner[j]=j+1;\n'
              'if(b3_spu_pick(3,99)!=B3_SPU_N) return 2;\n'
              'b3_spu_hand=0; if(b3_spu_pick(100,0)!=1) return 3;\n'
              'b3_spu_forget(5); if(b3_spu_owner[5] || b3_spu_pick(100,0)!=5) return 4;\n'
              'if(b3_spu_pick(100,100)!=B3_SPU_N) return 5;\n'
              'return 0;}\n')
            exe=p/"test"
            subprocess.run([cc,"-std=c99","-O2","-Wno-int-to-pointer-cast","-Wno-pointer-to-int-cast","-I",str(HEADER.parent),str(c),"-o",str(exe)],check=True)
            subprocess.run([str(exe)],check=True)

    def test_mips_compile(self):
        cc=shutil.which("clang")
        if not cc: self.skipTest("clang unavailable")
        targets=subprocess.run([cc,"--print-targets"],capture_output=True,text=True)
        if "mips" not in targets.stdout: self.skipTest("MIPS target unavailable")
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)
            c=p/"test.c"
            c.write_text('typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8;\n'
              '#include "b3_spu_cache.h"\n'
              'int f(u32 p,u8 *d,u32 w){b3_spu_store(p,d,w);b3_spu_forget(p);return b3_spu_restore(w,d);}\n')
            subprocess.run([cc,"--target=mipsel-none-elf","-march=mips1","-mabi=32","-msoft-float","-ffreestanding","-fno-pic","-mno-abicalls","-G0","-O2","-I",str(HEADER.parent),"-c",str(c),"-o",str(p/"test.o")],check=True)

if __name__=="__main__": unittest.main()
