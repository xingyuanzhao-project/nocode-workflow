"""Loader for MessyText configuration-driven flow YAML files.

The flow editor was rebuilt around an explicit graph: every YAML under
``server/data/flows/`` now stores ``flow.nodes[]`` and ``flow.edges[]``
directly. This module reads such a YAML, validates it as a
:class:`FlowDocument`, and *compiles* it into the runtime
:class:`FlowConfig` shape that :mod:`src.flow_builder` consumes.

Compilation walks the graph:

- The single ``csv_input`` / ``json_input`` node becomes the
  :class:`DataConfig`.
- The single ``csv_output`` / ``json_output`` node becomes the
  :class:`OutputConfig`.
- Processor execution order comes from a topological sort over
  ``feedforward`` edges (``csv_input → ... → csv_output``).
- Each processor's LLM resource comes from following its ``llm_call``
  edge to the ``llm_call`` target node and reading its config.
- Each processor's codebook (taxonomy) comes from following its
  ``codebook_inquiry`` edge to the ``codebook`` target node and reading
  its config.

The Pydantic models declared here split into two layers:

- *Graph schema* — :class:`NodeEntry`, :class:`EdgeEntry`,
  :class:`FlowSettings`, :class:`FlowDocument`. Validates the on-disk
  YAML before any compilation runs.
- *Runtime schema* — :class:`FlowConfig`, :class:`LLMResource`,
  :class:`DataConfig`, :class:`ProcessorConfig`, :class:`OutputConfig`,
  :class:`LoggingConfig`, :class:`DisplayConfig`, :class:`AsyncConfig`.
  The compiler builds these programmatically;
  :class:`FlowConfig` is the only object :mod:`src.flow_builder` reads.

Contents and relationships
--------------------------

- :class:`FlowSchema` — top-level envelope matching the YAML file. Wraps
  the parsed :class:`FlowDocument` and the compiled :class:`FlowConfig`.
  Exposes :meth:`FlowSchema.load_from_path` which reads the YAML, parses
  it as a :class:`FlowDocument`, runs the graph compiler, and returns
  the validated schema.
- :class:`FlowDocument` — the new ``flow:`` block: ``name``,
  ``description``, ``nodes[]``, ``edges[]``, and ``settings``.
- :class:`NodeEntry` — per-node ``{ id, type, position?, config }`` entry.
- :class:`EdgeEntry` — per-edge ``{ type, source, target }`` entry.
- :class:`FlowSettings` — flow-level settings block: ``processing_limit``,
  ``async``, ``logging``, ``display``, plus an optional ``prompts`` path.
- :class:`FlowConfig` — runtime form derived from the graph. Holds
  metadata, LLM resources, data source, taxonomy and prompt paths,
  ordered pipeline steps, async settings, output paths, logging, and
  display options.
- :class:`LLMResource` — one named LLM provider entry under
  ``flow.resources[*]``. Each resource is addressable by ``id`` and is
  referenced by :attr:`ProcessorConfig.llm` when a processor needs a non-default LLM.
- (Removed) ``LLMShorthand`` — was the single-LLM sugar block for the
  old flat format. No code path produces it in the node-edge schema.
- :class:`DataConfig` — the ``flow.data:`` block pointing at the input
  data file.
- :class:`ProcessorConfig` — one processor in the pipeline. ``type``
  selects the runtime behaviour; the set of accepted values is sourced
  from the :mod:`src.node_registry` registry (``config/node_types.yaml``)
  rather than from a hardcoded list.
- :class:`AsyncConfig`, :class:`OutputConfig`, :class:`LoggingConfig`, and
  :class:`DisplayConfig` — the remaining runtime sections that control
  concurrency, where results are written, what is logged, and whether
  progress bars are shown.

How the rest of the system uses this module
-------------------------------------------

:func:`src.flow_builder.build_flow` calls
:meth:`FlowSchema.load_from_path` to obtain a validated schema, then walks
:attr:`FlowConfig.resources` to construct OpenAI-compatible clients, walks
:attr:`FlowConfig.processors` to instantiate processor classes from
:mod:`src.processors`, and uses :attr:`FlowConfig.data`,
:attr:`FlowConfig.async_config`, and :attr:`FlowConfig.output` to drive the
runner loops.

Invariants enforced by this module
----------------------------------

- At least one :class:`LLMResource` exists after normalisation, and every
  resource has a unique ``id``.
- Every :attr:`ProcessorConfig.llm` string resolves to an existing resource
  ``id``. Processors that omit ``llm`` are wired to the resource with
  ``id = "default"`` by the builder.
- :attr:`ProcessorConfig.type` is one of the ids whose ``category`` is
  ``processor`` in :mod:`src.node_registry`'s default registry.
- :attr:`ProcessorConfig.unit` must be ``"row"``.
- Inline :attr:`ProcessorConfig.prompt` and
  :attr:`ProcessorConfig.prompts_ref` are mutually exclusive;
  :attr:`ProcessorConfig.prompt_overrides` requires
  :attr:`ProcessorConfig.prompts_ref`.
- :attr:`LLMResource.api_key_env` and :attr:`LLMResource.api_key` are
  mutually exclusive in the YAML: the builder resolves ``api_key_env``
  against ``os.environ`` at startup and the runtime copy of the resource
  ends up with ``api_key`` populated.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Literal, Optional, Tuple

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from src.io_schema import IOSchema
from src.node_registry import get_processor_types
from src.prompt_resolver import PromptInline, PromptOverride


def _registered_processor_types() -> FrozenSet[str]:
    """Return the registered processor type ids from the default registry.

    Returns:
        FrozenSet[str]: The processor type ids declared in
        :mod:`src.node_registry`'s default registry.
    """
    return get_processor_types()


UNIT_VALUES: frozenset[str] = frozenset({"row"})
"""Registered ``unit`` values accepted by :class:`ProcessorConfig`."""

VALID_ADJACENT_UNIT_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {("row", "row")}
)
"""Valid (prev_unit, next_unit) pairs for adjacent processors."""


SUPPORTED_INPUT_EXTENSIONS: frozenset[str] = frozenset({".csv", ".json", ".jsonl"})
"""File extensions accepted by :attr:`DataConfig.input_csv`.

The flow builder dispatches to the appropriate pandas reader based on the
extension: ``.csv`` → :func:`pandas.read_csv`, ``.json`` →
:func:`pandas.read_json` (records), ``.jsonl`` →
:func:`pandas.read_json` (lines)."""


PROVIDER_VALUES: frozenset[str] = frozenset({
    "openrouter", "openai", "claude", "google",
    "ollama", "vllm", "llama_cpp",
})
"""Registered provider values accepted by :class:`LLMResource`.

Cloud providers (``openrouter``, ``openai``, ``claude``, ``google``)
require a real API key via ``api_key_env``. Local providers
(``ollama``, ``vllm``, ``llama_cpp``) default to ``"dummy"`` when no
key is set."""




"""Well-known ``api_base`` URLs for cloud providers only.

Local providers (``ollama``, ``vllm``, ``llama_cpp``) are excluded —
their endpoint is resolved exclusively from the environment variable
set by the API Keys page."""

LOCAL_PROVIDERS: frozenset[str] = frozenset({
    "ollama", "vllm", "llama_cpp",
})
"""Providers that run on localhost and don't require a real API key."""


def _validate_project_relative_posix_path(value: str, field_name: str) -> str:
    """Reject path strings that would break host/container portability.

    Every file-path field in a flow YAML (``input_csv``, ``output.*_csv``,
    ``logging.file``, ``taxonomy``, ``prompts``) must be
    *project-root-relative* and written with POSIX forward slashes so
    that the FastAPI web process and the Celery worker container, which
    may run on different operating systems during development but always
    share the project root as their working directory, resolve the same
    string to the same absolute path.

    Rejected patterns:

    - Leading ``/`` (POSIX absolute path).
    - Windows drive letter prefix such as ``C:``.
    - Backslash separators (``\\``).
    - Empty string after stripping.

    Args:
        value (str): The raw string as read from the YAML.
        field_name (str): Name of the field being validated, used only
            for error messages.

    Returns:
        str: ``value`` unchanged.

    Raises:
        ValueError: If ``value`` violates any of the rules above.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    if "\\" in value:
        raise ValueError(
            f"{field_name}={value!r} contains a backslash; "
            "use forward slashes so the path is portable between the "
            "Windows host and the Linux worker container."
        )
    if value.startswith("/"):
        raise ValueError(
            f"{field_name}={value!r} is absolute; "
            "flow paths must be project-root-relative so both the web "
            "process and the worker container resolve them consistently."
        )
    if len(value) >= 2 and value[1] == ":":
        raise ValueError(
            f"{field_name}={value!r} has a Windows drive letter prefix; "
            "flow paths must be project-root-relative POSIX strings "
            "(for example 'data/input.csv')."
        )
    return value


class LLMResource(BaseModel):
    """One named LLM provider entry addressable by :attr:`id`.

    A resource describes a single OpenAI-compatible endpoint plus the
    generation parameters that :class:`src.processors.AsyncMessyTextProcessor`
    reads from its runtime config dict. The builder constructs one
    ``AsyncOpenAI`` client per resource and wires each step to the client
    whose resource ``id`` the step references.

    Attributes:
        id (str): Unique identifier referenced by
            :attr:`ProcessorConfig.llm`.
        type (Literal["llm_provider"]): Discriminator kept for future
            resource kinds. Always ``"llm_provider"`` in Phase 1.
        provider (str): One of :data:`PROVIDER_VALUES`.
        model (str): Model identifier sent to the endpoint as
            ``chat.completions.create(model=...)``.
        api_base (Optional[str]): OpenAI-compatible base URL. Defaults to
            the provider-specific base URL when omitted.
        api_key (Optional[str]): Literal API key. Local providers use
            ``"dummy"`` by default. For hosted providers, use
            :attr:`api_key_env` instead.
        api_key_env (Optional[str]): Name of the environment variable that
            holds the real API key. Resolved by the builder from the
            project-root ``.env`` file. Mutually exclusive with
            :attr:`api_key`.
        temperature (float): Temperature forwarded to every LLM call
            produced against this resource.

    Methods:
        validate_provider: Ensure :attr:`provider` is a registered value.
        validate_api_key_shape: Ensure ``api_key`` and ``api_key_env`` are
            not both set at the same time.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    type: Literal["llm_provider"] = "llm_provider"
    provider: str
    model: str
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None
    temperature: float = 0.0

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, provider_value: str) -> str:
        """Ensure the provider value is one registered in :data:`PROVIDER_VALUES`.

        Args:
            provider_value (str): The raw provider string as read from YAML.

        Returns:
            str: The provider value, unchanged.

        Raises:
            ValueError: If ``provider_value`` is not in
                :data:`PROVIDER_VALUES`.
        """
        if provider_value not in PROVIDER_VALUES:
            raise ValueError(
                f"provider must be one of {sorted(PROVIDER_VALUES)}; "
                f"got {provider_value!r}"
            )
        return provider_value

    @model_validator(mode="after")
    def validate_api_key_shape(self) -> "LLMResource":
        """Disallow declaring both :attr:`api_key` and :attr:`api_key_env`.

        Returns:
            LLMResource: The same instance, unchanged.

        Raises:
            ValueError: If both ``api_key`` and ``api_key_env`` are set.
        """
        if self.api_key is not None and self.api_key_env is not None:
            raise ValueError(
                f"Resource {self.id!r} declares both api_key and api_key_env; "
                "use exactly one. For hosted providers prefer api_key_env so "
                "the secret stays in .env."
            )
        return self




class DataConfig(BaseModel):
    """``flow.data:`` block: input data file path.

    Attributes:
        input_csv (str): Project-root-relative POSIX path to the input
            data file. Accepts ``.csv``, ``.json``, and ``.jsonl``
            extensions. The YAML key may also be written as
            ``input_file`` for clarity when using non-CSV formats;
            both keys map to this attribute. Validated by
            :func:`_validate_project_relative_posix_path` so the same
            string resolves to the same file in the FastAPI web
            process and the Celery worker container.

    Methods:
        validate_input_file_path: Enforce the project-root-relative
            POSIX convention and supported file extension on
            :attr:`input_csv`.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    input_csv: str = Field(
        validation_alias=AliasChoices("input_csv", "input_file"),
    )

    @field_validator("input_csv")
    @classmethod
    def validate_input_file_path(cls, input_path: str) -> str:
        """Enforce the project-root-relative POSIX convention and file extension.

        Args:
            input_path (str): Raw value as read from YAML.

        Returns:
            str: ``input_path`` unchanged.

        Raises:
            ValueError: If the path is absolute, empty, contains
                backslashes, begins with a Windows drive letter, or
                has an unsupported file extension.
        """
        validated = _validate_project_relative_posix_path(input_path, "data.input_csv")
        extension = Path(validated).suffix.lower()
        if extension not in SUPPORTED_INPUT_EXTENSIONS:
            raise ValueError(
                f"data.input_csv={validated!r} has extension {extension!r}; "
                f"supported extensions are {sorted(SUPPORTED_INPUT_EXTENSIONS)}"
            )
        return validated


class ProcessorConfig(BaseModel):
    """One processor in :attr:`FlowConfig.processors`.

    ``type`` selects the runtime behaviour. Accepted values are the ids
    whose category is ``processor`` in :mod:`src.node_registry`'s
    default registry (``config/node_types.yaml``). The registry also
    supplies each processor's default I/O schema and default prompt
    reference; users override those per processor through the optional
    :attr:`io_schema`, :attr:`prompt`, :attr:`prompts_ref`, and
    :attr:`prompt_overrides` fields.

    Attributes:
        type (str): Registered processor type id. Looked up in
            :mod:`src.node_registry`.
        unit (str): Always ``"row"``.
        group_by (Optional[str]): Deprecated, ignored.
        llm (Optional[str]): Resource ``id`` this processor uses. ``None``
            means the builder wires it to the resource with
            ``id = "default"``.
        mode (Optional[str]): Reserved for future use.
        keys (Optional[Any]): Reserved for future use.
        io_schema (Optional[IOSchema]): Per-processor override of the LLM
            I/O schema. When set, :mod:`src.flow_builder` converts its
            ``output`` dict into the OpenAI ``response_format`` via
            :func:`src.io_schema.to_response_format` and bypasses the
            registry default for this processor only.
        prompts_ref (Optional[str]): Pointer into the flow-level
            ``config/prompts.json``. Accepts both the bare-key form
            (``"summary"``) and the path-qualified form
            (``"config/prompts.json::summary"``). Used by
            :func:`src.prompt_resolver.resolve_step_prompt` to look up
            the base instruction list and ``output_format``.
        prompt (Optional[PromptInline]): Inline prompt block that
            fully replaces any referenced base. Mutually exclusive with
            :attr:`prompts_ref`.
        prompt_overrides (Optional[PromptOverride]): Append / prepend /
            replace directives applied on top of the :attr:`prompts_ref`
            base. Requires :attr:`prompts_ref` to be set.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    unit: str = "row"
    group_by: Optional[str] = None  # deprecated, ignored
    llm: Optional[str] = None
    mode: Optional[str] = None
    keys: Optional[Any] = None
    io_schema: Optional[IOSchema] = None
    prompts_ref: Optional[str] = None
    prompt: Optional[PromptInline] = None
    prompt_overrides: Optional[PromptOverride] = None
    has_codebook: bool = False

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        """Ensure the type is a registered processor type id.

        Raises:
            ValueError: If the type is not registered in
                :mod:`src.node_registry`.
        """
        registered = _registered_processor_types()
        if value not in registered:
            raise ValueError(
                f"processor type must be one of {sorted(registered)}; "
                f"got {value!r}. Registered processor types come from "
                "config/node_types.yaml via src/node_registry.py."
            )
        return value

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, unit_value: str) -> str:
        """Ensure the unit is one of :data:`UNIT_VALUES`."""
        if unit_value not in UNIT_VALUES:
            raise ValueError(
                f"unit must be one of {sorted(UNIT_VALUES)}; "
                f"got {unit_value!r}"
            )
        return unit_value

    @model_validator(mode="after")
    def validate_prompt_sources(self) -> "ProcessorConfig":
        """Enforce mutual-exclusion rules for the prompt fields."""
        if self.prompt is not None and self.prompts_ref is not None:
            raise ValueError(
                f"Processor (type={self.type!r}) sets both inline 'prompt' and "
                "'prompts_ref'. Use exactly one: inline for a full override, "
                "prompts_ref for a reference (with optional prompt_overrides)."
            )
        if self.prompt_overrides is not None and self.prompts_ref is None:
            raise ValueError(
                f"Processor (type={self.type!r}) sets 'prompt_overrides' without "
                "'prompts_ref'. Overrides apply on top of a reference; remove "
                "prompt_overrides or add prompts_ref."
            )
        return self


StepConfig = ProcessorConfig
"""Backward-compatible alias. Prefer :class:`ProcessorConfig`."""


class AsyncConfig(BaseModel):
    """``flow.async:`` block: concurrency and retry settings.

    Attributes:
        enabled (bool): When ``True`` the runner uses the async code path;
            otherwise the synchronous path is used.
        max_concurrent_rows (int): Upper bound on concurrent entity-level
            or row-level tasks. Matches ``max_concurrent_rows`` used by
            the existing scripts.
        max_concurrent_llm_calls (int): Upper bound on simultaneous
            in-flight LLM requests. Passed as an ``asyncio.Semaphore`` to
            every processor constructor that accepts ``llm_semaphore``.
        max_retries (int): Passed to ``AsyncOpenAI(max_retries=...)``.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_concurrent_rows: int = 15
    max_concurrent_llm_calls: int = 50
    max_retries: int = 5


class OutputConfig(BaseModel):
    """``flow.output:`` block: where runner results are written.

    Attributes:
        summary_csv (str): Project-root-relative POSIX path for the
            output CSV/JSON file.
        extend (bool): When ``True`` the writer appends to existing files
            while replacing rows for the current model.

    Methods:
        validate_csv_paths: Enforce the project-root-relative POSIX
            convention on the output path.
    """

    model_config = ConfigDict(extra="forbid")

    summary_csv: str
    results_csv: Optional[str] = None
    states_csv: Optional[str] = None
    spans_csv: Optional[str] = None
    extend: bool = False

    @field_validator("summary_csv", "results_csv", "states_csv", "spans_csv")
    @classmethod
    def validate_csv_paths(cls, value: Optional[str], info) -> Optional[str]:
        """Enforce the project-root-relative POSIX convention.

        Args:
            value (Optional[str]): Raw value as read from YAML. ``None``
                is accepted and returned as-is because every CSV field
                except :attr:`summary_csv` is optional.
            info: Pydantic validation context; ``info.field_name`` is
                used only for error messages.

        Returns:
            Optional[str]: ``value`` unchanged.

        Raises:
            ValueError: If a non-``None`` ``value`` is absolute, empty,
                contains backslashes, or begins with a drive letter.
        """
        if value is None:
            return value
        return _validate_project_relative_posix_path(
            value, f"output.{info.field_name}"
        )


class LoggingConfig(BaseModel):
    """``flow.logging:`` block: logger file path and verbosity flags.

    Attributes:
        file (str): Project-root-relative POSIX path to the log file.
            Validated by
            :func:`_validate_project_relative_posix_path`.
        log_progress (bool): When ``True`` the runner logs per-step
            progress messages.
        log_prompts (bool): When ``True`` processors log every constructed
            prompt.
        log_response (bool): When ``True`` processors log every raw LLM
            response. Matches the flag read by
            :class:`src.processors.AsyncMessyTextConversationTurnProcessor`.

    Methods:
        validate_log_file_path: Enforce the project-root-relative POSIX
            convention on :attr:`file`.
    """

    model_config = ConfigDict(extra="forbid")

    file: str = "processing.log"
    log_progress: bool = True
    log_prompts: bool = False
    log_response: bool = False

    @field_validator("file")
    @classmethod
    def validate_log_file_path(cls, file_path: str) -> str:
        """Enforce the project-root-relative POSIX convention.

        Args:
            file_path (str): Raw value as read from YAML.

        Returns:
            str: ``file_path`` unchanged.

        Raises:
            ValueError: If the path is absolute, empty, contains
                backslashes, or begins with a Windows drive letter.
        """
        return _validate_project_relative_posix_path(file_path, "logging.file")


class DisplayConfig(BaseModel):
    """``flow.display:`` block: user-visible progress options.

    Attributes:
        use_progress_bar (bool): When ``True`` the runner shows tqdm
            progress bars during processing.
    """

    model_config = ConfigDict(extra="forbid")

    use_progress_bar: bool = True


class FlowConfig(BaseModel):
    """Runtime view of a flow, derived from a :class:`FlowDocument`.

    The flow YAML stores nodes and edges. The graph compiler in
    :func:`compile_flow_document_to_runtime` walks the parsed
    :class:`FlowDocument` and constructs an instance of this class so
    :mod:`src.flow_builder` can read ``schema.flow.<field>``.

    Attributes:
        schema_version (int): Always ``1``.
        name (str): Short identifier for the flow.
        description (str): Free-form human-readable description.
        resources (List[LLMResource]): LLM provider entries derived from
            ``llm_call`` nodes targeted by ``llm_call`` edges.
        data (DataConfig): Input data file path, derived from the single
            ``csv_input`` / ``json_input`` node.
        taxonomy (str): Project-root-relative POSIX path or
            ``taxonomy://<id>`` URI to the codebook consumed by the
            processors. Derived from the codebook node targeted by any
            ``codebook_inquiry`` edge in the graph.
        prompts (str): Project-root-relative POSIX path to the prompts
            JSON file consumed by the processors. Comes from
            :attr:`FlowSettings.prompts`.
        processors (List[ProcessorConfig]): Processors in topological
            order derived from feedforward edges.
        processing_limit (Optional[int]): Optional cap on the number of
            entities/rows the runner processes.
        async_config (AsyncConfig): Concurrency settings.
        output (OutputConfig): Output paths derived from the single
            ``csv_output`` / ``json_output`` node.
        logging (LoggingConfig): Logger file and verbosity flags.
        display (DisplayConfig): User-visible progress options.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: int = 1
    name: str
    description: str = ""
    resources: List[LLMResource]
    data: DataConfig
    taxonomy: str = ""
    taxonomy_selected_keys: Optional[List[str]] = None
    prompts: str = "config/prompts.json"
    processors: List[ProcessorConfig] = Field(
        validation_alias=AliasChoices("processors", "steps"),
    )
    processing_limit: Optional[int] = None
    async_config: AsyncConfig = Field(default_factory=AsyncConfig, alias="async")
    output: OutputConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)

    @field_validator("taxonomy", "prompts")
    @classmethod
    def validate_taxonomy_and_prompt_paths(cls, value: str, info) -> str:
        """Enforce the project-root-relative POSIX convention.

        The ``taxonomy`` field also accepts ``taxonomy://<id>`` URIs
        produced by the GUI when the user selects a server-managed
        taxonomy. The URI is resolved at runtime by
        :func:`src.flow_builder.build_flow` or
        :func:`server.workers.flow_task.execute_flow`, not here.

        An empty string is accepted for ``taxonomy`` — it means no
        codebook is connected to any processor in the graph.

        Args:
            value (str): Raw value as read from YAML.
            info: Pydantic validation context; ``info.field_name`` is
                either ``"taxonomy"`` or ``"prompts"``.

        Returns:
            str: ``value`` unchanged.

        Raises:
            ValueError: If the path is absolute, empty (for prompts),
                contains backslashes, or begins with a Windows drive
                letter (unless it is a ``taxonomy://`` URI).
        """
        if info.field_name == "taxonomy" and not value:
            return value
        if info.field_name == "taxonomy" and value.startswith("taxonomy://"):
            if len(value) <= len("taxonomy://"):
                raise ValueError(
                    "taxonomy URI has no id after 'taxonomy://'"
                )
            return value
        return _validate_project_relative_posix_path(value, info.field_name)

    @model_validator(mode="after")
    def validate_resources(self) -> "FlowConfig":
        """Enforce unique resource ids and resolvable processor.llm references."""
        seen_ids: set[str] = set()
        for resource in self.resources:
            if resource.id in seen_ids:
                raise ValueError(
                    f"Duplicate LLM resource id: {resource.id!r}. "
                    "Every resource must have a unique id."
                )
            seen_ids.add(resource.id)

        if not self.resources:
            raise ValueError(
                "At least one LLM resource must be declared."
            )

        for idx, proc in enumerate(self.processors):
            if proc.llm is not None and proc.llm not in seen_ids:
                raise ValueError(
                    f"Processor {idx} (type={proc.type!r}) references "
                    f"llm={proc.llm!r}, which is not among the declared "
                    f"resource ids: {sorted(seen_ids)}"
                )
        return self

    @model_validator(mode="after")
    def validate_processors_non_empty(self) -> "FlowConfig":
        """Reject a flow with zero processors."""
        if not self.processors:
            raise ValueError("flow.processors must contain at least one processor.")
        return self

    @property
    def steps(self) -> List[ProcessorConfig]:
        """Backward-compatible alias for :attr:`processors`."""
        return self.processors



@dataclass
class ScheduledNode:
    """One processor node in the execution plan, paired with its graph connectivity.

    The compiler derives ``input_from`` from feedforward edges.
    The runner uses it to determine when this node is ready and
    which results to pass as input.
    """

    node_id: str
    config: ProcessorConfig
    input_from: List[str]


@dataclass
class ScheduledOutput:
    """One output node in the execution plan, paired with its graph connectivity.

    ``input_from`` lists the processor (or data-input) node IDs whose
    results this output node writes to disk. ``output_fields`` controls
    which result fields appear in the written file.
    """

    node_id: str
    config: OutputConfig
    input_from: List[str]
    output_fields: List[str]


@dataclass
class ExecutionPlan:
    """Graph-aware execution plan computed from feedforward edges.

    Produced by :func:`compile_flow_document_to_runtime` alongside the
    :class:`FlowConfig`. The runner consumes this to dispatch processors
    in readiness order and write outputs per-node.
    """

    data_input_node_id: str
    processors: List[ScheduledNode]
    outputs: List[ScheduledOutput]
    warnings: List[str] = dc_field(default_factory=list)


class NodeEntry(BaseModel):
    """One ``flow.nodes[*]`` entry from the new graph YAML.

    Attributes:
        id (str): Stable identifier referenced by edges.
        type (str): Discriminator (``csv_input``, ``json_input``,
            ``processor``, ``llm_call``, ``codebook``, ``csv_output``,
            ``json_output``).
        position (Optional[Dict[str, float]]): Optional canvas position
            preserved across save/load.
        config (Dict[str, Any]): Per-node configuration. Schema depends
            on :attr:`type` and is validated during graph compilation.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    position: Optional[Dict[str, float]] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class EdgeEntry(BaseModel):
    """One ``flow.edges[*]`` entry from the new graph YAML.

    Attributes:
        type (str): Discriminator (``feedforward``, ``llm_call``,
            ``codebook_inquiry``).
        source (str): Source :attr:`NodeEntry.id`.
        target (str): Target :attr:`NodeEntry.id`.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    source: str
    target: str


class FlowSettings(BaseModel):
    """The ``flow.settings:`` block.

    Attributes:
        processing_limit (Optional[int]): Optional cap on entities/rows.
        async_config (AsyncConfig): Concurrency settings; aliased as
            ``async`` in YAML.
        logging (LoggingConfig): Logger file and verbosity flags.
        display (DisplayConfig): User-visible progress options.
        prompts (str): Project-root-relative POSIX path to the prompts
            JSON file consumed by the processors. Defaults to
            ``config/prompts.json``.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    processing_limit: Optional[int] = None
    async_config: AsyncConfig = Field(default_factory=AsyncConfig, alias="async")
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    prompts: str = "config/prompts.json"


class FlowDocument(BaseModel):
    """The new ``flow:`` block: explicit graph + settings.

    Attributes:
        name (str): Short identifier for the flow.
        description (str): Free-form description.
        nodes (List[NodeEntry]): Every node placed on the canvas.
        edges (List[EdgeEntry]): Every relationship the user drew. The
            graph compiler walks these to derive execution order and
            wire LLM / codebook resources to processors.
        settings (FlowSettings): Flow-level settings block.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    nodes: List[NodeEntry]
    edges: List[EdgeEntry]
    settings: FlowSettings = Field(default_factory=FlowSettings)


# ---- Graph compilation -------------------------------------------------


_DATA_INPUT_TYPES: FrozenSet[str] = frozenset({"csv_input", "json_input"})
_DATA_OUTPUT_TYPES: FrozenSet[str] = frozenset({"csv_output", "json_output"})


def _exactly_one(
    nodes: List[NodeEntry], allowed_types: FrozenSet[str], role: str
) -> NodeEntry:
    """Return the single node whose ``type`` is in ``allowed_types``.

    Raises:
        ValueError: If zero or more than one such node exists.
    """
    matches = [node for node in nodes if node.type in allowed_types]
    if len(matches) == 0:
        raise ValueError(
            f"Flow has no {role} node "
            f"(expected one of {sorted(allowed_types)})."
        )
    if len(matches) > 1:
        raise ValueError(
            f"Flow has {len(matches)} {role} nodes; exactly one is required."
        )
    return matches[0]


def _index_nodes_by_id(nodes: List[NodeEntry]) -> Dict[str, NodeEntry]:
    """Build an ``id → NodeEntry`` map and reject duplicate ids."""
    index: Dict[str, NodeEntry] = {}
    for node in nodes:
        if node.id in index:
            raise ValueError(
                f"Duplicate node id {node.id!r} in flow.nodes."
            )
        index[node.id] = node
    return index


def _topo_sort_processors(
    document: FlowDocument, node_index: Dict[str, NodeEntry]
) -> List[str]:
    """Return processor node ids in feedforward execution order.

    Builds a directed graph from ``feedforward`` edges and returns the
    processors visited by a Kahn topological walk that starts from the
    data input node. Non-processor nodes (input, output) are excluded
    from the result; they are handled by the data and output config
    builders separately.
    """
    feedforward_targets: Dict[str, List[str]] = {node.id: [] for node in document.nodes}
    in_degree: Dict[str, int] = {node.id: 0 for node in document.nodes}
    for edge in document.edges:
        if edge.type != "feedforward":
            continue
        if edge.source not in node_index or edge.target not in node_index:
            raise ValueError(
                f"Feedforward edge references unknown node id "
                f"({edge.source!r} or {edge.target!r})."
            )
        feedforward_targets[edge.source].append(edge.target)
        in_degree[edge.target] += 1

    queue: List[str] = [
        node.id
        for node in document.nodes
        if in_degree[node.id] == 0 and node.type in _DATA_INPUT_TYPES
    ]
    visited_order: List[str] = []
    while queue:
        node_id = queue.pop(0)
        visited_order.append(node_id)
        for next_id in feedforward_targets[node_id]:
            in_degree[next_id] -= 1
            if in_degree[next_id] == 0:
                queue.append(next_id)

    all_processor_ids = {
        node.id for node in document.nodes if node.type == "processor"
    }
    visited_processor_ids = {
        nid for nid in visited_order if node_index[nid].type == "processor"
    }
    missing = all_processor_ids - visited_processor_ids
    if missing:
        raise ValueError(
            f"Cycle detected among processor nodes: {sorted(missing)}. "
            "These processors form a cycle and cannot be executed in "
            "any valid order. Remove a feedforward edge to break the cycle."
        )

    return [
        node_id
        for node_id in visited_order
        if node_index[node_id].type == "processor"
    ]


def _resolve_llm_resource_for_processor(
    processor_id: str,
    document: FlowDocument,
    node_index: Dict[str, NodeEntry],
) -> Optional[NodeEntry]:
    """Return the ``llm_call`` node targeted by this processor, if any."""
    for edge in document.edges:
        if edge.type != "llm_call":
            continue
        if edge.source != processor_id:
            continue
        target_node = node_index.get(edge.target)
        if target_node is None or target_node.type != "llm_call":
            raise ValueError(
                f"llm_call edge from {processor_id!r} points at "
                f"{edge.target!r}, which is not an llm_call node."
            )
        return target_node
    return None


def _resolve_codebook_for_processor(
    processor_id: str,
    document: FlowDocument,
    node_index: Dict[str, NodeEntry],
) -> Optional[NodeEntry]:
    """Return the ``codebook`` node targeted by this processor, if any."""
    for edge in document.edges:
        if edge.type != "codebook_inquiry":
            continue
        if edge.source != processor_id:
            continue
        target_node = node_index.get(edge.target)
        if target_node is None or target_node.type != "codebook":
            raise ValueError(
                f"codebook_inquiry edge from {processor_id!r} points at "
                f"{edge.target!r}, which is not a codebook node."
            )
        return target_node
    return None


def _build_llm_resource_from_node(node: NodeEntry) -> LLMResource:
    """Build a :class:`LLMResource` from one ``llm_call`` node entry."""
    config = dict(node.config)
    resource_id = str(config.get("resource_id") or node.id)
    raw_provider = config.get("provider")
    if not raw_provider:
        raise ValueError(
            f"LLM node {node.id!r} is missing 'provider'. "
            "Set it to one of: openrouter, openai, claude, google, vllm, ollama, llama_cpp."
        )
    provider = str(raw_provider)
    model = str(config.get("model") or "")
    api_base = config.get("api_base")
    api_key = config.get("api_key")
    api_key_env = config.get("api_key_env")
    temperature = float(config.get("temperature") or 0)

    return LLMResource(
        id=resource_id,
        type="llm_provider",
        provider=provider,
        model=model,
        api_base=api_base if isinstance(api_base, str) and api_base else None,
        api_key=api_key if isinstance(api_key, str) and api_key else None,
        api_key_env=api_key_env
        if isinstance(api_key_env, str) and api_key_env
        else None,
        temperature=temperature,
    )


def _build_data_config_from_node(node: NodeEntry) -> DataConfig:
    """Build a :class:`DataConfig` from one ``csv_input`` / ``json_input`` node."""
    config = dict(node.config)
    selected_file = config.get("selected_file")
    if not isinstance(selected_file, str) or not selected_file:
        raise ValueError(
            f"Data input node {node.id!r} has no selected_file set."
        )

    return DataConfig(input_csv=selected_file)


def _build_output_config_from_node(node: NodeEntry) -> OutputConfig:
    """Build an :class:`OutputConfig` from one ``csv_output`` / ``json_output`` node."""
    config = dict(node.config)
    output_path = config.get("output_path")
    if not isinstance(output_path, str) or not output_path:
        raise ValueError(f"Output node {node.id!r} has no output_path set.")

    extend = bool(config.get("extend"))

    return OutputConfig(
        summary_csv=output_path,
        extend=extend,
    )


def _build_taxonomy_path(node: NodeEntry) -> str:
    """Return the taxonomy URI / path encoded in one ``codebook`` node."""
    config = dict(node.config)
    codebook_id = config.get("codebook_id")
    codebook_path = config.get("codebook_path")
    if isinstance(codebook_id, str) and codebook_id:
        return f"taxonomy://{codebook_id}"
    if isinstance(codebook_path, str) and codebook_path:
        return codebook_path
    raise ValueError(
        f"Codebook node {node.id!r} sets neither codebook_id nor codebook_path."
    )


def _build_processor_config(node: NodeEntry, llm_resource_id: str) -> ProcessorConfig:
    """Build a :class:`ProcessorConfig` from one ``processor`` node entry."""
    config = dict(node.config)
    processor_type = str(config.get("step_type") or config.get("processor_type") or "processor")
    mode = config.get("mode")
    mode = mode if isinstance(mode, str) and mode else None
    keys = config.get("keys")

    io_schema_raw = config.get("io_schema")
    io_schema_obj = None
    if isinstance(io_schema_raw, dict) and io_schema_raw:
        normalized = dict(io_schema_raw)
        raw_output = normalized.get("output")
        if isinstance(raw_output, dict):
            canonical_output = {}
            for field_name, field_spec in raw_output.items():
                if isinstance(field_spec, str):
                    canonical_output[field_name] = {"data_type": field_spec}
                elif isinstance(field_spec, dict):
                    canonical_output[field_name] = field_spec
                else:
                    canonical_output[field_name] = {"data_type": "string"}
            normalized["output"] = canonical_output
        io_schema_obj = IOSchema.model_validate(normalized)

    prompt_raw = config.get("prompt")
    prompt_obj = (
        PromptInline.model_validate(prompt_raw)
        if isinstance(prompt_raw, dict) and prompt_raw.get("instructions")
        else None
    )

    prompts_ref = config.get("prompts_ref")
    prompts_ref = (
        prompts_ref
        if isinstance(prompts_ref, str) and prompts_ref
        else None
    )

    prompt_overrides_raw = config.get("prompt_overrides")
    prompt_overrides_obj = (
        PromptOverride.model_validate(prompt_overrides_raw)
        if isinstance(prompt_overrides_raw, dict) and prompt_overrides_raw
        else None
    )

    return ProcessorConfig(
        type=processor_type,
        unit="row",
        llm=llm_resource_id,
        mode=mode,
        keys=keys,
        io_schema=io_schema_obj,
        prompts_ref=prompts_ref,
        prompt=prompt_obj,
        prompt_overrides=prompt_overrides_obj,
    )


def _build_feedforward_sources(
    document: FlowDocument,
    node_index: Dict[str, NodeEntry],
) -> Dict[str, List[str]]:
    """Build ``{target_id: [source_ids]}`` from feedforward edges."""
    sources: Dict[str, List[str]] = {node.id: [] for node in document.nodes}
    for edge in document.edges:
        if edge.type != "feedforward":
            continue
        if edge.source in node_index and edge.target in node_index:
            sources[edge.target].append(edge.source)
    return sources


def compile_flow_document_to_runtime(
    document: FlowDocument,
) -> Tuple[FlowConfig, ExecutionPlan]:
    """Walk the parsed graph, construct the runtime :class:`FlowConfig`
    and the :class:`ExecutionPlan`.

    Returns:
        Tuple[FlowConfig, ExecutionPlan]: The validated runtime config
        and the graph-aware execution plan.

    Raises:
        ValueError: If the graph is malformed (missing input/output,
            cycles, unresolved llm/codebook references, processor
            without an LLM, output node without output_fields, etc.).
    """
    node_index = _index_nodes_by_id(document.nodes)
    data_node = _exactly_one(document.nodes, _DATA_INPUT_TYPES, "data input")

    output_nodes = [n for n in document.nodes if n.type in _DATA_OUTPUT_TYPES]
    if not output_nodes:
        raise ValueError(
            "Flow has no output node "
            f"(expected one of {sorted(_DATA_OUTPUT_TYPES)})."
        )

    processor_order = _topo_sort_processors(document, node_index)
    if not processor_order:
        raise ValueError("Flow has no processor nodes.")

    feedforward_sources = _build_feedforward_sources(document, node_index)

    resources_by_id: Dict[str, LLMResource] = {}
    processors: List[ProcessorConfig] = []
    processor_configs_by_id: Dict[str, ProcessorConfig] = {}
    taxonomy_path: Optional[str] = None
    taxonomy_selected_keys: Optional[List[str]] = None
    seen_codebook_node_id: Optional[str] = None

    for processor_id in processor_order:
        processor_node = node_index[processor_id]
        llm_node = _resolve_llm_resource_for_processor(
            processor_id, document, node_index
        )
        if llm_node is None:
            raise ValueError(
                f"Processor {processor_id!r} has no llm_call edge; "
                "every processor must wire to one llm_call node."
            )
        llm_resource = _build_llm_resource_from_node(llm_node)
        if llm_resource.id in resources_by_id:
            existing = resources_by_id[llm_resource.id]
            if existing.model_dump() != llm_resource.model_dump():
                raise ValueError(
                    f"Two llm_call nodes share resource id "
                    f"{llm_resource.id!r} but carry different config."
                )
        else:
            resources_by_id[llm_resource.id] = llm_resource

        codebook_node = _resolve_codebook_for_processor(
            processor_id, document, node_index
        )
        processor_has_codebook = False
        if codebook_node is not None:
            if (
                seen_codebook_node_id is not None
                and seen_codebook_node_id != codebook_node.id
            ):
                raise ValueError(
                    "Multiple processors point at different codebook nodes; "
                    "the runtime supports one codebook per flow."
                )
            seen_codebook_node_id = codebook_node.id
            taxonomy_path = _build_taxonomy_path(codebook_node)
            raw_keys = codebook_node.config.get("selected_keys")
            if isinstance(raw_keys, list) and raw_keys:
                taxonomy_selected_keys = [str(k) for k in raw_keys]
            processor_has_codebook = True

        step = _build_processor_config(processor_node, llm_resource.id)
        step.has_codebook = processor_has_codebook
        processors.append(step)
        processor_configs_by_id[processor_id] = step

    if taxonomy_path is None:
        taxonomy_path = ""

    # --- Build ExecutionPlan from feedforward edges ---

    plan_warnings: List[str] = []

    scheduled_processors: List[ScheduledNode] = []
    for proc_id in processor_order:
        input_from = feedforward_sources.get(proc_id, [])
        if not input_from:
            plan_warnings.append(
                f"Processor {proc_id!r} has no feedforward input edge."
            )
        scheduled_processors.append(ScheduledNode(
            node_id=proc_id,
            config=processor_configs_by_id[proc_id],
            input_from=input_from,
        ))

    scheduled_outputs: List[ScheduledOutput] = []
    for out_node in output_nodes:
        input_from = feedforward_sources.get(out_node.id, [])
        if not input_from:
            plan_warnings.append(
                f"Output node {out_node.id!r} has no feedforward input edge."
            )
        raw_fields = out_node.config.get("output_fields", [])
        out_fields = [str(f) for f in raw_fields if f] if isinstance(raw_fields, list) else []
        if not out_fields:
            raise ValueError(
                f"Output node {out_node.id!r} has no 'output_fields' configured. "
                "Every output node must declare at least one output field."
            )
        scheduled_outputs.append(ScheduledOutput(
            node_id=out_node.id,
            config=_build_output_config_from_node(out_node),
            input_from=input_from,
            output_fields=out_fields,
        ))

    consumed_ids: set[str] = set()
    for sn in scheduled_processors:
        consumed_ids.update(sn.input_from)
    for so in scheduled_outputs:
        consumed_ids.update(so.input_from)
    for proc_id in processor_order:
        if proc_id not in consumed_ids:
            plan_warnings.append(
                f"Processor {proc_id!r} output is not consumed by "
                "any downstream processor or output node."
            )

    execution_plan = ExecutionPlan(
        data_input_node_id=data_node.id,
        processors=scheduled_processors,
        outputs=scheduled_outputs,
        warnings=plan_warnings,
    )

    flow_config = FlowConfig(
        schema_version=1,
        name=document.name,
        description=document.description,
        resources=list(resources_by_id.values()),
        data=_build_data_config_from_node(data_node),
        taxonomy=taxonomy_path,
        taxonomy_selected_keys=taxonomy_selected_keys,
        prompts=document.settings.prompts,
        steps=processors,
        processing_limit=document.settings.processing_limit,
        async_config=document.settings.async_config,
        output=scheduled_outputs[0].config,
        logging=document.settings.logging,
        display=document.settings.display,
    )
    return flow_config, execution_plan


class FlowSchema(BaseModel):
    """Top-level envelope matching the YAML file structure.

    Attributes:
        document (FlowDocument): The parsed graph (nodes + edges +
            settings) read from the YAML.
        flow (FlowConfig): The runtime form compiled from
            :attr:`document`. :mod:`src.flow_builder` reads this.
        execution_plan (Optional[ExecutionPlan]): Graph-aware execution
            plan. Built by :meth:`load_from_path` and
            :meth:`from_document`. The runner uses this to dispatch
            processors in readiness order.
    """

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    document: FlowDocument
    flow: FlowConfig
    execution_plan: Optional[ExecutionPlan] = None

    @classmethod
    def load_from_path(cls, flow_yaml_path: Path) -> "FlowSchema":
        """Load and validate a flow YAML file in the new graph format.

        Args:
            flow_yaml_path (Path): Path to the flow YAML file on disk.

        Returns:
            FlowSchema: The validated schema with both the parsed graph
            and the compiled runtime view.

        Raises:
            FileNotFoundError: If ``flow_yaml_path`` does not exist.
            ValueError: If the YAML is not a valid graph or fails graph
                compilation.
        """
        flow_yaml_path = Path(flow_yaml_path)
        if not flow_yaml_path.exists():
            raise FileNotFoundError(
                f"Flow YAML file not found: {flow_yaml_path}"
            )

        with flow_yaml_path.open("r", encoding="utf-8") as yaml_file:
            raw_document: Dict[str, Any] = yaml.safe_load(yaml_file) or {}

        flow_block: Dict[str, Any] = raw_document.get("flow") or raw_document
        document = FlowDocument.model_validate(flow_block)
        flow_config, plan = compile_flow_document_to_runtime(document)
        return cls(document=document, flow=flow_config, execution_plan=plan)

    @classmethod
    def from_document(cls, document: FlowDocument) -> "FlowSchema":
        """Build a :class:`FlowSchema` from an in-memory :class:`FlowDocument`."""
        flow_config, plan = compile_flow_document_to_runtime(document)
        return cls(document=document, flow=flow_config, execution_plan=plan)
