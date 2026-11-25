"""ROM-free expanded cache placement / seed integrity tests."""
import pathlib
import tempfile
import unittest
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"merged"))
import b3_ext

class ExtendedCacheTest(unittest.TestCase):
    def test_plan_and_ceiling(self):
        self.assertEqual(b3_ext.plan(0x800eb430,0x80047430,48),0x800bb430)
        self.assertEqual(b3_ext.plan(0x800eb430,0x80047430,52),0x800b7430)
        self.assertEqual(b3_ext.plan(0x800eb430,0x80047430,0),0x800eb430)
        for n in (-4,1,56):
            with self.assertRaises(ValueError):
                b3_ext.plan(0x800eb430,0x80047430,n)
        with self.assertRaises(ValueError):
            b3_ext.plan(0x800e7430,0x80047430,52)

    def test_seeds(self):
        self.assertEqual(b3_ext.parse_seeds("1 a # comment\nfff",4),[1,10,4095])
        for data in ("1 01","1000","-1","1 2 3 4 5"):
            with self.assertRaises(ValueError):
                b3_ext.parse_seeds(data,4)

    def test_seed_verify(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)
            rom=p/"rom.gba"
            rom.write_bytes(bytes(16*1024*1024))
            (p/"ids").write_text("1")
            (p/"sfnat_place.h").write_text("#define SF_NAT_EXT_N 4u\n")
            self.assertEqual(b3_ext.generate(p,4,p/"ids",rom),1)
            self.assertEqual(b3_ext.verify(p,rom),4)
            with rom.open("r+b") as f:
                f.write(b"X")
            with self.assertRaises(ValueError):
                b3_ext.verify(p,rom)
            b3_ext.generate(p,4)
            self.assertEqual(b3_ext.verify(p,rom),4)
            with (p/"sfnat_ext_seed.h").open("ab") as f:
                f.write(b"bad")
            with self.assertRaises(ValueError):
                b3_ext.verify(p,rom)

if __name__=="__main__":
    unittest.main()
