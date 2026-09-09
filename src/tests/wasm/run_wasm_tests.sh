#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

NIZAM="${ROOT_DIR}/mantiq/nizam"

echo "============================================================"
echo "      Nizam WebAssembly (WASI) Test Suite Runner            "
echo "============================================================"
echo "Compiler: ${NIZAM}"
echo "Target:   wasm32-wasi"
echo ""

cd "${ROOT_DIR}"

TEST_FILES=(
    "mantiq/src/tests/wasm/test_wasm_abi.nz"
    "mantiq/src/tests/wasm/test_wasm_hello.nz"
    "mantiq/src/tests/wasm/test_wasm_features.nz"
    "mantiq/src/tests/wasm/test_wasm_concurrency.nz"
    "mantiq/src/tests/wasm/test_wasm_collections.nz"
    "mantiq/src/tests/wasm/test_wasm_classes.mq"
    "mantiq/src/tests/wasm/test_wasm_closures.mq"
    "mantiq/src/tests/wasm/test_wasm_fstrings.mq"
)

PASSED=0
FAILED=0

for test in "${TEST_FILES[@]}"; do
    echo "------------------------------------------------------------"
    echo "[TESTING WASM] ${test} ..."
    if "${NIZAM}" run "${test}" --target wasm32-wasi; then
        echo "[SUCCESS] ${test} PASSED!"
        PASSED=$((PASSED + 1))
    else
        echo "[FAILURE] ${test} FAILED!"
        FAILED=$((FAILED + 1))
    fi
    echo ""
done

echo "============================================================"
echo "            WASM TEST SUITE SUMMARY RESULTS                 "
echo "============================================================"
echo "Total Suites:  $((PASSED + FAILED))"
echo "Passed Suites: ${PASSED}"
echo "Failed Suites: ${FAILED}"

if [ "${FAILED}" -eq 0 ]; then
    echo ""
    echo ">>> ALL WASM TEST SUITES PASSED (100% SUCCESS) <<<"
    echo "============================================================"
    exit 0
else
    echo ""
    echo ">>> SOME WASM TEST SUITES FAILED <<<"
    echo "============================================================"
    exit 1
fi
