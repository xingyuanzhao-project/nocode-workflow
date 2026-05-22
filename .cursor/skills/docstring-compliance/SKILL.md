---
name: docstring-compliance
description: >-
  Enforce Google-style docstrings on Python modules, functions, and classes.
  Checks coverage, format, and quality. Use when writing, editing, or reviewing
  Python code, when the user mentions docstrings, documentation, or
  docstring compliance, or when adding new modules, functions, or classes.
disable-model-invocation: true
---

# Docstring Compliance

## Required Coverage

Every Python file must have docstrings on:

1. **Modules** — the first statement in every `.py` file
2. **Functions and methods** — every `def`, including `__init__`
3. **Classes** — every `class` definition

Exceptions: empty `__init__.py` files, and trivially obvious single-line lambdas (which cannot have docstrings anyway).

## Format Spec: Google Style

Use Google-style docstrings with the sections below. Only include sections that apply.

### Module docstring

```python
"""Short summary of what this module provides.

Longer description if needed — purpose, key abstractions, usage notes.
"""
```

### Function / method docstring

```python
def fetch_papers(query: str, max_results: int = 10) -> list[dict]:
    """Fetch papers from the Semantic Scholar API matching the query.

    Args:
        query: Search string passed to the API endpoint.
        max_results: Upper bound on returned papers. Defaults to 10.

    Returns:
        List of dicts, each with keys 'title', 'abstract', 'year', 'doi'.

    Raises:
        ConnectionError: If the API is unreachable after retries.
        ValueError: If query is empty.
    """
```

Required sections for functions:

| Section   | When to include                              |
|-----------|----------------------------------------------|
| Args      | Function takes parameters (excluding `self`) |
| Returns   | Function returns a value                     |
| Raises    | Function explicitly raises exceptions        |

Rules:

- One-liner summary is always present, imperative mood, ends with period.
- `Args`: list each param as `name: Description.` Include type only when not annotated in the signature.
- `Returns`: describe the shape and semantics, not just the type.
- `Raises`: list each exception and its trigger condition.

### Class docstring

```python
class PaperCache:
    """Local disk cache for downloaded papers.

    Attributes:
        cache_dir: Path to the directory where PDFs are stored.
        max_size_mb: Maximum total cache size in megabytes.
    """
```

Required sections for classes:

| Section    | When to include                              |
|------------|----------------------------------------------|
| Attributes | Class has public instance or class attributes |

Document `__init__` params in the `__init__` method's own docstring, not in the class docstring.

## Quality Rules

### DO

- **State the WHY or WHAT-FOR**, not just WHAT the code does.
- **Name the domain objects** — say "Fetch papers from Semantic Scholar" not "Fetch items from the API."
- **Describe return semantics** — say "List of dicts with keys 'title', 'year'" not "The result."
- **Document non-obvious defaults** — say "Defaults to 10, capped by API limit of 100."
- **Document side effects** — file I/O, network calls, mutations to shared state.
- **Keep it tight** — one informative sentence beats three vague ones.

### DON'T

- Don't restate the function signature in prose. `"""Get x."""` for `def get_x()` adds nothing.
- Don't pad with filler words: "This function is used to...", "This method basically..."
- Don't write a wall of text when a table or short list is clearer.
- Don't document private helpers to the same depth as public API unless they're complex.

## Anti-Patterns

### 1. Signature restating (word soup)

```python
# BAD — restates the signature, adds zero information
def calculate_score(paper: dict, weights: dict) -> float:
    """Calculate the score for a paper given weights.

    Args:
        paper: The paper.
        weights: The weights.

    Returns:
        The score.
    """
```

```python
# GOOD — explains what the score means and how inputs are used
def calculate_score(paper: dict, weights: dict) -> float:
    """Compute a relevance score by dot-producting paper field values with weights.

    Args:
        paper: Dict with keys matching weight keys; values are numeric
            feature magnitudes (citation count, recency, etc.).
        weights: Dict mapping feature names to their importance multipliers.

    Returns:
        Weighted sum in [0, 1], higher means more relevant.
    """
```

### 2. Filler preamble

```python
# BAD — "This function is responsible for" is pure filler
def load_config(path: str) -> dict:
    """This function is responsible for loading the configuration file.

    This function takes a path to a configuration file and loads it
    into a dictionary. It is used by the main application to get
    the configuration settings.

    Args:
        path: The path to the configuration file.

    Returns:
        A dictionary containing the configuration.
    """
```

```python
# GOOD — tight, informative, no filler
def load_config(path: str) -> dict:
    """Load a YAML config file and return it as a dict.

    Args:
        path: Absolute or project-relative path to a YAML file.

    Returns:
        Parsed config dict. Missing keys fall back to defaults
        defined in DEFAULT_CONFIG.

    Raises:
        FileNotFoundError: If path does not exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
```

### 3. Missing module docstring

```python
# BAD — module starts with imports, no docstring
import os
import sys

def main():
    ...
```

```python
# GOOD — module purpose is immediately clear
"""CLI entrypoint for the paper ingestion pipeline.

Usage:
    python ingest.py --query "transformer" --limit 50
"""

import os
import sys

def main():
    ...
```

### 4. Vacuous class docstring

```python
# BAD — says nothing beyond the class name
class DatabaseConnection:
    """DatabaseConnection class."""
```

```python
# GOOD — says what it wraps and why
class DatabaseConnection:
    """Pooled PostgreSQL connection with automatic retry on transient errors.

    Attributes:
        pool_size: Number of connections kept open.
        retry_limit: Max retries before raising ConnectionError.
    """
```

## Before / After Examples

### Example 1: Function

**Before (non-compliant):**

```python
def download(url, dest):
    """Download a file."""
```

**After (compliant):**

```python
def download(url: str, dest: Path) -> Path:
    """Download a file from url and write it to dest.

    Args:
        url: Full HTTP(S) URL of the remote file.
        dest: Local directory to save into. Filename is derived from
            the URL's last path segment.

    Returns:
        Path to the saved file.

    Raises:
        requests.HTTPError: On non-2xx response after 3 retries.
    """
```

### Example 2: Class

**Before (non-compliant):**

```python
class Tokenizer:
    """Tokenizer class for tokenizing text."""

    def __init__(self, vocab_path):
        """Initialize the tokenizer."""
```

**After (compliant):**

```python
class Tokenizer:
    """BPE tokenizer backed by a pre-trained vocabulary file.

    Attributes:
        vocab_size: Number of tokens in the loaded vocabulary.
    """

    def __init__(self, vocab_path: str) -> None:
        """Load a BPE vocabulary from disk.

        Args:
            vocab_path: Path to a JSON file mapping token strings to IDs.

        Raises:
            FileNotFoundError: If vocab_path does not exist.
        """
```

### Example 3: Module

**Before (non-compliant):**

```python
import re
from pathlib import Path

PATTERN = re.compile(r"\d+")

def extract_ids(text):
    ...
```

**After (compliant):**

```python
"""Utilities for extracting numeric identifiers from free-text metadata.

Handles DOI suffixes, PubMed IDs, and arXiv identifiers. Used by the
ingestion pipeline to normalize paper references.
"""

import re
from pathlib import Path

PATTERN = re.compile(r"\d+")

def extract_ids(text: str) -> list[str]:
    """Extract all numeric ID substrings from text.

    Args:
        text: Raw metadata string, may contain multiple IDs.

    Returns:
        List of numeric strings in the order they appear.
    """
```

## Validation Checklist

After writing or editing docstrings, verify each one against this checklist:

- [ ] **Module docstring exists** as the first statement in the file.
- [ ] **Every public function/method has a docstring** with a one-line summary.
- [ ] **Every class has a docstring** with a one-line summary.
- [ ] **Args section** lists every parameter (except `self`/`cls`) with a description.
- [ ] **Returns section** describes the return value's shape and semantics (not just the type).
- [ ] **Raises section** lists every explicitly raised exception.
- [ ] **No filler phrases**: no "This function is responsible for...", "This method basically...", "This class is used to...".
- [ ] **No signature restating**: the docstring adds information beyond what the signature already says.
- [ ] **Summary line is imperative mood**, ends with a period.
- [ ] **Descriptions are specific to the domain**, naming concrete objects, formats, or constraints rather than generic placeholders.
