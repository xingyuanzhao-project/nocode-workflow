"""Run one configuration-driven pipeline defined by a single YAML file.

This script has exactly one job: take the path in the module-level
:data:`flow_config` variable, hand it to :func:`src.flow_builder.build_flow`,
and call :meth:`src.flow_builder.FlowRunner.run` on the result. The only
runtime knob exposed on the command line is ``--resume``, which toggles
entity-level checkpoint recovery.

How configuration works
-----------------------

There is no separate "settings" file. The YAML at :data:`flow_config` is
the **entire** run specification, bundling two different things in one
file:

1. **Workflow** -- the ``steps:`` block, which selects processor step
   types registered in :mod:`src.node_registry` via
   ``config/node_types.yaml`` (currently
   ``single_summary``, ``conversation_summary_first``,
   ``conversation_summary_update``, ``label_extraction``,
   ``label_summary``, and ``classification``) implemented by the
   classes in :mod:`src.processors`.
2. **Settings** -- everything else in the same file: LLM provider,
   model, ``api_base``, ``api_key_env``, temperature, token budgets,
   input CSV, column roles, prompts/taxonomy paths, concurrency limits,
   output paths, and logging.

:func:`src.flow_builder.build_flow` validates the YAML against
:class:`src.flow_loader.FlowSchema`, resolves ``api_key_env`` against
``os.environ`` (loading the project-root ``.env`` if present), loads
the node-type registry, and returns a
:class:`src.flow_builder.FlowRunner` already wired to the configured
LLM client and data source.

Switching pipelines
-------------------

To run a different pipeline, edit :data:`flow_config` below to point at
a different file under ``config/flows/``. The selected pipeline is
recorded in version control alongside the code; the CLI intentionally
does not accept a YAML path.

Resuming a killed run
---------------------

Pass ``--resume`` to threads ``resume=True`` into
:func:`src.flow_builder.build_flow`. The runner then loads the
entity-level checkpoint for :data:`flow_config` (see
:class:`src.flow_builder.EntityCheckpoint`), skips entities already
marked complete, and continues with the remainder.

Usage
-----

From the project root::

    python scripts/run_custom_flow.py
    python scripts/run_custom_flow.py --resume
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.flow_builder import build_flow  # noqa: E402


flow_config: str = "config/flows/openrouter_smoke_test.yml"
"""Path (relative to the project root) of the YAML to execute.

The referenced file is a combined workflow + settings specification
validated by :class:`src.flow_loader.FlowSchema`. Changing this string
is the only supported way to switch which pipeline runs.
"""


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse this script's command-line arguments.

    The only accepted flag is ``--resume``. The selected flow YAML is
    deliberately not a CLI argument; it is controlled by
    :data:`flow_config`.

    Args:
        argv (Optional[List[str]]): Argument list to parse. ``None``
            defers to :data:`sys.argv`.

    Returns:
        argparse.Namespace: Parsed arguments with a ``resume`` boolean
        attribute.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Run the flow defined by the module-level flow_config "
            "variable. Pass --resume to continue an interrupted run "
            "from its entity-level checkpoint."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Load the entity-level checkpoint for this flow, skip "
            "entities that were already marked complete, and continue."
        ),
    )
    return parser.parse_args(argv)


def main() -> None:
    """Build the :class:`FlowRunner` from :data:`flow_config` and run it.

    Parses ``--resume`` from :data:`sys.argv` and threads the flag into
    :func:`src.flow_builder.build_flow`.

    Returns:
        None. All outputs (summary / results / states / spans CSVs and
        the log file) are written to the paths declared inside the YAML
        at :data:`flow_config`.
    """
    args = parse_cli_args()
    flow_runner = build_flow(Path(flow_config), resume=args.resume)
    flow_runner.run()


if __name__ == "__main__":
    main()
