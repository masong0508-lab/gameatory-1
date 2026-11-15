import sys
d=[tuple(map(int,l.split())) for l in open(sys.argv[1])]; n={a:b for a,b,c in d}; cy={a:b+c for a,b,c in d}
def w(a,b,m): return [m[i]+m.get(i+1,0) for i in range(a,b)]
x=w(10,130,n); y=w(10,130,cy)
print(f'AIR6 ticks 10-130 per 30fps frame: instr avg {sum(x)//len(x)} max {max(x)} | with mult/div model avg {sum(y)//len(y)} max {max(y)}')
