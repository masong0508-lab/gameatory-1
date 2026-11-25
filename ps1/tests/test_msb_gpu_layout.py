"""GPU memory ownership gate: allocated sections, load images and stack."""
import struct
import sys
import unittest
from pathlib import Path
from elf_fixture import mips_elf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"merged"))
from gpu_layout import assess, elf_ranges, interval, physical, union_bytes

WORLD=0x800cd800
STACK=(0x800c8000,0x800cd800)


class GPULayout(unittest.TestCase):
    def test_clean_and_overlapping_sections(self):
        self.assertTrue(assess(elf_ranges(mips_elf([0],[])),WORLD,*STACK)["safe"])
        elf=mips_elf([0]*64,[],text_address=0x800ed000)
        report=assess(elf_ranges(elf),WORLD,*STACK)
        self.assertFalse(report["safe"])
        self.assertEqual(report["zones"]["world"]["conflicting_bytes"],256)

    def test_kseg1_alias_and_stack_are_not_free(self):
        elf=mips_elf([0],[],[0]*4,data_address=0xa0108000)
        report=assess(elf_ranges(elf),WORLD,0x80119000,0x8011c000)
        self.assertFalse(report["safe"])
        self.assertEqual(report["zones"]["primitive_ot_stamp_side"]["conflicting_bytes"],8720)
        self.assertEqual(physical(0x00108000),0x80108000)

    def test_load_address_is_checked_even_if_vma_is_elsewhere(self):
        raw=bytearray(mips_elf([0],[],[0x12345678],data_address=0x801ed004))
        shoff,=struct.unpack_from("<I",raw,32)
        dataoff,=struct.unpack_from("<I",raw,shoff+2*40+16)
        phoff=len(raw)
        raw.extend(struct.pack("<8I",1,dataoff,0x801ed004,0x80117000,4,4,6,4))
        struct.pack_into("<I",raw,28,phoff)
        struct.pack_into("<H",raw,44,1)
        report=assess(elf_ranges(raw),WORLD,*STACK)
        self.assertFalse(report["safe"])
        self.assertEqual(report["zones"]["primitive_ot_stamp_side"]["conflicting_bytes"],4)

    def test_overlap_union_does_not_count_twice(self):
        a=interval("a",0x80108000,100)
        b=interval("b",0x80108020,100)
        report=assess([a,b],WORLD,*STACK)
        self.assertEqual(report["zones"]["primitive_ot_stamp_side"]["conflicting_bytes"],132)
        self.assertEqual(union_bytes([(1,5),(5,8),(20,24)]),11)

    def test_invalid_layout_rejected(self):
        with self.assertRaises(ValueError):
            assess([],WORLD+2048,*STACK)
        with self.assertRaises(ValueError):
            assess([],WORLD,0x80120001,0x80123000)
        with self.assertRaises(ValueError):
            elf_ranges(b"invalid")
        with self.assertRaises(ValueError):
            interval("invalid",0x801fffff,2)


if __name__=="__main__":
    unittest.main()
