"""Compact native maths: synthetic ROM-free tables and actual source consumers."""
import ctypes as C
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PS1=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PS1/'merged'))
from compact_math import apply,array,compress,NEW

SIN=[round(16384*math.sin(2*math.pi*i/4096)) for i in range(4096)]
RTAB=[0x80000000//(2048+i) for i in range(2048)]
ERECIP=[0]+[(1<<24)//i for i in range(1,2561)]


def tables(sin=SIN,rtab=RTAB,erecip=ERECIP):
    return '#include "gba.h"\n'+array('sin_table','s16',sin)+'\n'+array('rtab','u32',rtab)+'\n'+array('erecip','u32',erecip)+'\n'


class CompactMath(unittest.TestCase):
    def test_exact_native_values(self):
        c,report=compress(tables())
        self.assertEqual(report,dict(original_table_bytes=26628,
                                     compact_table_bytes=12806,
                                     raw_table_bytes_saved=13822))
        with tempfile.TemporaryDirectory(prefix='compact-math-') as tmp:
            t=Path(tmp)
            (t/'gba.h').write_text('typedef unsigned int u32; typedef int s32; typedef unsigned short u16; typedef short s16; typedef unsigned char u8;\n')
            shutil.copy(PS1/'merged/include/compact_math.h',t)
            (t/'tables.c').write_text(c)
            (t/'check.c').write_text('#include "compact_math.h"\nu32 get_r(u32 i){return sfcm_rtab(i);}\nu32 get_e(u32 i){return sfcm_erecip(i);}\n')
            cc=shutil.which('cc') or shutil.which('clang')
            if not cc: self.fail('host C compiler required')
            subprocess.run([cc,'-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
                            str(t/'tables.c'),str(t/'check.c'),'-o',str(t/'math.so')],check=True)
            lib=C.CDLL(str(t/'math.so'))
            lib.sfcm_sin.argtypes=[C.c_uint]; lib.sfcm_sin.restype=C.c_int
            for i in range(65536):
                self.assertEqual(lib.sfcm_sin(i),SIN[i>>4])
                self.assertEqual(lib.sfcm_sin(i+16384),SIN[((i>>4)+1024)&4095])
                self.assertEqual(lib.sfcm_sin(i-65536),SIN[i>>4])
            for name,ref in [('get_r',RTAB),('get_e',ERECIP)]:
                func=getattr(lib,name);func.argtypes=[C.c_uint];func.restype=C.c_uint
                self.assertEqual([func(i) for i in range(len(ref))],ref)

    def test_reject_changed_table_ranges(self):
        sin=SIN.copy();sin[2500]+=1
        with self.assertRaises(ValueError):compress(tables(sin=sin))
        r=RTAB.copy();r[0]=0
        with self.assertRaises(ValueError):compress(tables(rtab=r))
        e=ERECIP.copy();e[300]=65536
        with self.assertRaises(ValueError):compress(tables(erecip=e))

    def test_copy_rewrite_and_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='compact-src-') as tmp:
            root=Path(tmp);src=root/'src';gen=root/'build/gen'
            shutil.copytree(PS1.parent/'stuntfox/src',src)
            shutil.copy(PS1/'merged/include/compact_math.h',src)
            gen.mkdir(parents=True)
            data=gen/'tables.c'; original=tables(); data.write_text(original)
            bad=src/'unexpected.c'
            bad.write_text('int f(int *a){return rtab[a[0]];}\n')
            with self.assertRaises(ValueError):apply(root)
            self.assertEqual(data.read_text(),original)
            bad.write_text('void f(void){asm("la $2, sin_table");}\n')
            with self.assertRaises(ValueError):apply(root)
            self.assertEqual(data.read_text(),original)
            bad.unlink()
            report=apply(root)
            self.assertEqual(report['rewritten_files'],['fx.h','planet.c','render.c','tex.c'])
            self.assertIn('sfcm_sin((u32)a)',(src/'fx.h').read_text())
            for n in NEW:self.assertIn(n,data.read_text())
            self.assertEqual(report['raw_table_bytes_saved'],13822)


if __name__=='__main__':unittest.main()
