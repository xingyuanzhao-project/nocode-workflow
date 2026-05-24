"""Regression check: existing flow YAMLs still load under the new loader.

The new graph-format flows live under ``server/data/flows/``. Each must
parse as a :class:`FlowDocument` and compile into a runtime
:class:`FlowConfig` cleanly.

Run with ``.venv/Scripts/python.exe _verify_existing_flows.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.flow_loader import FlowSchema


SKIPPED: set[str] = set()


def main() -> None:
    """Load every non-skipped flow YAML through FlowSchema and report results.

    Iterates ``server/data/flows/*.yml``, validates each with
    :meth:`FlowSchema.load_from_path`, and prints step types and units
    for every successfully loaded flow.  Asserts at least one YAML exists.
    """
    flow_dir = REPO_ROOT / "server" / "data" / "flows"
    flow_paths = sorted(flow_dir.glob("*.yml"))
    assert flow_paths, f"No flow YAMLs found in {flow_dir}"

    loaded_count = 0
    skipped_count = 0
    for flow_path in flow_paths:
        if flow_path.name in SKIPPED:
            print(f"SKIP  {flow_path.name} (deliberately scheduled for rewrite)")
            skipped_count += 1
            continue
        schema = FlowSchema.load_from_path(flow_path)
        proc_types = [proc.type for proc in schema.flow.processors]
        proc_units = [proc.unit for proc in schema.flow.processors]
        print(
            f"OK    {flow_path.name}: types={proc_types} "
            f"units={proc_units}"
        )
        loaded_count += 1

    print(
        f"\nSummary: {loaded_count} flows loaded, "
        f"{skipped_count} skipped, total {len(flow_paths)}"
    )


if __name__ == "__main__":
    main()
