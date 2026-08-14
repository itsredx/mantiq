#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export LD_LIBRARY_PATH="${ROOT_DIR}:${LD_LIBRARY_PATH}"
NIZAM="${ROOT_DIR}/nizam"

echo "============================================================"
echo "    Mantiq / Nizam Self-Hosted Compiler Test Suite Runner   "
echo "============================================================"
echo "Compiler: ${NIZAM}"
echo "Lib dir:  ${ROOT_DIR}"
echo ""

TEST_FILES=(
    "src/tests/test_types.nz"
    "src/tests/test_abi.nz"
    "src/tests/test_std.nz"
    "src/tests/test_magic.nz"
    "src/tests/test_ast.nz"
    "src/tests/test_error.nz"
    "src/tests/test_macro.nz"
)

TOTAL_SUITES=${#TEST_FILES[@]}
PASSED_SUITES=0
FAILED_SUITES=0

for test_file in "${TEST_FILES[@]}"; do
    test_path="${ROOT_DIR}/${test_file}"
    test_name="$(basename "${test_file}" .nz)"
    bin_path="/tmp/${test_name}"

    echo "------------------------------------------------------------"
    echo "[BUILDING] ${test_file} ..."
    if ${NIZAM} build "${test_path}" -o "${bin_path}" --lib-dir "${ROOT_DIR}"; then
        echo "[RUNNING]  ${bin_path} ..."
        if "${bin_path}"; then
            echo "[SUCCESS]  ${test_file} PASSED!"
            PASSED_SUITES=$((PASSED_SUITES + 1))
        else
            echo "[FAILED]   Execution failed for ${test_file}!"
            FAILED_SUITES=$((FAILED_SUITES + 1))
        fi
    else
        echo "[FAILED]   Compilation failed for ${test_file}!"
        FAILED_SUITES=$((FAILED_SUITES + 1))
    fi
    echo ""
done

echo "============================================================"
echo "                TEST SUITE SUMMARY RESULTS                  "
echo "============================================================"
echo "Total Suites:  ${TOTAL_SUITES}"
echo "Passed Suites: ${PASSED_SUITES}"
echo "Failed Suites: ${FAILED_SUITES}"

if [ "${FAILED_SUITES}" -eq 0 ]; then
    echo ""
    echo ">>> ALL SELF-HOSTED COMPILER TEST SUITES PASSED (100% PARITY) <<<"
    echo "============================================================"
    exit 0
else
    echo ""
    echo ">>> SOME TEST SUITES FAILED! <<<"
    echo "============================================================"
    exit 1
fi
