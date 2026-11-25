"""ROM-free regression test of the extra authoritative key-edge latch."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADER = ROOT / "stage19" / "ps1rt"
class KeyEdgesTest(unittest.TestCase):
    def test_native_read_cannot_acknowledge(self):
        cc = shutil.which("cc") or shutil.which("clang")
        if not cc: self.skipTest("C compiler unavailable")
        source = r'''
#include "b3_key_edges.h"
#include <assert.h>
int main(void){
 B3KeyEdges s={0,0};
 b3_key_observe(&s,0x3ff,1);
 b3_key_observe(&s,0x3f7,1);
 b3_key_observe(&s,0x3ff,1);
 assert(b3_key_before(&s,1,0)==0);
 b3_key_after(&s,0x3f7,1,0);
 assert(b3_key_before(&s,1,1)==8);
 b3_key_after(&s,0x3ff,1,1); /* deferred press */
 assert(b3_key_before(&s,1,1)==8);
 b3_key_observe(&s,0x3fe,1);
 assert(b3_key_before(&s,1,1)==9);
 b3_key_after(&s,0x3f7,1,1);
 assert(b3_key_before(&s,1,1)==1);
 b3_key_after(&s,0x3fe,1,1);
 assert(b3_key_before(&s,1,1)==0);
 b3_key_observe(&s,0x3fe,1); /* held, no duplicate edge */
 assert(s.pending==0);
 b3_key_observe(&s,0x3ff,1);
 b3_key_observe(&s,0x3f7,1);
 assert(s.pending==8);
 assert(b3_key_before(&s,0,1)==0);
 b3_key_observe(&s,0x3f7,0);
 b3_key_observe(&s,0x3f7,1);
 assert(s.pending==0);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d); (p/"test.c").write_text(source)
            subprocess.run([cc,"-std=c99","-Wall","-Werror","-I",str(HEADER),str(p/"test.c"),"-o",str(p/"test")],check=True)
            subprocess.run([str(p/"test")],check=True)
if __name__=="__main__": unittest.main()
