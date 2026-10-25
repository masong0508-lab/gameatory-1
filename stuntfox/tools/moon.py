import math, itertools
t=(1+5**0.5)/2
V=[(-1,t,0),(1,t,0),(-1,-t,0),(1,-t,0),(0,-1,t),(0,1,t),(0,-1,-t),(0,1,-t),(t,0,-1),(t,0,1),(-t,0,-1),(-t,0,1)]
V=[tuple(c/math.sqrt(x*x+y*y+z*z) for c in (x,y,z)) for x,y,z in V]
F=[(0,11,5),(0,5,1),(0,1,7),(0,7,10),(0,10,11),(1,5,9),(5,11,4),(11,10,2),(10,7,6),(7,1,8),(3,9,4),(3,4,2),(3,2,6),(3,6,8),(3,8,9),(4,9,5),(2,4,11),(6,2,10),(8,6,7),(9,8,1)]
mid={}
def m(a,b):
    k=(min(a,b),max(a,b))
    if k not in mid:
        p=[(V[a][i]+V[b][i]) for i in range(3)]
        l=math.sqrt(sum(c*c for c in p)); V.append(tuple(c/l for c in p)); mid[k]=len(V)-1
    return mid[k]
G=[]
for a,b,c in F:
    ab,bc,ca=m(a,b),m(b,c),m(c,a)
    G+= [(a,ab,ca),(b,bc,ab),(c,ca,bc),(ab,bc,ca)]
print(len(V),len(G))
# verts at radius 256, wind outward (ccw seen from outside) -- model.c flips normals itself but we compute own
R=256
pv=[tuple(round(c*R) for c in v) for v in V]
out=[]
import random
random.seed(7)
for (a,b,c) in G:
    A,B,C=[V[i] for i in (a,b,c)]
    e1=[B[i]-A[i] for i in range(3)]; e2=[C[i]-A[i] for i in range(3)]
    n=[e1[1]*e2[2]-e1[2]*e2[1],e1[2]*e2[0]-e1[0]*e2[2],e1[0]*e2[1]-e1[1]*e2[0]]
    cen=[(A[i]+B[i]+C[i])/3 for i in range(3)]
    if sum(n[i]*cen[i] for i in range(3))<0:
        b,c=c,b; B,C=C,B; n=[-x for x in n]
    l=math.sqrt(sum(x*x for x in n)); n=[x/l for x in n]
    # plane distance in unit-radius terms using real (rounded) verts
    d=sum(n[i]*pv[a][i] for i in range(3))/R  # n . vertex, vertex radius 1
    # use mean of three rounded verts
    d=sum(n[i]*(pv[a][i]+pv[b][i]+pv[c][i])/3 for i in range(3))/R
    out.append((a,b,c,[round(x*16384) for x in n],round(d*16384)))
print('d range',min(o[4] for o in out)/16384,max(o[4] for o in out)/16384)
with open('moon_tables.h','w') as f:
    f.write('static const s16 moon_v[%d][3] = {\n'%len(pv))
    for i in range(0,len(pv),6):
        f.write('    '+' '.join('{%d, %d, %d},'%p for p in pv[i:i+6])+'\n')
    f.write('};\n')
    f.write('/* face: its three corners, its outward normal (1.14) and how far its plane lies from the middle (1.14 of the radius), and 2^29 / that */\n')
    f.write('static const struct { u8 a, b, c; s16 n[3], d; u16 id; } moon_f[%d] = {\n'%len(out))
    for i in range(0,len(out),3):
        f.write('    '+' '.join('{%d, %d, %d, {%d, %d, %d}, %d, %d},'%(o[0],o[1],o[2],*o[3],o[4],round(2**29/o[4])) for o in out[i:i+3])+'\n')
    f.write('};\n')

    # the coarse moon: the same twelve corners in the 20 big faces, outward normals (every plane 13020/16384 of the radius out)
    f.write('static const struct { u8 a, b, c; s16 n[3]; } moon_c20[20] = {\n')
    for i, (a, b, c) in enumerate(F):
        A, B, C = V[a], V[b], V[c]
        e1 = [B[k] - A[k] for k in range(3)]; e2 = [C[k] - A[k] for k in range(3)]
        n = [e1[1]*e2[2]-e1[2]*e2[1], e1[2]*e2[0]-e1[0]*e2[2], e1[0]*e2[1]-e1[1]*e2[0]]
        if sum(n[k]*(A[k]+B[k]+C[k]) for k in range(3)) < 0: n = [-x for x in n]
        l = math.sqrt(sum(x*x for x in n))
        f.write('    {%d, %d, %d, {%d, %d, %d}},\n' % (a, b, c, *[round(x/l*16384) for x in n]))
    f.write('};\n')
