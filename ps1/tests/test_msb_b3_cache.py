"""Synthetic, ROM-free tests of the B3 packer and production C cache."""
import ctypes as C
import json
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

PS1 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PS1/"merged"))
from b3_cache_pack import (encode_page, decode_page, plan_cache, render_header,
                           load_meta, sha, REGIONS, ROM_BYTES, PAGE_BYTES)


class CacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="b3-cache-")
        root = Path(cls.tmp.name)
        cc = shutil.which("cc") or shutil.which("clang")
        if not cc:
            raise RuntimeError("host C compiler required")
        (root/"test.c").write_text(
            'typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8;\n'
            '#include "b3_cache.h"\n'
            'int decode(const u8*s,u32 n,u8*d){return b3_decode_page(s,n,d);}\n'
            'int restore(u32 p,u8*d,const B3CachePage*t,u32 n){return b3_restore_page(p,d,t,n);}\n'
            'u32 victim(u32 n,u32*h,const u16*o,const u8**m,const u8*p,int a)'
            '{return b3_clock_victim(n,h,o,m,p,a);}\n')
        subprocess.run([cc,"-std=c99","-O2","-shared","-fPIC","-Wall","-Wextra","-Werror",
                        "-I",str(PS1/"stage19/ps1rt"),str(root/"test.c"),"-o",str(root/"test.so")],
                       check=True)
        cls.lib = C.CDLL(str(root/"test.so"))
        cls.lib.decode.argtypes = [C.c_void_p,C.c_uint,C.c_void_p]
        cls.lib.decode.restype = C.c_int
        cls.lib.victim.argtypes = [C.c_uint,C.POINTER(C.c_uint),C.POINTER(C.c_ushort),
                                  C.POINTER(C.c_void_p),C.c_void_p,C.c_int]
        cls.lib.victim.restype = C.c_uint

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decode_c(self, blob):
        source = C.create_string_buffer(blob)
        dst = (C.c_ubyte*(PAGE_BYTES+32))(*([0xa5]*(PAGE_BYTES+32)))
        ok = self.lib.decode(source,len(blob),C.byref(dst,16))
        self.assertEqual(bytes(dst[:16]),b"\xa5"*16)
        self.assertEqual(bytes(dst[-16:]),b"\xa5"*16)
        return ok,bytes(dst[16:-16])

    def test_real_c_decoder_round_trips(self):
        rng = random.Random(11)
        pages = [bytes(PAGE_BYTES), bytes(range(256))*16, b"abc"*1365+b"a",
                 bytes([255])*PAGE_BYTES]
        pages += [bytes(rng.randrange(8) for _ in range(PAGE_BYTES)) for _ in range(10)]
        for page in pages:
            blob = encode_page(page)
            self.assertEqual(decode_page(blob),page)
            if len(blob)<PAGE_BYTES:
                self.assertEqual(self.decode_c(blob),(1,page))
        random_page = rng.randbytes(PAGE_BYTES)
        self.assertEqual(decode_page(encode_page(random_page)),random_page)

    def test_malformed_stream_cannot_overwrite_guards(self):
        for bad in (b"",b"\x00\x00\x00",b"\xf0\xff",b"\x10x",
                    b"\x1fx\x01\x00"+b"\xff"*18+b"\x00"):
            self.assertEqual(self.decode_c(bad)[0],0)

    def victim(self, hot, active, hand=0, mapping=(1,2,3,4)):
        owners = (C.c_ushort*4)(1,2,3,4)
        mapped = (C.c_void_p*4)(*mapping)
        bitmap = (C.c_ubyte*512)()
        for pg in hot:
            bitmap[pg>>3] |= 1<<(pg&7)
        h = C.c_uint(hand)
        f = self.lib.victim(4,C.byref(h),owners,mapped,bitmap,active)
        self.assertEqual(list(owners),[1,2,3,4])
        return f,h.value,list(mapped)

    def test_preferred_frames_remain_mapped(self):
        self.assertEqual(self.victim([0,1,2],1),(3,0,[1,2,3,None]))
        self.assertEqual(self.victim([0,1,2],1,2,(1,2,3,0)),(3,0,[1,2,3,None]))

    def test_all_preferred_or_inactive_falls_back(self):
        self.assertEqual(self.victim(range(4),1),(0,1,[None]*4))
        self.assertEqual(self.victim([0,1,2],0,2),(2,3,[None]*4))

    def test_private_plan_and_digest_gate(self):
        rom = bytearray(ROM_BYTES)
        rom[PAGE_BYTES:2*PAGE_BYTES] = bytes(range(256))*16
        rng = random.Random(5)
        rom[2*PAGE_BYTES:3*PAGE_BYTES] = rng.randbytes(PAGE_BYTES)
        scores = {0:Fraction(2),1:Fraction(1),2:Fraction(3),0x900:Fraction(1)}
        banks,entries,hot = plan_cache(rom,scores,dict(r1=70,r3=300,rt=0),3)
        self.assertTrue(entries)
        self.assertIn(2,hot)
        self.assertFalse({e[0] for e in entries}&set(hot))
        for pg,region,off,size in entries:
            self.assertEqual(decode_page(banks[region][off:off+size]),rom[pg*PAGE_BYTES:(pg+1)*PAGE_BYTES])
        header = render_header(banks,entries,hot)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            sizes={r:len(banks[r]) for r in REGIONS}
            (p/"b3_cache_data.h").write_bytes(header)
            (p/"cache_meta.json").write_text(json.dumps(dict(schema=1,rom_bytes=ROM_BYTES,
                rom_sha256=sha(rom),header_sha256=sha(header),region_bytes=sizes,
                pages=len(entries),hot=len(hot))))
            place=p/"place.h"
            place.write_text("".join("#define SF_NAT_CACHE_%s %du\n"%(r.upper(),sizes[r]) for r in REGIONS))
            self.assertEqual(load_meta(p,rom,place)["pages"],len(entries))
            wrong=bytearray(rom);wrong[0]=1
            with self.assertRaises(ValueError):
                load_meta(p,wrong,place)
            place.write_text("#define SF_NAT_CACHE_R1 0u\n")
            with self.assertRaises(ValueError):
                load_meta(p,rom,place)
            (p/"b3_cache_data.h").write_bytes(header+b" ")
            with self.assertRaises(ValueError):
                load_meta(p,rom)

    def test_runtime_restores_before_counting_physical_miss(self):
        src=(PS1/"stage19/ps1rt/rt.c").read_text()
        part=src[src.index("static __attribute__((noinline)) const u8 *cd_fetch(u32 pg){"):]
        self.assertLess(part.index("b3_restore_page(pg,d"),part.index("PGPROF_MISS(pg); rom_miss_count++",part.index("b3_restore_page(pg,d")))
        self.assertIn("pool_set(f,pg); b3_cache_hits++; return d;",part)
        self.assertIn("if(pz_arm || (pz_done==c && pz_lclk==c)) return 0;",src)


if __name__ == "__main__":
    unittest.main()
