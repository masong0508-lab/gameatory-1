import pickle,sys
A=pickle.load(open(sys.argv[1],'rb')); B=pickle.load(open(sys.argv[2],'rb'))
n=min(len(A),len(B)); print('presents compared',n,'last frame',A[n-1][1] if n else None)
bad=[i for i in range(n) if A[i][2:]!=B[i][2:]]
bh=[i for i in range(n) if A[i][2]!=B[i][2]]; bi=[i for i in range(n) if A[i][3:]!=B[i][3:]]
print('state-hash mismatches',len(bh),'first',bh[:3],'| io-write mismatches',len(bi),'first',bi[:3])
if bad: i=bad[0]; print('first divergence present',A[i][0],'frame',A[i][1],A[i],B[i])
