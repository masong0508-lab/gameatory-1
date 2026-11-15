# Stage 13 cities pass: the PS1 renderer follows Payback's own map (code only)

No Payback code, assets, ROM or audio here. EMULATOR-ONLY (PCSXR, HLE BIOS). Apply the patches (patch -p1) on top of the stage 10 tree (patches/ in stage10 already applied):
- patches/ps1rt_rt.c.patch: gather3 reads the guest grid id (EWRAM 0x02001e66), stage7_pre follows it (MAPFOLLOW) with L2/R2 as viewer override (MAPCHANGE), DEFER init for any map, cold-conflict falls back to the interpreter instead of turning the renderer off, lift of poses far below the world ground, test-only hooks (-DTESTUNLOCK=n sets the rampage unlock halfwords at EWRAM 0x020026d0, -DSPINTEST=n heading sweep, -DTG_LOADS/-DTG_TO guest-grid test hook, PRINT_EVERY_SF3).
- patches/sf_sf3.c.patch: sf3_first_map, sf3_floor_at.
- patches/t_disc7.sh.patch: KPDIR selects the kplan table dir.
- scripts/: env.sh (ROM path), buildall.sh (13 test discs), runcity.sh/run13.sh (emulator run with its own X server and binary names), queue3.sh, simcov.sh, mkhome.sh (blank card HOME).
- tools13/: padcity.py/padstory.py (pad plans to each city / story level, KPLAN tables), startpos.py (start pose vs world cell check), analyze.py (lines per frame, sweep, start pose), mont.py (screenshot montage), tour13.py (state-aware L2/R2 + guest-follow test, retries key presses; needs a fresh blank card each run).
Release disc: NPAGES=56 PRD=pr_lb WORLDPRD=pr_l RPG=out/touched_f1_boot.pkl.rompages VOL=PAYBACK bash t/disc7.sh NAME "-DSF3_DEFER -DPADDBG" 0, then tools7/mkdisc2.py --default-tracks.
Results, per-map lines and gaps: see the disc README in builds/ps1.
