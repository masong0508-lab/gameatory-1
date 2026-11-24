/* Pure tree geometry-detail policy. Reach, object placement, collision and
   visibility checks remain with citydraw/world; this only caps crown detail. */
#ifndef SF_TREE_LOD_H
#define SF_TREE_LOD_H

enum { SF_TREE_SIMPLE, SF_TREE_MEDIUM, SF_TREE_NORMAL };

static inline int tree_detail_lod(int depth, int cap)
{
    int natural = depth < 2600 ? SF_TREE_NORMAL :
                  depth < 4200 ? SF_TREE_MEDIUM : SF_TREE_SIMPLE;
    if ((unsigned)cap > SF_TREE_NORMAL)
        cap = SF_TREE_NORMAL;      /* invalid or legacy choices use normal */
    return natural < cap ? natural : cap;
}

#endif
