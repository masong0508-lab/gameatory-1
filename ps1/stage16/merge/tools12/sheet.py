import sys,glob; from PIL import Image,ImageDraw
fs=sorted(glob.glob(sys.argv[1]+'_*.png')); fs=[f for f in fs if '_cmp' not in f]; a,b=int(sys.argv[3]),int(sys.argv[4]); fs=fs[a:b]; cols=6
W=Image.new('RGB',(256*cols,192*((len(fs)+cols-1)//cols)))
for i,f in enumerate(fs):
    im=Image.open(f).convert('RGB').crop((0,0,640,480)).resize((256,192)); W.paste(im,((i%cols)*256,(i//cols)*192)); ImageDraw.Draw(W).text(((i%cols)*256+2,(i//cols)*192+2),f.split('_',1)[1][:22],fill=(255,255,0))
W.save(sys.argv[2])
