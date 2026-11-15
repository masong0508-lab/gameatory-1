import sys,re
def load(f):
    r=[]
    for l in open(f,errors='ignore'):
        m=re.search(r'SPIN (\d+) hd (\d+) host (\d+) prim (\d+) lod (\d+) hash (\S+) ph ([\d ]+)cnt ([\d ]+)',l)
        if m: r.append((int(m[1]),int(m[2]),int(m[3]),int(m[4]),int(m[5]),m[6],list(map(int,m[7].split())),list(map(int,m[8].split()))))
    return r
if __name__=='__main__':
    r=load(sys.argv[1]); n0=int(sys.argv[2]) if len(sys.argv)>2 else 0
    r=[x for x in r if x[0]>=n0]
    if not r: print('none'); sys.exit()
    n=len(r); print('n',n,'mean host %.1f max %d'%(sum(x[2] for x in r)/n,max(x[2] for x in r)),'prim %.0f'%(sum(x[3] for x in r)/n))
    print('lod dist',{l:sum(1 for x in r if x[4]==l) for l in range(4)})
    print('ph mean sky isl city gnd ents hud send',[round(sum(x[6][k] for x in r)/n,1) for k in range(7)])
    print('cnt mean proj leaf clip box ramp tree gc clipt rect qoff qf nbox nrect ncell ncull ncleaf wg fw top nwg nwcell nwq nwfallback gc_edge gc_rect gt_row0 gt_rowproj fan',[round(sum(x[7][k] for x in r)/n,1) for k in range(28)])
