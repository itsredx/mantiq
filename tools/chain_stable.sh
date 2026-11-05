#!/usr/bin/env bash
# Milestone D pivot: SINGLE-STAGE runtime unlink.
#   The TU now defines its full mantiq surface in Nizam (main.nz ports +
#   TU-local ast_alloc/box32/intern_string/page_alloc/page_free), so the OLD
#   builder's baked d_argv still lists runtime.c on the link line, but the
#   linker never PULLS runtime.o (no undefined symbol it can satisfy) and all
#   runtime.c defs are weak as a collision safety net. Output: fixed7 built
#   in one shot, zero runtime code inside.
#   Gate: nm-sweep fixed7 for undefined mantiq symbols, then the FULL
#   50-test suite with a FRESH journal (rt_nolink.state).
#   Promote: only if 50/50.
set -u
ROOT=/home/red-x/code/nizam-lang/mantiq
TOOLS=/home/red-x/.local/share/nizam-tools
LOG=$TOOLS/rtunlink.log
BUILDER=$TOOLS/nizam-self-promoted
BIN=$TOOLS/nizam-new-fixed7
WRAP=$TOOLS/nizam-new-wrap
STATE=$TOOLS/rt_nolink.state
BIGLOG=$TOOLS/rt_nolink_suite.log
: > "$LOG"
log() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
log "=== rtunlink chain (single-stage) start ==="

cd "$ROOT" || exit 1
export PATH="$TOOLS/clangshim:${PATH}"
export CPATH="${CPATH:+${CPATH}:}$HOME/.local/lib/mantiq/include"
export LD_LIBRARY_PATH="$ROOT:${LD_LIBRARY_PATH-}"
ulimit -s unlimited 2>/dev/null || true

# ── Single stage: old builder compiles the new sources -> fixed7 ──
log "stage: builder=$BUILDER -> $BIN (runtime.c on link line, expected unpulled)"
rm -f /tmp/*.ll /tmp/*.o /tmp/*.log 2>/dev/null
timeout 7200 "$BUILDER" build src/main.nz -o "$BIN" --no-cache --lib-dir "$PWD" \
    > "$TOOLS/selfbuild50.log" 2>&1
RC=$?
echo "rc=$RC" >> "$TOOLS/selfbuild50.log"
log "stage rc=$RC"
if [ $RC -ne 0 ]; then
    sed 's/\x1b\[[0-9;]*m//g' "$TOOLS/selfbuild50.log" | tail -15 >> "$LOG"
    log "FATAL: build failed"
    exit 1
fi
ls -la "$BIN" | awk '{print "fixed7 bin:", $5, $9}' >> "$LOG"

# ── verify runtime.o was NOT pulled (no mantiq code from runtime.c) ──
RTDEFS=$(nm --defined-only "$BIN" 2>/dev/null | grep -cE " T (mantiq_|__mantiq_)" )
log "runtime-class T-symbols defined in fixed7: $RTDEFS"
UNDEF=$(nm -u "$BIN" 2>/dev/null | grep -E "mantiq|__nizam" | grep -vE "ts_|nizam_get_terminal|nizam_set_target|nizam_get_target|compiler_lib_dir|set_compiler_lib_dir" | head -20)
if [ -n "$UNDEF" ]; then
    echo "$UNDEF" >> "$LOG"
    log "WARN: fixed7 has undefined mantiq symbols (see above)"
else
    log "nm sweep: no undefined mantiq symbols in fixed7"
fi
log "ldd runtime refs: $(ldd "$BIN" 2>/dev/null | grep -c "runtime") (expect 0)"

# ── quick gate with fixed7 ──
export NIZAM_NEW_BIN="$BIN"
rm -rf "$ROOT/.mantiq_cache"
timeout 600 "$WRAP" build "$ROOT/src/tests/test_std.nz" -o /tmp/rtu_std.bin --lib-dir "$ROOT" \
    > "$TOOLS/rtu_std.build" 2>&1
BRC=$?
if [ $BRC -ne 0 ]; then
    sed 's/\x1b\[[0-9;]*m//g' "$TOOLS/rtu_std.build" | tail -8 >> "$LOG"
    log "FATAL: test_std gate BUILD failed (rc=$BRC)"
    exit 1
fi
timeout 120 /tmp/rtu_std.bin > "$TOOLS/rtu_std.run" 2>&1
RRC=$?
if [ $RRC -ne 0 ]; then
    tail -6 "$TOOLS/rtu_std.run" >> "$LOG"
    log "FATAL: test_std gate RUN failed (rc=$RRC)"
    exit 1
fi
log "gate test_std PASS (fixed7 binary, no runtime.c)"

# ── Full suite with FRESH journal ──
rm -f "$STATE"
: > "$BIGLOG"
echo "=== RT-UNLINK SUITE RUN $(date) ===" >> "$BIGLOG"

TEST_FILES=(
    "src/tests/test_types.nz" "src/tests/test_abi.nz" "src/tests/test_std.nz"
    "src/tests/test_list_methods.nz" "src/tests/test_string_methods.nz"
    "src/tests/test_magic.nz" "src/tests/test_ast.nz" "src/tests/test_error.nz"
    "src/tests/test_macro.nz" "src/tests/test_sema.nz" "src/tests/test_borrowck.nz"
    "src/tests/test_ffi.nz" "src/tests/test_lower.nz" "src/tests/test_traverse.nz"
    "src/tests/test_utils.nz" "src/tests/test_codegen.nz"
    "src/tests/test_tagged_imports_and_options.nz" "src/tests/test_multifile_error.nz"
    "src/tests/test_match.nz" "src/tests/test_enum_payload_and_match.nz"
    "src/tests/test_expr_body_and_generics.nz" "src/tests/test_lifetimes_and_pointers.nz"
    "src/tests/test_systems_and_type_intrinsics.nz" "src/tests/test_for_loops_and_concurrency.nz"
    "src/tests/test_context_managers_and_with.nz" "src/tests/test_try_catch_raise_result.nz"
    "src/tests/test_param_block.nz" "src/tests/test_extended_types.nz"
    "src/tests/test_import_tags_and_link.nz" "src/tests/test_quantum_dce.nz"
    "src/tests/test_macro_expansion.nz" "src/tests/test_nll_borrowck.nz"
    "src/tests/test_interfaces_and_classes.mq" "src/tests/test_oop_override_final_access.mq"
    "src/tests/test_reflection_downcast.mq" "src/tests/test_color_literals.mq"
    "src/tests/test_list_comprehensions.mq" "src/tests/test_string_interpolation.mq"
    "src/tests/test_spread_operator.mq" "src/tests/test_async_concurrency.mq"
    "src/tests/test_channels_actors.mq" "src/tests/test_closures_lambdas.mq"
    "src/tests/test_statement_temporaries.nz" "src/tests/test_recursive_drop_glue.nz"
    "src/tests/test_multiline_delimiters.nz" "src/tests/test_dict_methods.nz"
    "src/tests/test_set_methods.nz" "src/tests/test_tuple_methods.nz"
    "src/tests/test_bytes_methods.nz" "src/tests/test_allocator_suite.nz"
)

# Two-way parallel suite. .mantiq_cache is cwd-relative, so worker 2 runs
# from a scratch cwd with its OWN cache, wiped every run like the main one
# (the fake-pass trap: a persisted cache would serve stale binaries without
# invoking clang). Per-entry cache files have no shared index, but a torn
# concurrent write of the SAME entry is still possible if two workers shared
# a cache dir -- isolation sidesteps it entirely.
rm -rf "$TOOLS/w2_cwd"
mkdir -p "$TOOLS/w2_cwd"

run_test() {
    test_file="$1"
    test_path="$ROOT/$test_file"
    test_name="$(basename "$test_file" | sed 's/\.[^.]*$//')"
    bin_path="/tmp/rtu_${test_name}"
    if grep -qx "PASS  $test_file" "$STATE"; then
        echo "[SKIP-PASSED] $test_file" >> "$BIGLOG"
        echo "PASS $test_file" >> "$TOOLS/rtu_worker_$2.res"
        return
    fi
    echo "[BUILDING] $test_file" >> "$BIGLOG"
    log "w$2 building $test_file"
    if timeout 600 "$WRAP" build "$test_path" -o "$bin_path" --lib-dir "$ROOT" \
        > "$TOOLS/rtu_${test_name}.build" 2>&1; then
        echo "[RUNNING] $bin_path" >> "$BIGLOG"
        if timeout 120 "$bin_path" > "$TOOLS/rtu_${test_name}.run" 2>&1; then
            echo "[SUCCESS] $test_file PASSED!" >> "$BIGLOG"
            echo "PASS  $test_file" >> "$STATE"
            echo "PASS $test_file" >> "$TOOLS/rtu_worker_$2.res"
        else
            echo "[FAILED] Execution failed for $test_file!" >> "$BIGLOG"
            tail -3 "$TOOLS/rtu_${test_name}.run" >> "$BIGLOG"
            echo "FAIL  $test_file" >> "$STATE"
            echo "FAIL $test_file" >> "$TOOLS/rtu_worker_$2.res"
        fi
    else
        echo "[FAILED] Compilation failed for $test_file!" >> "$BIGLOG"
        sed 's/\x1b\[[0-9;]*m//g' "$TOOLS/rtu_${test_name}.build" | tail -6 >> "$BIGLOG"
        echo "FAIL  $test_file" >> "$STATE"
        echo "FAIL $test_file" >> "$TOOLS/rtu_worker_$2.res"
    fi
    echo "" >> "$BIGLOG"
}

run_half() {
    wid="$1"; shift
    : > "$TOOLS/rtu_worker_${wid}.res"
    for t in "$@"; do
        run_test "$t" "$wid"
    done
}

( cd "$ROOT" && run_half 1 "${TEST_FILES[@]:0:25}" ) &
( cd "$TOOLS/w2_cwd" && run_half 2 "${TEST_FILES[@]:25}" ) &
wait

PASSED=$(cat "$TOOLS"/rtu_worker_1.res "$TOOLS"/rtu_worker_2.res | grep -c "^PASS")
FAILED=$(cat "$TOOLS"/rtu_worker_1.res "$TOOLS"/rtu_worker_2.res | grep -c "^FAIL")
rm -f "$TOOLS"/rtu_worker_1.res "$TOOLS"/rtu_worker_2.res
log "suite tally: $PASSED passed, $FAILED failed (of ${#TEST_FILES[@]})"
grep -a "\[FAILED\]" "$BIGLOG" | head -10 | while read -r l; do log "$l"; done

# ── promote if 50/50 ──
if [ "$FAILED" -eq 0 ] && [ "$PASSED" -eq 50 ]; then
    cp "$TOOLS/nizam-new" "$TOOLS/nizam-new-prev.bak" 2>/dev/null
    cp "$BIN" "$TOOLS/nizam-new" && log "PROMOTED nizam-new-fixed7 -> nizam-new (prev saved as nizam-new-prev.bak)"
else
    log "PROMOTION SKIPPED ($PASSED/50)"
fi
log "=== RT-UNLINK CHAIN COMPLETE ($PASSED/50) ==="
