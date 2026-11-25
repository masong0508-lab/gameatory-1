#!/usr/bin/env python3
"""Fail closed before a merged-native PS1 build can claim sf3's memory.

Inspect the actual ELF's allocated sections and file-backed load addresses,
plus the native stack (which has no ELF section). No ROM contents needed.
The world address comes from the matching prepared t/worldaddr.py.
"""
import argparse
import json
import struct
from pathlib import Path

RAM_LO, RAM_HI = 0x80000000, 0x80200000
PBUF, WORLD_END = 0x80108000, 0x8011b200
MIN_WORLD = 239616


def physical(addr):
    if 0 <= addr < 0x200000:
        return RAM_LO + addr
    if RAM_LO <= addr < RAM_HI:
        return addr
    if 0xa0000000 <= addr < 0xa0200000:
        return addr - 0x20000000
    raise ValueError("address outside PS1 main RAM")


def interval(name, addr, size):
    start = physical(addr)
    if size <= 0 or start + size > RAM_HI:
        raise ValueError("invalid live range: " + name)
    return name, start, start + size


def elf_ranges(raw):
    if len(raw) < 52 or raw[:6] != b"\x7fELF\x01\x01" or struct.unpack_from("<H",raw,18)[0] != 8:
        raise ValueError("expected ELF32 little-endian MIPS")
    phoff, shoff = struct.unpack_from("<II",raw,28)
    phents, phnum, shents, shnum, stridx = struct.unpack_from("<HHHHH",raw,42)
    if shents < 40 or not shnum or stridx >= shnum or shoff + shents*shnum > len(raw):
        raise ValueError("invalid ELF section table")
    if phnum and (phents < 32 or phoff + phents*phnum > len(raw)):
        raise ValueError("invalid ELF load table")
    secs=[struct.unpack_from("<10I",raw,shoff+i*shents) for i in range(shnum)]
    strings=secs[stridx]
    if strings[4]+strings[5]>len(raw):
        raise ValueError("invalid ELF string table")
    names=raw[strings[4]:strings[4]+strings[5]]
    live=[]
    for name,typ,flags,addr,off,size,*_ in secs:
        if not flags&2 or not size:  # SHF_ALLOC
            continue
        if name>=len(names) or (typ!=8 and off+size>len(raw)):
            raise ValueError("invalid allocated section")
        label=names[name:].split(b"\0",1)[0].decode("ascii",errors="replace")
        live.append(interval(label,addr,size))
    for i in range(phnum):
        typ,off,vma,lma,filesz,memsz,_,_=struct.unpack_from("<8I",raw,phoff+i*phents)
        if typ!=1 or not filesz or vma==lma:
            continue
        if off+filesz>len(raw) or filesz>memsz:
            raise ValueError("invalid file-backed load segment")
        live.append(interval("load-image-%d"%i,lma,filesz))
    return live


def union_bytes(spans):
    end=total=0
    for lo,hi in sorted(spans):
        if hi>end:
            total+=hi-max(lo,end)
            end=hi
    return total


def assess(live, world, stack_lo, stack_hi):
    if world%2048 or not RAM_LO<=world<=PBUF-MIN_WORLD:
        raise ValueError("sf3 world window must fit the largest map")
    if not RAM_LO<=stack_lo<stack_hi<=RAM_HI or stack_lo%16 or stack_hi%16:
        raise ValueError("invalid native stack bounds")
    live=list(live)+[interval("native-stack",stack_lo,stack_hi-stack_lo)]
    zones={"world":(world,PBUF),"primitive_ot_stamp_side":(PBUF,WORLD_END)}
    report={}
    for zone,(start,end) in zones.items():
        overlap=[]
        for name,lo,hi in live:
            a,b=max(lo,start),min(hi,end)
            if a<b:
                overlap.append(dict(owner=name,start=a,end=b,bytes=b-a))
        report[zone]=dict(start=start,end=end,capacity_bytes=end-start,
                          conflicting_bytes=union_bytes((x["start"],x["end"]) for x in overlap),
                          conflicts=overlap)
    return dict(safe=not any(x["conflicts"] for x in report.values()),zones=report)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--elf",type=Path,required=True)
    ap.add_argument("--world-start",type=lambda v:int(v,0),required=True)
    ap.add_argument("--stack-lo",type=lambda v:int(v,0),required=True)
    ap.add_argument("--stack-hi",type=lambda v:int(v,0),required=True)
    args=ap.parse_args()
    try:
        result=assess(elf_ranges(args.elf.read_bytes()),args.world_start,args.stack_lo,args.stack_hi)
    except (OSError,ValueError,struct.error) as exc:
        ap.error(str(exc))
    print(json.dumps(result,indent=2))
    return 0 if result["safe"] else 1


if __name__=="__main__":
    raise SystemExit(main())
