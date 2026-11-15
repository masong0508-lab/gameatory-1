import sys
f=sys.argv[1]; d=[tuple(map(int,l.split())) for l in open(f)]
n={a:b for a,b,c in d}; cy={a:b+c for a,b,c in d}   # instr-equivalents ; plus mult/div penalty cycles
def w(a,b,m=n): return [m[i]+m.get(i+1,0) for i in range(a,b)]   # cost of one 30 fps frame = two 60 Hz ticks
for name,a,b in (('six-in-flight window ticks 170-300',170,300),('ticks 100-170 driver only',100,170),('whole run',0,719)):
    x=w(a,b); y=w(a,b,cy)
    print(f'{name}: per 30fps frame instr avg {sum(x)//len(x)} max {max(x)} | with mult/div model avg {sum(y)//len(y)} max {max(y)}')
