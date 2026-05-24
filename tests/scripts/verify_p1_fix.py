"""Verification script for P1 fix: sentiment field missing.

Run with:
    .venv/Scripts/python.exe tests/scripts/verify_p1_fix.py

Requires OPENROUTER_API_KEY in .env or environment.
Runs the test_generic_processor flow directly and prints:
  - The adapted system message (with schema instruction)
  - The LLM response (with finish_reason)
  - The parsed output (should have both summary and sentiment)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.flow_builder import build_flow


async def main() -> None:
    flow_path = Path("config/templates/test_generic_processor.yml")
    if not flow_path.exists():
        print(f"ERROR: {flow_path} not found")
        sys.exit(1)

    print(f"Loading flow from: {flow_path}")
    runner = build_flow(str(flow_path))
    print(f"Flow loaded: {runner.schema.flow.name}")
    print(f"Processors: {len(runner.schema.flow.processors)}")
    print(f"Resources: {list(runner.clients_by_id.keys())}")
    print()

    result_df = await runner.run()

    print("\n=== RESULTS ===")
    print(result_df[["summary", "sentiment"]].to_string())
    print()

    has_sentiment = result_df["sentiment"].notna() & (result_df["sentiment"] != "")
    n_with_sentiment = has_sentiment.sum()
    n_total = len(result_df)
    print(f"Rows with sentiment: {n_with_sentiment}/{n_total}")

    if n_with_sentiment == n_total:
        print("PASS: All rows have sentiment populated")
    else:
        print("FAIL: Some rows missing sentiment")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
