# Known Issues


## 2. Taxonomy/Codebook Naming Inconsistency

**Status:** Open  
**Affected:** Codebase-wide naming confusion

**Problem:**  
The codebase uses two names for the same concept:
- "taxonomy" — used in `FlowConfig.taxonomy`, `taxonomy://` URI scheme, `taxonomy_selected_keys`, `_build_taxonomy_path()`, `server/services/__init__.py` docstring reference to `taxonomy_repository`
- "codebook" — used in the actual service file (`server/services/codebook_repository.py`), GUI labels, node type (`codebook`), edge type (`codebook_inquiry`), `codebooks/` directory

The `taxonomy://` URI scheme is embedded in saved workflow YAMLs and resolved at runtime by `flow_builder.build_flow` and `server/workers/flow_task.py`. The GUI and all user-facing surfaces use "codebook."

**Suggested fix:**  
Rename all internal references from "taxonomy" to "codebook":
- `FlowConfig.taxonomy` → `FlowConfig.codebook_path`
- `FlowConfig.taxonomy_selected_keys` → `FlowConfig.codebook_selected_keys`
- `taxonomy://` URI scheme → `codebook://`
- `_build_taxonomy_path()` → `_build_codebook_path()`
- `validate_taxonomy_and_prompt_paths()` → `validate_codebook_and_prompt_paths()`
- `server/services/__init__.py` docstring reference

Migration: Add a backward-compat shim that recognizes `taxonomy://` in existing saved YAMLs and treats it as `codebook://`.

**Files involved:**
- `src/flow_loader.py` — `FlowConfig` class, `_build_taxonomy_path`, validator
- `src/flow_builder.py` — taxonomy resolution at runtime
- `server/workers/flow_task.py` — taxonomy URI resolution
- `server/storage/paths.py` — docstring reference
- `server/services/__init__.py` — docstring reference
