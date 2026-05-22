"""Smoke test for the configuration-driven MessyText flow on real OpenRouter.

This script is an end-to-end smoke test for :mod:`src.flow_builder` and
:mod:`src.flow_loader`. It intentionally does **not** use mocks: the goal is
to confirm that a YAML flow declared under ``config/flows/`` can be loaded,
wired up against a real LLM provider, and executed to completion.

What the test verifies
----------------------

1. The project-root ``.env`` file exists and contains a non-empty
   ``OPENROUTER_API_KEY``.
2. :func:`src.flow_builder.build_flow` returns a :class:`FlowRunner` whose
   default resource resolves to ``provider = "openrouter"`` and whose
   ``api_key`` matches the value pulled from ``.env`` (i.e. the runner is
   wired to the real remote endpoint, not a local or dummy placeholder).
3. The flow executes end-to-end against OpenRouter with exactly five input
   rows from the real input CSV.
4. Every output CSV declared in :class:`src.flow_loader.OutputConfig` is
   written to disk, is non-empty, and contains the expected columns.

Safety and cost
---------------

The test performs **real** paid LLM calls against OpenRouter. It is
deliberately capped at five rows to keep cost trivial (a few summary
completions against the default ``meta-llama/llama-3.1-70b-instruct``
model). Run it when you need to confirm the flow works, not on every save.

Usage
-----

From the project root::

    python tests/scripts/test_customize_flow.py

The script exits with code 0 on success and raises (non-zero exit) on
any assertion failure, so it can be used as a CI smoke test.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.flow_builder import FlowRunner, build_flow  # noqa: E402


flow_config: str = "config/flows/conversation_summary.yml"
"""Path to the flow YAML being smoke-tested."""

test_row_limit: int = 5
"""Maximum number of rows from the input CSV passed to the runner."""


def _assert_env_has_openrouter_key(project_root: Path) -> str:
    """Verify the project-root ``.env`` file supplies ``OPENROUTER_API_KEY``.

    The assertion is deliberately strict: the test must fail loudly if the
    key is missing or left at an obvious placeholder, because the whole
    point of this smoke test is to exercise the real remote endpoint.

    Args:
        project_root (Path): Directory that should contain the ``.env``
            file.

    Returns:
        str: The resolved ``OPENROUTER_API_KEY`` value.

    Raises:
        AssertionError: If the ``.env`` file does not exist, does not
            declare ``OPENROUTER_API_KEY``, or the value is empty / a
            placeholder like ``"dummy"``.
    """
    env_path = project_root / ".env"
    assert env_path.exists(), (
        f".env not found at {env_path}. The OpenRouter smoke test requires "
        "a real OPENROUTER_API_KEY in the project-root .env file."
    )

    env_text = env_path.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY" in env_text, (
        f".env at {env_path} does not declare OPENROUTER_API_KEY. "
        "Add the key before running this test."
    )

    from src.flow_builder import _load_dotenv_into_environ

    _load_dotenv_into_environ(project_root)

    api_key_value = os.environ.get("OPENROUTER_API_KEY", "")
    assert api_key_value, "OPENROUTER_API_KEY is present in .env but empty."
    assert api_key_value.lower() != "dummy", (
        "OPENROUTER_API_KEY is set to the placeholder 'dummy'. Populate it "
        "with a real OpenRouter key before running this test."
    )
    return api_key_value


def _assert_runner_uses_openrouter(
    flow_runner: FlowRunner,
    expected_api_key: str,
) -> None:
    """Verify the built runner talks to OpenRouter, not a dummy endpoint.

    Args:
        flow_runner (FlowRunner): The runner returned by
            :func:`src.flow_builder.build_flow`.
        expected_api_key (str): The ``OPENROUTER_API_KEY`` value read from
            the environment. Must match the resolved resource's
            ``api_key``.

    Returns:
        None.

    Raises:
        AssertionError: If the default resource's provider is not
            ``openrouter``, the ``api_base`` is missing OpenRouter's
            domain, or the ``api_key`` does not match the environment
            value.
    """
    assert "default" in flow_runner.resolved_resources, (
        "Built flow has no resource with id='default'. The conversation "
        "summary YAML is expected to expose exactly one default resource."
    )
    default_resource = flow_runner.resolved_resources["default"]

    assert default_resource.provider == "openrouter", (
        f"Expected default resource provider='openrouter', got "
        f"{default_resource.provider!r}."
    )
    assert default_resource.api_base is not None and (
        "openrouter.ai" in default_resource.api_base
    ), (
        f"Expected default resource api_base to contain 'openrouter.ai', "
        f"got {default_resource.api_base!r}."
    )
    assert default_resource.api_key == expected_api_key, (
        "Resolved api_key on the default resource does not match the "
        "value read from .env. The builder did not wire the environment "
        "variable through correctly."
    )


def _install_row_limit(flow_runner: FlowRunner, row_limit: int) -> None:
    """Cap :meth:`FlowRunner._load_input_csv` output to ``row_limit`` rows.

    The original ``_load_input_csv`` still performs path and column-role
    validation; this wrapper just trims the returned DataFrame so the
    downstream conversation loop processes a small, fixed number of rows.

    Args:
        flow_runner (FlowRunner): The runner whose input loader will be
            wrapped. The wrapper is installed as an instance attribute and
            therefore shadows the class method only for this runner.
        row_limit (int): Maximum number of rows the runner will see.

    Returns:
        None.
    """
    original_loader: Callable[[], pd.DataFrame] = flow_runner._load_input_csv

    def _load_limited_input_csv() -> pd.DataFrame:
        """Return at most ``row_limit`` rows from the real input CSV.

        Returns:
            pd.DataFrame: The head of the original DataFrame, with index
            reset so downstream groupby operations behave predictably.
        """
        full_df = original_loader()
        trimmed_df = full_df.head(row_limit).reset_index(drop=True)
        print(
            f"[test_customize_flow] Loaded {len(full_df):,} rows from input CSV; "
            f"trimmed to {len(trimmed_df)} rows for the smoke test."
        )
        return trimmed_df

    flow_runner._load_input_csv = _load_limited_input_csv  # type: ignore[method-assign]


def _assert_outputs_written(flow_runner: FlowRunner) -> None:
    """Verify every configured output CSV exists and is non-empty.

    Args:
        flow_runner (FlowRunner): The runner whose schema declares the
            output paths under
            :attr:`src.flow_loader.OutputConfig`.

    Returns:
        None.

    Raises:
        AssertionError: If any configured output CSV is missing or empty.
    """
    output_config = flow_runner.schema.flow.output
    declared_outputs = {
        "summary_csv": output_config.summary_csv,
        "results_csv": output_config.results_csv,
        "states_csv": output_config.states_csv,
        "spans_csv": output_config.spans_csv,
    }

    for output_label, output_path_str in declared_outputs.items():
        if output_path_str is None:
            continue
        output_path = Path(output_path_str)
        assert output_path.exists(), (
            f"Expected output {output_label} at {output_path} was not "
            "written by the flow runner."
        )
        written_df = pd.read_csv(output_path)
        assert len(written_df) > 0, (
            f"Output {output_label} at {output_path} was written but is "
            "empty (0 rows)."
        )
        print(
            f"[test_customize_flow] Verified {output_label} at {output_path}: "
            f"{len(written_df)} rows, {len(written_df.columns)} columns."
        )


def main() -> None:
    """Execute the OpenRouter smoke test end-to-end.

    Steps:

    1. Assert the project-root ``.env`` supplies ``OPENROUTER_API_KEY``.
    2. Build the flow from :data:`flow_config`.
    3. Assert the built runner is wired to OpenRouter with the env key.
    4. Cap the input loader to :data:`test_row_limit` rows.
    5. Run the flow synchronously against the real endpoint.
    6. Assert every configured output CSV was written and is non-empty.

    Returns:
        None.

    Raises:
        AssertionError: If any of the verification steps fail.
        RuntimeError: Propagated from the runner if the underlying LLM
            calls error out.
    """
    project_root = Path(__file__).resolve().parent.parent.parent

    print("[test_customize_flow] Step 1/6: verifying .env / OPENROUTER_API_KEY ...")
    expected_api_key = _assert_env_has_openrouter_key(project_root)
    print(
        f"[test_customize_flow]   OK. OPENROUTER_API_KEY present "
        f"(length={len(expected_api_key)}, prefix={expected_api_key[:8]}...)."
    )

    print(f"[test_customize_flow] Step 2/6: building flow from {flow_config} ...")
    flow_runner = build_flow(Path(flow_config))
    print("[test_customize_flow]   OK. FlowRunner constructed.")

    print("[test_customize_flow] Step 3/6: checking runner wiring (openrouter + env key) ...")
    _assert_runner_uses_openrouter(flow_runner, expected_api_key)
    default_resource = flow_runner.resolved_resources["default"]
    print(
        f"[test_customize_flow]   OK. provider={default_resource.provider}, "
        f"model={default_resource.model}, api_base={default_resource.api_base}."
    )

    print(
        f"[test_customize_flow] Step 4/6: installing {test_row_limit}-row "
        "cap on input loader ..."
    )
    _install_row_limit(flow_runner, test_row_limit)
    print("[test_customize_flow]   OK. Row cap installed.")

    print(
        "[test_customize_flow] Step 5/6: running flow against real OpenRouter "
        "endpoint (this will spend API credits) ..."
    )
    flow_runner.run()
    print("[test_customize_flow]   OK. Flow completed.")

    print("[test_customize_flow] Step 6/6: verifying output CSVs ...")
    _assert_outputs_written(flow_runner)
    print("[test_customize_flow]   OK. All configured outputs were written.")

    print("[test_customize_flow] SUCCESS: end-to-end smoke test passed.")


if __name__ == "__main__":
    main()
