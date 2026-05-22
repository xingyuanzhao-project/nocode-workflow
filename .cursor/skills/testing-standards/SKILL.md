---
name: testing-standards
description: >-
  Enforce rigorous, authentic test quality standards. Prohibits superficial
  tests (import-only, existence checks, no-assertion smoke tests) and requires
  real end-to-end validation with cost-aware resource usage. Use when writing,
  reviewing, or generating test code, when the agent creates test files, or
  when the user mentions test quality, test authenticity, or fake tests.
disable-model-invocation: true
---

# Testing Standards

## Test Authenticity Rules

1. Tests must exercise the **real code path** — the same entry points, initialization, and control flow used in production.
2. The test's control flow must match production usage; simplified re-implementations of the system under test are not tests.
3. Importing a module and asserting it exists is **not** a test.
4. Calling a function with no assertions beyond "it didn't crash" is **not** a test.
5. Tests must validate **actual outputs**, **state changes**, or **observable side effects**.
6. If the code under test produces a result, the test must assert properties of that result against expected values.

## Test vs Fake-Test Taxonomy

| Category | Fake test (prohibited) | Real test (required) |
|----------|------------------------|----------------------|
| Import check | Imports a module, asserts the module object is truthy | Calls a function from the module with representative inputs, asserts output matches expected |
| Smoke test | Instantiates a class, asserts `is not None` | Instantiates with production-representative config, exercises key methods, validates return values or state |
| Integration | Mocks every external dependency and tests glue code in isolation | Uses real dependencies (or faithful test doubles that preserve interface contracts) through the real entry point |
| Pipeline | Runs pipeline, checks output file exists | Runs pipeline on known input, validates output content against expected values |
| API/service | Sends request, checks status == 200 | Sends request with known payload, validates response body structure and values |

## Resource-Cost Discipline

1. When tests require paid resources (API calls, cloud services, GPU compute, metered endpoints), prefer the **cheapest viable alternative** that preserves test logic.
2. "Cheap resource consumption does not equal cheap test" — a test can use fewer resources while remaining rigorous. The logic, assertions, and coverage must stay identical; only the scale or tier changes.
3. Preference order for cost reduction:
   - Use a cheaper tier of the same service (e.g., dev-tier API, smaller model variant, free sandbox)
   - Use a local faithful substitute (local server, in-memory database, recorded responses with contract verification)
   - Reduce batch size to a small representative sample while preserving full pipeline logic
4. If no cheaper option is obvious, test on a **small representative batch** but preserve the full pipeline logic end-to-end.
5. **Never sacrifice test logic or assertion coverage to save cost.** Only reduce scale or substitute equivalent resources.
6. If the user provides a specific cheaper alternative to use in tests, use that alternative.

## Exhaustiveness Guidance

1. Cover the **happy path** (expected inputs produce expected outputs).
2. Cover **error paths** (invalid inputs, missing dependencies, network failures raise appropriate errors or return appropriate fallbacks).
3. Cover **edge cases** (empty inputs, maximum-size inputs, boundary values, unicode, special characters where relevant).
4. Cover **boundary conditions** (off-by-one, zero-length, single-element, type boundaries).
5. Integration tests should exercise the **full pipeline** from input to final output, verifying intermediate results at stage boundaries — not just the final artifact.
6. When testing a multi-stage system, assert on intermediate state between stages, not only on the terminal output.

## Anti-Patterns (Prohibited)

### Import-only test

```python
def test_module():
    import mymodule  # No call, no assertion on behavior
```

Why prohibited: proves the file is importable, nothing about correctness.

### Existence-only assertion

```python
def test_class():
    obj = MyClass()
    assert obj is not None
```

Why prohibited: any class that doesn't raise in `__init__` passes this. Tests zero behavior.

### Crash-absence test

```python
def test_pipeline():
    run_pipeline(data)
    # no assertions — "it didn't crash" is the only signal
```

Why prohibited: a pipeline that silently produces garbage passes this test.

### Output-existence-only test

```python
def test_export():
    export_data(records, "output.csv")
    assert os.path.exists("output.csv")
```

Why prohibited: an empty file or corrupted output passes this test.

### Mock-everything integration test

```python
def test_integration(mock_db, mock_api, mock_cache, mock_queue):
    result = service.process(mock_db, mock_api, mock_cache, mock_queue)
    assert result == "ok"
```

Why prohibited: tests the glue code's interaction with mocks, not the system's actual behavior.

## Good Test Patterns (Required)

### Data pipeline test

```python
def test_pipeline_transforms():
    input_data = [{"name": "Alice", "score": 85}, {"name": "Bob", "score": 92}]
    result = run_pipeline(input_data)

    assert len(result) == 2
    assert result[0]["normalized_score"] == 0.85
    assert result[1]["normalized_score"] == 0.92
    assert all("processed_at" in r for r in result)
```

Why valid: known input, validated output values, checks structure and content.

### API endpoint test

```python
def test_create_item():
    payload = {"title": "Test Item", "quantity": 3}
    response = client.post("/items", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Test Item"
    assert body["quantity"] == 3
    assert "id" in body
```

Why valid: real request through the app, validates response body — not just status code.

### Cost-aware integration test

```python
def test_summarization_pipeline():
    # Use smallest viable model tier and 2-item batch instead of full corpus
    sample_docs = FIXTURE_DOCS[:2]
    results = summarize_batch(sample_docs, model_tier="cheapest")

    assert len(results) == 2
    for doc, summary in zip(sample_docs, results):
        assert len(summary) > 0
        assert len(summary) < len(doc["text"])
        assert summary != doc["text"][:len(summary)]  # Not just a prefix truncation
```

Why valid: full pipeline logic preserved, outputs validated meaningfully, cost reduced via batch size and tier — not via removing assertions.

### Multi-stage verification

```python
def test_etl_stages():
    raw = load_raw(FIXTURE_PATH)
    assert len(raw) == 10
    assert "timestamp" in raw.columns

    cleaned = clean_stage(raw)
    assert cleaned["timestamp"].isna().sum() == 0
    assert len(cleaned) <= len(raw)

    enriched = enrich_stage(cleaned)
    assert "derived_metric" in enriched.columns
    assert enriched["derived_metric"].notna().all()
```

Why valid: verifies each stage independently, catches regressions at the stage boundary where they originate.

### Error-path test

```python
def test_invalid_input_raises():
    with pytest.raises(ValueError, match="must be positive"):
        compute_score(value=-1)

def test_missing_dependency_fallback():
    result = fetch_with_fallback(url="http://unreachable.invalid")
    assert result == DEFAULT_FALLBACK_VALUE
```

Why valid: tests error behavior explicitly, asserts on the specific error or fallback — not just "something happened."

## Checklist Before Marking a Test Complete

1. Does every test function contain at least one `assert` on a **computed value or observable effect**?
2. Does the test use **representative inputs** (not empty, not trivial single-element unless testing that edge)?
3. Are assertions checking **content/values**, not just existence or type?
4. If paid resources are involved, is the cheapest viable alternative being used?
5. Is the control flow identical to production (same entry point, same initialization)?
6. For multi-stage code, are intermediate results verified — not just the terminal output?
