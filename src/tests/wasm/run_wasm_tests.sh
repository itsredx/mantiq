#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

# Compiler: NIZAM env var overrides the default (the self-hosted
# nizam-new driver through the wrap — bare binaries segfault on the
# deep wasm32 sema/codegen recursion without the wrap's ulimit/env).
NIZAM="${NIZAM:-$HOME/.local/share/nizam-tools/nizam-new-wrap}"

echo "============================================================"
echo "      Nizam WebAssembly (WASI) Test Suite Runner            "
echo "============================================================"
echo "Compiler: ${NIZAM}"
echo "Target:   wasm32-wasi"
echo ""

# Module imports resolve cwd-relative (node-22 WASI drops the "."
# preopen's relative lookups), so run from the mantiq tree root and
# pass --lib-dir explicitly.
cd "${ROOT_DIR}/mantiq"

TEST_FILES=(
    "src/tests/wasm/test_wasm_abi.nz"
    "src/tests/wasm/test_wasm_hello.nz"
    "src/tests/wasm/test_wasm_features.nz"
    "src/tests/wasm/test_wasm_concurrency.nz"
    "src/tests/wasm/test_wasm_collections.nz"
    "src/tests/wasm/test_wasm_classes.mq"
    "src/tests/wasm/test_wasm_closures.mq"
    "src/tests/wasm/test_wasm_fstrings.mq"
)

PASSED=0
FAILED=0

for test in "${TEST_FILES[@]}"; do
    echo "------------------------------------------------------------"
    echo "[TESTING WASM] ${test} ..."
    if "${NIZAM}" run "${test}" --target wasm32 --lib-dir "$PWD"; then
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
