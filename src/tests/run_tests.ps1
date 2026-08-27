# ── Mantiq / Nizam Windows PowerShell Test Suite Runner ────────────────
$ErrorActionPreference = "Continue"

$ScriptDir = $PSScriptRoot
$RootDir = (Get-Item (Join-Path $ScriptDir "..\..")).FullName

$NizamExe = Join-Path $RootDir "nizam.exe"
if (!(Test-Path $NizamExe)) { $NizamExe = Join-Path $RootDir "stage3\mantiq.exe" }
if (!(Test-Path $NizamExe)) { $NizamExe = Join-Path $RootDir "mantiq\nizam.exe" }

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "     Mantiq / Nizam Windows PowerShell Test Suite Runner    " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Compiler: $NizamExe"
Write-Host "Lib dir:  $RootDir"
Write-Host ""

if (!(Test-Path $NizamExe)) {
    Write-Host "[ERROR] Nizam compiler not found! Run build.ps1 first." -ForegroundColor Red
    exit 1
}

$TestFiles = @(
    "src\tests\test_types.nz",
    "src\tests\test_abi.nz",
    "src\tests\test_std.nz",
    "src\tests\test_magic.nz",
    "src\tests\test_ast.nz",
    "src\tests\test_error.nz",
    "src\tests\test_macro.nz",
    "src\tests\test_sema.nz",
    "src\tests\test_borrowck.nz",
    "src\tests\test_ffi.nz",
    "src\tests\test_lower.nz",
    "src\tests\test_traverse.nz",
    "src\tests\test_utils.nz",
    "src\tests\test_codegen.nz",
    "src\tests\test_tagged_imports_and_options.nz",
    "src\tests\test_multifile_error.nz",
    "src\tests\test_match.nz",
    "src\tests\test_enum_payload_and_match.nz",
    "src\tests\test_expr_body_and_generics.nz",
    "src\tests\test_lifetimes_and_pointers.nz",
    "src\tests\test_systems_and_type_intrinsics.nz",
    "src\tests\test_for_loops_and_concurrency.nz",
    "src\tests\test_context_managers_and_with.nz",
    "src\tests\test_try_catch_raise_result.nz",
    "src\tests\test_param_block.nz",
    "src\tests\test_extended_types.nz",
    "src\tests\test_import_tags_and_link.nz",
    "src\tests\test_quantum_dce.nz",
    "src\tests\test_macro_expansion.nz",
    "src\tests\test_nll_borrowck.nz",
    "src\tests\test_interfaces_and_classes.mq",
    "src\tests\test_oop_override_final_access.mq",
    "src\tests\test_reflection_downcast.mq",
    "src\tests\test_color_literals.mq",
    "src\tests\test_list_comprehensions.mq",
    "src\tests\test_string_interpolation.mq",
    "src\tests\test_spread_operator.mq",
    "src\tests\test_async_concurrency.mq",
    "src\tests\test_channels_actors.mq",
    "src\tests\test_closures_lambdas.mq"
)

$TotalSuites = $TestFiles.Count
$PassedSuites = 0
$FailedSuites = 0

Push-Location $RootDir

foreach ($relFile in $TestFiles) {
    $testPath = Join-Path $RootDir $relFile
    $testName = [System.IO.Path]::GetFileNameWithoutExtension($relFile)
    $binPath = Join-Path ([System.IO.Path]::GetTempPath()) "$testName.exe"

    Write-Host "------------------------------------------------------------"
    Write-Host "[BUILDING] $relFile ..." -ForegroundColor Yellow

    & $NizamExe build $testPath -o $binPath --lib-dir $RootDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAILED]   Compilation failed for $relFile!" -ForegroundColor Red
        $FailedSuites++
        continue
    }

    Write-Host "[RUNNING]  $binPath ..." -ForegroundColor Yellow
    & $binPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAILED]   Execution failed for $relFile!" -ForegroundColor Red
        $FailedSuites++
    } else {
        Write-Host "[SUCCESS]  $relFile PASSED!" -ForegroundColor Green
        $PassedSuites++
    }
    Write-Host ""
}

Pop-Location

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "                 TEST SUITE SUMMARY RESULTS                  " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Total Suites:  $TotalSuites"
Write-Host "Passed Suites: $PassedSuites" -ForegroundColor Green
Write-Host "Failed Suites: $FailedSuites" -ForegroundColor $(if ($FailedSuites -gt 0) { "Red" } else { "Green" })
Write-Host ""

if ($FailedSuites -gt 0) {
    Write-Host ">>> SOME TEST SUITES FAILED! <<<" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Cyan
    exit 1
} else {
    Write-Host ">>> ALL SELF-HOSTED COMPILER TEST SUITES PASSED (100% PARITY) <<<" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Cyan
    exit 0
}
