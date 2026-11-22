# openboot: a minimal PlayStation boot ROM that traces instead of serving

Location: `ps1/rig/openboot/` (sources and `build.sh`; the images are built into `openboot/build/`, which is never committed). Paths below are relative to `ps1/rig/`.
Own work, written from the public hardware documentation only (psx-spx pages memorycontrol, kernelbios, cdromdrive, interrupts, iomap, graphicsprocessingunitgpu). No Sony code or data, no BIOS image was downloaded or read.
It is a TEST TOOL: it starts a disc's boot executable on an accurate emulator without a Sony BIOS and records what the program asks a kernel for. It is not a kernel. The rig uses it instead of a BIOS: no Sony BIOS is used or needed anywhere.
The cores are the Linux x86_64 nightlies of the libretro buildbot (<https://buildbot.libretro.com/nightly/linux/x86_64/latest/>): SwanStation (`swanstation_libretro.so`) and Beetle PSX (`mednafen_psx_libretro.so`) load openboot as their firmware; PCSX-ReARMed (`pcsx_rearmed_libretro.so`) needs none, it has its own HLE BIOS. Where to put the cores and the images: `README.md`.

## Files
| file | content |
|---|---|
| `ob.h` | RAM layout, trace table offsets, behaviour flags, error codes (mirrored by `tools/obrig.py`) |
| `start.S` | reset vector 0xBFC00000, memory control, cache initialisation, copy of the resident image to RAM, the cache flush routine (must run uncached) |
| `resident.S` | stays in RAM while the game runs: vectors for 0x80 / 0xA0 / 0xB0 / 0xC0, call counters, putchar, FlushCache, exception handler, start of the game |
| `boot.c` | loader: CD-ROM controller (polled), ISO9660, SYSTEM.CNF, PS-X EXE, machine state |
| `ob.ld`, `build.sh`, `mkvariant.py` | link (ROM at 0xBFC00000, resident image linked for 0x80002000), build, 512 KiB image + flags word |
| `build/openboot.bin` and `openboot_{abi,irq,strict,noflush,real,kern}.bin` | the images built by `build.sh` (same code, different flags word at ROM offset 0x150); not committed |

Build: `sh openboot/build.sh` (clang 18 `--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -mllvm -disable-mips-delay-filler -mno-check-zero-division`, ld.lld, llvm-objcopy, python3; `OUT=DIR` builds elsewhere). Checked with `tools/mips1_lint.py` (no opcode outside MIPS I) and `tools/loaddelay.py` (no load-delay hazard).
Install for the rig: copy `build/openboot.bin` into the system directory (`RIG_SYSTEM`, default `ps1/rig/system/`) under each of the names `scph5500.bin`, `scph5501.bin` and `scph5502.bin` (README.md).

## How the two cores take it
| core | what to do | what the core says |
|---|---|---|
| SwanStation | image as `scph5501.bin` (US), `scph5500.bin` (J), `scph5502.bin` (PAL) in the system directory AND the option `swanstation_BIOS_PathNTSCU=scph5501.bin` (RetroArch passes the first option value by default; a frontend that passes nothing must set it; `tools/obrun.py` `DEFAULT_OPTS` does) | nothing: it loads the named file without a hash check. WITHOUT the path option the core searches the directory, accepts only images whose hash it knows, logs `No BIOS image found for NTSC-U/C (US, Canada) region` (or nothing) and silently runs its BUILT-IN OpenBIOS (PCSX-Redux, shows a rotating cube) |
| Beetle PSX | image as `scph5501.bin` / `scph5500.bin` / `scph5502.bin` | a warning that the firmware's SHA1 is not the one it expects (it names the hash of the Sony image) and that unsupported firmware may cause glitches, then it runs it |

The same directory serves both cores. Variants for experiments: one directory per variant holding that image as `scph5501.bin` (a US disc; `scph5500.bin` / `scph5502.bin` for the other regions): `abi`, `irq`, `strict`, `noflush`, `real`, `kern`, and one image per flag group (`f01`, `f02`, `f06`, `f08`, `f30`, `f80`, made with `mkvariant.py`), given with `--sys DIR`. An empty directory makes the cores fall back to the open-source BIOS they carry inside (see below); `tools/ob_openbios_halt.py` makes one for its run.
`tools/obrun.py` and `tools/ob_session.py` use `--sys DIR` as given, else `RIG_SYSTEM`, else `ps1/rig/system/`; they stop with an error when that default directory lacks one of the three names, and print the directory they used.

Without a firmware file they accept, the cores do not stop: SwanStation logs `No BIOS image found for NTSC-U/C (US, Canada) region`, Beetle `Firmware is missing: scph5501.bin`, and both then run the open-source BIOS they carry inside (PCSX-Redux OpenBIOS: a complete kernel; its shell runs in RAM at 0x80030000, so a PC there does not mean the game runs; its halt loop is at 0xBFC05F5C). `tools/obrun.py` then prints `no openboot trace table in RAM`. That BIOS stops at the first unresolved exception and leaves the faulting PC and Cause in its thread record at RAM 0x9088: a second opinion that is independent of openboot (`tools/ob_openbios_halt.py` for SwanStation, `sessions_ob/openbios_record.py` for any core).
Beetle refuses to deliver data sectors (ReadN answers INT5, openboot error 2) when the system area of the image carries no licence text; openboot itself checks nothing of that kind. A raw image converted from a plain ISO with `tools/iso2raw.py` therefore takes sectors 0 to 15 from a raw image of the project's own disc (`--sysarea-from RAW.bin`).

## Boot sequence
1. Reset (ROM, KSEG1, `start.S`): DEV2 delay/size 0x1F801010 = 0x0013243F, RAM configuration 0x1F801060 = 0x00000B88, then 0x1F801000 = 0x1F000000, 0x1F801004 = 0x1F802000, 0x1F801008 = 0x0013243F, 0x1F80100C = 0x00003022, 0x1F801014 = 0x200931E1, 0x1F801018 = 0x00020843, 0x1F80101C = 0x00070777, 0x1F801020 = 0x00031125 (the values the documentation lists as set by the BIOS). SR = 0x00400000 (BEV, interrupts off), CAUSE = 0, I_MASK = 0, I_STAT = 0.
2. Instruction cache: the documented sequence on 0xFFFE0130 (0x804 with the cache isolated, one store per 16 bytes over 4 KiB; 0x800 isolated, one store per word; 8 reads of 0xA0000000; 0x0001E988). The same routine is A(44h).
3. RAM 0x00000000..0x0000FFFF cleared, resident image copied to 0x80002000, flags word copied into the trace table, stack 0x8000FFF0, jump to the loader in RAM.
4. Loader (`boot.c`): RAM words [0x60] = 2, [0x64] = 0, [0x68] = 0xFF; four 4-instruction vectors at 0x80, 0xA0, 0xB0, 0xC0.
5. CD-ROM, as in the documentation's "To init the CD": acknowledge all interrupts, HCHPCTL = 0, HINTMSK = 0x1F, COM_DELAY = 0x1325, Nop, Nop, Init (INT3 then INT2), Demute, Setmode 0xA0 (double speed, 0x924 bytes per sector). All waits are polled with the documented double read of the interrupt flags and have time limits; failures are retried and counted.
6. Sector reads: Setloc, ReadN, per INT1: BFRD 0 then 1, wait for DRQSTS, acknowledge, read the 12 byte address/sub-header and compare the address with the sector asked for, read 2048 data bytes, drain the rest; Pause (INT3, INT2). A sector with the wrong address restarts the read at that sector (counted in `boot retries`).
7. ISO9660: primary volume descriptor at sector 16, root directory record at offset 156, path walk for `SYSTEM.CNF;1`. Lines `BOOT = cdrom:\NAME;1 [argument]`, `TCB`, `EVENT`, `STACK` (hexadecimal); the argument is copied to 0x80000180. Without SYSTEM.CNF: `PSX.EXE;1`, stack 0x801FFF00.
8. PS-X EXE: header checked (`PS-X EXE`, load address inside main RAM above 64 KiB, size inside the file), body read to t_addr, the header's memfill region cleared, drive paused, Setmode 0x80, cache flushed.
9. Start (`ob_launch`): see the next table.
If something fails the screen is filled with one colour and the code is in the trace table (`error`): 1 CD init (red), 2 CD read, 3 no volume descriptor, 5 boot file not found, 6 not a PS-X EXE, 7 exception during boot.

## Machine state at the entry point
| item | value | basis |
|---|---|---|
| PC | header pc0 | Exec |
| r4, r5 | 1, 0 | LoadExec: "Exec(headerbuf,1,0)" |
| SP = FP | STACK of SYSTEM.CNF (0x801FFF00 for the test disc); header s_addr + s_size only when STACK is 0 | documented boot behaviour |
| GP | header gp0 | Exec |
| RA | a stub in the resident code that counts the return (`game returned`) and loops | a real kernel reloads the boot file / locks up |
| all other registers, HI, LO | 0 (plain) or 0xDEAD00nn (flag GARBREGS) | undefined on a real kernel |
| SR | plain: 0 (BEV = 0, interrupts disabled). Flag KIRQ: 0x00000401 (IEc = 1, IM2 = 1) | ASSUMPTION, see below |
| I_MASK / I_STAT | plain: 0 / 0. KIRQ: 0x0C (CD-ROM, DMA) / 0. The I_STAT value before the final acknowledge is recorded | ASSUMPTION |
| DPCR / DICR | untouched reset values; KIRQ: DPCR OR 0x8000, DICR = (x AND 0xFFFFFF) OR 0x880000 | documented kernel CD read sequence |
| CD-ROM | initialised, demuted, mode 0x80, paused, HINTMSK 0x1F, no flag pending, register bank 1 selected | as after a kernel load |
| GPU, SPU, timers, SIO | untouched since reset (display off) | a real BIOS leaves its own picture and settings; a program must not depend on them |
| RAM 0x00010000 and up | what the emulator powers on with, the EXE body; with flag DIRTY a non-zero pattern everywhere else | a real console never hands over zeroed RAM |
| RAM below 0x00010000 | openboot: vectors, trace table 0x1000, resident code 0x2000, TTY ring 0x5000, scratch 0xA000, boot stack below 0xFFF0. NO kernel tables (no table of tables at 0x100, no TCB/EvCB/device tables) | not a kernel |

## What is implemented, and what only counts
| request | what openboot does | a standard kernel (documentation) |
|---|---|---|
| A(3Ch), B(3Dh) putchar | byte into the RAM ring at 0x5000 (u32 write counter, u32 reserved, 16 KiB ring); r2 = the byte | TTY |
| A(44h) FlushCache | the real sequence, executed in ROM; counted in `FlushCache executed` (flag NOFLUSH: returns without doing it) | same |
| SYS(01h) EnterCriticalSection, SYS(02h) ExitCriticalSection | SR bits 2 and 10 cleared / set, r2 as documented; counted | same |
| any other A/B/C function | counted per function number, `unknown call` = table letter << 8 OR number, returns r2 = 0 | the service |
| other syscalls | counted, return | DeliverEvent, return |
| interrupt | counted per I_STAT bit that is pending and enabled, acknowledged in I_STAT, return to EPC. Flag KIRQ: a CD-ROM interrupt is also acknowledged at the controller (HCLRCTL = 0x1F), as a kernel CD driver does | handler chains |
| break, reserved instruction, address error, bus error, overflow, coprocessor unusable | counted by cause, the address entered in the site table (12 addresses with counts), the instruction SKIPPED, execution continues. An exception in a branch delay slot resumes behind the slot (the branch is lost; counted) | `SystemErrorUnresolvedException`: the machine locks up. Flag STRICT does exactly that |
Register discipline: calls use only registers a kernel function may destroy; the exception handler restores everything except k0. With flag REGS every call returns with r1, r3..r15, r24, r25, HI, LO overwritten (the documented right of a kernel function); with SMASH1 putchar overwrites the caller's [SP+0] (the documented argument slot of a one-parameter function: "the caller MUST always allocate N words on the stack, and ... the sub-function is allowed to use/destroy these words at [SP+0..N*4-1]"); with SMASH4 it overwrites [SP+0..15] (the whole argument area of the MIPS calling convention, more than the documentation grants a one-parameter function). The pattern written is 0x5AC5BAD1, so a value that came from such a slot is recognisable in registers, in the TTY text and in exception addresses.

## Variants (flags word at ROM offset 0x150, `mkvariant.py`)
| image | flags | purpose |
|---|---|---|
| `openboot.bin` | 0 | quiet machine: interrupts off, nothing destroyed. Most favourable for the program |
| `openboot_abi.bin` | REGS, SMASH1, DIRTY, GARBREGS (0x8B) | does the program rely on registers / stack words / RAM a kernel may change? |
| `openboot_irq.bin` | KIRQ (0x10) | interrupts on at entry and a kernel-style CD-ROM interrupt handler: does the program take the machine over before it polls hardware? |
| `openboot_strict.bin` | STRICT (0x100) | an unresolved exception stops the machine: how far does the program get on a kernel that does what the documentation says? |
| `openboot_noflush.bin` | NOFLUSH (0x40) | is A(44h) needed? (only meaningful on a core that emulates the instruction cache) |
| `openboot_real.bin` | REGS, SMASH1, DIRTY, KIRQ, GARBREGS, STRICT (0x19B) | closest to the documented behaviour of a real kernel |
| `openboot_kern.bin` | REGS, SMASH1, SMASH4, DIRTY, KIRQ, KVBL, GARBREGS (0xBF) | everything a kernel might do to the program short of stopping it: also the whole 16-byte argument area overwritten by putchar and the VBLANK interrupt owned by the kernel. Two of its flags (SMASH4, KVBL) go BEYOND the documentation |
| `f01`, `f02`, `f06`, `f08`, `f30`, `f80` | one flag group each (REGS; SMASH1; SMASH1 + SMASH4; DIRTY; KIRQ + KVBL; GARBREGS), made with `mkvariant.py` | to find which single behaviour a program cannot take when a combined variant fails |

Flag values: REGS 0x01, SMASH1 0x02, SMASH4 0x04, DIRTY 0x08, KIRQ 0x10, KVBL 0x20, NOFLUSH 0x40, GARBREGS 0x80, STRICT 0x100 (`ob.h`). `python3 mkvariant.py build/openboot.raw OUT.bin 0xNNN` makes any combination.

## The trace table (physical RAM 0x1000, little-endian words; `Emu2.trace()` / `format_trace()` in `tools/obrig.py`)
| offset | meaning |
|---|---|
| 0x000 | magic `OBT1` (0x3154424F) |
| 0x004 | stage: 1 loader entered, 2 vectors installed, 3 CD initialised, 4 volume descriptor read, 5 SYSTEM.CNF done, 6 EXE header accepted, 7 EXE loaded, 8 game started |
| 0x008 | error (0 none; 4 = no SYSTEM.CNF, informational; 8 = STRICT stop) |
| 0x00C | flags of this image |
| 0x010..0x024 | pc0, t_addr, t_size, LBA of the EXE, SP at entry, GP |
| 0x028 | the game returned to its caller (count) |
| 0x02C | characters written with putchar |
| 0x030, 0x034, 0x038 | CAUSE, EPC, BadVaddr of the last exception |
| 0x03C, 0x040 | exceptions total (interrupts included), interrupts total |
| 0x044, 0x048 | last call without implementation, return address of the last A/B/C call |
| 0x04C | I_MASK when the first interrupt was taken |
| 0x050 | SR given to the game |
| 0x054, 0x058 | sectors read by the loader, retries |
| 0x05C | CD-ROM interrupts acknowledged by the kernel-style handler (KIRQ) |
| 0x060 | 16 words: exceptions by cause code (0 interrupt, 4/5 address error, 6/7 bus error, 8 syscall, 9 break, 10 reserved instruction, 11 coprocessor unusable, 12 overflow) |
| 0x0A0 | 16 words: interrupts by I_STAT bit (0 VBLANK, 1 GPU, 2 CDROM, 3 DMA, 4..6 timers, 7 pad/card, 8 SIO, 9 SPU, 10 PIO), [11] none pending |
| 0x0E0 | 8 words: syscalls by r4 (0..6), [7] other |
| 0x100 | break: total, last 20 bit code, division by zero (0x1C00), overflow (0x1800) |
| 0x110..0x12C | exceptions in a delay slot, I_STAT before the start, TCB, EVENT, STACK of SYSTEM.CNF, last CD status byte, FlushCache executed, site table overflow |
| 0x130, 0x134, 0x138 | CD init: last step << 8 OR INT, the same at the first failure, INT3 seen where a second response was due |
| 0x140 | 12 x {EPC, count}: where unresolved exceptions were raised |
| 0x200, 0x600, 0xA00 | 256 / 256 / 128 words: calls of A(nn), B(nn), C(nn) |
| 0xC00 | count, then the first 63 CD-ROM events of the loader: command << 16 OR first result byte << 8 OR INT |
| 0xE00 | register save slots of the exception handler (not data) |
How to read it: every non-zero entry in the A/B/C tables or the syscall row is a kernel service the program uses. Entries other than putchar / FlushCache mean the program got a 0 where a kernel would have done work. Every entry in the exception rows other than `interrupt` and `syscall` is a place where a standard kernel stops the machine. `interrupts taken` other than 0 on the plain image means the program enabled interrupts itself.

## Assumptions (things the documentation does not pin down, or that I chose)
1. SR and I_MASK at the entry point. The documentation says LoadExec "Enables IRQs via ExitCriticalSection" before Exec, that "Before starting the boot executable, the BIOS automatically calls _96_init()" and that for the kernel's loader "IRQ2 (cdrom) and IRQ3 (dma) need to be enabled". KIRQ models exactly that (IEc = 1, IM2 = 1, I_MASK = 0x0C). The plain image starts with interrupts off, which is friendlier than a real kernel. The exact register values of a Sony kernel at this point were not available to me.
2. The kernel CD-ROM handler is modelled by its visible effect on a polling program: the interrupt flags (and, as the documentation says of an acknowledge, the result FIFO) are gone before the program sees them. Events are not delivered.
3. The stack is the SYSTEM.CNF value; TCB and EVENT are parsed and recorded but nothing is allocated.
4. No licence check, no logo, no shell, no memory card or pad services, no file functions, no heap, no events, no threads, no kernel tables. A program that uses any of them shows up in the call tables and gets 0.
5. COM_DELAY is written as 0x00001325 before the CD init (the documentation's CD init note); CDROM_DELAY stays 0x00020843.
6. Init answered with INT3, INT3, INT2 on SwanStation (documented: INT3, INT2). The loader accepts further INT3 before the INT2 and counts them.
7. Unresolved exceptions are skipped so that a run can go on and every faulting address is found; this is the opposite of what a kernel does (see STRICT).
8. putchar does no TAB/LF translation and knows no file handles; A(3Fh) printf is not implemented (it would be counted).
9. The exception handler uses fixed save slots and never re-enables interrupts: it is not re-entrant and needs none.
10. An interrupt that hits a GTE command is returned to at EPC (no re-execution fix-up).

## Tools around it (`tools/`, `sessions_ob/`)
| tool | purpose |
|---|---|
| `tools/obrig.py` | `Emu2`: the rig frontend plus system directory, trace table reader (`trace()`, `format_trace()`), TTY ring reader, CPU registers out of save states (`swan_regs`, `beetle_regs`) |
| `tools/obrun.py` | one sampled session: `--core --disc --sym --script --out [--sys DIR] [--opt KEY=VALUE] [--pad-name TEXT] [--load STATE]`; writes summary.json, samples.csv, renders.csv, misses.csv, tty.log, trace.txt, shots/, core.log |
| `tools/ob_report.py`, `ob_speed.py`, `ob_misses.py`, `ob_compare.py` | facts of a run as JSON; speed figures; which ROM clusters are fetched; side-by-side sheets at the same guest moments |
| `tools/ob_where.py`, `ob_openbios_halt.py` | where the CPU is, for any firmware; why the built-in open-source BIOS of SwanStation halted |
| `tools/ob_session.py` | runs a session script of `sessions/` (the `ps1game.py` / `payback.py` framework) on an accurate core with openboot |
| `tools/mips1_lint.py`, `loaddelay.py`, `bioscalls.py`, `gpuwait_classify.py` | static checks of a PS1 ELF: opcodes outside MIPS I, load-delay hazards, kernel call sites and their stack use, waits on GPUSTAT bit 26 by the kind of word that follows |
| `tools/patch_disc.py`, `patch_elf.py`, `iso2raw.py` | TEST-ONLY disc copies with words of the boot executable replaced, the matching symbol file, raw image from a plain ISO |
| `sessions_ob/*.py` | scripts for `obrun.py`: `assist_level.py` (menus by the disc's assist, pad holds in the level, screenshots at fixed guest frames), `freeze_pc.py`, `until_gf.py`, `pad_taps.py`, `pad_cfg.py`, `flicker.py`, `cluster_check.py`, `openbios_record.py` |

## What the trace showed for the test disc (RC v2, before the stage-19 fixes)
- A(3Ch) putchar 5482 calls, A(44h) FlushCache 41 calls per session into the level; no B / C function, no syscall, no break, no interrupt on the plain image; the program never returned.
- 3.19 million Reserved Instruction exceptions from 3 addresses (`teq` after divisions): the one thing a standard kernel would not survive. With `strict` both cores stop at the first, EPC 0x80012d30.
- Of the things a kernel may do, only one derails the program: putchar using more of the caller's stack than the one documented word (`f06`). Registers destroyed (`f01`), the documented word overwritten (`f02`), RAM not zero (`f08`), kernel-owned CD-ROM and VBLANK interrupts (`f30`, `irq`: one `CD timeout`), registers not zero at entry (`f80`) and FlushCache doing nothing (`noflush`) make no difference to its progress.
- Counter-check with a TEST-ONLY copy of the disc in which the 54 wrong GP0 waits and the 4 `teq` words are replaced by `nop` (`tools/gpuwait_scan.py`, `tools/patch_disc.py`): `strict` reaches the level with 0 exceptions and 0 interrupts; `real` (REGS, SMASH1, DIRTY, KIRQ, GARBREGS, STRICT) reaches it with 1 CD-ROM interrupt and one `CD timeout`; the open-source BIOS built into SwanStation and into Beetle reaches it too.
