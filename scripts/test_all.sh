#!/usr/bin/env bash
# =============================================================================
# test_all.sh -- run the full nocode-workflow test matrix in a strict fail-fast
#                pipeline (POSIX / bash twin of scripts/test_all.ps1).
#
# Usage: scripts/test_all.sh [--integration] [-h|--help]
#
# Description
#   Executes seven stages in a fixed order:
#
#     1. Python backend unit + route tests
#        (server/tests/unit, server/tests/routes, src/tests)
#     2. Python backend integration tests  (opt-in via --integration)
#     3. getState() ban grep check under gui/tests/rtl and gui/tests/e2e
#     4. Vitest data-layer tier            (npm run test:data)
#     5. Vitest RTL tier                   (npm run test:rtl)
#     6. Vitest contract tier              (npm run test:contract)
#     7. Playwright e2e                    (npx playwright test --reporter=line)
#
#   The pipeline is fail-fast: the first non-zero exit code stops the run
#   and becomes the script's exit code. Every stage prints a banner
#   containing the stage number, description, working directory, and the
#   exact command being executed, so a developer reading CI logs can
#   reproduce any failing stage in isolation.
#
# Parameters
#   --integration   Include Stage 2 (pytest -m integration). Requires the
#                   docker compose stack at the repository root to be up so
#                   that the integration tests can reach redis / celery /
#                   the FastAPI web service. Default: off.
#   -h | --help     Print usage and exit 0.
#
# Behaviour
#   - `set -euo pipefail` is active; any unhandled failing command aborts
#     the script.
#   - For Stage 3 the grep-ban inversion (`rg` exit 0 = FAIL,
#     exit 1 = PASS) is implemented with explicit exit-code checks,
#     because `set -e` cannot express that inversion on its own.
#   - The Python interpreter is resolved in this order:
#        .venv/bin/python           (POSIX venv)
#        .venv/Scripts/python.exe   (Windows venv under Git Bash / WSL)
#        python3 on PATH
#        python  on PATH
#
# Example
#   # Default pipeline (no docker required)
#   scripts/test_all.sh
#
#   # Full pipeline including integration tests (docker compose must be up)
#   scripts/test_all.sh --integration
# =============================================================================

set -euo pipefail

# --- argument parsing ---------------------------------------------------------
include_integration=0

for arg in "$@"; do
    case "$arg" in
        --integration)
            include_integration=1
            ;;
        -h|--help)
            sed -n '2,51p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: scripts/test_all.sh [--integration] [-h|--help]" >&2
            exit 2
            ;;
    esac
done

# --- environment discovery ----------------------------------------------------
script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
gui_dir="$repo_root/gui"
total_stages=7

if [[ -x "$repo_root/.venv/bin/python" ]]; then
    venv_python="$repo_root/.venv/bin/python"
elif [[ -x "$repo_root/.venv/Scripts/python.exe" ]]; then
    venv_python="$repo_root/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    venv_python="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    venv_python="$(command -v python)"
else
    echo "!! Could not locate a Python interpreter (.venv or python3/python on PATH)." >&2
    exit 2
fi

cd "$repo_root"

# --- helpers ------------------------------------------------------------------
print_stage_banner() {
    local stage_number="$1"
    local stage_description="$2"
    local working_dir="$3"
    local command_display="$4"
    echo
    echo "==> Stage ${stage_number} / ${total_stages}: ${stage_description}"
    echo "    cwd     : ${working_dir}"
    echo "    command : ${command_display}"
}

fail_stage() {
    local stage_number="$1"
    local stage_description="$2"
    local exit_code="$3"
    local elapsed_seconds="$4"
    echo "!! FAILED at Stage ${stage_number}: ${stage_description} (exit ${exit_code}, ${elapsed_seconds}s)"
    exit "$exit_code"
}

ok_stage() {
    local elapsed_seconds="$1"
    echo "    ok      : ${elapsed_seconds}s"
}

now_seconds() { date +%s; }

# --- Stage 1 : Python backend unit + route tests ------------------------------
stage_number=1
stage_description='Python backend unit + route tests'
print_stage_banner "$stage_number" "$stage_description" "$repo_root" \
    "$venv_python -m pytest server/tests/unit server/tests/routes src/tests -q"
stage_start=$(now_seconds)
cd "$repo_root"
set +e
"$venv_python" -m pytest server/tests/unit server/tests/routes src/tests -q
pytest_unit_exit=$?
set -e
stage_elapsed=$(( $(now_seconds) - stage_start ))
if [[ $pytest_unit_exit -ne 0 ]]; then
    fail_stage "$stage_number" "$stage_description" "$pytest_unit_exit" "$stage_elapsed"
fi
ok_stage "$stage_elapsed"

# --- Stage 2 : Python backend integration tests (opt-in) ----------------------
stage_number=2
stage_description='Python backend integration tests'
if [[ $include_integration -eq 1 ]]; then
    print_stage_banner "$stage_number" "$stage_description" "$repo_root" \
        "$venv_python -m pytest server/tests/integration -q -m integration"
    stage_start=$(now_seconds)
    cd "$repo_root"
    set +e
    "$venv_python" -m pytest server/tests/integration -q -m integration
    pytest_integration_exit=$?
    set -e
    stage_elapsed=$(( $(now_seconds) - stage_start ))
    if [[ $pytest_integration_exit -ne 0 ]]; then
        fail_stage "$stage_number" "$stage_description" "$pytest_integration_exit" "$stage_elapsed"
    fi
    ok_stage "$stage_elapsed"
else
    echo
    echo "==> Stage ${stage_number} / ${total_stages}: ${stage_description} -- SKIPPED (pass --integration to include)"
fi

# --- Stage 3 : getState() ban grep check --------------------------------------
# Scope the ban to actual test/spec files. Shared infrastructure such as
# tests/rtl/_helpers.tsx legitimately calls store.getState() to reset Zustand
# state between renders; the ban is only meant to catch test bodies that
# assert on store state instead of observing the rendered DOM.
#
# Prefer ripgrep when it is on PATH (fast, supports --glob directly). Fall
# back to a POSIX `find | xargs grep` combination so the pipeline still
# runs on minimal CI images that do not ship ripgrep.
stage_number=3
stage_description='getState() ban grep check'
if command -v rg >/dev/null 2>&1; then
    stage_command_display="rg --files-with-matches --glob '*.test.ts' --glob '*.test.tsx' --glob '*.spec.ts' --glob '*.spec.tsx' 'getState\\(' tests/rtl tests/e2e"
else
    stage_command_display="find tests/rtl tests/e2e -type f \\( -name '*.test.ts' -o -name '*.test.tsx' -o -name '*.spec.ts' -o -name '*.spec.tsx' \\) -print0 | xargs -0 grep -l 'getState('"
fi
print_stage_banner "$stage_number" "$stage_description" "$gui_dir" "$stage_command_display"
stage_start=$(now_seconds)
cd "$gui_dir"
set +e
if command -v rg >/dev/null 2>&1; then
    offender_output="$(rg --files-with-matches \
        --glob '*.test.ts'  --glob '*.test.tsx' \
        --glob '*.spec.ts'  --glob '*.spec.tsx' \
        'getState\(' tests/rtl tests/e2e)"
    grep_exit=$?
else
    offender_output="$(find tests/rtl tests/e2e -type f \
        \( -name '*.test.ts' -o -name '*.test.tsx' \
        -o -name '*.spec.ts' -o -name '*.spec.tsx' \) -print0 \
        | xargs -0 -r grep -l 'getState(')"
    grep_exit=$?
fi
set -e
stage_elapsed=$(( $(now_seconds) - stage_start ))
if [[ -n "$offender_output" ]]; then
    echo
    echo 'Offending files (contain getState( ):'
    while IFS= read -r offender; do
        [[ -n "$offender" ]] && echo "    $offender"
    done <<< "$offender_output"
    fail_stage "$stage_number" "$stage_description" 1 "$stage_elapsed"
fi
# Exit codes 0 (matches) and 1 (no matches) are both expected for rg/grep;
# anything else is a real error.
if [[ $grep_exit -gt 1 ]]; then
    echo "grep failed with exit code $grep_exit" >&2
    fail_stage "$stage_number" "$stage_description" "$grep_exit" "$stage_elapsed"
fi
echo "    ok      : ${stage_elapsed}s (no matches)"

# --- Stage 4 : Vitest data-layer tier -----------------------------------------
stage_number=4
stage_description='Vitest data-layer tier'
print_stage_banner "$stage_number" "$stage_description" "$gui_dir" 'npm run test:data'
stage_start=$(now_seconds)
cd "$gui_dir"
set +e
npm run test:data
vitest_data_exit=$?
set -e
stage_elapsed=$(( $(now_seconds) - stage_start ))
if [[ $vitest_data_exit -ne 0 ]]; then
    fail_stage "$stage_number" "$stage_description" "$vitest_data_exit" "$stage_elapsed"
fi
ok_stage "$stage_elapsed"

# --- Stage 5 : Vitest RTL tier ------------------------------------------------
stage_number=5
stage_description='Vitest RTL tier'
print_stage_banner "$stage_number" "$stage_description" "$gui_dir" 'npm run test:rtl'
stage_start=$(now_seconds)
cd "$gui_dir"
set +e
npm run test:rtl
vitest_rtl_exit=$?
set -e
stage_elapsed=$(( $(now_seconds) - stage_start ))
if [[ $vitest_rtl_exit -ne 0 ]]; then
    fail_stage "$stage_number" "$stage_description" "$vitest_rtl_exit" "$stage_elapsed"
fi
ok_stage "$stage_elapsed"

# --- Stage 6 : Vitest contract tier -------------------------------------------
stage_number=6
stage_description='Vitest contract tier'
print_stage_banner "$stage_number" "$stage_description" "$gui_dir" 'npm run test:contract'
stage_start=$(now_seconds)
cd "$gui_dir"
set +e
npm run test:contract
vitest_contract_exit=$?
set -e
stage_elapsed=$(( $(now_seconds) - stage_start ))
if [[ $vitest_contract_exit -ne 0 ]]; then
    fail_stage "$stage_number" "$stage_description" "$vitest_contract_exit" "$stage_elapsed"
fi
ok_stage "$stage_elapsed"

# --- Stage 7 : Playwright e2e -------------------------------------------------
stage_number=7
stage_description='Playwright e2e'
print_stage_banner "$stage_number" "$stage_description" "$gui_dir" 'npx playwright test --reporter=line'
stage_start=$(now_seconds)
cd "$gui_dir"
set +e
npx playwright test --reporter=line
playwright_exit=$?
set -e
stage_elapsed=$(( $(now_seconds) - stage_start ))
if [[ $playwright_exit -ne 0 ]]; then
    fail_stage "$stage_number" "$stage_description" "$playwright_exit" "$stage_elapsed"
fi
ok_stage "$stage_elapsed"

echo
echo 'All stages passed.'
exit 0
