# Stage 5: ragdoll speed pass (code only)
Code only. No Payback code, data or ROM anywhere. Emulator-only results (PCSXR, substitute BIOS, instruction-count model); see REPORT.md.
- `src/ragdoll_ps1.c/.h`  stage 5 solver + RP_FAST (caches, GTE, sleeping, adaptive substeps), lod 3, dtf, rp_free_flight
- `src/gte_rp.h`          the GTE operations used (SQR sum, MVMVA) with a COP2 back end and a C model (RP_GTE_SIM) for PC and the model
- `src/scenario.inc`      test scene + the budget governor (-DPOLICY); -DSC_AIR6 = six dolls in flight
- `src/app.c` ... as stage 5 (camera target moved to scenario.inc)
- `build.sh TAG flags`    disc. f1: `. tools/cfgs.sh; ./build.sh f1 $(cfg c5) -DRP_FAST=1 -DPOLICY`
- `tools/eval.sh TAG flags`  bench (instructions per 30 fps frame) + PC quality; `bench_build.sh`, `mipsprof.py`, `win.py`, `winair.py`, `host_*.c`, `t_dist.c`, `cmp_trace.py`
- `tests/trace_*.txt`     PC traces (reference, c5, f1); `tests/run.sh iso out.png secs` headless PCSXR
- `ref/`                  PC reference solver (copy)

## g2 (stage 7c): ground-case pass on top of f1
Config: `. tools/cfgs.sh; ./build.sh g2 $(cfg3 f1) -DRP_ITER=2 -DRP_SLOW_NS=2 -DRP_SLOW_C=4`  (cfg3 f1 already has RP_FAST and POLICY; later -D wins only if the cfg does not set it: ITER is not in f1, so no clash).
- RP_ITER=2: with RP_FAST (tolerance band + factor series) two constraint passes now match three (bone samples over 10%: 14 vs 15, worst stretch 0.234 vs 0.199 vs reference 0.208). Before RP_FAST this was rejected (0.44).
- RP_SLOW_NS=2 / RP_SLOW_C=4 / RP_SLOW_V=3 m/s: a doll with 4+ joints touching, no motors, all joint speeds under 3 m/s uses 2 substeps, not 3.
- tools/host_win.c prints per tick state of each doll in the ground window. tools/eval.sh NAME flags gives the numbers.
