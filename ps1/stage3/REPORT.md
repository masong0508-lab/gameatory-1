# Stage 3: stage 2 logic + stage 2b renderer, one disc
Everything here ran only in pcsxr (HLE substitute BIOS, interpreter, GL plugin), never on hardware.
- GBA hook (confirmed from stuntfox keyhook.s/merge.c): sf_frame replaces Payback's world renderer 0x0800adac (called from 0x080177fa/0x08017692), calls sf_draw(view); if that returns 0 the original renderer runs. It reads entity list IW 0x03000c60 (last index 0x0300000c), controlled index EW 0x02001db8, clock 0x02001e00, map 0x02001d40; entity x +4, y +8, z u16 +0xc, heading s16 +0x12, descriptor +0x1c.
- 0x03000580 (stage-2 stub id 5) is the IWRAM entity drawer, also called in menus, so it is not the hook. rt.c gather3() reads the same guest state directly each present and calls sf3_frame.
- Layout: coldtab moved to 0x80131c00, STREAM=1 (no rompack), renderer buffers in cold groups never loaded in gameplay coverage (25-27, 31-32, 36-50), guard in h_miss turns the renderer off if a cold load would hit them.
- Coverage (mGBA, 3 runs): 295 cold functions touched, groups used 0,1,3-15,17-24,28-30,33-35,51,52,54,55,57-59.
- Renderer on real Payback RAM snapshots (14 poses): 475-803 hblank lines/frame (30-51 ms), 123-483 prims, ovf 0, LOD 2-3.
Code only; build needs the user's ROM and tools/mksf3.py outputs.
