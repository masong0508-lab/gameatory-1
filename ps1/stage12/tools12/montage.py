import sys,pickle,struct; sys.path.insert(0,'tools12'); from pagerender import *; from PIL import Image,ImageDraw
d=pickle.load(open(sys.argv[1],'rb')); ts=sorted(d['snaps']); n=len(ts); cols=4
W=Image.new('RGB',(240*cols,170*((n+cols-1)//cols)))
for i,t in enumerate(ts):
    s=d['snaps'][t]; disp=struct.unpack_from('<H',s['io'],0)[0]
    im=Image.fromarray(page_img(s['vr'],s['pal'],disp)); dr=ImageDraw.Draw(im); 
    W.paste(im,((i%cols)*240,(i//cols)*170)); ImageDraw.Draw(W).text(((i%cols)*240+2,(i//cols)*170+161),'t%d d%x'%(t,disp),fill=(255,255,0))
W.save(sys.argv[2])
