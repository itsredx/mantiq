@echo off
rem ── Mantiq / Nizam Windows Test Runner ───────────────────────────────
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\.."
set "MANTIQ_DIR=%CD%"
popd
pushd "%MANTIQ_DIR%\.."
set "REPO_ROOT=%CD%"
popd

set "NIZAM=%MANTIQ_DIR%\nizam.exe"
if not exist "%NIZAM%" set "NIZAM=%MANTIQ_DIR%\mantiq.exe"
if not exist "%NIZAM%" set "NIZAM=%REPO_ROOT%\stage3\mantiq.exe"
if not exist "%NIZAM%" set "NIZAM=%REPO_ROOT%\stage3\nizam.exe"
if not exist "%NIZAM%" (
    where nizam.exe >nul 2>&1
    if not errorlevel 1 set "NIZAM=nizam.exe"
)

echo ============================================================
echo      Mantiq / Nizam Windows Test Suite Runner               
echo ============================================================
echo Compiler: "%NIZAM%"
echo Lib dir:  "%MANTIQ_DIR%"
echo.

if not exist "%NIZAM%" (
    echo [ERROR] Nizam compiler not found!
    echo Please run build.bat first or ensure nizam is installed on PATH.
    exit /b 1
)

set TOTAL_SUITES=0
set PASSED_SUITES=0
set FAILED_SUITES=0

set TEST_FILES=^
src\tests\test_types.nz ^
src\tests\test_abi.nz ^
src\tests\test_std.nz ^
src\tests\test_magic.nz ^
src\tests\test_ast.nz ^
src\tests\test_error.nz ^
src\tests\test_macro.nz ^
src\tests\test_sema.nz ^
src\tests\test_borrowck.nz ^
src\tests\test_ffi.nz ^
src\tests\test_lower.nz ^
src\tests\test_traverse.nz ^
src\tests\test_utils.nz ^
src\tests\test_codegen.nz ^
src\tests\test_tagged_imports_and_options.nz ^
src\tests\test_multifile_error.nz ^
src\tests\test_match.nz ^
src\tests\test_enum_payload_and_match.nz ^
src\tests\test_expr_body_and_generics.nz ^
src\tests\test_lifetimes_and_pointers.nz ^
src\tests\test_systems_and_type_intrinsics.nz ^
src\tests\test_for_loops_and_concurrency.nz ^
src\tests\test_context_managers_and_with.nz ^
src\tests\test_try_catch_raise_result.nz ^
src\tests\test_param_block.nz ^
src\tests\test_extended_types.nz ^
src\tests\test_import_tags_and_link.nz ^
src\tests\test_quantum_dce.nz ^
src\tests\test_macro_expansion.nz ^
src\tests\test_nll_borrowck.nz ^
src\tests\test_interfaces_and_classes.mq ^
src\tests\test_oop_override_final_access.mq ^
src\tests\test_reflection_downcast.mq ^
src\tests\test_color_literals.mq ^
src\tests\test_list_comprehensions.mq ^
src\tests\test_string_interpolation.mq ^
src\tests\test_spread_operator.mq ^
src\tests\test_async_concurrency.mq ^
src\tests\test_channels_actors.mq ^
src\tests\test_closures_lambdas.mq

cd /d "%MANTIQ_DIR%"

for %%f in (%TEST_FILES%) do (
    set /a TOTAL_SUITES+=1
    set "TEST_PATH=%MANTIQ_DIR%\%%f"
    set "TEST_NAME=%%~nf"
    set "BIN_PATH=%TEMP%\!TEST_NAME!.exe"

    echo ------------------------------------------------------------
    echo [BUILDING] %%f ...
    "%NIZAM%" build "!TEST_PATH!" -o "!BIN_PATH!" --lib-dir "%MANTIQ_DIR%"
    if errorlevel 1 (
        echo [FAILED]   Compilation failed for %%f!
        set /a FAILED_SUITES+=1
    ) else (
        echo [RUNNING]  !BIN_PATH! ...
        "!BIN_PATH!"
        if errorlevel 1 (
            echo [FAILED]   Execution failed for %%f!
            set /a FAILED_SUITES+=1
        ) else (
            echo [SUCCESS]  %%f PASSED!
            set /a PASSED_SUITES+=1
        )
    )
    echo.
)

echo ============================================================
echo                 TEST SUITE SUMMARY RESULTS                  
echo ============================================================
echo Total Suites:  %TOTAL_SUITES%
echo Passed Suites: %PASSED_SUITES%
echo Failed Suites: %FAILED_SUITES%
echo.

if %FAILED_SUITES% gtr 0 (
    echo ^>^>^> SOME TEST SUITES FAILED! ^<^<^<
    echo ============================================================
    exit /b 1
) else (
    echo ^>^>^> ALL SELF-HOSTED COMPILER TEST SUITES PASSED ^(100%% PARITY^) ^<^<^<
    echo ============================================================
    exit /b 0
)
