#!/bin/bash
# ==============================================================================
# Phase 5 Test Suite: Embedded Python in Nizam (import[python])
# Tests:
#  1. Compile test_embedded_python.nz to native binary
#  2. Execute native binary verifying math.sqrt, numpy.array, numpy.mean, and auto-drops
#  3. Run Valgrind leak check asserting 0 definite memory leaks from Nizam bindings
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
COMPILER="$WORKSPACE_ROOT/stage3/mantiq"

if [ ! -f "$COMPILER" ]; then
    COMPILER="$WORKSPACE_ROOT/compiler-service/bin/nizam"
fi

echo "============================================================"
echo " Running Python FFI Phase 5 Integration Tests (Embedded Python)"
echo " Compiler: $COMPILER"
echo "============================================================"

BIN_PATH="/tmp/test_embedded_py"
rm -f "$BIN_PATH"

# ── Test 1: Compile test_embedded_python.nz ──────────────────────────────
echo "[1/3] Compiling test_embedded_python.nz -> $BIN_PATH..."
$COMPILER build "$SCRIPT_DIR/test_embedded_python.nz" -o "$BIN_PATH" --lib-dir "$WORKSPACE_ROOT/stage3"

if [ ! -f "$BIN_PATH" ]; then
    echo "ERROR: Failed to generate $BIN_PATH"
    exit 1
fi
echo "  ✓ Generated $BIN_PATH successfully"

# ── Test 2: Execute Binary Directly ──────────────────────────────────────
echo "[2/3] Executing native binary directly..."
"$BIN_PATH"
echo "  ✓ Direct native execution passed successfully"

# ── Test 3: Valgrind Memory Leak Verification ────────────────────────────
echo "[3/3] Running Valgrind leak check on scope-exit PyObject auto-drops..."
export PYTHONMALLOC=malloc
valgrind --leak-check=full --show-leak-kinds=definite --errors-for-leak-kinds=definite --error-exitcode=42 "$BIN_PATH"
echo "  ✓ Valgrind reported 0 definite memory leaks"

echo "============================================================"
echo " Phase 5 Embedded Python Tests Completed Successfully! "
echo "============================================================"
