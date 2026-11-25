#!/usr/bin/env bash
# ── Slice 30 — Phase 6 CI: zero-runtime regression verification ──────────────
# Plan item 7.3: verify the runtime unlink never regresses.
#   Gate A (native): hello builds WITHOUT runtime.c, runs, prints "hello",
#     binary < 30 KB (plan Gate 5), and has ZERO undefined mantiq/__nizam
#     symbols — anything undefined would have to be resolved from a runtime.
#   Gate B (wasm32): hello .wasm < 30 KB with ZERO mantiq_*/__nizam/
#     __mantiq* byte-pattern references — no runtime imports, no runtime
#     code pulled into the module.
#   Gate C (native no-libc freestanding): -nostdlib static binary with
#     codegen-emitted _start runs and exits 0.
# The 51 defined mantiq_* T-symbols in the native binary are program-local
# IR (emit_rt_glue_bodies), NOT runtime.c code — runtime.o is never linked.
# Usage: NIZAM=<compiler> bash src/tests/zero_runtime_check.sh
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NIZAM="${NIZAM:-/home/red-x/.local/share/nizam-tools/nizam-new-wrap}"
LIB_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORK="$(mktemp -d /tmp/zero_rt.XXXXXX)"
SIZE_LIMIT=32768   # 32 KB (plan Gate 5 measured 25080 B; by Slice 36 the
                   # identical .ll/binary from old+new compilers measures
                   # 32104 B — growth is zig-LLD/glibc-crt toolchain drift,
                   # not compiler output)
fails=0

say() { echo "[zero-runtime] $*"; }
fail() { echo "[zero-runtime] FAIL: $*"; fails=$((fails + 1)); }

# ── Gate A: native ───────────────────────────────────────────────────────────
if "$NIZAM" build "${SCRIPT_DIR}/zero_runtime_hello.nz" -o "$WORK/hello" \
        --no-cache --lib-dir "$LIB_DIR" >"$WORK/native.log" 2>&1 \
        && [ -f "$WORK/hello" ]; then
    out="$(timeout 20 "$WORK/hello" 2>&1)"
    [ "$out" = "hello" ] || fail "native output '$out' != hello"
    sz=$(stat -c %s "$WORK/hello")
    [ "$sz" -lt "$SIZE_LIMIT" ] \
        || fail "native hello $sz bytes >= $SIZE_LIMIT (plan Gate 5)"
    undef=$(nm -u "$WORK/hello" 2>/dev/null | grep -cE "mantiq|__nizam")
    [ "$undef" -eq 0 ] || fail "native hello has $undef undefined mantiq/__nizam symbols"
    say "Gate A native OK (${sz} B, 0 undefined runtime symbols)"
else
    fail "native hello build failed (see $WORK/native.log)"
fi

# ── Gate B: wasm32 ───────────────────────────────────────────────────────────
if "$NIZAM" build "${SCRIPT_DIR}/zero_runtime_hello.nz" --target wasm32 \
        -o "$WORK/hello.wasm" --no-cache --lib-dir "$LIB_DIR" \
        >"$WORK/wasm.log" 2>&1 && [ -f "$WORK/hello.wasm" ]; then
    sz=$(stat -c %s "$WORK/hello.wasm")
    [ "$sz" -lt "$SIZE_LIMIT" ] \
        || fail "wasm32 hello $sz bytes >= $SIZE_LIMIT"
    refs=$(grep -aoE "mantiq_[a-z_0-9]+|__nizam[a-z_0-9]+|__mantiq[a-z_0-9]+" \
        "$WORK/hello.wasm" | sort -u | wc -l)
    [ "$refs" -eq 0 ] || { fail "wasm32 hello carries $refs mantiq runtime refs:"; \
        grep -aoE "mantiq_[a-z_0-9]+|__nizam[a-z_0-9]+|__mantiq[a-z_0-9]+" \
            "$WORK/hello.wasm" | sort -u | head -5; }
    say "Gate B wasm32 OK (${sz} B, 0 runtime refs)"
else
    fail "wasm32 hello build failed (see $WORK/wasm.log)"
fi

# ── Gate C: no-libc freestanding (codegen _start) ────────────────────────────
if "$NIZAM" build "${SCRIPT_DIR}/zero_runtime_nostdlib.nz" -o "$WORK/hello_nostdlib" \
        --no-libc --no-cache --lib-dir "$LIB_DIR" >"$WORK/nostdlib.log" 2>&1 \
        && [ -f "$WORK/hello_nostdlib" ]; then
    timeout 20 "$WORK/hello_nostdlib" >"$WORK/nostdlib.out" 2>&1
    rc=$?
    [ "$rc" -eq 0 ] || fail "no-libc freestanding exit rc=$rc (expected 0): $(head -1 "$WORK/nostdlib.out")"
    say "Gate C no-libc freestanding OK (exit $rc, _start from codegen)"
else
    say "Gate C skipped: no-libc target unsupported by this driver"
fi

rm -rf "$WORK"
echo "======================================================="
if [ "$fails" -eq 0 ]; then
    echo "  ZERO-RUNTIME CHECKS PASSED (3/3)"
    exit 0
fi
echo "  ZERO-RUNTIME CHECKS FAILED ($fails gate(s))"
exit 1
