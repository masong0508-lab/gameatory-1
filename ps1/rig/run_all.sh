#!/bin/sh
# run_all.sh DISC OUTROOT [SYMS] [CORE]
# Scripted PS1 acceptance run. A test FAIL, empty result or a crashed child
# makes the entire runner fail. RIG_OPTS passes --opt KEY=VALUE to EVERY session.
# This script never handles copyrighted data.
set -u
DISC=${1:-}; OUT=${2:-}; SYMS=${3:-}; CORE=${4:-pcsx_rearmed}
HERE=$(cd "$(dirname "$0")" && pwd)
if [ -z "$DISC" ] || [ -z "$OUT" ]; then
    echo 'usage: run_all.sh DISC OUTROOT [SYMS] [CORE]' >&2
    exit 2
fi
case "$CORE" in
    swanstation|beetle|pcsx_rearmed) ;;
    *) echo "unknown libretro core: $CORE" >&2; exit 2 ;;
esac
ONLY=${ONLY:-}
SOAK_FRAMES=${SOAK_FRAMES:-120000}
SOAK_GAME_SECONDS=${SOAK_GAME_SECONDS:-600}
# Whitespace-separated KEY=VALUE tokens, optionally prefixed with --opt.
# No eval or shell interpolation: an option is always passed as one argv item.
RIG_OPTS=${RIG_OPTS:-}
set -f                              # prevent wildcard expansion of option values
expect_value=0
for rig_token in $RIG_OPTS; do
    if [ "$rig_token" = "--opt" ]; then
        [ "$expect_value" -eq 0 ] || { echo 'RIG_OPTS: duplicate --opt' >&2; exit 2; }
        expect_value=1
        continue
    fi
    case "$rig_token" in
        [A-Za-z_]*=*) ;;
        *) echo 'RIG_OPTS: expected KEY=VALUE tokens' >&2; exit 2 ;;
    esac
    rig_key=${rig_token%%=*}
    case "$rig_key" in
        *[!A-Za-z0-9_]*|'') echo 'RIG_OPTS: invalid option name' >&2; exit 2 ;;
    esac
    rig_value=${rig_token#*=}
    # Value grammar deliberately avoids shell metacharacters, spaces and
    # substitutions. Valid core options use strings such as 400, 10, false,
    # Software, 2x(native) and scph5501.bin.
    case "$rig_value" in
        ''|*[!A-Za-z0-9_./:%+(),-]*)
            echo 'RIG_OPTS: invalid option value' >&2; exit 2 ;;
    esac
    expect_value=0
done
[ "$expect_value" -eq 0 ] || { echo 'RIG_OPTS: missing KEY=VALUE after --opt' >&2; exit 2; }
for duration in "$SOAK_FRAMES" "$SOAK_GAME_SECONDS"; do
    case "$duration" in
        ''|*[!0-9]*) echo 'SOAK_FRAMES and SOAK_GAME_SECONDS must be positive integers' >&2; exit 2 ;;
    esac
    [ "$duration" -gt 0 ] 2>/dev/null || {
        echo 'SOAK_FRAMES and SOAK_GAME_SECONDS must be greater than zero' >&2; exit 2;
    }
done
# Do not create an output directory until all user settings pass validation.
mkdir -p "$OUT"
failures="$OUT/session_failures.txt"
: > "$failures"             # do not include stale FAIL lines from prior runs
failed=0
ran=0
want() {
    [ -z "$ONLY" ] && return 0
    for x in $ONLY; do [ "$x" = "$1" ] && return 0; done
    return 1
}
run() {
    letter=$1; name=$2; shift 2
    want "$letter" || return 0
    ran=$((ran + 1))
    log="$OUT/$name.log"
    echo "=== $name: $*"
    set -- "$@" --disc "$DISC" --core "$CORE"
    [ -z "$SYMS" ] || set -- "$@" --syms "$SYMS"
    for rig_opt in $RIG_OPTS; do
        [ "$rig_opt" = "--opt" ] || set -- "$@" --opt "$rig_opt"
    done
    set -- "$@" --state-dir "$OUT/states" --out "$OUT/$name"
    if [ "$CORE" = swanstation ] || [ "$CORE" = beetle ]; then
        python3 "$HERE/tools/ob_session.py" "$@" > "$log" 2>&1
        status=$?
    else
        python3 "$@" > "$log" 2>&1
        status=$?
    fi
    passed=$(grep -c '^PASS' "$log" || :)
    found_fail=$(grep -c '^FAIL' "$log" || :)
    echo "    exit $status ($passed PASS, $found_fail FAIL)"
    grep '^FAIL' "$log" >> "$failures" || :
    if [ "$status" -ne 0 ] || [ "$found_fail" -ne 0 ] || [ "$passed" -eq 0 ]; then
        failed=$((failed + 1))
        [ "$passed" -gt 0 ] || echo "FAIL $name: no PASS assertions were produced" >> "$failures"
        [ "$status" -eq 0 ] || echo "FAIL $name: child exited with $status" >> "$failures"
    fi
}
run a a_boot_to_title      "$HERE/sessions/boot_to_title.py" --save-state
run b b_new_game_to_level  "$HERE/sessions/new_game_to_level.py" --path pad --save-state
# KPL/KPLB assist hooks exist only on TEST discs. Real release images
# must not run this impossible route or fail the entire matrix by design.
if [ -n "$SYMS" ] && [ -f "$SYMS" ] && grep -aq 'KPL' "$SYMS"; then
    run b b_assist_path    "$HERE/sessions/new_game_to_level.py" --path assist --save-state
else
    echo "SKIP b_assist_path: no KPL menu-assist symbols in this build"
fi
run j j_replay_script      "$HERE/sessions/replay.py" --script "$OUT/b_new_game_to_level/script.txt" --assist off
run d d_maps               "$HERE/sessions/maps.py"
run e e_save_load          "$HERE/sessions/save_load.py"
run f f_soak               "$HERE/sessions/soak.py" --max-frames "$SOAK_FRAMES" --game-seconds "$SOAK_GAME_SECONDS"
run c c_in_level           "$HERE/sessions/in_level.py"
run g g_state_check        "$HERE/sessions/state_check.py"
run h h_speed              "$HERE/sessions/speed.py"
if [ "$CORE" = pcsx_rearmed ]; then
    run i i_strict_cpu         "$HERE/sessions/strict_cpu.py"
    run i i_strict_cpu_patched "$HERE/sessions/strict_cpu.py" --patch-invalid
fi
printf '=== done: %s sessions; %s failed\n' "$ran" "$failed"
echo '--- every FAIL of this invocation (count, line):'
sed 's/ \[.*//' "$failures" | sort | uniq -c | sort -rn | head -60
[ "$ran" -ne 0 ] && [ "$failed" -eq 0 ]
