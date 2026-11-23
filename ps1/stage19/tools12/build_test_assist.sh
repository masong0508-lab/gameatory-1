#!/bin/bash
# TEST disc for rig sessions (sessions_ob/assist_level.py): the release profile of tools12/build.sh plus the self-playing menu assist (KPLAN),
# which walks from power-on to a level by itself unless Triangle is held during the first 300 GBA frames, and the PADDBG log.  Never a release.
# usage: build_test_assist.sh NAME "extra cflags"   (needs ROM env)
set -euo pipefail
# rc9: without the pause block (PZF=) and the menu pool switch (POOLF=): with the assist the runtime has no room for them (TEST only; the
# assist walks to the level and never opens the Credits; PZF=-DPZBLOCK / POOLF=-DPOOL_THRASH=32 ask for them anyway)
PZF=${PZF-} POOLF=${POOLF-} KPLAN=1 exec bash "$(dirname "$0")/build.sh" "${1:?give an output name}" "${2:-}"
