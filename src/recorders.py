"""Serialisation and CSV persistence for processor outputs.

Converts :class:`src.processors.ProcessorResult` and
:class:`src.processors.MessyTextConversationState` objects into flat
row dicts and writes them to CSV files with optional extend-mode
(append while replacing rows for the current model).
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

from src.processors import MessyTextConversationState, ProcessorResult


def serialize_result_entry(
    result: ProcessorResult,
    victim_id: str,
    model_name: str,
    turn_index: int,
) -> Dict[str, Any]:
    """Flatten a single :class:`ProcessorResult` into a CSV-ready dict.

    Args:
        result: Structured result returned by the processor.
        victim_id: Entity identifier carried through to the output row.
        model_name: Model identifier written to the ``model`` column.
        turn_index: Zero-based position of this turn within the entity's
            conversation.

    Returns:
        Dict with keys ``victim_id``, ``model``, ``turn_index``,
        ``task_name``, ``doc_id``, ``values``, and ``error``.
    """
    return {
        "victim_id": victim_id,
        "model": model_name,
        "turn_index": turn_index,
        "task_name": result.task_name,
        "doc_id": result.doc_id,
        "values": result.values,
        "error": result.error or "",
    }


def serialize_state_entry(
    state: MessyTextConversationState,
    victim_id: str,
    model_name: str,
) -> Dict[str, Any]:
    """Collapse an entity's full conversation state into one CSV row.

    The per-turn results are JSON-serialised into the ``results`` column
    so each entity occupies exactly one row in the states CSV.

    Args:
        state: Conversation state holding all per-turn
            :class:`ProcessorResult` objects.
        victim_id: Entity identifier for the output row.
        model_name: Model identifier written to the ``model`` column.

    Returns:
        Dict with keys ``victim_id``, ``model``, ``turns``, and
        ``results`` (a JSON string of serialised result dicts).
    """
    serialized_results: List[Dict[str, Any]] = []
    for turn_index, result in enumerate(state.results):
        serialized_results.append(
            serialize_result_entry(
                result=result,
                victim_id=victim_id,
                model_name=model_name,
                turn_index=turn_index,
            )
        )

    return {
        "victim_id": victim_id,
        "model": model_name,
        "turns": state.turn_index,
        "results": json.dumps(serialized_results, ensure_ascii=False),
    }


def flatten_spans_from_state(
    state: MessyTextConversationState,
    victim_id: str,
    model_name: str,
) -> List[Dict[str, Any]]:
    """Explode ``summary_by_item`` / ``spans_by_item`` into one row per span.

    Walks every :class:`ProcessorResult` in *state*, extracts span dicts
    from the ``summary_by_item`` or ``spans_by_item`` field, and yields
    one flat row per span keyed by ``victim_id``, ``model``,
    ``label_key``, ``span``, ``doc_id``, ``offset``, ``turn_index``, and
    ``index``.

    Args:
        state: Conversation state whose results may contain span dicts.
        victim_id: Entity identifier propagated to every output row.
        model_name: Model identifier propagated to every output row.

    Returns:
        List of flat dicts, one per span. Empty when no results contain
        span data.
    """
    rows: List[Dict[str, Any]] = []

    for turn_index, result in enumerate(state.results):
        spans_dict = result.get("spans_by_item") or result.get("summary_by_item")
        if not isinstance(spans_dict, dict):
            continue

        for label_key, spans in spans_dict.items():
            if not isinstance(spans, list):
                continue
            for item in spans:
                if not isinstance(item, dict):
                    continue
                span_text = item.get("span")
                if not span_text:
                    continue
                rows.append(
                    {
                        "victim_id": victim_id,
                        "model": model_name,
                        "label_key": label_key,
                        "span": span_text,
                        # Use the runner-provided document identifier to keep
                        # spans aligned with the input index column.
                        "doc_id": result.doc_id,
                        "offset": item.get("offset", -1),
                        "turn_index": turn_index,
                        "index": result.doc_id,
                    }
                )
    return rows


def _write_csv_with_extend(
    rows: Iterable[Dict[str, Any]],
    path: Path,
    extend: bool,
    model_name: str,
) -> None:
    """Write row dicts to a CSV, with optional model-scoped extend mode.

    When *extend* is ``True`` and *path* already exists, existing rows
    whose ``model`` column equals *model_name* are dropped before the
    new rows are appended. Surrogate Unicode characters are stripped from
    string columns to avoid encoding errors.

    Args:
        rows: Iterable of flat dicts to write.
        path: Destination CSV path (parent directory must exist).
        extend: When ``True``, append to the existing file while
            replacing rows for *model_name*.
        model_name: Model identifier used to scope the replacement when
            extending.
    """
    new_df = _expand_values(pd.DataFrame(list(rows)))
    _SURROGATE_RE = re.compile(r'[\ud800-\udfff]')
    for col in new_df.select_dtypes(include="object").columns:
        new_df[col] = new_df[col].apply(
            lambda x: _SURROGATE_RE.sub('', x) if isinstance(x, str) else x
        )
    if extend and path.exists():
        existing_df = pd.read_csv(path, encoding="utf-8")
        existing_df = _expand_values(existing_df)
        if "model" in existing_df.columns:
            existing_df = existing_df[existing_df["model"] != model_name]

        all_columns = sorted(set(existing_df.columns).union(new_df.columns))
        existing_df = existing_df.reindex(columns=all_columns)
        new_df = new_df.reindex(columns=all_columns)

        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        combined_df.to_csv(path, index=False, encoding="utf-8")
        return

    new_df.to_csv(path, index=False, encoding="utf-8")


def write_results(
    rows: Iterable[Dict[str, Any]],
    path: Path,
    extend: bool,
    model_name: str,
) -> None:
    """Write per-turn result rows to a CSV via :func:`_write_csv_with_extend`.

    Args:
        rows: Flat result dicts produced by :func:`serialize_result_entry`.
        path: Destination CSV path.
        extend: Append-and-replace mode flag.
        model_name: Model identifier for extend-mode scoping.
    """
    _write_csv_with_extend(rows, path, extend, model_name)


def _expand_values(df: pd.DataFrame) -> pd.DataFrame:
    """Expand a ``values`` column of dicts/JSON strings into top-level columns.

    Each entry in the ``values`` column is parsed (if a JSON string) or
    used directly (if already a dict), then normalised into individual
    columns via :func:`pandas.json_normalize`. The original ``values``
    column is dropped.

    Args:
        df: DataFrame that may contain a ``values`` column. If absent,
            the frame is returned unchanged.

    Returns:
        A new DataFrame with the ``values`` column replaced by its
        constituent fields.
    """
    if "values" not in df.columns:
        return df

    parsed: List[Dict[str, Any]] = []
    for val in df["values"].tolist():
        if isinstance(val, dict):
            parsed.append(val)
        elif isinstance(val, str):
            try:
                parsed.append(json.loads(val))
            except Exception:
                parsed.append({})
        else:
            parsed.append({})

    values_df = pd.json_normalize(parsed)
    values_df = values_df.rename(columns=lambda c: str(c))

    base_df = df.drop(columns=["values"]).reset_index(drop=True)
    values_df = values_df.reset_index(drop=True)
    expanded = pd.concat([base_df, values_df], axis=1)
    return expanded


def write_states(
    rows: Iterable[Dict[str, Any]],
    path: Path,
    extend: bool,
    model_name: str,
) -> None:
    """Write per-entity state rows to a CSV via :func:`_write_csv_with_extend`.

    Args:
        rows: State dicts produced by :func:`serialize_state_entry`.
        path: Destination CSV path.
        extend: Append-and-replace mode flag.
        model_name: Model identifier for extend-mode scoping.
    """
    _write_csv_with_extend(rows, path, extend, model_name)


def write_spans(
    rows: Iterable[Dict[str, Any]],
    path: Path,
    extend: bool,
    model_name: str,
) -> None:
    """Write per-span rows to a CSV via :func:`_write_csv_with_extend`.

    Args:
        rows: Span dicts produced by :func:`flatten_spans_from_state`.
        path: Destination CSV path.
        extend: Append-and-replace mode flag.
        model_name: Model identifier for extend-mode scoping.
    """
    _write_csv_with_extend(rows, path, extend, model_name)
