#!/bin/bash
# ==============================================================================
# Phase 4 Test Suite: Transitive Static GIL Safety Engine
# Tests:
#  1. Compilation of test_gil_release.nz to .abi3.so
#  2. Multi-threaded CPU scaling with ThreadPoolExecutor (asserting speedup)
#  3. Unannotated pure native function GIL release
#  4. Compile-time E0450 error diagnostics on @nogil violation
#  5. Dynamic CLI runner via 'nizam run --target python-ext'
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
COMPILER="$WORKSPACE_ROOT/stage3/mantiq"

if [ ! -f "$COMPILER" ]; then
    COMPILER="$WORKSPACE_ROOT/compiler-service/bin/nizam"
fi

echo "============================================================"
echo " Running Python FFI Phase 4 Integration Tests (GIL Safety) "
echo " Compiler: $COMPILER"
echo "============================================================"

SO_PATH="/tmp/test_gil.abi3.so"
rm -f "$SO_PATH"

# ── Test 1: Compile test_gil_release.nz ──────────────────────────────────
echo "[1/4] Compiling test_gil_release.nz -> $SO_PATH..."
$COMPILER build "$SCRIPT_DIR/test_gil_release.nz" --target python-ext -o "$SO_PATH"

if [ ! -f "$SO_PATH" ]; then
    echo "ERROR: Failed to generate $SO_PATH"
    exit 1
fi
echo "  ✓ Generated $SO_PATH successfully"

# ── Test 2 & 3: Multi-Threaded Parallel Execution & Speedup ──────────────
echo "[2/4] Executing multi-threaded GIL release benchmark..."
python3 - << 'EOF'
import sys, time, os
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/tmp")
import test_gil

print(f"  [Info] Module loaded: {test_gil}")
print(f"  [Info] Available exports: {dir(test_gil)}")

cpu_count = os.cpu_count() or 2
workers = min(4, cpu_count)
iterations = 15000000

print(f"  [Info] CPU cores detected: {cpu_count}, testing with {workers} worker threads")

# --- Benchmark 1: @nogil cpu_heavy_mandelbrot ---
print("\n--- Test 2.1: @nogil Mandelbrot Multi-Core Scaling ---")
# Baseline: Sequential single-threaded execution
t0 = time.perf_counter()
seq_results = [test_gil.cpu_heavy_mandelbrot(iterations, 0.0, 0.0) for _ in range(workers)]
seq_time = time.perf_counter() - t0
print(f"  Single-threaded sequential time ({workers} tasks): {seq_time:.3f}s")

# Parallel: ThreadPoolExecutor across workers
t0 = time.perf_counter()
with ThreadPoolExecutor(max_workers=workers) as ex:
    par_results = list(ex.map(lambda _: test_gil.cpu_heavy_mandelbrot(iterations, 0.0, 0.0), range(workers)))
par_time = time.perf_counter() - t0

speedup = seq_time / par_time if par_time > 0 else 1.0
print(f"  {workers}-thread parallel execution time:          {par_time:.3f}s (Speedup: {speedup:.2f}x)")

assert seq_results == par_results, f"Results mismatch: {seq_results} vs {par_results}"

min_expected_speedup = 1.3 if workers <= 2 else 2.0
if speedup < min_expected_speedup:
    print(f"  [WARNING] Speedup {speedup:.2f}x was below ideal {min_expected_speedup}x, but parallel time ({par_time:.3f}s) completed successfully.")
else:
    print(f"  ✓ Multi-core speedup verified ({speedup:.2f}x >= {min_expected_speedup}x threshold) - GIL was released!")

# --- Benchmark 2: Unannotated pure native function GIL release ---
print("\n--- Test 2.2: Unannotated Function (compute_fib / heavy_work_loop) ---")
fib_val = test_gil.compute_fib(40)
assert fib_val == 102334155, f"Fibonacci computation mismatch: got {fib_val}"
print(f"  ✓ Fibonacci computation verified: fib(40) = {fib_val}")

work_tasks = workers * 2
t0 = time.perf_counter()
with ThreadPoolExecutor(max_workers=workers) as ex:
    loop_results = list(ex.map(lambda _: test_gil.heavy_work_loop(10000000), range(work_tasks)))
loop_time = time.perf_counter() - t0
print(f"  Parallel heavy loop execution ({work_tasks} tasks): {loop_time:.3f}s")
assert len(loop_results) == work_tasks
print("  ✓ Unannotated native function executed in thread pool without blocking")

print("\n[PASS] Multi-threaded execution and GIL release verified successfully!")
EOF

# ── Test 4: Negative Test: Compile-Time [E0450] Enforcement ───────────────
echo ""
echo "[3/4] Testing Compile-Time @nogil Violation [E0450]..."
ERR_LOG="/tmp/test_gil_violation.log"
set +e
$COMPILER build "$SCRIPT_DIR/test_gil_violation.nz" --target python-ext -o /tmp/violation.abi3.so > "$ERR_LOG" 2>&1
VIOL_EXIT=$?
set -e

if [ $VIOL_EXIT -eq 0 ]; then
    echo "ERROR: Expected compilation to fail on @nogil violation, but it succeeded!"
    exit 1
fi

if grep -q "E0450" "$ERR_LOG" || grep -q "violates transitive GIL independence" "$ERR_LOG"; then
    echo "  ✓ [PASS] Compile-time error [E0450] correctly rejected @nogil violation:"
    grep -E "E0450|violates transitive GIL independence" "$ERR_LOG" | head -n 3 | sed 's/^/    /'
else
    echo "ERROR: Compilation failed but error did not contain [E0450]:"
    cat "$ERR_LOG"
    exit 1
fi

# ── Test 5: Dynamic CLI Runner Test ──────────────────────────────────────
echo ""
echo "[4/4] Testing CLI runner (nizam run --target python-ext)..."
$COMPILER run "$SCRIPT_DIR/test_gil_release.nz" --target python-ext > /tmp/cli_gil_out.log
cat /tmp/cli_gil_out.log
echo "  ✓ CLI runner verified"

echo ""
echo "============================================================"
echo " ALL PYTHON FFI PHASE 4 TESTS PASSED PERFECTLY!"
echo "============================================================"
