#!/usr/bin/env bash
set -e

# ── Phase 6 Test Runner: In-Process Loader & Packaging Backend ─────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../../../" && pwd)"
cd "${ROOT_DIR}"

echo "=== Running Python FFI Phase 6 Test Suite ==="

# 1. Verify workspace sync
echo "--- [1/5] Checking workspace parity ---"
./dev-sync.sh --check

# 2. Test automated PEP 484 .pyi type stub generation
echo "--- [2/5] Testing automated .pyi type stub emission ---"
rm -f /tmp/phase6_test_primitives.*
./mantiq/nizam build mantiq/src/tests/python/test_primitives.nz --target python-ext -o /tmp/phase6_test_primitives.abi3.so --lib-dir mantiq
if [ ! -f /tmp/phase6_test_primitives.pyi ]; then
    echo "ERROR: /tmp/phase6_test_primitives.pyi was not generated!"
    exit 1
fi
echo "Verified generated type stub (/tmp/phase6_test_primitives.pyi):"
grep -E "def add_i64|class Point|def scale_f64|class MantiqBuffer" /tmp/phase6_test_primitives.pyi || true
rm -f /tmp/phase6_test_primitives.*

# 3. Test 8-worker concurrent on-the-fly import hook & lockfile protocol
echo "--- [3/5] Testing 8-worker concurrent import hook & atomic cache protocol ---"
rm -rf mantiq/src/tests/python/__pycache__
PYTHONPATH=python:mantiq/src/tests/python python3 mantiq/src/tests/python/concurrent_workers.py
rm -rf mantiq/src/tests/python/__pycache__

# 4. Test PEP 517 build backend and wheel creation
echo "--- [4/5] Testing PEP 517 build backend & wheel creation ---"
cd mantiq/src/tests/python/test_packaging_project
rm -rf dist build *.egg-info .nizam_build_tmp
PYTHONPATH="${ROOT_DIR}/python" python3 -m build --wheel --no-isolation -o dist

WHL_FILE=$(ls dist/*.whl | head -n 1)
echo "Inspecting built wheel archive: ${WHL_FILE}"
unzip -l "${WHL_FILE}"

# 5. Test wheel installation and execution
echo "--- [5/5] Testing wheel installation & execution ---"
rm -rf /tmp/phase6_wheel_install
python3 -m pip install --target /tmp/phase6_wheel_install "${WHL_FILE}" --no-deps
PYTHONPATH=/tmp/phase6_wheel_install python3 -c "import math_kernel, array; pt = math_kernel.Point2D(3.0, 4.0); assert pt.length_sq() == 25.0; buf = array.array('d', [10.0, 20.0, 30.0]); assert math_kernel.fast_sum(buf) == 60.0; assert math_kernel.compute_statistics(buf) == 20.0; print('Wheel installed and tested successfully!')"
rm -rf /tmp/phase6_wheel_install
rm -rf dist build *.egg-info .nizam_build_tmp
cd "${ROOT_DIR}"

echo ""
echo "=========================================================================="
echo "✔ [PASS] Phase 6: In-Process Loader & Packaging Backend 100% Verified!"
echo "=========================================================================="
