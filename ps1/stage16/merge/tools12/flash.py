import sys,subprocess,numpy as np
# usage: flash.py cap.mp4 : 5 fps capture of the PCSXR window (640x480 at 0,0); mean luminance per captured frame; flash events = opposing swings > 10% (of full scale) between consecutive captures
f=sys.argv[1]
raw=subprocess.run(['ffmpeg','-loglevel','error','-i',f,'-vf','crop=640:480:0:0,scale=160:120,format=gray','-f','rawvideo','-'],capture_output=True).stdout
a=np.frombuffer(raw,np.uint8).reshape(-1,120,160).astype(float); L=a.mean((1,2))/255; d=np.diff(L)
ev=[(i,float(d[i]),float(d[i+1])) for i in range(len(d)-1) if abs(d[i])>0.10 and abs(d[i+1])>0.10 and d[i]*d[i+1]<0]
big=np.abs(d).max() if len(d) else 0
print(f,'captures',len(L),'(%.0f s)'%(len(L)/5),'max step %.3f'%big,'opposing swings >10%%: %d'%len(ev),ev[:8])
# also: any capture that differs from both neighbours by >5% area-brightness
iso=[i for i in range(1,len(L)-1) if abs(L[i]-L[i-1])>0.05 and abs(L[i]-L[i+1])>0.05 and (L[i]-L[i-1])*(L[i]-L[i+1])>0]
print('isolated single-capture spikes >5%%: %d'%len(iso),iso[:10])
