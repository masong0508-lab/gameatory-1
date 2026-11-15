import sys,subprocess,numpy as np
# usage: flash.py cap.mp4 [fps]; decodes at 5 fps, 800x600 gray; analyzes the PCSXR window region only (whole screen)
f=sys.argv[1]; fps=5
raw=subprocess.run(['ffmpeg','-loglevel','error','-i',f,'-vf','scale=200:150,format=gray','-f','rawvideo','-'],capture_output=True).stdout
a=np.frombuffer(raw,np.uint8).reshape(-1,150,200).astype(float)/255
n=len(a); lum=a.mean((1,2))
# relative luminance change between successive distinct frames; general flash = pair of opposing changes >=10% of full-range luminance, area >= 25% of frame
d=np.diff(a,axis=0); big=(np.abs(d)>0.1).mean((1,2))   # fraction of pixels changing by >10% luminance
dl=np.diff(lum)
print("frames",n,"duration %.0fs"%(n/fps))
print("max whole-screen mean-luminance step: %.3f (flash threshold 0.10 swing)"%np.abs(dl).max())
print("max fraction of pixels changing >10%% between captures: %.3f at t=%.1fs"%(big.max(),big.argmax()/fps))
# opposing-change pairs: sign change of dl with both |dl|>0.10
pairs=[i for i in range(len(dl)-1) if abs(dl[i])>0.10 and abs(dl[i+1])>0.10 and dl[i]*dl[i+1]<0]
print("opposing mean-luminance swings >10%%: %d"%len(pairs))
# area-based: count captures where >25% of pixels change >10% (potential flash events)
ev=np.where(big>0.25)[0]; print("captures with >25%% of area changing >10%%: %d"%len(ev), [round(e/fps,1) for e in ev[:20]])
# worst 1-second window event count of such large changes
w=max((big[i:i+fps]>0.25).sum() for i in range(max(1,len(big)-fps)))
print("max such events in any 1 s window (limit 3):",w)
# conservative re-timing: drop duplicate captures, treat each distinct presented frame as one 1/30 s frame (the target rate on a console)
keep=[0]+[i for i in range(1,n) if np.abs(a[i]-a[i-1]).max()>0.02]
b=a[keep]; m=len(b); print("distinct presented frames in capture:",m)
if m>2:
    db=np.abs(np.diff(b,axis=0)); bigb=(db>0.1).mean((1,2)); lb=b.mean((1,2)); dlb=np.diff(lb)
    print("distinct-frame max pixel fraction changing >10%%: %.3f; max mean-lum step %.3f"%(bigb.max(),np.abs(dlb).max()))
    evb=(bigb>0.25); w=max(evb[i:i+30].sum() for i in range(max(1,len(evb)-29)))
    print("worst 30-frame window (=1 s at 30 fps) with >25%% area changing >10%%: %d events (limit 3)"%w)
    sw=max(((np.abs(dlb[i:i+29])>0.10).sum()) for i in range(max(1,len(dlb)-28)))
    print("worst 30-frame window mean-luminance swings >10%%: %d"%sw)
