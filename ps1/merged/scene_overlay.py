#!/usr/bin/env python3
"""Pack a linked MIPS-I scene overlay into a private sector-aligned SOV1 file.

Overlay ELF is linked at the explicit slot address. All writable/persistent
state must be in resident guest RAM, not in the overlay; no dynamic relocations,
undefined imports or writable allocated sections are accepted. Entry IDs map
to actual executable function symbols. Generated code/data stay private.
"""
import argparse
import struct
import zlib
from pathlib import Path

SECTOR=2048
MAGIC=0x31564f53
MAX_SLOT=0x22000
MAX_ENTRY=64


def pack_elf(raw, scene, address, capacity, entries):
    if scene not in (1,2) or address%SECTOR or capacity%SECTOR or not 0<capacity<=MAX_SLOT or not 0x80010000<=address<address+capacity<=0x801f8000:
        raise ValueError('invalid scene or slot')
    if len(raw)<52 or raw[:6]!=b'\x7fELF\x01\x01' or struct.unpack_from('<HH',raw,16)!=(2,8):
        raise ValueError('expected linked ELF32 little-endian MIPS executable')
    shoff,=struct.unpack_from('<I',raw,32)
    shents,shnum,stridx=struct.unpack_from('<HHH',raw,46)
    if shents!=40 or not shnum or stridx>=shnum or shoff+shnum*shents>len(raw):
        raise ValueError('invalid ELF section table')
    sections=[struct.unpack_from('<10I',raw,shoff+i*shents) for i in range(shnum)]
    def data(s):
        if s[4]+s[5]>len(raw): raise ValueError('truncated ELF section')
        return raw[s[4]:s[4]+s[5]]
    def name(table,off):
        if off>=len(table) or b'\0' not in table[off:]: raise ValueError('invalid string table')
        return table[off:].split(b'\0',1)[0].decode('ascii')
    strings=data(sections[stridx]); image=bytearray(capacity); used=[]; code=set(); symbols={}
    for i,s in enumerate(sections):
        label=name(strings,s[0]); typ,flags,ad,off,size=s[1:6]
        if typ in (4,9) and size: raise ValueError('overlay must have no relocation sections')
        if not flags&2 or not size: continue
        if typ!=1 or flags&1 or not address<=ad<ad+size<=address+capacity:
            raise ValueError('allocated section is writable or outside slot: '+label)
        a,b=ad-address,ad-address+size
        if any(a<hi and b>lo for lo,hi in used): raise ValueError('overlapping allocated sections')
        used.append((a,b)); image[a:b]=data(s)
        if flags&4: code.add(i)
    if not code or not used: raise ValueError('no executable overlay')
    for s in sections:
        if s[1]!=2: continue
        if s[6]>=len(sections) or s[9]!=16 or s[5]%16: raise ValueError('invalid symbols')
        table=data(sections[s[6]])
        for off in range(0,s[5],16):
            nm,value,size,info,other,idx=struct.unpack_from('<IIIBBH',raw,s[4]+off)
            if idx==0 and nm and info>>4: raise ValueError('unresolved overlay import: '+name(table,nm))
            if idx in code and info&15==2 and info>>4==1:
                sec=sections[idx]
                if value%4 or not size or not sec[3]<=value<value+size<=sec[3]+sec[5]: raise ValueError('invalid function extent')
                key=name(table,nm)
                if key in symbols: raise ValueError('duplicate entry symbol')
                symbols[key]=value-address
    if not 0<len(entries)<=MAX_ENTRY: raise ValueError('entry count outside limits')
    rows=[]
    for ident,symbol in sorted(entries.items()):
        if type(ident)!=int or not 0<ident<=0xffffffff or symbol not in symbols: raise ValueError('entry is not a global executable function: '+str(symbol))
        rows.append((ident,symbols[symbol]))
    size=(max(hi for _,hi in used)+3)&~3; sectors=(size+SECTOR-1)//SECTOR
    payload=bytes(image[:sectors*SECTOR]); header=bytearray(SECTOR)
    struct.pack_into('<10I',header,0,MAGIC,1,scene,address,capacity,size,sectors,zlib.crc32(payload),len(rows),0)
    for i,row in enumerate(rows): struct.pack_into('<2I',header,40+i*8,*row)
    struct.pack_into('<I',header,SECTOR-4,zlib.crc32(header[:-4]))
    return bytes(header)+payload


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--elf',type=Path,required=True); ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--scene',type=int,choices=(1,2),required=True)
    ap.add_argument('--address',type=lambda x:int(x,0),required=True); ap.add_argument('--capacity',type=lambda x:int(x,0),required=True)
    ap.add_argument('--entry',action='append',required=True,help='ID:global_function')
    a=ap.parse_args(argv)
    try:
        parent=Path(__file__).resolve().parents[1]; repo=parent.parent if parent.name=='ps1' else parent
        if a.out.resolve().is_relative_to(repo): raise ValueError('output must be outside source checkout')
        entries={}
        for spec in a.entry:
            k,v=spec.split(':',1); ident=int(k,0)
            if ident in entries: raise ValueError('duplicate entry ID')
            entries[ident]=v
        blob=pack_elf(a.elf.read_bytes(),a.scene,a.address,a.capacity,entries)
        with a.out.open('xb') as f: f.write(blob)
        print('private SOV1 overlay:',len(blob)//SECTOR,'sectors;',len(entries),'entries')
    except (OSError,ValueError,struct.error) as exc: ap.error(str(exc))
    return 0

if __name__=='__main__': raise SystemExit(main())
