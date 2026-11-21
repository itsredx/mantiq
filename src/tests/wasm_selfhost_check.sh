#!/usr/bin/env bash
# ── Gate 6 — wasm32 self-hosting chain in CI ─────────────────────────────────
# Plan item 8 / Gate 6: stage3 wasm rebuilds stage4 wasm under the WASI
# runner, and the stage4 wasm compiler compiles + runs the
# hello/dict/mini probes (previously verified manually only — notes F11).
#
# Chain:
#   1. native compiler  -> stage3 wasm   (build src/main.nz --target wasm32)
#   2. node + nizam_wasi.js runs stage3: stage3 compiles src/main.nz
#      in-wasm -> stage4 wasm (the self-hosted wasm compiler)
#   3. stage4 wasm prints its version banner
#   4. stage4 wasm compiles each probe (hello / mini / dict) to wasm32
#   5. each built probe runs under the WASI runner with rc=0
#
# Usage: bash src/tests/wasm_selfhost_check.sh
#   NATIVE=<compiler>   (default: ~/.local/share/nizam-tools/nizam-new-wrap)
#   Node flags per notes F11: --no-incremental-marking --stack-size=16384
#   --max-old-space-size=384 (self-hosted wasm32 compiles recurse deeply
#   in sema/codegen — ulimit -s raised accordingly).
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NATIVE="${NATIVE:-$HOME/.local/share/nizam-tools/nizam-new-wrap}"
RUNNER="$ROOT/nizam_wasi.js"
NODE_FLAGS=(--no-incremental-marking --stack-size=16384 --max-old-space-size=384)
WORK="$(mktemp -d /tmp/wasm_selfhost.XXXXXX)"
fails=0

say() { echo "[wasm-selfhost] $*"; }
fail() { echo "[wasm-selfhost] FAIL: $*"; fails=$((fails + 1)); }
cleanup() { [ "$fails" -eq 0 ] && rm -rf "$WORK" || say "logs kept in $WORK"; }
trap cleanup EXIT

command -v node >/dev/null || { echo "node not found"; exit 1; }
ulimit -s 1048576 2>/dev/null || true

# ── [1/4] stage3: native compiler -> wasm32 ──────────────────────────────────
say "[1/4] compiling stage3 (native -> wasm32-wasi)"
if ! "$NATIVE" build "$ROOT/src/main.nz" -o "$WORK/stage3.wasm" \
        --target wasm32 --no-cache --lib-dir "$ROOT" \
        >"$WORK/stage3.log" 2>&1 || [ ! -f "$WORK/stage3.wasm" ]; then
    fail "stage3 build failed (see $WORK/stage3.log)"
    exit 1
fi
say "      stage3: $(stat -c %s "$WORK/stage3.wasm") bytes"

# ── [2/4] stage4: stage3 compiles the compiler in-wasm ───────────────────────
say "[2/4] bootstrapping stage4 (stage3 wasm compiles src/main.nz in-wasm)"
if ! ( cd "$ROOT" && node "${NODE_FLAGS[@]}" "$RUNNER" "$WORK/stage3.wasm" \
        build src/main.nz -o "$WORK/stage4.wasm" --target wasm32 \
        --lib-dir "$ROOT" ) >"$WORK/stage4.log" 2>&1 \
        || [ ! -f "$WORK/stage4.wasm" ]; then
    fail "stage4 bootstrap failed (see $WORK/stage4.log)"
    exit 1
fi
say "      stage4: $(stat -c %s "$WORK/stage4.wasm") bytes"

# ── [3/4] stage4 version banner ──────────────────────────────────────────────
say "[3/4] stage4 version check"
ver="$( cd "$ROOT" && NIZAM_WASM="$WORK/stage4.wasm" node "${NODE_FLAGS[@]}" \
    "$RUNNER" version 2>"$WORK/ver.log" )"
if echo "$ver" | grep -q "Self-Hosting Compiler"; then
    say "      $ver"
else
    fail "stage4 version output unexpected: '$ver'"
fi

# ── [4/4] stage4 compiles + runs the probes ──────────────────────────────────
say "[4/4] stage4 compiles + runs probes"
for p in probe_hello probe_mini probe_dict; do
    if ( cd "$ROOT" && node "${NODE_FLAGS[@]}" "$RUNNER" "$WORK/stage4.wasm" \
            build "src/tests/wasm_selfhost/$p.nz" -o "$WORK/$p.wasm" \
            --target wasm32 --lib-dir "$ROOT" ) >"$WORK/$p.build.log" 2>&1 \
            && [ -f "$WORK/$p.wasm" ]; then
        ( cd "$ROOT" && node "${NODE_FLAGS[@]}" "$RUNNER" "$WORK/$p.wasm" ) \
            >"$WORK/$p.run.log" 2>&1
        rc=$?
        if [ "$rc" -eq 0 ]; then
            say "      $p: build+run OK"
        else
            fail "$p run rc=$rc (see $WORK/$p.run.log)"
        fi
    else
        fail "$p build failed (see $WORK/$p.build.log)"
    fi
done

echo "======================================================="
if [ "$fails" -eq 0 ]; then
    echo "  WASM SELF-HOST CHAIN PASSED (stage3 -> stage4 -> probes)"
    exit 0
fi
echo "  WASM SELF-HOST CHAIN FAILED ($fails step(s))"
exit 1
