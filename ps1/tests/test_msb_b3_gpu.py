"""B3 GPU camera and flat packet math, with production C and MIPS-I build."""
import ctypes as C
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PS1=Path(__file__).resolve().parents[1]
SF=PS1/"stage19"/"sf"
TYPES="typedef int s32; typedef short s16; typedef unsigned int u32; typedef unsigned short u16;\n"


class Camera(C.Structure):
    _fields_=[("pos",C.c_int*3),("right",C.c_int*3),("up",C.c_int*3),
              ("forward",C.c_int*3),("focal",C.c_int)]


class B3GPU(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix="b3-gpu-")
        root=Path(cls.tmp.name)
        src=root/"bridge.c"
        src.write_text(TYPES+'#include "b3_gpu.h"\n'
                       'int camera(const B3Camera*c){return b3_camera_ok(c);}\n'
                       'u32 xy(s16 x,s16 y){return b3_xy(x,y);}\n'
                       'int hx(int f){return b3_hx(f);}\n'
                       'int hy(int f){return b3_hy(f);}\n'
                       'int packet(u32*d,u32 n,const s16*p,int c,u32 r){return b3_flat_packet(d,n,p,c,r);}\n'
                       'u32 rgb(u16 c){return b3_rgb555(c);}\n')
        cc=shutil.which("cc") or shutil.which("clang")
        if not cc:
            raise RuntimeError("host compiler required")
        subprocess.run([cc,"-O2","-std=c99","-Wall","-Wextra","-Werror","-shared","-fPIC",
                        "-I",str(SF),str(src),"-o",str(root/"bridge.so")],check=True)
        cls.lib=C.CDLL(str(root/"bridge.so"))
        cls.lib.camera.argtypes=[C.POINTER(Camera)]
        cls.lib.xy.argtypes=[C.c_short,C.c_short]
        cls.lib.xy.restype=C.c_uint
        cls.lib.packet.argtypes=[C.POINTER(C.c_uint),C.c_uint,C.POINTER(C.c_short),C.c_int,C.c_uint]
        cls.lib.rgb.argtypes=[C.c_ushort]
        cls.lib.rgb.restype=C.c_uint
        cls.source=src

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def camera(yaw=0,pitch=0,focal=136):
        s,c=math.sin(yaw),math.cos(yaw)
        p,q=math.sin(pitch),math.cos(pitch)
        v=lambda *a:(C.c_int*3)(*(round(x*16384) for x in a))
        return Camera((C.c_int*3)(65536,400,65536),v(-c,0,s),
                      v(-s*p,q,-c*p),v(s*q,p,c*q),focal)

    def test_real_game_camera_conventions(self):
        for yaw in [0,math.pi/4,math.pi/2,math.pi,math.pi*1.5]:
            for pitch in [-.6,-.15,0,.2]:
                for focal in [136,176]:
                    cam=self.camera(yaw,pitch,focal)
                    self.assertEqual(self.lib.camera(C.byref(cam)),1)
        cam=self.camera()
        cam.right[0]=16384
        self.assertEqual(self.lib.camera(C.byref(cam)),0)
        cam=self.camera()
        cam.right[1]=500
        self.assertEqual(self.lib.camera(C.byref(cam)),0)
        cam=self.camera()
        cam.pos[1]=12001
        self.assertEqual(self.lib.camera(C.byref(cam)),0)
        cam=self.camera()
        cam.forward[0]=2147483647
        self.assertEqual(self.lib.camera(C.byref(cam)),0)
        cam=self.camera()
        cam.focal=0
        self.assertEqual(self.lib.camera(C.byref(cam)),0)

    def test_lens_agrees_with_scaled_gba_at_eight_points(self):
        # Exact input projection and integer sf3 lens, across both zooms.
        # This checks CPU math, not hardware GTE rounding.
        points=[(-90,50,160),(90,50,160),(-90,-50,160),(90,-50,160),
                (0,0,24),(100,-20,300),(-300,100,700),(300,120,850)]
        for focal in (136,176):
            hx,hy=self.lib.hx(focal),self.lib.hy(focal)
            for x,y,z in points:
                gx=120+focal*x/z; gy=80-focal*y/z
                expected=(gx*4/3,8+gy*7/5)
                actual=(160+hx*x/z,120-hy*y/z)
                for a,b in zip(actual,expected):
                    self.assertLessEqual(abs(a-b),1)

    def test_viewport_and_palette(self):
        self.assertEqual(self.lib.xy(0,0),8<<16)
        self.assertEqual(self.lib.xy(1920,1280),160|(120<<16))
        self.assertEqual(self.lib.xy(3840,2560),320|(232<<16))
        self.assertEqual(self.lib.rgb(0x001f),0x0000f8)
        self.assertEqual(self.lib.rgb(0x03e0),0x00f800)
        self.assertEqual(self.lib.rgb(0x7c00),0xf80000)
        self.assertEqual(self.lib.rgb(0xffff),0xf8f8f8)

    def test_convex_quad_and_maximum_fan(self):
        q=(C.c_short*8)(0,0,3840,0,3840,2560,0,2560)
        out=(C.c_uint*128)(*([0xa5a5a5a5]*128))
        self.assertEqual(self.lib.packet(out,5,q,4,0xff123456),5)
        self.assertEqual(list(out[:5]),[0x28123456,8<<16,320|(8<<16),
                         232<<16,320|(232<<16)])
        self.assertEqual(out[5],0xa5a5a5a5)
        ring=[]
        for i in range(32):
            angle=2*math.pi*i/32
            ring.extend((round(1920+1800*math.cos(angle)),
                         round(1280+1100*math.sin(angle))))
        poly=(C.c_short*64)(*ring)
        self.assertEqual(self.lib.packet(out,120,poly,32,0x123456),120)
        self.assertTrue(all(out[i]==0x20123456 for i in range(0,120,4)))
        self.assertEqual(out[120],0xa5a5a5a5)
        before=list(out)
        self.assertEqual(self.lib.packet(out,119,poly,32,0),-1)
        self.assertEqual(list(out),before)
        self.assertEqual(self.lib.packet(out,128,poly,33,0),-1)
        poly[63]=2561
        self.assertEqual(self.lib.packet(out,128,poly,32,0),-1)
        self.assertEqual(list(out),before)

    def test_mips_i_helper_compiles(self):
        clang=shutil.which("clang")
        if not clang:
            self.skipTest("MIPS clang unavailable")
        out=Path(self.tmp.name)/"bridge.o"
        subprocess.run([clang,"--target=mipsel-none-elf","-march=mips1",
                        "-mno-abicalls","-mfp32","-msoft-float","-fno-pic",
                        "-ffreestanding","-fno-builtin","-Os","-mno-check-zero-division",
                        "-mllvm","-disable-mips-delay-filler","-I",str(SF),
                        "-c",str(self.source),"-o",str(out)],check=True)
        self.assertGreater(out.stat().st_size,0)

    def test_sf3_bridge_uses_native_camera_and_atomic_submission(self):
        src=(SF/"sf3.c").read_text()
        begin=src.split("int sf3_b3_begin(",1)[1].split("int sf3_b3_flat(",1)[0]
        self.assertIn("b3_camera_ok(camera)",begin)
        self.assertIn("cam_commit();",begin)
        self.assertNotIn("cam_from_angles();",begin)
        self.assertIn("city_draw(); ground_draw();",begin)
        self.assertNotIn("list_send();",begin)
        submit=src.split("int sf3_b3_flat(",1)[1].split("int sf3_b3_end(",1)[0]
        self.assertLess(submit.index("b3_flat_packet("),submit.index("pnew(words)"))
        end=src.split("int sf3_b3_end(",1)[1]
        self.assertLess(end.index("b3_bad || ovf"),end.index("list_send();"))


if __name__=="__main__":
    unittest.main()
