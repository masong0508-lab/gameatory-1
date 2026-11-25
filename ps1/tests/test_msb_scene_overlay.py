"""ROM-free SOV1 writer, resident loader, and cold slot policy tests."""
import ctypes as C
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from elf_fixture import mips_elf

PS1=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PS1/'merged'))
from scene_overlay import pack_elf, SECTOR, MAGIC
from scene_layout import plan

ADDRESS=0x800ab800
CAP=0x22000


def elf(value):
    # One synthetic MIPS instruction plus jr ra and nop; host tests do
    # not execute it. The two-core probe executes actual compiled code.
    return mips_elf([value,0x03e00008,0],[('entry',0,12)],text_address=ADDRESS)


class PackTests(unittest.TestCase):
    def test_sector_image_and_header_crc(self):
        raw=pack_elf(elf(0x24020017),1,ADDRESS,CAP,{1:'entry'})
        self.assertEqual(len(raw),2*SECTOR)
        self.assertEqual(struct.unpack_from('<10I',raw)[:7],(MAGIC,1,1,ADDRESS,CAP,12,1))
        self.assertEqual(struct.unpack_from('<I',raw,28)[0],zlib.crc32(raw[SECTOR:]))
        self.assertEqual(struct.unpack_from('<I',raw,SECTOR-4)[0],zlib.crc32(raw[:SECTOR-4]))
        self.assertEqual(struct.unpack_from('<2I',raw,40),(1,0))
        self.assertEqual(raw[SECTOR+12:],bytes(SECTOR-12))

    def test_pack_rejects_state_or_wrong_link(self):
        for raw,scene,address,capacity,entries in [
            (elf(0),3,ADDRESS,CAP,{1:'entry'}),
            (elf(0),1,ADDRESS+SECTOR,CAP,{1:'entry'}),
            (elf(0),1,ADDRESS,CAP,{0:'entry'}),
            (elf(0),1,ADDRESS,CAP,{1:'missing'}),
            (mips_elf([0],[('entry',0,4)],[123],text_address=ADDRESS,data_address=ADDRESS+32),1,ADDRESS,CAP,{1:'entry'}),
        ]:
            with self.subTest(scene=scene,address=address,entries=entries),self.assertRaises(ValueError):
                pack_elf(raw,scene,address,capacity,entries)

    def test_actual_elf_slot_calculation(self):
        # Synthetic extents shaped like the private B2 layout. Numeric
        # addresses only, no ROM or translated code.
        live=[('.blob',0x80030000,0x80047430),('.bootimg',0x80047430,0x800a80d0),
              ('.sfn1',0x800eb430,0x80115684)]
        out=plan(live,0x800eb430)
        self.assertTrue(out['slot_fit'])
        self.assertFalse(out['full_gpu_layout_verified'])
        self.assertEqual((out['slot_start'],out['slot_bytes']),(ADDRESS,CAP))
        self.assertEqual((out['old_cold_groups'],out['new_cold_groups']),(41,25))
        self.assertEqual(out['cold_ceiling'],0x800ab430)
        self.assertEqual(out['groups_intersecting_slot'],list(range(25,34)))
        self.assertFalse(plan(live+[('resident',ADDRESS,ADDRESS+4)],0x800eb430)['slot_fit'])
        with self.assertRaises(ValueError):
            plan(live,0x800eb430,world=0x800a8000)

    def test_cold_ceiling_is_consistent_in_runtime(self):
        src=(PS1/'stage19/ps1rt/rt.c').read_text()
        self.assertIn('if(COLD_HOST+(g1+1)*16384u>SF_COLD_LIMIT)',src)
        self.assertIn('u32 ng=(SF_COLD_LIMIT-COLD_HOST)>>14',src)
        self.assertIn('if((u32)w+20>SF_COLD_LIMIT)',src)
        self.assertIn('COLD_HOST+(g1+1)*16384u<=SF_COLD_LIMIT',src)
        self.assertIn('#define SF_COLD_LIMIT SF_NAT_LO',src)


class LoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='sov1-')
        root=Path(cls.tmp.name)
        source=root/'loader.c'
        source.write_text(
            'typedef unsigned char u8; typedef unsigned int u32;\n'
            '#include "scene_overlay.h"\n'
            'static SOState s; static u8 buf[SO_MAX_SLOT+2],scratch[SO_SECTOR];\n'
            'static const u8 *a,*b; static u32 mode,reads,claims,syncs;\n'
            'static int read_cb(void*c,u32 l,u32 n,u8*d){(void)c;reads++;const u8*p;'
            'if(l>=10&&l+n<=12)p=a+(l-10)*SO_SECTOR;else if(l>=20&&l+n<=22)p=b+(l-20)*SO_SECTOR;else return 0;'
            'for(u32 i=0;i<n*SO_SECTOR;i++)d[i]=p[i];'
            'if(mode==1&&l==20)d[4]^=1;if(mode==2&&l==21)d[0]^=1;return !(mode==5&&l==21);}\n'
            'static int claim_cb(void*c,u32 ad,u32 n){(void)c;claims++;return mode!=3&&ad==0x800ab800u&&n==SO_MAX_SLOT;}\n'
            'static int sync_cb(void*c){(void)c;syncs++;return mode!=4;}\n'
            'static const SOOps ops={read_cb,claim_cb,sync_cb,0};\n'
            'int init(const u8*x,const u8*y){a=x;b=y;mode=reads=claims=syncs=0;buf[0]=0x73;buf[SO_MAX_SLOT+1]=0x4d;'
            'return so_init(&s,buf+1,0x800ab800u,SO_MAX_SLOT);}\n'
            'int select_scene(u32 scene,u32 depth,u32 fail){mode=fail;return so_select(&s,&ops,scratch,scene,scene==1?10:20,depth);}\n'
            'int overlap(void){return so_select(&s,&ops,buf+1,2,20,0);}\n'
            'u32 enter(u32 scene,u32 id){u8*p=so_enter(&s,scene,id);return p?so_word(p):0;}\n'
            'int leave(void){return so_leave(&s);}\n'
            'u32 active(void){return s.active;} u32 generation(void){return s.generation;}\n'
            'u32 read_count(void){return reads;} u32 sync_count(void){return syncs;}\n'
            'int guard(void){return buf[0]==0x73&&buf[SO_MAX_SLOT+1]==0x4d&&buf[SO_MAX_SLOT]==0;}\n')
        cc=shutil.which('cc') or shutil.which('clang')
        if not cc: raise RuntimeError('host C compiler required')
        lib=root/'loader.so'
        subprocess.run([cc,'-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
                        '-I',str(PS1/'merged'),str(source),'-o',str(lib)],check=True)
        cls.lib=C.CDLL(str(lib))
        cls.lib.init.argtypes=[C.c_void_p,C.c_void_p]
        cls.lib.enter.restype=C.c_uint

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def setUp(self):
        self.a=C.create_string_buffer(pack_elf(elf(0x24020017),1,ADDRESS,CAP,{1:'entry'}))
        self.b=C.create_string_buffer(pack_elf(elf(0x24020031),2,ADDRESS,CAP,{1:'entry'}))
        self.assertEqual(self.lib.init(self.a,self.b),1)

    def test_shared_slot_switch_and_leases(self):
        L=self.lib
        self.assertEqual(L.select_scene(1,0,0),1)
        self.assertEqual(L.enter(1,1),0x24020017)
        self.assertEqual(L.select_scene(2,0,0),0)
        self.assertEqual(L.leave(),1)
        self.assertEqual(L.select_scene(2,1,0),0)
        self.assertEqual(L.overlap(),0)
        self.assertEqual(L.read_count(),2)
        self.assertEqual(L.select_scene(2,0,0),1)
        self.assertEqual(L.enter(1,1),0)
        self.assertEqual(L.enter(2,1),0x24020031)
        self.assertEqual(L.leave(),1)
        self.assertEqual(L.select_scene(1,0,0),1)
        self.assertEqual(L.enter(1,1),0x24020017)
        self.assertEqual(L.leave(),1)
        self.assertEqual(L.generation(),3)
        self.assertEqual(L.sync_count(),3)
        self.assertEqual(L.guard(),1)

    def test_corruption_and_callbacks_fail_closed(self):
        L=self.lib
        self.assertEqual(L.select_scene(1,0,0),1)
        for failure in (1,3): # bad header or refused claim preserves old
            self.assertEqual(L.select_scene(2,0,failure),0)
            self.assertEqual(L.active(),1)
        for failure in (2,4,5): # partial data or failed I-cache sync invalidates
            self.assertEqual(L.select_scene(2,0,failure),0)
            self.assertEqual(L.active(),0)
            self.assertEqual(L.enter(1,1),0)
            self.assertEqual(L.enter(2,1),0)
            self.assertEqual(L.select_scene(1,0,0),1)
        self.assertEqual(L.select_scene(2,0,0),1)
        self.assertEqual(L.guard(),1)


if __name__=='__main__': unittest.main()
