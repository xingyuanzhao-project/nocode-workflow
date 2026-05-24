"""Standalone test script for the format adapter.

Usage:
    python tests/test_format_adapter_live.py --model google/gemini-2.0-flash-001
    python tests/test_format_adapter_live.py --model anthropic/claude-3.5-haiku
    python tests/test_format_adapter_live.py --model mistralai/mistral-7b-instruct
    python tests/test_format_adapter_live.py --model meta-llama/llama-3.1-8b-instruct
    python tests/test_format_adapter_live.py --model openai/gpt-4o-mini

Requires OPENROUTER_API_KEY in .env or environment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from openai import AsyncOpenAI

from src.format_adapter import normalize_llm_response
from src.io_schema import IOSchema, to_response_format


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TEST_SCHEMA = IOSchema(
    input={"text": {"type": "string"}},
    output={
        "summary": {"type": "string"},
        "sentiment": {"type": "string"},
    },
)

TEST_INSTRUCTIONS = (
    "You are a text analyst.\n"
    "Read the text and produce a one-sentence summary and a sentiment label "
    "(positive, negative, or neutral)."
)

TEST_INPUT = (
    "The city council voted unanimously to approve the new park project. "
    "Residents expressed overwhelming support during the public hearing, "
    "noting the lack of green spaces in the neighborhood. Construction is "
    "expected to begin in spring 2027."
)


async def run_test(model: str) -> dict:
    """Run a single test against the given model and return results."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {"model": model, "error": "OPENROUTER_API_KEY not set", "success": False}

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        max_retries=2,
    )

    response_format = to_response_format(TEST_SCHEMA, "test_output")
    output_keys = list(TEST_SCHEMA.output.keys())

    messages = [
        {"role": "system", "content": TEST_INSTRUCTIONS},
        {"role": "user", "content": TEST_INPUT},
    ]

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 512,
        "response_format": response_format,
    }

    adapted_kwargs = kwargs
    used_response_format = "response_format" in adapted_kwargs

    print(f"\n{'='*60}")
    print(f"MODEL: {model}")
    print(f"  response_format sent: {used_response_format}")
    print(f"{'='*60}")

    try:
        response = await client.chat.completions.create(**adapted_kwargs)
        raw_content = response.choices[0].message.content or ""

        print(f"\n  RAW RESPONSE ({len(raw_content)} chars):")
        print(f"  {raw_content[:500]}")
        if len(raw_content) > 500:
            print(f"  ... ({len(raw_content) - 500} more chars)")

        # Apply output normalization
        result, success = normalize_llm_response(raw_content, output_keys)

        print(f"\n  NORMALIZED RESULT:")
        print(f"    success: {success}")
        for k, v in result.items():
            val_preview = str(v)[:100]
            print(f"    {k}: {val_preview}")

        # Validate
        has_summary = bool(result.get("summary"))
        has_sentiment = bool(result.get("sentiment"))
        sentiment_valid = result.get("sentiment", "").lower() in {
            "positive", "negative", "neutral", ""
        }

        test_passed = success and has_summary and has_sentiment and sentiment_valid

        print(f"\n  TEST RESULT: {'PASS' if test_passed else 'FAIL'}")
        if not test_passed:
            if not success:
                print("    - JSON parsing/normalization failed")
            if not has_summary:
                print("    - summary field is empty")
            if not has_sentiment:
                print("    - sentiment field is empty")
            if not sentiment_valid:
                print(f"    - sentiment '{result.get('sentiment')}' not in valid set")

        return {
            "model": model,
            "success": test_passed,
            "parse_success": success,
            "raw_length": len(raw_content),
            "raw_preview": raw_content[:200],
            "result": result,
            "used_response_format": used_response_format,
            "error": None,
        }

    except Exception as exc:
        print(f"\n  ERROR: {exc}")
        return {
            "model": model,
            "success": False,
            "parse_success": False,
            "error": str(exc),
            "used_response_format": used_response_format,
        }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="Model slug on OpenRouter")
    args = parser.parse_args()

    result = await run_test(args.model)

    # Write result to a file for the main agent to read
    output_dir = Path(__file__).resolve().parent.parent / "test_results"
    output_dir.mkdir(exist_ok=True)
    safe_name = args.model.replace("/", "_").replace(".", "_")
    output_file = output_dir / f"format_adapter_{safe_name}.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n  Result written to: {output_file}")

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
