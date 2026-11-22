#!/bin/bash
# TEST disc for rig sessions (sessions_ob/assist_level.py): the release profile of tools12/build.sh plus the self-playing menu assist (KPLAN),
# which walks from power-on to a level by itself unless Triangle is held during the first 300 GBA frames.  Never a release.
# usage: build_test_assist.sh NAME "extra cflags"   (needs ROM env)
set -euo pipefail
KPLAN=1 exec bash "$(dirname "$0")/build.sh" "${1:?give an output name}" "${2:-}"
