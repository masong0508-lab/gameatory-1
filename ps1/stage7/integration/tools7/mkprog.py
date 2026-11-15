import sys,os,pickle
sys.path.insert(0,'.')
import disc,prune
rom=open(os.environ['ROM'],'rb').read(); iw=open('out/iw.bin','rb').read()
P=disc.discover(rom,iw,False,stubs=prune.stub_dict(),templates=[],extra=[(0x100,prune.SWI_STUB)],seeds=[(0x100,'A')])
P.img=None; pickle.dump(P,open('out/s2/prog_pr.pkl','wb')); print('prog ok',len(P.ins))
