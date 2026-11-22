#!/usr/bin/env python3
"""Independent BPS patch verify: integrity, size, source copy, overlap and target CRC."""
import hashlib
import sys
import zlib
from pathlib import Path

def apply(source, patch):
    if len(patch) < 19 or not patch.startswith(b'BPS1'):
        raise ValueError('invalid BPS header')
    if zlib.crc32(patch[:-4]) != int.from_bytes(patch[-4:],'little'):
        raise ValueError('invalid patch CRC')
    end=len(patch)-12
    pos=4
    def varnum():
        nonlocal pos
        num=0;step=1
        for _ in range(10):
            if pos>=end:raise ValueError('truncated varnum')
            x=patch[pos];pos+=1
            num+=(x&127)*step
            if x&128:return num
            step <<= 7;num += step
        raise ValueError('varnum too large')
    src_size,tgt_size,meta=varnum(),varnum(),varnum()
    assert src_size==len(source)
    assert end-pos>=meta
    pos+=meta
    assert zlib.crc32(source)==int.from_bytes(patch[-12:-8],'little')
    out=bytearray(tgt_size)
    src_relative=tgt_relative=written=0
    ops=[0,0,0,0]
    while pos<end:
        ins=varnum();op=ins&3;length=(ins>>2)+1
        ops[op]+=1
        assert length<=tgt_size-written,(op,length,written)
        if op==0:
            assert written+length<=len(source)
            out[written:written+length]=source[written:written+length]
        elif op==1:
            assert pos+length<=end
            out[written:written+length]=patch[pos:pos+length]
            pos+=length
        elif op==2:
            d=varnum();d=-(d>>1) if d&1 else (d>>1)
            src_relative+=d
            assert 0<=src_relative<=len(source)-length
            out[written:written+length]=source[src_relative:src_relative+length]
            src_relative+=length
        else:
            d=varnum();d=-(d>>1) if d&1 else (d>>1)
            tgt_relative+=d
            assert 0<=tgt_relative<written
            for k in range(length):
                out[written+k]=out[tgt_relative+k]
            tgt_relative+=length
        written+=length
    assert written==tgt_size
    assert zlib.crc32(out)==int.from_bytes(patch[-8:-4],'little')
    return bytes(out),ops

if __name__=='__main__':
    source=Path(sys.argv[1]).read_bytes()
    patch=Path(sys.argv[2]).read_bytes()
    expected=Path(sys.argv[3]).read_bytes()
    result,ops=apply(source,patch)
    assert result==expected,'applied output differs from original produced image'
    print('BPS application: PASSED')
    print('BPS operations (SourceRead, TargetRead, SourceCopy, TargetCopy):',ops)
    print('Target SHA1:',hashlib.sha1(result).hexdigest())
