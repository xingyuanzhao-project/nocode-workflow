"""CSV persistence utilities for flow runner outputs.

Provides extend-mode writing (append while replacing rows for the current
model) and a values-column expansion helper.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd


def _write_csv_with_extend(
    rows: Iterable[Dict[str, Any]],
    path: Path,
    extend: bool,
    model_name: str,
) -> None:
    """Write row dicts to a CSV, with optional model-scoped extend mode.

    When *extend* is ``True`` and *path* already exists, existing rows
    whose ``model`` column equals *model_name* are dropped before the
    new rows are appended.
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


def _expand_values(df: pd.DataFrame) -> pd.DataFrame:
    """Expand a ``values`` column of dicts/JSON strings into top-level columns."""
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


def write_results(
    rows: Iterable[Dict[str, Any]],
    path: Path,
    extend: bool,
    model_name: str,
) -> None:
    """Write result rows to a CSV via :func:`_write_csv_with_extend`."""
    _write_csv_with_extend(rows, path, extend, model_name)
