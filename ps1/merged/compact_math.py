#!/usr/bin/env python3
"""Losslessly shrink native SF lookup tables in a private copied build tree.

The original GBA sources, ELF, ROM and generated tables remain untouched.
This is opt-in: the RAM saving is exact at the data level; native instruction
cost and linked total size need a matched B2/B3 build comparison.
"""
import re
from pathlib import Path

TABLES = {'sin_table': ('s16',4096), 'rtab': ('u32',2048), 'erecip': ('u32',2561)}
NEW = {'sfcm_sin_q','sfcm_rtab_lo','sfcm_rtab_hi','sfcm_erecip_hi','sfcm_erecip_lo'}


def read_table(text,name,ctype,count):
    pat=rf'\bconst\s+{ctype}\s+{name}\s*\[\s*{count}\s*\]\s*=\s*\{{([^}}]*)\}}\s*;'
    hits=list(re.finditer(pat,text,re.S))
    if len(hits)!=1:
        raise ValueError('expected exactly one generated table: '+name)
    vals=[int(s.strip(),0) for s in hits[0].group(1).split(',') if s.strip()]
    if len(vals)!=count:
        raise ValueError('wrong table length: '+name)
    return hits[0],vals


def array(name,ctype,values):
    rows=['    '+', '.join(str(x) for x in values[i:i+16])+',' for i in range(0,len(values),16)]
    return f'const {ctype} {name}[{len(values)}] = {{\n'+'\n'.join(rows)+'\n};'


def compress(text):
    found={n:read_table(text,n,t,c) for n,(t,c) in TABLES.items()}
    sin,rtab,erecip=(found[n][1] for n in TABLES)
    q=sin[:1025]
    if any(not -32768<=v<=32767 for v in sin) or q[0]!=0 or q[-1]!=16384:
        raise ValueError('unexpected sine representation')
    restored=[(-1 if i&2048 else 1)*q[min(i&2047,2048-(i&2047))] for i in range(4096)]
    if restored!=sin:
        raise ValueError('sine table is not exactly quadrant symmetric')
    hi=[(v>>16)-8 for v in rtab]
    if any(not 0<=h<=15 for h in hi):
        raise ValueError('reciprocal high nibble outside encoding')
    lo=[v&65535 for v in rtab]
    packed=[hi[i]|(hi[i+1]<<4) for i in range(0,len(hi),2)]
    if [((8+((packed[i>>1]>>(4*(i&1)))&15))<<16)|lo[i] for i in range(2048)]!=rtab:
        raise ValueError('reciprocal round trip mismatch')
    eh,el=erecip[:257],erecip[257:]
    if any(not 0<=v<=0xffffffff for v in eh) or any(not 0<=v<=65535 for v in el):
        raise ValueError('edge reciprocal outside compact representation')
    replacement={
        'sin_table':array('sfcm_sin_q','s16',q),
        'rtab':array('sfcm_rtab_lo','u16',lo)+'\n'+array('sfcm_rtab_hi','u8',packed),
        'erecip':array('sfcm_erecip_hi','u32',eh)+'\n'+array('sfcm_erecip_lo','u16',el),
    }
    for n,(match,_) in sorted(found.items(),key=lambda item:-item[1][0].start()):
        text=text[:match.start()]+replacement[n]+text[match.end():]
    text+='\n/* Native-only quadrant decoder; never called by GBA code. */\n'
    text+='__attribute__((noinline)) s32 sfcm_sin(u32 angle){\n'
    text+='    u32 i=(angle>>4)&4095u, j=i&2047u;\n'
    text+='    s32 v=sfcm_sin_q[j<=1024u?j:2048u-j];\n'
    text+='    return (i&2048u)?-v:v;\n}\n'
    before=4096*2+2048*4+2561*4
    after=1025*2+2048*2+1024+257*4+2304*2
    return text,{'original_table_bytes':before,'compact_table_bytes':after,'raw_table_bytes_saved':before-after}


# Preserve C strings/comments while finding real references. Replacing an
# unknown use with a formula would silently change the game: reject instead.
TOKEN=re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',re.S)


def code_only(text):
    return TOKEN.sub(lambda m:re.sub(r'[^\n]',' ',m.group(0)),text)


def replace_code(text,pattern,replacement,flags=0):
    matches=list(re.finditer(pattern,code_only(text),flags))
    for m in reversed(matches):
        text=text[:m.start()]+replacement(m)+text[m.end():]
    return text


def check_refs(text,path):
    names=r'\b(?:sin_table|rtab|erecip)\b'
    if re.search(names,code_only(text)) or any(
        m.group(0).startswith(chr(34)) and re.search(names,m.group(0)) for m in TOKEN.finditer(text)
    ):
        raise ValueError('unhandled native table reference in '+path.name)


def rewrite_sources(src):
    src=Path(src)
    fx=src/'fx.h'; t=fx.read_text()
    start=re.compile(r'extern const s16 sin_table\[4096\];\s*static inline s32 fsin\(s32 a\) \{ return sin_table\[\(a >> 4\) & 4095\]; \}\s*static inline s32 fcos\(s32 a\) \{ return sin_table\[\(\(a >> 4\) \+ 1024\) & 4095\]; \}')
    t,n=start.subn('#include "compact_math.h"\n\nstatic inline s32 fsin(s32 a) { return sfcm_sin((u32)a); }\nstatic inline s32 fcos(s32 a) { return sfcm_sin((u32)a+16384u); }',t)
    if n!=1: raise ValueError('unrecognized sine accessors in fx.h')
    changed={fx:t}
    for p in sorted(src.glob('*.c')):
        t=p.read_text(); old=t
        for name,n in (('rtab',2048),('erecip',2561)):
            t=replace_code(t,rf'^extern const u32 {name}\[{n}\];[^\n]*\n',lambda m:'',re.M)
            # The current consumers have scalar indices without nested [].
            t=replace_code(t,rf'\b{name}\[([^\[\]\n]+)\]',lambda m:f'sfcm_{name}({m.group(1)})')
        if t!=old:
            changed[p]='#include "compact_math.h"\n'+t
    for p in sorted(src.glob('*')):
        if p.suffix not in ('.c','.h','.s','.S'): continue
        t=changed.get(p,p.read_text())
        check_refs(t,p)
    return changed


def apply(root):
    root=Path(root); tables=root/'build'/'gen'/'tables.c'
    new,report=compress(tables.read_text())
    sources=rewrite_sources(root/'src')
    for path in tables.parent.glob('*.c'):
        if path!=tables: check_refs(path.read_text(),path)
    if not (root/'src'/'compact_math.h').is_file():
        raise ValueError('missing native compact_math.h')
    # All validations precede any writes. Root is natbuild's private copy.
    tables.write_text(new)
    for path,text in sources.items(): path.write_text(text)
    report['rewritten_files']=[p.name for p in sorted(sources)]
    return report
