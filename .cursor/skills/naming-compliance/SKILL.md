---
name: naming-compliance
description: >-
  Enforce meaningful, readable names for all Python identifiers (variables,
  functions, methods, classes, parameters, constants). Rejects single-letter
  names and cryptic abbreviations. Use when writing, editing, or reviewing
  Python code, when the user mentions naming conventions, readability, or
  code clarity, or when adding new functions, classes, or variables.
disable-model-invocation: true
---

# Naming Compliance

## Core Rule

All identifiers — variables, functions, methods, classes, parameters, and constants — must be self-descriptive. A reader must understand what the name refers to without reading surrounding code.

## Prohibited Patterns

### Single-letter names

Names of 1 character are banned except in the allowed exceptions list below.

### Ultra-short names (2 characters)

Names of 2 characters are banned unless they are a well-known domain term (e.g., `id`, `df` in pandas-heavy code where `DataFrame` context is unambiguous).

### Cryptic abbreviations

Do not use shortened forms that require mental decoding:

| Banned       | Use instead              |
|--------------|--------------------------|
| `proc`       | `process` or `processor` |
| `mgr`        | `manager`                |
| `cfg`        | `config` or `configuration` |
| `val`        | `value` or the specific thing it holds |
| `tmp`        | `temporary_file` or the specific thing |
| `cnt`        | `count` or `counter`     |
| `buf`        | `buffer`                 |
| `ctx`        | `context`                |
| `msg`        | `message`                |
| `req`        | `request`                |
| `res`        | `response` or `result`   |
| `cb`         | `callback`               |
| `fn`         | `function` or the specific callable |
| `idx`        | `index`                  |
| `num`        | `number` or `count`      |
| `src`        | `source`                 |
| `dst`        | `destination`            |
| `args`       | acceptable (stdlib convention) |
| `kwargs`     | acceptable (stdlib convention) |

### Names requiring context to understand

If the name only makes sense because of what's on the previous line, it's too vague. Each name must carry its own meaning.

## Allowed Exceptions

These specific patterns are permitted:

| Pattern | Context | Rationale |
|---------|---------|-----------|
| `i`, `j`, `k` | Numeric loop index in trivial loops (`for i in range(n)`) | Universal convention, always an integer index |
| `e` | `except SomeError as e` | Universal exception-binding convention |
| `_` | Throwaway value (`for _, value in pairs`) | Python convention for unused bindings |
| `x`, `y`, `z` | Mathematical/coordinate computations where these are domain terms | Standard mathematical notation |
| `n` | A count passed to `range()` or similar when immediately obvious | Only in tight numeric scope |
| `f` | File handle in `with open(...) as f` when the block is ≤5 lines | Common but only in trivially short blocks |
| `T` | TypeVar declaration (`T = TypeVar("T")`) | Typing convention |
| `self`, `cls` | Method parameters | Language convention |
| `args`, `kwargs` | Variadic parameters | Language convention |
| `df` | pandas DataFrame in data-analysis code where context is unambiguous | Domain convention, but prefer descriptive names like `papers_df` |

## Good / Bad Examples

### Example 1: Function signature

```python
# BAD
def proc_f(d, n):
    for i in d:
        if i > n:
            return True
    return False
```

```python
# GOOD
def has_value_above_threshold(data_points, threshold):
    for data_point in data_points:
        if data_point > threshold:
            return True
    return False
```

### Example 2: Variable assignments

```python
# BAD
r = requests.get(url)
j = r.json()
t = j["title"]
a = j["authors"]
```

```python
# GOOD
response = requests.get(url)
paper_metadata = response.json()
paper_title = paper_metadata["title"]
author_list = paper_metadata["authors"]
```

### Example 3: Class and method names

```python
# BAD
class PProc:
    def run_q(self, q, lim):
        pass
```

```python
# GOOD
class PaperProcessor:
    def run_query(self, search_query, result_limit):
        pass
```

### Example 4: Constants and module-level names

```python
# BAD
MAX_R = 100
DEF_T = 30
FMT = "%Y-%m-%d"

# GOOD
MAX_RETRY_ATTEMPTS = 100
DEFAULT_TIMEOUT_SECONDS = 30
DATE_FORMAT = "%Y-%m-%d"
```

## Validation Checklist

After writing or editing code, verify against this list:

- [ ] **No single-letter variables** outside the allowed exceptions.
- [ ] **No 2-character names** unless they are recognized domain terms.
- [ ] **No cryptic abbreviations** from the prohibited list above.
- [ ] **Function names describe the action** — verb + object (`fetch_papers`, `validate_config`).
- [ ] **Variable names describe the content** — noun or adjective + noun (`paper_count`, `active_connections`).
- [ ] **Class names describe the entity** — noun or adjective + noun (`PaperProcessor`, `DatabaseConnection`).
- [ ] **Parameter names describe what's passed in** — not generic (`query` vs `q`, `max_results` vs `n`).
- [ ] **Loop variables are descriptive** when iterating over domain objects (`for paper in papers`, not `for p in papers`).
- [ ] **Boolean names read as predicates** — `is_valid`, `has_results`, `should_retry`, not `flag` or `status`.
- [ ] **Names are greppable** — unique enough that searching the codebase for them finds relevant hits.
