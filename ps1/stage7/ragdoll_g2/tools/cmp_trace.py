import re,sys,math
def load(f):
    d={}
    for l in open(f):
        m=re.match(r'F (\d+) car',l)
        if not m: continue
        t=int(m.group(1))
        for i,h,x,y,z,s in re.findall(r'(\d+):([0-9a-f]{8})\((-?\d+),(-?\d+),(-?\d+),s(\d)\)',l):
            d[(t,int(i))]=(int(x)/1048576,int(y)/1048576,int(z)/1048576)
    return d
ref=load(sys.argv[1])
for name in sys.argv[2:]:
    c=load(name); out=[]
    for i in range(6):
        ks=[k for k in ref if k[1]==i and k in c]
        dev=[(k[0],math.dist(ref[k],c[k])) for k in sorted(ks)]
        early=[e for t,e in dev if t<=260]; 
        out.append(f'doll{i}: max {max(e for t,e in dev):.2f} m, mean {sum(e for t,e in dev)/len(dev):.2f} m, end {dev[-1][1]:.2f} m')
    print(name); print('  '+'\n  '.join(out))
