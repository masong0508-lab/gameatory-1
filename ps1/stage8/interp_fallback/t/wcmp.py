import sys
def mp(v):
    if 0x02000000<=v<=0x02040000: return 0x801b0000+v-0x02000000
    if 0x03000000<=v<0x04000000: return 0x801f0000+(v&0x7fff)
    return v
def iscode(v): return 0x80000000<=v<0x801b0000 or 0x801f8000<=v<0x80800000
def load(fn):
    raw=[]
    for l in open(fn):
        p=l.split(); a=int(p[0],16); sz=int(p[1][2:]); v=int(p[2][2:],16); rest=l.split(' pc=')[1].strip()
        for i in range(sz): raw.append((a+i,(v>>(8*i))&0xff,rest))
    out=[]; i=0
    while i<len(raw):
        a=raw[i][0]
        if a%4==0 and i+3<len(raw) and all(raw[i+k][0]==a+k for k in (1,2,3)):
            w=sum(raw[i+k][1]<<(8*k) for k in range(4)); out.append((a,4,w,raw[i][2])); i+=4
        else: out.append((a,1,raw[i][1],raw[i][2])); i+=1
    return out
def eq(x,y):
    if x[:2]!=y[:2]: return False
    if x[1]==1: return x[2]==y[2]
    a,b=x[2],y[2]
    if a==b: return True
    if iscode(a) and iscode(b): return True
    return mp(a)==mp(b)
if __name__=='__main__':
    A=load(sys.argv[1]); B=load(sys.argv[2]); LIM=int(sys.argv[3],16) if len(sys.argv)>3 else 0x1f6000
    A=[x for x in A if x[0]<LIM]; B=[x for x in B if x[0]<LIM]
    print(len(A),len(B)); i=0
    while i<min(len(A),len(B)) and eq(A[i],B[i]): i+=1
    print('first mismatch idx',i)
    for k in range(max(0,i-3),i+6):
        print(k,'A',hex(A[k][0]),A[k][1],'%x'%A[k][2],A[k][3][:80],'| B',hex(B[k][0]),B[k][1],'%x'%B[k][2],B[k][3][:80])
