#!/usr/bin/env python3 -I
"""mkmaps7.py: all 11 maps in the stage 4 sf3 compact layout.  usage: mkmaps7.py MAPS_PARENT ELF ROM OUTDIR
OUTDIR/m<N>/{SF3W.BIN,SF3A.BIN,SIDE.BIN} per map (stage 4 mksf3.py layout) + OUTDIR/SF3M.BIN (CD image: sector 0 header 'SF3M', u32 n, per map 8 u32:
first sector, SF3W sectors, SF3A sectors, SIDE bytes, start x,y,z, 0; then per map SF3W, SF3A, SIDE each sector aligned).
Derived from the player's ROM: build output only, never committed."""
import sys,os,struct,subprocess,importlib.util,json
par,elf,rom,out=sys.argv[1:5]
here=os.path.dirname(os.path.abspath(__file__))
sp=importlib.util.spec_from_file_location('mkps1world',here+'/mkps1world.py'); m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
rd=open(rom,'rb').read(); os.makedirs(out,exist_ok=True)
pad=lambda b:b+b'\0'*((-len(b))%2048)
hdr=struct.pack('<4sI',b'SF3M',11); body=b''; sec=1; man=[]
for n in range(11):
    d,info=m.convert('%s/world%d'%(par,n),elf,rd)
    w=out+'/m%d'%n; os.makedirs(w,exist_ok=True)
    for k,fn in (('WORLD','WORLD.SFW'),('ATLAS','ATLAS.VRM'),('SIDE','SIDE.BIN'),('CLUT','CLUT.BIN')): open(w+'/'+fn,'wb').write(d[k])
    open(w+'/FONT.VRM','wb').write(m.make_font())
    subprocess.run([sys.executable,'-I',here+'/mksf3.py',w,w],check=True,stdout=subprocess.DEVNULL)
    parts=[open(w+'/SF3W.BIN','rb').read(),open(w+'/SF3A.BIN','rb').read(),d['SIDE']]
    hdr+=struct.pack('<8I',sec,len(parts[0])//2048,len(parts[1])//2048,len(parts[2]),*info['start'],0)
    for p in parts: body+=pad(p); sec+=len(pad(p))//2048
    man.append(dict(map=n,w=len(parts[0]),a=len(parts[1]),s=len(parts[2]),start=info['start'])); print(n,man[-1],flush=True)
open(out+'/SF3M.BIN','wb').write(pad(hdr)+body); json.dump(man,open(out+'/manifest.json','w'))
print('SF3M.BIN sectors',sec)
