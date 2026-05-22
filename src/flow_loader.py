"""Loader for MessyText configuration-driven flow YAML files.

The *schema* itself lives in the YAML documents under ``config/flows/``. This
module is the actor that reads one of those YAML files from disk, applies the
``llm:`` shorthand normalisation, and validates the result against a set of
Pydantic models. It produces a typed :class:`FlowSchema` Python object that
:mod:`src.flow_builder` consumes.

The Pydantic models declared here are the *validation rules* for the YAML
schema — not the schema. Validation runs before any LLM call is made, so
typos and missing fields fail fast with clear error messages instead of
surfacing as runtime errors deep inside the processors.

Contents and relationships
--------------------------

- :class:`FlowSchema` — top-level envelope matching the YAML file. Wraps a
  single :class:`FlowConfig` under the ``flow:`` key. Exposes
  :meth:`FlowSchema.load_from_path` which reads the YAML from disk, applies
  the ``llm:`` shorthand normalisation, and returns the validated object.
- :class:`FlowConfig` — the ``flow:`` block. Holds schema version, metadata,
  LLM resources, data source, taxonomy and prompt paths, ordered pipeline
  steps, async settings, output paths, logging, and display options.
- :class:`LLMResource` — one named LLM provider entry under
  ``flow.resources[*]``. Each resource is addressable by ``id`` and is
  referenced by :attr:`StepConfig.llm` when a step needs a non-default LLM.
- :class:`LLMShorthand` — the single-LLM sugar block accepted as
  ``flow.llm:``. The loader rewrites this into a one-entry ``resources``
  list with ``id = "default"`` so downstream code only deals with the
  canonical :class:`LLMResource` list.
- :class:`ColumnRoles` — maps the user's actual CSV column names to the
  internal roles (``text``, ``entity_id``, ``doc_id``, ``sort_by``,
  ``passthrough``) that the runner loops use.
- :class:`DataConfig` — the ``flow.data:`` block pointing at the input CSV
  and holding the :class:`ColumnRoles` binding.
- :class:`StepConfig` — a single processing step. ``type`` selects the
  runtime behaviour; the set of accepted values is sourced from the
  :mod:`src.node_registry` registry (``config/node_types.yaml``) rather
  than from a hardcoded list. Optional fields let the user override the
  step's LLM-facing I/O schema (:attr:`StepConfig.io_schema`) and the
  effective prompt (:attr:`StepConfig.prompt`,
  :attr:`StepConfig.prompts_ref`, :attr:`StepConfig.prompt_overrides`).
- :class:`AsyncConfig`, :class:`OutputConfig`, :class:`LoggingConfig`, and
  :class:`DisplayConfig` — the remaining runtime sections that control
  concurrency, where results are written, what is logged, and whether
  progress bars are shown.

How the rest of the system uses this module
-------------------------------------------

:func:`src.flow_builder.build_flow` calls
:meth:`FlowSchema.load_from_path` to obtain a validated schema, then walks
:attr:`FlowConfig.resources` to construct OpenAI-compatible clients, walks
:attr:`FlowConfig.steps` to instantiate the matching processor classes from
:mod:`src.processors`, and uses :attr:`FlowConfig.data`,
:attr:`FlowConfig.async_config`, and :attr:`FlowConfig.output` to drive the
runner loops.

Invariants enforced by this module
----------------------------------

- At least one :class:`LLMResource` exists after normalisation, and every
  resource has a unique ``id``.
- Every :attr:`StepConfig.llm` string resolves to an existing resource
  ``id``. Steps that omit ``llm`` are wired to the resource with ``id =
  "default"`` by the builder.
- :attr:`StepConfig.type` is one of the ids whose ``category`` is
  ``processor`` in :mod:`src.node_registry`'s default registry.
- :attr:`StepConfig.unit` is one of ``row`` / ``document`` / ``entity``.
- Adjacent steps in :attr:`FlowConfig.steps` must have compatible
  :attr:`StepConfig.unit` values (enforced by
  :meth:`FlowConfig.validate_adjacent_unit_transitions`): ``row→row``,
  ``document→document``, ``document→entity`` (aggregation), and
  ``entity→entity`` are accepted; all other transitions are rejected.
- Inline :attr:`StepConfig.prompt` and :attr:`StepConfig.prompts_ref`
  are mutually exclusive; :attr:`StepConfig.prompt_overrides` requires
  :attr:`StepConfig.prompts_ref`. Enforced by
  :meth:`StepConfig.validate_prompt_sources`.
- :class:`ColumnRoles` requires ``text``, ``entity_id``, ``doc_id``, and
  ``sort_by`` to be present.
- :attr:`LLMResource.api_key_env` and :attr:`LLMResource.api_key` are
  mutually exclusive in the YAML: the builder resolves ``api_key_env``
  against ``os.environ`` at startup and the runtime copy of the resource
  ends up with ``api_key`` populated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Literal, Optional

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from src.io_schema import IOSchema
from src.node_registry import get_processor_step_types
from src.prompt_resolver import PromptInline, PromptOverride


def _registered_processor_step_types() -> FrozenSet[str]:
    """Return the current set of processor step-type ids from the default registry.

    The indirection avoids baking the registry's contents into a module
    constant, which would otherwise freeze the set at import time and
    make tests that patch :data:`src.node_registry.DEFAULT_REGISTRY_PATH`
    harder to write.

    Returns:
        FrozenSet[str]: The processor step-type ids declared in
        :mod:`src.node_registry`'s default registry.
    """
    return get_processor_step_types()


UNIT_VALUES: frozenset[str] = frozenset({"row", "document", "entity"})
"""Registered step ``unit`` values accepted by :class:`StepConfig`."""


VALID_ADJACENT_UNIT_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("row", "row"),
        ("document", "document"),
        ("document", "entity"),
        ("entity", "entity"),
    }
)
"""Allowed ``(previous_unit, current_unit)`` pairs between neighbouring steps.

``row→row`` keeps a flat row-wise pipeline. ``document→document`` and
``entity→entity`` keep the stream at the same unit. ``document→entity``
is the aggregation transition used by flows that first run per-document
work and then roll up into a per-entity summary. Every other pair is
rejected by :meth:`FlowConfig.validate_adjacent_unit_transitions` because
the runner has no loop that mixes the two units."""


SUPPORTED_INPUT_EXTENSIONS: frozenset[str] = frozenset({".csv", ".json", ".jsonl"})
"""File extensions accepted by :attr:`DataConfig.input_csv`.

The flow builder dispatches to the appropriate pandas reader based on the
extension: ``.csv`` → :func:`pandas.read_csv`, ``.json`` →
:func:`pandas.read_json` (records), ``.jsonl`` →
:func:`pandas.read_json` (lines)."""


PROVIDER_VALUES: frozenset[str] = frozenset({"local_vllm", "openrouter", "openai"})
"""Registered provider values accepted by :class:`LLMResource`."""


PROVIDER_DEFAULT_API_BASE: Dict[str, str] = {
    "local_vllm": "http://localhost:8000/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
}
"""Default ``api_base`` per provider. Used by the builder when the YAML
omits ``api_base`` on a resource."""


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
            :attr:`StepConfig.llm`. The shorthand block is normalised into a
            resource with ``id = "default"``.
        type (Literal["llm_provider"]): Discriminator kept for future
            resource kinds. Always ``"llm_provider"`` in Phase 1.
        provider (str): One of :data:`PROVIDER_VALUES`. Selects the default
            ``api_base`` via :data:`PROVIDER_DEFAULT_API_BASE` when
            ``api_base`` is omitted.
        model (str): Model identifier sent to the endpoint as
            ``chat.completions.create(model=...)``.
        api_base (Optional[str]): OpenAI-compatible base URL. Defaults to
            the provider-specific base URL when omitted.
        api_key (Optional[str]): Literal API key. Only used for
            ``local_vllm`` where the key is ``"dummy"``. For hosted
            providers, use :attr:`api_key_env` instead.
        api_key_env (Optional[str]): Name of the environment variable that
            holds the real API key. Resolved by the builder from the
            project-root ``.env`` file. Mutually exclusive with
            :attr:`api_key`.
        temperature (float): Temperature forwarded to every LLM call
            produced against this resource.
        max_tokens_summary (int): ``max_tokens`` for summary-style calls.
        max_tokens_classification (int): ``max_tokens`` for classification
            calls.

    Methods:
        validate_provider: Ensure :attr:`provider` is a registered value.
        validate_api_key_shape: Ensure ``api_key`` and ``api_key_env`` are
            not both set at the same time.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["llm_provider"] = "llm_provider"
    provider: str
    model: str
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None
    temperature: float = 0.0
    max_tokens_summary: int = 1024
    max_tokens_classification: int = 256

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


class LLMShorthand(BaseModel):
    """Single-LLM sugar block accepted as ``flow.llm:``.

    This object exists only to support the shorthand form of the schema. The
    loader normalises it into a one-entry :class:`LLMResource` list with
    ``id = "default"`` before any downstream code runs.

    Attributes:
        provider (str): Same meaning as :attr:`LLMResource.provider`.
        model (str): Same meaning as :attr:`LLMResource.model`.
        api_base (Optional[str]): Same meaning as :attr:`LLMResource.api_base`.
        api_key (Optional[str]): Same meaning as :attr:`LLMResource.api_key`.
        api_key_env (Optional[str]): Same meaning as
            :attr:`LLMResource.api_key_env`.
        temperature (float): Same meaning as :attr:`LLMResource.temperature`.
        max_tokens_summary (int): Same meaning as
            :attr:`LLMResource.max_tokens_summary`.
        max_tokens_classification (int): Same meaning as
            :attr:`LLMResource.max_tokens_classification`.

    Methods:
        to_resource: Convert this shorthand block into a canonical
            :class:`LLMResource` with ``id = "default"``.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None
    temperature: float = 0.0
    max_tokens_summary: int = 1024
    max_tokens_classification: int = 256

    def to_resource(self) -> LLMResource:
        """Promote this shorthand block into a canonical :class:`LLMResource`.

        Returns:
            LLMResource: A resource with ``id = "default"`` and
            ``type = "llm_provider"``, carrying every value from this
            shorthand block.
        """
        return LLMResource(
            id="default",
            type="llm_provider",
            provider=self.provider,
            model=self.model,
            api_base=self.api_base,
            api_key=self.api_key,
            api_key_env=self.api_key_env,
            temperature=self.temperature,
            max_tokens_summary=self.max_tokens_summary,
            max_tokens_classification=self.max_tokens_classification,
        )


class ColumnRoles(BaseModel):
    """Mapping from user CSV column names to the pipeline's internal roles.

    The runner never hard-codes column names. Instead, every loop reads
    column names out of this object. A user whose CSV has columns named
    ``article_body``, ``case_number``, ``report_id``, ``pub_date`` sets the
    four role fields accordingly, and the processors see the same
    ``text: str`` / ``doc_id: Any`` arguments they always see.

    Attributes:
        text (str): Name of the column that contains the raw document text
            fed to the LLM.
        entity_id (str): Name of the column that groups rows belonging to
            the same entity. For the current dataset this is ``victim``.
        doc_id (str): Name of the column that uniquely identifies each
            document. Passed through to :class:`src.processors.ProcessorResult`
            as ``doc_id`` for traceability.
        sort_by (str): Name of the column used to order documents within
            an entity group before sequential processing.
        passthrough (List[str]): Extra column names the user wants kept
            untouched in the output CSVs.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    entity_id: str
    doc_id: str
    sort_by: str
    passthrough: List[str] = Field(default_factory=list)


class DataConfig(BaseModel):
    """``flow.data:`` block: input data file path and column role binding.

    Attributes:
        input_csv (str): Project-root-relative POSIX path to the input
            data file. Accepts ``.csv``, ``.json``, and ``.jsonl``
            extensions. The YAML key may also be written as
            ``input_file`` for clarity when using non-CSV formats;
            both keys map to this attribute. Validated by
            :func:`_validate_project_relative_posix_path` so the same
            string resolves to the same file in the FastAPI web
            process and the Celery worker container.
        column_roles (ColumnRoles): The column-to-role mapping used by
            every runner loop.

    Methods:
        validate_input_file_path: Enforce the project-root-relative
            POSIX convention and supported file extension on
            :attr:`input_csv`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    input_csv: str = Field(
        validation_alias=AliasChoices("input_csv", "input_file"),
    )
    column_roles: ColumnRoles

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


class StepConfig(BaseModel):
    """One processing step in :attr:`FlowConfig.steps`.

    ``type`` selects the runtime behaviour. Accepted values are the ids
    whose category is ``processor`` in :mod:`src.node_registry`'s
    default registry (``config/node_types.yaml``). The registry also
    supplies each step's default I/O schema and default prompt
    reference; users override those per step through the optional
    :attr:`io_schema`, :attr:`prompt`, :attr:`prompts_ref`, and
    :attr:`prompt_overrides` fields.

    Optional fields reserved for specific step types:

    - ``mode`` applies to ``label_summary`` (``hybrid`` or ``full_async``).
    - ``keys`` applies to ``classification`` (``"all"`` or a list of
      taxonomy keys).

    Attributes:
        type (str): Registered processor step-type id. Looked up in
            :mod:`src.node_registry`.
        unit (str): One of :data:`UNIT_VALUES`. Declares the unit of
            analysis the step operates on.
        group_by (Optional[str]): Grouping rule. Currently accepts
            ``"entity"`` for grouped loops; ``None`` means the runner
            iterates rows directly.
        llm (Optional[str]): Resource ``id`` this step uses. ``None`` means
            the builder wires the step to the resource with
            ``id = "default"``.
        mode (Optional[str]): ``hybrid`` or ``full_async`` for
            ``label_summary``.
        keys (Optional[Any]): ``"all"`` or a list of taxonomy keys for
            ``classification``.
        io_schema (Optional[IOSchema]): Per-step override of the LLM
            I/O schema. When set, :mod:`src.flow_builder` converts its
            ``output`` dict into the OpenAI ``response_format`` via
            :func:`src.io_schema.to_response_format` and bypasses the
            registry default for this step only.
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

    Methods:
        validate_type: Ensure :attr:`type` is a registered processor
            step-type id.
        validate_unit: Ensure :attr:`unit` is in :data:`UNIT_VALUES`.
        validate_prompt_sources: Enforce that :attr:`prompt` and
            :attr:`prompts_ref` are not both set and that
            :attr:`prompt_overrides` requires :attr:`prompts_ref`.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    unit: str
    group_by: Optional[str] = None
    llm: Optional[str] = None
    mode: Optional[str] = None
    keys: Optional[Any] = None
    io_schema: Optional[IOSchema] = None
    prompts_ref: Optional[str] = None
    prompt: Optional[PromptInline] = None
    prompt_overrides: Optional[PromptOverride] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, step_type_value: str) -> str:
        """Ensure the step type is a registered processor step-type id.

        Args:
            step_type_value (str): Raw step type string from YAML.

        Returns:
            str: The step type, unchanged.

        Raises:
            ValueError: If the step type is not registered as a
                ``processor`` node in :mod:`src.node_registry`.
        """
        registered_step_types = _registered_processor_step_types()
        if step_type_value not in registered_step_types:
            raise ValueError(
                "step type must be one of "
                f"{sorted(registered_step_types)}; got {step_type_value!r}. "
                "Registered processor step types come from "
                "config/node_types.yaml via src/node_registry.py."
            )
        return step_type_value

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, unit_value: str) -> str:
        """Ensure the unit is one of :data:`UNIT_VALUES`.

        Args:
            unit_value (str): Raw unit string from YAML.

        Returns:
            str: The unit, unchanged.

        Raises:
            ValueError: If the unit is not registered.
        """
        if unit_value not in UNIT_VALUES:
            raise ValueError(
                f"unit must be one of {sorted(UNIT_VALUES)}; "
                f"got {unit_value!r}"
            )
        return unit_value

    @model_validator(mode="after")
    def validate_prompt_sources(self) -> "StepConfig":
        """Enforce the mutual-exclusion rules for the prompt fields.

        Inline :attr:`prompt` and :attr:`prompts_ref` cannot both be set
        on the same step, and :attr:`prompt_overrides` requires
        :attr:`prompts_ref` to name a base instruction list.

        Returns:
            StepConfig: The same instance, unchanged.

        Raises:
            ValueError: If inline :attr:`prompt` and :attr:`prompts_ref`
                are both set, or if :attr:`prompt_overrides` is set
                without :attr:`prompts_ref`.
        """
        if self.prompt is not None and self.prompts_ref is not None:
            raise ValueError(
                f"Step (type={self.type!r}) sets both inline 'prompt' and "
                "'prompts_ref'. Use exactly one: inline for a full override, "
                "prompts_ref for a reference (with optional prompt_overrides)."
            )
        if self.prompt_overrides is not None and self.prompts_ref is None:
            raise ValueError(
                f"Step (type={self.type!r}) sets 'prompt_overrides' without "
                "'prompts_ref'. Overrides apply on top of a reference; remove "
                "prompt_overrides or add prompts_ref."
            )
        return self


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

    All four CSV paths are validated by
    :func:`_validate_project_relative_posix_path` so they cross host and
    container boundaries cleanly. The run dispatcher rewrites every one
    of them to a run-scoped path under ``server/data/runs/<run_id>/``
    before the YAML lands on disk.

    Attributes:
        summary_csv (str): Project-root-relative POSIX path for the
            per-row summary CSV.
        results_csv (Optional[str]): Project-root-relative POSIX path
            for the flattened per-turn result CSV. ``None`` disables
            results output.
        states_csv (Optional[str]): Project-root-relative POSIX path
            for the per-entity serialized state CSV. ``None`` disables
            states output.
        spans_csv (Optional[str]): Project-root-relative POSIX path for
            the flattened spans CSV. ``None`` disables spans output.
        extend (bool): When ``True`` the writer appends to existing files
            while replacing rows for the current model.

    Methods:
        validate_csv_paths: Enforce the project-root-relative POSIX
            convention on each of the four CSV path fields.
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
    """The ``flow:`` block: the full validated flow definition.

    Attributes:
        schema_version (int): Version of the YAML format. Incremented when
            the schema changes in an incompatible way.
        name (str): Short identifier for the flow. Used in logs and output
            file prefixes.
        description (str): Free-form human-readable description.
        resources (List[LLMResource]): Named LLM provider entries. Either
            declared directly under ``resources:`` or produced from the
            ``llm:`` shorthand.
        data (DataConfig): Input CSV and column role binding.
        taxonomy (str): Project-root-relative POSIX path to the taxonomy
            JSON file consumed by the processors.
        prompts (str): Project-root-relative POSIX path to the prompts
            JSON file consumed by the processors.
        steps (List[StepConfig]): Ordered pipeline steps.
        processing_limit (Optional[int]): When set, caps the number of
            entities (grouped pipelines) or rows (flat pipelines) the
            runner processes. ``None`` means process all.
        async_config (AsyncConfig): Concurrency settings. Aliased as
            ``async`` in the YAML.
        output (OutputConfig): Output CSV paths.
        logging (LoggingConfig): Logger file and verbosity flags.
        display (DisplayConfig): User-visible progress options.

    Methods:
        validate_taxonomy_and_prompt_paths: Enforce the project-root-relative
            POSIX convention on :attr:`taxonomy` and :attr:`prompts`.
        validate_resources: Ensure resource ids are unique and that every
            ``step.llm`` reference resolves.
        validate_steps_non_empty: Ensure at least one step is declared.
        validate_adjacent_unit_transitions: Enforce the unit compat matrix
            defined by :data:`VALID_ADJACENT_UNIT_TRANSITIONS`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: int
    name: str
    description: str = ""
    resources: List[LLMResource]
    data: DataConfig
    taxonomy: str
    prompts: str
    steps: List[StepConfig]
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

        Args:
            value (str): Raw value as read from YAML.
            info: Pydantic validation context; ``info.field_name`` is
                either ``"taxonomy"`` or ``"prompts"``.

        Returns:
            str: ``value`` unchanged.

        Raises:
            ValueError: If the path is absolute, empty, contains
                backslashes, or begins with a Windows drive letter
                (unless it is a ``taxonomy://`` URI).
        """
        if info.field_name == "taxonomy" and value.startswith("taxonomy://"):
            if len(value) <= len("taxonomy://"):
                raise ValueError(
                    "taxonomy URI has no id after 'taxonomy://'"
                )
            return value
        return _validate_project_relative_posix_path(value, info.field_name)

    @model_validator(mode="after")
    def validate_resources(self) -> "FlowConfig":
        """Enforce unique resource ids and resolvable ``step.llm`` references.

        Returns:
            FlowConfig: The same instance, unchanged.

        Raises:
            ValueError: If a duplicate resource id is found or a step
                references an unknown resource id.
        """
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
                "At least one LLM resource must be declared (either under "
                "flow.resources[*] or via the flow.llm shorthand)."
            )

        for step_index, step in enumerate(self.steps):
            if step.llm is not None and step.llm not in seen_ids:
                raise ValueError(
                    f"Step {step_index} (type={step.type!r}) references "
                    f"llm={step.llm!r}, which is not among the declared "
                    f"resource ids: {sorted(seen_ids)}"
                )
        return self

    @model_validator(mode="after")
    def validate_steps_non_empty(self) -> "FlowConfig":
        """Reject a flow with zero steps.

        Returns:
            FlowConfig: The same instance, unchanged.

        Raises:
            ValueError: If :attr:`steps` is empty.
        """
        if not self.steps:
            raise ValueError("flow.steps must contain at least one step.")
        return self

    @model_validator(mode="after")
    def validate_adjacent_unit_transitions(self) -> "FlowConfig":
        """Reject neighbouring steps whose ``unit`` pair is not allowed.

        Walks :attr:`steps` left-to-right and for each neighbouring pair
        ``(steps[i], steps[i + 1])`` checks that
        ``(steps[i].unit, steps[i + 1].unit)`` is listed in
        :data:`VALID_ADJACENT_UNIT_TRANSITIONS`. A single flow may therefore
        advance through ``row → row``, stay on ``document``, aggregate
        ``document → entity``, or stay on ``entity``, but must not, for
        example, drop from ``document`` back to ``row`` or jump ``row``
        straight to ``entity`` — those combinations have no runner loop.

        Returns:
            FlowConfig: The same instance, unchanged.

        Raises:
            ValueError: If any neighbouring step pair violates
                :data:`VALID_ADJACENT_UNIT_TRANSITIONS`. The message names
                both offending step indices, their types, and the
                offending unit pair so the user can find them in the YAML.
        """
        for step_index in range(len(self.steps) - 1):
            previous_step = self.steps[step_index]
            current_step = self.steps[step_index + 1]
            unit_transition = (previous_step.unit, current_step.unit)
            if unit_transition not in VALID_ADJACENT_UNIT_TRANSITIONS:
                sorted_valid_pairs = sorted(VALID_ADJACENT_UNIT_TRANSITIONS)
                raise ValueError(
                    f"Invalid adjacent unit transition between step "
                    f"{step_index} (type={previous_step.type!r}, "
                    f"unit={previous_step.unit!r}) and step "
                    f"{step_index + 1} (type={current_step.type!r}, "
                    f"unit={current_step.unit!r}): "
                    f"{previous_step.unit!r}→{current_step.unit!r} "
                    f"is not allowed. Allowed transitions are "
                    f"{sorted_valid_pairs}."
                )
        return self


class FlowSchema(BaseModel):
    """Top-level envelope matching the YAML file structure.

    Attributes:
        flow (FlowConfig): The validated flow definition.

    Methods:
        load_from_path: Read a YAML file from disk, apply shorthand
            normalisation, and return the validated :class:`FlowSchema`.
    """

    model_config = ConfigDict(extra="forbid")

    flow: FlowConfig

    @classmethod
    def load_from_path(cls, flow_yaml_path: Path) -> "FlowSchema":
        """Load and validate a flow YAML file.

        The loader applies the ``llm:`` shorthand normalisation before
        validation: if the YAML declares ``flow.llm:`` but not
        ``flow.resources:``, the ``llm:`` block is promoted to a one-entry
        ``resources`` list with ``id = "default"``. Declaring both
        ``flow.llm`` and ``flow.resources`` is rejected to avoid ambiguity.

        Args:
            flow_yaml_path (Path): Path to the flow YAML file on disk.

        Returns:
            FlowSchema: The validated schema with ``resources`` always
            populated.

        Raises:
            FileNotFoundError: If ``flow_yaml_path`` does not exist.
            ValueError: If the YAML declares both ``flow.llm`` and
                ``flow.resources``, or if Pydantic validation fails.
        """
        flow_yaml_path = Path(flow_yaml_path)
        if not flow_yaml_path.exists():
            raise FileNotFoundError(
                f"Flow YAML file not found: {flow_yaml_path}"
            )

        with flow_yaml_path.open("r", encoding="utf-8") as yaml_file:
            raw_document: Dict[str, Any] = yaml.safe_load(yaml_file) or {}

        flow_block: Dict[str, Any] = raw_document.get("flow") or {}
        has_shorthand = "llm" in flow_block
        has_resources = "resources" in flow_block

        if has_shorthand and has_resources:
            raise ValueError(
                "flow.llm (shorthand) and flow.resources (canonical) are "
                "mutually exclusive. Use exactly one of them."
            )

        if has_shorthand:
            shorthand_block = LLMShorthand(**flow_block["llm"])
            flow_block = dict(flow_block)
            del flow_block["llm"]
            flow_block["resources"] = [shorthand_block.to_resource().model_dump()]
            raw_document = dict(raw_document)
            raw_document["flow"] = flow_block

        return cls.model_validate(raw_document)
