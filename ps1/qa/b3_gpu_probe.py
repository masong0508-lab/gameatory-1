#!/usr/bin/env python3
"""Private, synthetic GPU/GTE probe using the actual B3 packet header.

Run once per core. The existing user's private MODE2/2352 disc is only a
boot carrier; its PSX.EXE is replaced in a scratch data-track copy with
the synthetic test. Original disc is never modified. No game execution,
screenshots or private files are needed in the repository.
"""
import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

PS1=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PS1/"rig"))
sys.path.insert(0,str(PS1/"rig/tools"))
from patch_disc import fix_sector
from obrig import Emu2

POINTS=[(-90,50,160),(90,50,160),(-90,-50,160),(90,-50,160),
        (0,0,32),(100,-20,300),(-300,100,700),(300,120,850)]
FLAGS="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic -ffreestanding -G0 -mno-gpopt -Os -mno-check-zero-division -mllvm -disable-mips-delay-filler".split()


def build(out):
    tree=out/"prepared"
    subprocess.run([sys.executable,str(PS1/"tools/prepare.py"),"--output",str(tree)],check=True)
    clang=shutil.which("clang")
    nm=shutil.which("llvm-nm") or shutil.which("nm")
    objcopy=shutil.which("llvm-objcopy")
    lld=shutil.which("ld.lld")
    if not all((clang,nm,objcopy,lld)):
        raise ValueError("probe needs clang, ld.lld, llvm-objcopy and nm")
    subprocess.run([clang,*FLAGS,"-I"+str(tree/"sf"),"-c",
                    str(PS1/"qa/b3_gpu_probe.c"),"-o",str(out/"probe.o")],check=True)
    subprocess.run([clang,*FLAGS,"-c",str(PS1/"hello/crt0.s"),
                    "-o",str(out/"crt0.o")],check=True)
    elf=out/"probe.elf"
    subprocess.run([lld,"-T",str(PS1/"hello/ps1.ld"),str(out/"crt0.o"),
                    str(out/"probe.o"),"-o",str(elf)],check=True)
    subprocess.run([objcopy,"-O","binary",str(elf),str(out/"probe.bin")],check=True)
    syms={s[2]:int(s[0],16) for line in subprocess.check_output(
        [nm,str(elf)],text=True).splitlines() if len(s:=line.split())==3}
    raw=(out/"probe.bin").read_bytes()
    raw+=bytes(-len(raw)%2048)
    header=bytearray(2048)
    header[:8]=b"PS-X EXE"
    struct.pack_into("<IIIIIIIIIIII",header,0x10,0x80010000,0,0x80010000,len(raw),
                     0,0,0,0,0x801fff00,0,0,0)
    return bytes(header)+raw,syms["results"]


def private_carrier(cue,exe,out):
    """Copy only the first data track; replace its EXE and root size."""
    text=cue.read_text()
    files=re.findall(r'FILE\s+"([^"]+)"\s+BINARY',text,re.I)
    if len(files)!=1 or not re.search(r'TRACK\s+01\s+MODE2/2352',text,re.I):
        raise ValueError("expected one-BIN MODE2/2352 carrier")
    raw=(cue.parent/files[0]).resolve()
    tracks=re.split(r'TRACK\s+\d+\s+',text,flags=re.I)[1:]
    start=re.search(r'INDEX\s+01\s+00:00:00',tracks[0],re.I)
    if not start:
        raise ValueError("carrier data track must begin at sector zero")
    n=raw.stat().st_size//2352
    if len(tracks)>1:
        m=re.search(r'INDEX\s+0[01]\s+(\d+):(\d+):(\d+)',tracks[1],re.I)
        if not m:
            raise ValueError("missing next track index")
        a,b,c=map(int,m.groups())
        n=a*4500+b*75+c
    if n<32 or n*2352>raw.stat().st_size:
        raise ValueError("invalid first data track size")
    with raw.open("rb") as stream:
        image=bytearray(stream.read(n*2352))
    def user(lba):
        if not 0<=lba<n:
            raise ValueError("carrier sector outside data track")
        return memoryview(image)[lba*2352+24:lba*2352+24+2048]
    pvd=user(16)
    if bytes(pvd[1:6])!=b"CD001":
        raise ValueError("carrier is not an ISO9660 data track")
    root,rs=struct.unpack_from("<I",pvd,158)[0],struct.unpack_from("<I",pvd,166)[0]
    for i in range((rs+2047)//2048):
        directory=user(root+i)
        off=0
        while off<len(directory) and directory[off]:
            length=directory[off]
            if length<34 or off+length>len(directory):
                raise ValueError("bad ISO directory record")
            name=bytes(directory[off+33:off+33+directory[off+32]]).split(b";")[0]
            if name==b"PSX.EXE":
                lba,size=struct.unpack_from("<I",directory,off+2)[0],struct.unpack_from("<I",directory,off+10)[0]
                if len(exe)>size or lba+(len(exe)+2047)//2048>n:
                    raise ValueError("test EXE does not fit carrier")
                struct.pack_into("<I",directory,off+10,len(exe))
                struct.pack_into(">I",directory,off+14,len(exe))
                dirty=[root+i]
                for j in range(0,len(exe),2048):
                    q=lba+j//2048
                    user(q)[:]=exe[j:j+2048]
                    dirty.append(q)
                for q in dirty:
                    image[q*2352:(q+1)*2352]=fix_sector(image[q*2352:(q+1)*2352])
                (out/"probe.raw.bin").write_bytes(image)
                path=out/"probe.cue"
                path.write_text('FILE "probe.raw.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
                return path
            off+=length
    raise ValueError("PSX.EXE absent from carrier")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--carrier",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--core",choices=("swanstation","beetle"),required=True)
    ap.add_argument("--sys",type=Path,required=True)
    ap.add_argument("--frames",type=int,default=1200)
    args=ap.parse_args()
    root=args.out.resolve()
    if root.is_relative_to(PS1.parent) or not 60<=args.frames<=3600:
        ap.error("use a new private output outside checkout, 60..3600 frames")
    root.mkdir(parents=True,exist_ok=False)
    exe,address=build(root)
    disc=private_carrier(args.carrier.resolve(),exe,root)
    emu=Emu2(args.core,str(disc),str(root/"run"),sysdir=str(args.sys.resolve()))
    try:
        for start in range(0,args.frames,60):
            emu.run(min(60,args.frames-start))
            if emu.r32(address)==0xb3c0ffee:
                break
        v=struct.unpack("<40I",emu.read(address,160))
        errors=[]
        for fi,f in enumerate((136,176)):
            for i,(x,y,z) in enumerate(POINTS):
                sx,sy=struct.unpack("<hh",struct.pack("<I",v[10+fi*8+i]))
                ref=(round(160+4*f*x/(3*z)),round(120-7*f*y/(5*z)))
                errors.append(max(abs(sx-ref[0]),abs(sy-ref[1])))
        expected=[0x3e0,0x1f,0,0,0x3e0,0x3e0,0]
        result=dict(core=args.core,frames=emu.frames,completed=v[0]==0xb3c0ffee,
                    packet_errors=v[1],pixel_samples_passed=sum(a==b for a,b in zip(v[2:9],expected)),
                    projection_samples=len(errors),max_projection_error_px=max(errors))
        result["passed"]=(result["completed"] and v[1]==0 and
                          result["pixel_samples_passed"]==7 and max(errors)<=1)
        (root/"numeric_result.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result,indent=2))
        return 0 if result["passed"] else 1
    finally:
        emu.close()


if __name__=="__main__":
    raise SystemExit(main())
