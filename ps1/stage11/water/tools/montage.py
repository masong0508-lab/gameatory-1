import sys
from PIL import Image
d=sys.argv[1]; ks=[int(v) for v in sys.argv[3].split(',')]; out=sys.argv[2]; cols=3
ims=[Image.open('%s/p%02d_a.png'%(d,k)).convert('RGB').resize((427,320)) for k in ks]
rows=(len(ims)+cols-1)//cols
M=Image.new('RGB',(427*cols,320*rows))
for i,im in enumerate(ims): M.paste(im,((i%cols)*427,(i//cols)*320))
M.save(out)
