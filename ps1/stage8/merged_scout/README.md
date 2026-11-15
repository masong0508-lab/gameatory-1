# merged_scout (stage 8, task B): code only

Scripts used for `../merged_plan.md`. Code only: no Payback code, data, ROM or screenshots. They read the user's ROM and the merged build's ELF/object folder
(`stuntfox/build/merge/`, made by `python3 build.py --merge --no-remixes ...`) and print numbers.

| file | what |
|---|---|
| `patches/disc_tbh_sf.patch` | on top of `stage7/integration/disc.py`: ROM spans for a second code region (Stunt Fox at 0x081b0000), TBB/TBH inline-table recognizer (`add pc,rN`), SF->IWRAM call logging, SF-literal exclusion from the Payback IWRAM seeds |
| `patches/gbashim_pcprof.patch` | on top of `stage7/integration/mgba/gbashim.c`: `gba_pcprof` (instruction histogram + coverage per frame run), `gba_longsteps` |
| `tools/elfsyms.py` | function / mapping-symbol / section tables of the ELF, owner object of each function |
| `tools/elfcount.py` | ground truth bytes: ARM / Thumb / data per section and per module |
| `tools/scan_merged.py` | discovery run on the merged ROM (or `--payback` for the baseline), counts by span and mode |
| `tools/gt_cover.py`, `gaps.py`, `cover_elf.py` | discovery coverage against the ELF's mapping symbols (what was missed, what is data decoded as code) |
| `tools/trsize.py` | translator analysis + emission without link: MIPS words, translator counters |
| `tools/hotscan.py` | the .hot..hot11 IWRAM overlays: SF-version IWRAM image, discovery, translation |
| `tools/gbaprof.py` | libmgba profile of the standard scenes (city, Arwing, space, hangar, station): guest instructions per vblank frame by function/module, vblanks per game tick, coverage bitmaps |
| `tools/hotset.py` | size of the functions carrying 90 / 99 % of the executed instructions per scene |

Layout used: `s8m/{t2m.py,disc.py (patched),armdec.py,semantics.py,prune.py,mips.py,tools/,mg/,out/}`; `PYTHONPATH=s8m` (not `python3 -I`: the translator imports its siblings).
mGBA, translator and ELF results only: nothing was run on a PS1 emulator in this task.
