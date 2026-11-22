# PlayStation port: current handoff

The repository now has a reproducible, ROM-free assembly of the **stage16 runtime
plus stage17 models/trees and stage18 model refinements**. The combined native
modules compile and link with checked RAM allocations. This is preparation for
finishing the port; it is not a newly validated PlayStation game or release disc.

The source manifest starts from repository commit
`109c747067bc4ab6ced2d9713656c658f00c9441` and explicitly records the integration
changes in this cleanup. Historical stage directories remain available for
comparison. Earlier plans and milestone READMEs describe their own snapshots,
not the current aggregate.

## Commands to use now

From the repository root:

```sh
# No ROM or compiler required; needs Python 3 and the standard patch utility.
python3 ps1/tools/prepare.py --check

# Assemble into a new directory; an existing destination is never replaced.
python3 ps1/tools/prepare.py --output /tmp/payback-ps1-work

# ROM-free build-driver, assembly, ABI, VRAM and PPU-cache regression tests.
python3 -m unittest discover -s ps1/tests -v

# Compile/link the native modules with Clang, LLD, LLVM objcopy and LLVM nm.
python3 ps1/tools/check_native.py
```

Preparation verifies **149 source files and six ordered patches**, checking the
SHA-256 of every input, each patch's starting file and its exact result. It
produces a deterministic `SOURCE_MANIFEST.json` in the assembled tree. A changed
input, incompatible patch or incorrect result aborts before publication.
`tools/source_manifest.json` is intentionally reviewed and updated when its
source inputs change; silently accepting local drift would defeat this check.

The prepared tree includes a [build handoff](PREPARED.md). Inspect the private
build prerequisites there with:

```sh
cd /tmp/payback-ps1-work
ROM=/absolute/path/to/Payback-Europe.gba sh ps1rt/build.sh --check
```

That preflight requires the matching translated guest, boot state and extracted
map data, plus the disc tools. Source preparation does not manufacture those
inputs. The old `stage7/integration/build_ps1.sh` is a historical snapshot build
script with environment-specific assumptions; it is not the supported release
orchestration entry point.

## Integration problems closed in this cleanup

| Problem | Current behavior |
| --- | --- |
| Compiler failures were filtered through `grep ... || true`; stale objects could reach a later link. | Each build has a fresh directory, every command must succeed, and full step logs are retained. |
| Earlier EXE/ISO outputs could be replaced before the two-pass sector check finished. | New artifacts are published only after both complete passes agree on required disc-file locations. Failed builds preserve earlier outputs. |
| Outer wrappers hid errors or embedded an obsolete private ROM path. | The stage16 wrappers require `ROM`, preserve the caller's relative ROM path and propagate failures. |
| The stage17 runtime patch was based on stage13 and failed against stage16. | An explicit stage16 integration patch preserves PPU, controls, map-follow and interpreter behavior while adding the model fields. Runtime and renderer use one checked `SfEnt` definition. |
| The combined model/tree renderer exceeded its reserved region with the old `-O2` default. | The renderer defaults to `-Os`, with `SFOPT` available for measured experiments. Linker bounds remain enforced. |
| PPU and cold-veneer scratch occupied memory used by the enlarged renderer, and the old scratch areas overlapped each other. | All three linker variants reserve separate 4 KiB PPU and veneer areas at `0x8017a000` and `0x8017b000`; ragdoll growth is checked against the first area. |
| PPU OBJ uploads overwrote model textures/palettes; the PPU page overwrote world atlas page 6. | Shared VRAM allocations move the models and PPU page into separate regions. All persistent regions are checked for bounds and overlap. |
| The direct build's default 64-page cache overlapped ragdoll code. | The default is eight pages. Partial four-page CD fetch groups are rejected, and the actual compiled cache bounds are checked against resident pages and the actual ragdoll location. |
| A larger merged ROM could be passed to an eight-MiB runtime window. | The build rejects ROM sizes other than 8 MiB. Extending the merged Stunt Fox address space is explicit remaining port work. |

The PPU backdrop cache now uses two pages. Opaque blits copy their pixels into
the guest framebuffer immediately, so eviction cannot erase a previously drawn
backdrop. A native host test runs the production cache/blit functions using
synthetic pixels: it covers a maximum-sized cached image, eviction, preservation
of the other guest page, reloading and the direct-copy fallback.

The revised GPU allocation leaves all seven world atlas pages intact. Models
occupy `(960,64)` with a 32-halfword by 128-row atlas and palettes at `(992,0)`.
The PPU backdrop cache uses the two pages beginning at `(576,256)` and `(704,256)`;
its display page starts at `(832,256)`. The existing OBJ pages remain at
`(960,256)` and `(960,384)`. Model uploads, texture-page selection and UV offsets
use the same definitions as the allocation checks.

## What the existing stages actually contain

| Area | Current source state | Remaining acceptance |
| --- | --- | --- |
| Guest execution | Stage8 interpreter fallback and stage10 packaging support are included with the stage16 runtime. | Rebuild matching private translation metadata and verify coverage in the final game. |
| Menus and HUD | Stage12 PPU-lite plus later stage16 composition are present. Older claims that no PPU exists are obsolete. | Finish the explicitly deferred glow/logo, menu 3D models and BLDY behavior; compare actual menu transitions. |
| Controls and saving | Later pad packet handling, latched input, memory-card save paths and saved-card-aware menu assistance are present. | Re-run blank and initialized cards, digital/analog pads, pause/resume and quit/restart on the combined build. |
| Cities | The runtime follows the guest map and uses an interpreter fallback for cold code that conflicts with world data. | Exercise all maps and real level changes on the combined image. |
| Vehicles, people and trees | Stage17 geometry/tree changes and stage18 wheel, shading and LOD refinements now assemble together. | Measure frame cost and visual behavior after the `-Os` and cache-allocation changes. Cached per-class display lists remain unfinished. |
| Full merged Stunt Fox game | [The merged-ROM scout](stage8/merged_plan.md) is an architectural plan, not a completed port. The current runtime still has a 2048-page/8-MiB ROM window. | Address-space expansion, merged-code discovery/overlay coverage, the GPU backend for the merged renderer, and the space/station/mission/settings paths still need implementation and gameplay proof. |

References: [stage10](stage10/README.md), [stage12](stage12/README.md),
[controls and saves](stage13/ctl_saves_gameplay/README.md),
[city following](stage13/cities/README.md), [stage17 models](stage17/models/README.md),
[stage17 trees](stage17/trees/README.md), and [stage18 refinements](stage18/models/README.md).
In particular, stage18 explicitly lists unfinished menu effects and model work;
the earlier [PS1 plan](PS1_PLAN.md) must be read alongside these later sources.

## Validation and its limits

The cleanup's ROM-free unit suite passes **20 tests**. The native module check
was also run with **LLVM 19.1.7**, using the real production linker script and
normal interpreter-enabled title-boot configuration:

| Native allocation | Used | Reserved before the next owner |
| --- | ---: | ---: |
| C runtime and interpreter, with minimal generated-table fixtures | 96,180 bytes | 98,304 bytes |
| Ragdoll code and data | 78,564 bytes | 94,208 bytes |
| Combined renderer code and data | 92,316 bytes | 94,208 bytes |
| PPU scratch | 4,096 bytes | 4,096 bytes |
| Cold-veneer scratch | 4,096 bytes | 4,096 bytes |

The same check deliberately rejects an invalid three-page cache, the old
64-page cache overlapping ragdoll code, and a ragdoll allocation growing into
PPU scratch. The host tests verify the shared entity ABI and nonoverlapping
VRAM layout. These checks exercise real compilers and linker assertions; the
build-publication tests separately use mocked tools to reproduce failure paths.

Generated guest tables and game assets are placeholders in the native check.
Their final sizes, cold-code/world placement, disc sectors and real frame cost
must still be tested with the private inputs. The runtime and renderer have
limited free space, so a complete image must pass the same linker assertions.
No new PS1 boot, gameplay, save, audio, real-BIOS or hardware test is claimed
here. Historical stage17/18 results were recorded with PCSXR HLE; they do not
establish acceptance for this newly combined source tree.

## Next port milestone

1. Produce one matching private translation/map set from the chosen 8-MiB
   Payback baseline and build through the hardened driver. Keep game-containing
   outputs outside the repository.
2. Run the combined image through title, saved-card menu paths, every city,
   pause/resume, restart, vehicles/people, HUD, audio and map transitions; record
   screenshots and frame timing. Check texture persistence after both 4-bit and
   8-bit OBJ uploads.
3. Finish the documented menu/fade and performance gaps, then establish a
   real-BIOS emulator baseline before treating the image as a release candidate.
4. Continue the full merged Stunt Fox port with an explicit address-space and
   renderer-backend milestone. The larger GBA milestone cannot be substituted
   into this baseline by changing only the input filename.
