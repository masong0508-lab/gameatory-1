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
