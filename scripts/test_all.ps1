<#
.SYNOPSIS
    Run the full academic_pipeline test matrix in a strict fail-fast pipeline.

.DESCRIPTION
    Executes seven stages in a fixed order:

        1. Python backend unit + route tests
           (server/tests/unit, server/tests/routes, src/tests)
        2. Python backend integration tests (opt-in via -Integration)
        3. getState() ban grep check under gui/tests/rtl and gui/tests/e2e
        4. Vitest data-layer tier     (npm run test:data)
        5. Vitest RTL tier            (npm run test:rtl)
        6. Vitest contract tier       (npm run test:contract)
        7. Playwright e2e             (npx playwright test --reporter=line)

    The pipeline is fail-fast: the first non-zero exit code stops the
    run and becomes the script's exit code. Every stage prints a
    banner containing the stage number, description, working
    directory, and the exact command being executed, so a developer
    reading CI logs can reproduce any failing stage in isolation.

.PARAMETER Integration
    If present, Stage 2 (pytest -m integration) is included. Requires
    the docker compose stack at the repository root to be up so that
    the integration tests can reach redis / celery / the FastAPI web
    service. Default: off (Stage 2 is skipped).

.EXAMPLE
    # Default pipeline (no docker required)
    .\scripts\test_all.ps1

.EXAMPLE
    # Full pipeline including integration tests (docker compose must be up)
    .\scripts\test_all.ps1 -Integration

.NOTES
    - Uses the project-local virtualenv at .venv\Scripts\python.exe
      for every Python command.
    - Uses npm / npx as found on PATH for the Node commands (no
      hard-coded paths beyond the venv).
    - Stage 3 uses the built-in Select-String cmdlet so the script
      runs on a stock Windows PowerShell without requiring ripgrep.
    - PowerShell's $ErrorActionPreference = 'Stop' does NOT catch
      non-zero exits from native executables, so each native call is
      followed by an explicit $LASTEXITCODE check.
#>

param(
    [switch]$Integration
)

$ErrorActionPreference = 'Stop'

$repo_root   = Split-Path -Parent $PSScriptRoot
$venv_python = Join-Path $repo_root '.venv\Scripts\python.exe'
$gui_dir     = Join-Path $repo_root 'gui'

$total_stages = 7

Set-Location $repo_root

function Write-StageBanner {
    param(
        [int]    $Number,
        [string] $Description,
        [string] $WorkingDir,
        [string] $CommandDisplay
    )
    Write-Host ''
    Write-Host "==> Stage $Number / ${total_stages}: $Description"
    Write-Host "    cwd     : $WorkingDir"
    Write-Host "    command : $CommandDisplay"
}

function Assert-StageSucceeded {
    param(
        [int]      $Number,
        [string]   $Description,
        [int]      $ExitCode,
        [TimeSpan] $Elapsed
    )
    if ($ExitCode -ne 0) {
        Write-Host ("!! FAILED at Stage {0}: {1} (exit {2}, {3:N1}s)" `
            -f $Number, $Description, $ExitCode, $Elapsed.TotalSeconds)
        exit $ExitCode
    }
    Write-Host ("    ok      : {0:N1}s" -f $Elapsed.TotalSeconds)
}

# --- Stage 1 : Python backend unit + route tests ------------------------------
$stage_number      = 1
$stage_description = 'Python backend unit + route tests'
Write-StageBanner $stage_number $stage_description $repo_root `
    "$venv_python -m pytest server/tests/unit server/tests/routes src/tests -q"
$stage_start = Get-Date
Set-Location $repo_root
& $venv_python -m pytest 'server/tests/unit' 'server/tests/routes' 'src/tests' -q
$pytest_unit_exit = $LASTEXITCODE
Assert-StageSucceeded $stage_number $stage_description $pytest_unit_exit ((Get-Date) - $stage_start)

# --- Stage 2 : Python backend integration tests (opt-in) ----------------------
$stage_number      = 2
$stage_description = 'Python backend integration tests'
if ($Integration) {
    Write-StageBanner $stage_number $stage_description $repo_root `
        "$venv_python -m pytest server/tests/integration -q -m integration"
    $stage_start = Get-Date
    Set-Location $repo_root
    & $venv_python -m pytest 'server/tests/integration' -q -m integration
    $pytest_integration_exit = $LASTEXITCODE
    Assert-StageSucceeded $stage_number $stage_description $pytest_integration_exit ((Get-Date) - $stage_start)
}
else {
    Write-Host ''
    Write-Host "==> Stage $stage_number / ${total_stages}: $stage_description -- SKIPPED (pass -Integration to include)"
}

# --- Stage 3 : getState() ban grep check --------------------------------------
# Scope the ban to actual test/spec files. Shared infrastructure such as
# tests/rtl/_helpers.tsx legitimately calls store.getState() to reset Zustand
# state between renders; the ban is only meant to catch test bodies that
# assert on store state instead of observing the rendered DOM.
#
# PowerShell ships with Select-String; we use it here instead of ripgrep so
# the runner works on any Windows machine out of the box. The bash twin
# still uses rg where it is conventionally available.
$stage_number      = 3
$stage_description = 'getState() ban grep check'
Write-StageBanner $stage_number $stage_description $gui_dir `
    "Select-String 'getState\(' in tests/rtl + tests/e2e (*.test.*, *.spec.*)"
$stage_start = Get-Date
Set-Location $gui_dir
$offender_paths = Get-ChildItem -Path 'tests/rtl', 'tests/e2e' -Recurse -Include `
    '*.test.ts', '*.test.tsx', '*.spec.ts', '*.spec.tsx' -ErrorAction SilentlyContinue |
    Select-String -Pattern 'getState\(' -SimpleMatch:$false |
    Select-Object -ExpandProperty Path -Unique
$stage_elapsed = (Get-Date) - $stage_start
if ($null -ne $offender_paths -and $offender_paths.Count -gt 0) {
    Write-Host ''
    Write-Host 'Offending files (contain getState( ):'
    foreach ($offender in $offender_paths) {
        Write-Host "    $offender"
    }
    Write-Host ("!! FAILED at Stage {0}: {1} (found offenders, {2:N1}s)" `
        -f $stage_number, $stage_description, $stage_elapsed.TotalSeconds)
    exit 1
}
Write-Host ("    ok      : {0:N1}s (no matches)" -f $stage_elapsed.TotalSeconds)

# --- Stage 4 : Vitest data-layer tier -----------------------------------------
$stage_number      = 4
$stage_description = 'Vitest data-layer tier'
Write-StageBanner $stage_number $stage_description $gui_dir 'npm run test:data'
$stage_start = Get-Date
Set-Location $gui_dir
npm run test:data
$vitest_data_exit = $LASTEXITCODE
Assert-StageSucceeded $stage_number $stage_description $vitest_data_exit ((Get-Date) - $stage_start)

# --- Stage 5 : Vitest RTL tier ------------------------------------------------
$stage_number      = 5
$stage_description = 'Vitest RTL tier'
Write-StageBanner $stage_number $stage_description $gui_dir 'npm run test:rtl'
$stage_start = Get-Date
Set-Location $gui_dir
npm run test:rtl
$vitest_rtl_exit = $LASTEXITCODE
Assert-StageSucceeded $stage_number $stage_description $vitest_rtl_exit ((Get-Date) - $stage_start)

# --- Stage 6 : Vitest contract tier -------------------------------------------
$stage_number      = 6
$stage_description = 'Vitest contract tier'
Write-StageBanner $stage_number $stage_description $gui_dir 'npm run test:contract'
$stage_start = Get-Date
Set-Location $gui_dir
npm run test:contract
$vitest_contract_exit = $LASTEXITCODE
Assert-StageSucceeded $stage_number $stage_description $vitest_contract_exit ((Get-Date) - $stage_start)

# --- Stage 7 : Playwright e2e -------------------------------------------------
$stage_number      = 7
$stage_description = 'Playwright e2e'
Write-StageBanner $stage_number $stage_description $gui_dir 'npx playwright test --reporter=line'
$stage_start = Get-Date
Set-Location $gui_dir
npx playwright test --reporter=line
$playwright_exit = $LASTEXITCODE
Assert-StageSucceeded $stage_number $stage_description $playwright_exit ((Get-Date) - $stage_start)

Write-Host ''
Write-Host 'All stages passed.'
exit 0
