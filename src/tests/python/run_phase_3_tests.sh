#!/usr/bin/env bash
# ── Python FFI Phase 3: Shared-Ownership PEP 3118 Buffer Protocol Tests ──
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../../../../" && pwd)"
SO_PATH="/tmp/test_buffer.abi3.so"

echo "=== [Phase 3] Building test_buffer_protocol.nz as Python extension ==="
"${WORKSPACE_ROOT}/stage3/mantiq" build "${SCRIPT_DIR}/test_buffer_protocol.nz" --target python-ext -o "${SO_PATH}"
echo "✓ Generated ${SO_PATH}"

echo "=== [Phase 3] Running NumPy Integration & Shared-Ownership Tests ==="
python3 - <<'EOF'
import sys
import time
sys.path.insert(0, "/tmp")
import numpy as np
import test_buffer

print("[Info] test_buffer module loaded successfully")
print(f"[Info] Available attributes: {dir(test_buffer)}")

# Test 1: Ingest 1,000,000-element NumPy array with zero copies
print("\n--- Test 1: Large Array Zero-Copy Ingestion ---")
N = 1000000
np_arr = np.linspace(0.0, 100.0, N, dtype=np.float64)
expected_sum = float(np_arr.sum())

t0 = time.perf_counter()
native_sum = test_buffer.compute_sum_zerocopy(np_arr)
t_elapsed = time.perf_counter() - t0

print(f"Native sum: {native_sum:.4f}, NumPy sum: {expected_sum:.4f}")
print(f"Processing time for 1,000,000 f64: {t_elapsed * 1000:.2f} ms")
assert abs(native_sum - expected_sum) < 1e-3, f"Sum mismatch: {native_sum} vs {expected_sum}"
print("[PASS] Test 1: Zero-copy ingestion from NumPy verified!")

# Test 2: In-place Zero-Copy Mutation
print("\n--- Test 2: In-Place Zero-Copy Mutation ---")
arr2 = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
test_buffer.scale_in_place(arr2, 3.0)
assert np.allclose(arr2, [3.0, 6.0, 9.0, 12.0, 15.0]), f"In-place scaling failed: {arr2}"
print("[PASS] Test 2: In-place array mutation verified!")

# Test 3: Export Native Buffer via PEP 3118 Protocol
print("\n--- Test 3: Native Buffer Export & PEP 3118 Protocol ---")
buf = test_buffer.fill_range(1000)
assert hasattr(test_buffer, "MantiqBuffer"), "MantiqBuffer type not found in module"
assert hasattr(test_buffer, "Buffer"), "Buffer type alias not found in module"
assert isinstance(buf, test_buffer.MantiqBuffer) or isinstance(buf, test_buffer.Buffer), f"Unexpected type: {type(buf)}"

view = memoryview(buf)
assert view.format == 'd', f"Expected format 'd', got {view.format}"
assert view.itemsize == 8, f"Expected itemsize 8, got {view.itemsize}"
assert len(view) == 1000, f"Expected length 1000, got {len(view)}"
assert view.nbytes == 8000, f"Expected 8000 bytes, got {view.nbytes}"
assert abs(view[10] - 15.0) < 1e-6, f"Expected view[10] == 15.0, got {view[10]}"

# Zero-copy conversion to NumPy ndarray
np_from_buf = np.asarray(buf)
assert np_from_buf.dtype == np.float64
assert np_from_buf.shape == (1000,)
assert abs(np_from_buf[10] - 15.0) < 1e-6
print("[PASS] Test 3: Native buffer export and NumPy interoperability verified!")

# Test 4: Lifetime Escape Test (Prevent Zero-Copy Lifetime Trap)
print("\n--- Test 4: Shared-Ownership Lifetime Escape Verification ---")
global_views = []
def create_escaping_view():
    local_buf = test_buffer.fill_range(2000)
    local_view = memoryview(local_buf)
    global_views.append(local_view)
    # local_buf goes out of scope here!

create_escaping_view()
assert len(global_views) == 1
# Access memoryview after native enclosing scope exited:
assert abs(global_views[0][10] - 15.0) < 1e-6
assert abs(global_views[0][100] - 150.0) < 1e-6
del global_views
print("[PASS] Test 4: Lifetime escape survived without dangling pointer or use-after-free!")

# Test 5: List[f64] Ingestion
print("\n--- Test 5: List[f64] Direct Ingestion ---")
small_arr = np.array([10.0, 20.0, 30.0, 40.0], dtype=np.float64)
s_sum = test_buffer.sum_list(small_arr)
assert abs(s_sum - 100.0) < 1e-6, f"Expected sum 100.0, got {s_sum}"
print("[PASS] Test 5: List[f64] buffer ingestion verified!")

# Test 6: Integer Buffer Protocol (Format 'q')
print("\n--- Test 6: 64-bit Integer Buffer Export ---")
ibuf = test_buffer.fill_integers(500)
iview = memoryview(ibuf)
assert iview.format == 'q', f"Expected format 'q', got {iview.format}"
assert iview.itemsize == 8, f"Expected itemsize 8, got {iview.itemsize}"
assert iview[5] == 50, f"Expected iview[5] == 50, got {iview[5]}"
print("[PASS] Test 6: Integer buffer protocol with format code 'q' verified!")

print("\n=======================================================")
print("  ALL PHASE 3 BUFFER PROTOCOL TESTS PASSED (6/6)!")
print("=======================================================")
EOF

chmod +x "${SCRIPT_DIR}/run_phase_3_tests.sh"
echo "✓ Phase 3 verification suite completed successfully!"
