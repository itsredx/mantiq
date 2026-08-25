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

cd "${ROOT_DIR}"

TEST_FILES=(
    "src/tests/test_types.nz"
    "src/tests/test_abi.nz"
    "src/tests/test_std.nz"
    "src/tests/test_magic.nz"
    "src/tests/test_ast.nz"
    "src/tests/test_error.nz"
    "src/tests/test_macro.nz"
    "src/tests/test_sema.nz"
    "src/tests/test_borrowck.nz"
    "src/tests/test_ffi.nz"
    "src/tests/test_lower.nz"
    "src/tests/test_traverse.nz"
    "src/tests/test_utils.nz"
    "src/tests/test_codegen.nz"
    "src/tests/test_tagged_imports_and_options.nz"
    "src/tests/test_multifile_error.nz"
    "src/tests/test_match.nz"
    "src/tests/test_enum_payload_and_match.nz"
    "src/tests/test_expr_body_and_generics.nz"
    "src/tests/test_lifetimes_and_pointers.nz"
    "src/tests/test_systems_and_type_intrinsics.nz"
    "src/tests/test_for_loops_and_concurrency.nz"
    "src/tests/test_context_managers_and_with.nz"
    "src/tests/test_try_catch_raise_result.nz"
    "src/tests/test_param_block.nz"
    "src/tests/test_extended_types.nz"
    "src/tests/test_import_tags_and_link.nz"
    "src/tests/test_quantum_dce.nz"
    "src/tests/test_macro_expansion.nz"
    "src/tests/test_nll_borrowck.nz"
    "src/tests/test_interfaces_and_classes.mq"
    "src/tests/test_oop_override_final_access.mq"
    "src/tests/test_reflection_downcast.mq"
    "src/tests/test_color_literals.mq"
    "src/tests/test_list_comprehensions.mq"
    "src/tests/test_string_interpolation.mq"
    "src/tests/test_spread_operator.mq"
    "src/tests/test_async_concurrency.mq"
    "src/tests/test_channels_actors.mq"
)

TOTAL_SUITES=${#TEST_FILES[@]}
PASSED_SUITES=0
FAILED_SUITES=0

for test_file in "${TEST_FILES[@]}"; do
    test_path="${ROOT_DIR}/${test_file}"
    test_name="$(basename "${test_file}" | sed 's/\.[^.]*$//')"
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
