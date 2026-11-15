import sys
from PIL import Image
n,u,out=sys.argv[1:4]; ks=[int(v) for v in sys.argv[4].split(',')]
M=Image.new('RGB',(640*2//2*2//1,0)) if False else None
W=427; Hh=320
M=Image.new('RGB',(W*2,Hh*len(ks)))
for i,k in enumerate(ks):
    M.paste(Image.open('%s/p%02d_a.png'%(n,k)).convert('RGB').resize((W,Hh)),(0,i*Hh)); M.paste(Image.open('%s/p%02d_a.png'%(u,k)).convert('RGB').resize((W,Hh)),(W,i*Hh))
M.save(out)
