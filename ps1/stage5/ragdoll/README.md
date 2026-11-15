# Stage 5: ragdolls on PS1 (solver port + scripted ramp-throw test disc)

Code only. No Payback code, data or ROM anywhere in this directory. Emulator-only results (PCSXR, substitute HLE BIOS); nothing was run on a real PS1 or with a real BIOS.

- `src/ragdoll_ps1.c/.h`  the solver: tools/ragdoll_ps1_ref.c rebuilt for the R3000 (RP_LEVEL 0/1/2 + tuning macros, see the header comment of the .c)
- `src/scenario.inc`      the scripted test (shared by the disc and the PC checks): car up a ramp, bail-out at the lip, five pedestrians hit, building behind them
- `src/app.c`             the disc: GTE projection, OT + DMA, capsule/box drawing, per-frame timing and a summary line per run on the BIOS TTY (psxout)
- `src/rt.inc`            64-bit divide/multiply helpers clang calls on mips1 (no libgcc)
- `src/ps1.h crt0.s ps1.ld`  the stage 2b runtime (copy)
- `src/bench.c bstart.s`, `tools/bench_build.sh`, `tools/mipsprof.py`  the same code with no hardware, run on a MIPS-I model (unicorn) that counts executed instructions per frame, per function and per source line
- `tools/host_test.c host_quality.c`  PC checks: trace against the reference solver; stretch/penetration/speed metrics
- `ref/`                  the PC reference solver (copy of stuntfox/tools/ragdoll_ps1_ref.c/.h)
- `build.sh TAG [cflags]` -> build/rd_TAG.iso (clang --target=mipsel, ld.lld, genisoimage). Example: `./build.sh c5 -DRP_LEVEL=2 -DRP_NS_BASE=3 -DRP_NS_DIV=10 -DRP_NSMAX=6 -DRP_HINGE_LAST=1`
- `tests/run.sh iso out.png secs`  headless PCSXR + screenshot (copy of stage 2b's)
- `ps1_stage5_ragdoll_montage.png`  six frames of the default disc (emulator screenshots)
