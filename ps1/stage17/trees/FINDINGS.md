# Trees on the three ports (stage 17, step 1)
- Original Payback (GBA): a top-down 3/4 view; trees are textured cut-outs (dithered needle bitmaps for firs, a leafy round bitmap for bushes) with a black ground shadow; cell object types 5, 7, 25 = firs, 8, 32 = round bushes (mkworld OBJ_TREES). Its look is texture detail, not geometry.
- Our GBA (mkworld Tree list, citydraw.c draw_tree): every tree was a camera-facing hexagon pair (crown + lit hexagon) on a trunk quad, fir or not (kind = type & 1 was only a colour). PS1 (sf3.c draw_tree): the same two hexagons.
- New: firs are stacked lit triangles, broad trees a dark crown with lighter and lit clumps (GBA, flat polygons) or Gouraud fans (PS1); three detail levels by depth; far trees cost what the old pair did.
- Not done: Payback's leaf textures and ground shadows (a GBA r_poly_tex tree would cost fps; PS1 needs a VRAM page for a procedural leaf texture).
