"""Configuration-driven flow builder and runner for MessyText pipelines.

This module turns a validated :class:`src.flow_loader.FlowSchema` into a
ready-to-execute pipeline on top of the existing processors in
:mod:`src.processors`. It contains no new processing logic: every LLM call,
prompt construction, and JSON schema handling is delegated to the classes
already defined in :mod:`src.processors`. The role of this module is strictly
orchestration — wiring classes together according to the flow YAML,
resolving step-level overrides against the node-type registry, and
driving the processor loops.

Contents and relationships
--------------------------

- :func:`build_flow` — public entry point. Loads and validates the flow
  YAML, loads ``.env`` into ``os.environ``, loads the taxonomy and prompts
  JSON files, loads the default :class:`src.node_registry.NodeTypeRegistry`,
  constructs one :class:`openai.AsyncOpenAI` client per LLM resource, and
  returns a :class:`FlowRunner`.
- :class:`FlowRunner` — owns the execution loop. :meth:`FlowRunner.run`
  loads the input CSV, dispatches each step in order, and writes the output
  CSVs declared in :class:`src.flow_loader.OutputConfig`. Each dispatcher
  calls :meth:`FlowRunner._resolve_processor_config_for_step` to obtain a
  per-step processor config with ``io_schema_resolved`` and
  ``prompt_resolved`` layered onto the resource-level base.
- :class:`_ConversationSummaryPlan` — internal helper that pairs
  ``conversation_summary_first`` with ``conversation_summary_update`` so
  the two schema steps are executed as one sequential per-entity loop,
  matching :mod:`scripts.run_summary_conversation`.
- :func:`_load_dotenv_into_environ` — robust ``.env`` loader that uses
  ``python-dotenv`` when available and falls back to a manual
  ``KEY=VALUE`` parser when the dependency is not installed. The project
  root is resolved from ``__file__``.
- :func:`_resolve_resource_credentials` — normalises every resource so it
  has a concrete ``api_base`` and a concrete ``api_key`` string after
  reading ``api_key_env`` from the environment.
- :func:`_build_processor_runtime_config` — shapes the nested dict that
  :class:`src.processors.AsyncMessyTextProcessor` expects at construction
  time. When called with a ``step`` + ``registry`` pair it also resolves
  the step's :attr:`src.flow_loader.StepConfig.io_schema` (falling back
  to the :class:`src.node_registry.NodeTypeEntry.default_io_schema`) and
  the step's prompt (via :func:`src.prompt_resolver.resolve_step_prompt`),
  and injects both under ``io_schema_resolved`` / ``prompt_resolved``.

How the rest of the system uses this module
-------------------------------------------

:mod:`scripts.run_custom_flow` is the only intended caller. It sets a
module-level ``flow_config`` variable, calls :func:`build_flow`, and runs
the returned :class:`FlowRunner`. Per-step I/O schema and prompt
resolution happen lazily at dispatch time in
:meth:`FlowRunner._resolve_processor_config_for_step`, so the flow YAML
alone controls which schema and which prompt reach each LLM call.

Invariants enforced by this module
----------------------------------

- Every LLM resource ends up with a non-empty ``api_key`` before any
  client is constructed. ``api_key_env`` is resolved against
  ``os.environ`` and a missing variable fails fast with a clear error.
- Every :class:`src.flow_loader.StepConfig` referenced at runtime
  corresponds to an implemented dispatcher. Step types declared in the
  schema but not yet implemented raise :class:`NotImplementedError` with
  an actionable message pointing at the existing script that still covers
  that flow.
- Every step-level I/O schema override is wrapped in
  :class:`src.io_schema.IOSchema` before being injected into the
  processor config, so downstream code can uniformly call
  :func:`src.io_schema.to_response_format` on it.
- Every step-level prompt override obeys the precedence documented in
  :func:`src.prompt_resolver.resolve_step_prompt`: inline ``prompt`` >
  ``prompts_ref`` + overrides > ``prompts_ref`` alone > registry default
  > ``None`` (hardcoded fallback in the processor).
- Output directories are created before any CSV is written.
- Runner-owned state (``running_summary``,
  :class:`src.processors.MessyTextConversationState`) is managed in
  :class:`FlowRunner`, not in the processors.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from openai import AsyncOpenAI
from tqdm.asyncio import tqdm as tqdm_async

from src.flow_loader import (
    FlowSchema,
    LLMResource,
    LoggingConfig,
    PROVIDER_DEFAULT_API_BASE,
    StepConfig,
)
from src.io_schema import IOSchema
from src.node_registry import NodeTypeRegistry, get_default_registry
from src.processors import (
    AsyncLabelExtractor,
    AsyncMessyTextConversationTurnProcessor,
    AsyncMessyTextProcessor,
    AsyncTextConversationOrchestrator,
    AsyncTextLabelsSummaryProcessor,
    MessyTextConversationState,
    ProcessorResult,
)
from src.prompt_resolver import ResolvedPrompt, resolve_step_prompt
from src.recorders import (
    flatten_spans_from_state,
    serialize_result_entry,
    serialize_state_entry,
    write_results,
    write_spans,
    write_states,
)
from src.utils import is_informative_summary, setup_logger


_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
"""Absolute path of the project root directory (the parent of ``src/``)."""


def _load_dotenv_into_environ(project_root: Path) -> None:
    """Load ``project_root/.env`` into :data:`os.environ`.

    Uses :mod:`dotenv` when importable; otherwise falls back to a minimal
    ``KEY=VALUE`` parser that handles blank lines, ``#`` comments, and
    values optionally wrapped in matching single or double quotes. Missing
    ``.env`` files are silently ignored so the rest of the flow still runs
    when every resource uses a literal ``api_key``.

    Args:
        project_root (Path): Directory that contains the ``.env`` file.

    Returns:
        None: This function mutates :data:`os.environ` in place.
    """
    env_path = project_root / ".env"
    if not env_path.exists():
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_path, override=False)
        return
    except ImportError:
        pass

    with env_path.open("r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            stripped_line = raw_line.strip()
            if not stripped_line or stripped_line.startswith("#"):
                continue
            if "=" not in stripped_line:
                continue
            key_part, _, value_part = stripped_line.partition("=")
            key_name = key_part.strip()
            raw_value = value_part.strip()
            if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
                raw_value = raw_value[1:-1]
            os.environ.setdefault(key_name, raw_value)


def _resolve_resource_credentials(resource: LLMResource) -> LLMResource:
    """Fill in ``api_base`` and ``api_key`` for a validated resource.

    ``api_base`` falls back to
    :data:`src.flow_loader.PROVIDER_DEFAULT_API_BASE` when omitted.
    ``api_key`` is resolved from :attr:`LLMResource.api_key_env` against
    :data:`os.environ`. For ``local_vllm`` the convention from the existing
    codebase is to pass the literal string ``"dummy"`` when no explicit
    key is provided.

    Args:
        resource (LLMResource): The validated resource whose credentials
            still need to be materialised.

    Returns:
        LLMResource: A new resource instance with ``api_base`` and
        ``api_key`` populated and ``api_key_env`` cleared.

    Raises:
        ValueError: If ``api_key_env`` is declared but the named
            environment variable is missing, or if a hosted provider ends
            up with no usable API key.
    """
    resolved_api_base = resource.api_base or PROVIDER_DEFAULT_API_BASE[resource.provider]

    if resource.api_key is not None:
        resolved_api_key: str = resource.api_key
    elif resource.api_key_env is not None:
        resolved_api_key_opt = os.environ.get(resource.api_key_env)
        if not resolved_api_key_opt:
            raise ValueError(
                f"Resource {resource.id!r} declares api_key_env="
                f"{resource.api_key_env!r}, but that environment variable "
                "is not set. Populate it in the project-root .env file or "
                "export it before running."
            )
        resolved_api_key = resolved_api_key_opt
    elif resource.provider == "local_vllm":
        resolved_api_key = "dummy"
    else:
        raise ValueError(
            f"Resource {resource.id!r} (provider={resource.provider!r}) has "
            "neither api_key nor api_key_env set. Hosted providers require "
            "api_key_env pointing at a variable in the .env file."
        )

    return resource.model_copy(
        update={
            "api_base": resolved_api_base,
            "api_key": resolved_api_key,
            "api_key_env": None,
        }
    )


def _build_async_client(resource: LLMResource, max_retries: int) -> AsyncOpenAI:
    """Construct an :class:`openai.AsyncOpenAI` client for a resolved resource.

    Args:
        resource (LLMResource): A resource that has been passed through
            :func:`_resolve_resource_credentials` so ``api_base`` and
            ``api_key`` are non-None.
        max_retries (int): Maximum retry count forwarded to the client.

    Returns:
        AsyncOpenAI: A configured asynchronous client instance.

    Raises:
        ValueError: If ``api_base`` or ``api_key`` is missing on the
            resource after resolution.
    """
    if resource.api_base is None or resource.api_key is None:
        raise ValueError(
            f"Resource {resource.id!r} is missing api_base or api_key after "
            "resolution. Call _resolve_resource_credentials first."
        )
    return AsyncOpenAI(
        base_url=resource.api_base,
        api_key=resource.api_key,
        max_retries=max_retries,
    )


def _build_processor_runtime_config(
    resource: LLMResource,
    prompts_payload: Dict[str, Any],
    logging_config: LoggingConfig,
    *,
    step: Optional[StepConfig] = None,
    registry: Optional[NodeTypeRegistry] = None,
    flow_prompts_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Shape the runtime config dict consumed by processor constructors.

    :class:`src.processors.AsyncMessyTextProcessor` and its siblings read a
    nested dict at construction time. This helper assembles that dict from
    the resource's generation parameters and the loaded prompts payload so
    the runner does not hand-roll the same shape in every dispatcher.

    When ``step`` and ``registry`` are both supplied, the helper also
    resolves the step's I/O schema and prompt and injects them under the
    ``io_schema_resolved`` and ``prompt_resolved`` keys:

    - ``io_schema_resolved`` (Optional[IOSchema]) — the step's
      :attr:`src.flow_loader.StepConfig.io_schema` if set, otherwise the
      :attr:`src.node_registry.NodeTypeEntry.default_io_schema` for
      ``step.type`` wrapped in :class:`src.io_schema.IOSchema`, otherwise
      ``None``. A ``None`` value leaves the processor on its hardcoded
      fallback.
    - ``prompt_resolved`` (Optional[ResolvedPrompt]) — the output of
      :func:`src.prompt_resolver.resolve_step_prompt`, with the same
      precedence order (inline prompt > ``prompts_ref`` + overrides >
      ``prompts_ref`` alone > registry default > ``None``).

    When ``step`` is ``None`` (startup path that pre-computes one base
    config per resource), the returned dict carries only the four base
    keys. Existing callers that omit ``step`` therefore see the same
    shape they always saw.

    Args:
        resource (LLMResource): The resolved resource whose model name and
            generation parameters are copied into the config.
        prompts_payload (Dict[str, Any]): Parsed ``config/prompts.json``
            content. Surfaced under the ``prompts`` key.
        logging_config (LoggingConfig): The flow's logging configuration,
            surfaced under the ``logging`` key so processors can honour
            :attr:`LoggingConfig.log_response`.
        step (Optional[StepConfig]): The step being configured. When
            supplied, ``io_schema_resolved`` and ``prompt_resolved``
            are injected into the returned dict. When ``None``, only
            the base keys are returned.
        registry (Optional[NodeTypeRegistry]): Node-type registry used
            to resolve :attr:`src.node_registry.NodeTypeEntry.default_io_schema`
            and :attr:`NodeTypeEntry.default_prompt_ref`. Required when
            ``step`` is provided.
        flow_prompts_path (Optional[str]): Path string of the flow-level
            prompts file, forwarded to
            :func:`src.prompt_resolver.resolve_step_prompt` for
            path-qualified ``prompts_ref`` validation.

    Returns:
        Dict[str, Any]: A dict with keys ``model``, ``processing``,
        ``prompts``, and ``logging``, plus ``io_schema_resolved`` and
        ``prompt_resolved`` when ``step`` is supplied.

    Raises:
        ValueError: If ``step`` is supplied without ``registry``.
        KeyError: If ``step.type`` is not a registered processor
            step-type in ``registry`` (bubbled up from
            :meth:`NodeTypeRegistry.get_entry`).
    """
    runtime_config: Dict[str, Any] = {
        "model": {"name": resource.model},
        "processing": {
            "temperature": resource.temperature,
            "max_tokens_summary": resource.max_tokens_summary,
            "max_tokens_classification": resource.max_tokens_classification,
        },
        "prompts": prompts_payload,
        "logging": logging_config.model_dump(),
    }
    if step is None:
        return runtime_config
    if registry is None:
        raise ValueError(
            "_build_processor_runtime_config requires 'registry' whenever "
            "'step' is supplied, so step overrides can be resolved against "
            "the NodeTypeEntry defaults."
        )

    registry_entry = registry.get_entry(step.type)

    resolved_io_schema: Optional[IOSchema]
    if step.io_schema is not None:
        resolved_io_schema = step.io_schema
    elif registry_entry.default_io_schema is not None:
        resolved_io_schema = IOSchema(**registry_entry.default_io_schema)
    else:
        resolved_io_schema = None

    resolved_prompt: Optional[ResolvedPrompt] = resolve_step_prompt(
        step=step,
        prompts_file=prompts_payload,
        registry_entry=registry_entry,
        flow_prompts_path=flow_prompts_path,
    )

    runtime_config["io_schema_resolved"] = resolved_io_schema
    runtime_config["prompt_resolved"] = resolved_prompt
    return runtime_config


def _load_json_file(json_path: Path) -> Dict[str, Any]:
    """Read a JSON file and return its parsed contents.

    Args:
        json_path (Path): Path to the JSON file on disk.

    Returns:
        Dict[str, Any]: The parsed JSON object.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a JSON object.
    """
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    with json_path.open("r", encoding="utf-8") as json_file:
        payload = json.load(json_file)
    if not isinstance(payload, dict):
        raise ValueError(
            f"Expected a JSON object at {json_path}, got {type(payload).__name__}"
        )
    return payload


class _ConversationSummaryPlan:
    """Holder that marks whether the conversation summary pair has been executed.

    The two schema steps ``conversation_summary_first`` and
    ``conversation_summary_update`` are executed as a single sequential
    per-entity loop (matching :mod:`scripts.run_summary_conversation`).
    This helper records that the loop has already run so the second of
    the two steps does not trigger a duplicate pass.

    Attributes:
        executed (bool): ``True`` once the per-entity loop has run.
    """

    def __init__(self) -> None:
        """Initialise the plan with ``executed = False``."""
        self.executed: bool = False


class _LabelPlan:
    """Holder that marks whether the label extraction + summary pair ran.

    ``label_extraction`` and ``label_summary`` are tightly coupled: the
    runner executes both in a single pass over entities. This flag
    prevents the second step from triggering a duplicate pass.

    Attributes:
        executed (bool): ``True`` once the combined loop has run.
    """

    def __init__(self) -> None:
        """Initialise the plan with ``executed = False``."""
        self.executed: bool = False


class _Checkpoint:
    """Entity-level checkpoint manager for resumable flows.

    After each entity completes all pipeline steps the runner calls
    :meth:`mark_completed`. On resume, :meth:`completed_entity_ids`
    returns the set of entity ids that already succeeded so they can be
    skipped.

    Attributes:
        checkpoint_dir (Path): Directory where checkpoint files are
            stored.
        completed_file (Path): JSON file listing completed entity ids.
    """

    def __init__(self, output_dir: Path, flow_name: str) -> None:
        """Initialise the checkpoint under ``output_dir/.checkpoint/``.

        Args:
            output_dir (Path): Parent of the summary CSV.
            flow_name (str): Used in log messages.
        """
        self.checkpoint_dir = output_dir / ".checkpoint"
        self.completed_file = self.checkpoint_dir / "completed_entities.json"
        self._flow_name = flow_name

    def completed_entity_ids(self) -> Set[str]:
        """Load previously completed entity ids from disk.

        Returns:
            Set[str]: Entity ids (stringified) that already succeeded.
        """
        if not self.completed_file.exists():
            return set()
        with self.completed_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("completed", []))

    def mark_completed(self, entity_id: Any) -> None:
        """Append one entity id to the checkpoint file.

        Args:
            entity_id (Any): The entity id to record.
        """
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        completed = self.completed_entity_ids()
        completed.add(str(entity_id))
        with self.completed_file.open("w", encoding="utf-8") as f:
            json.dump({"completed": sorted(completed)}, f, indent=2)

    def clear(self) -> None:
        """Remove the checkpoint file to start fresh."""
        if self.completed_file.exists():
            self.completed_file.unlink()


class FlowRunner:
    """Execute a validated :class:`src.flow_loader.FlowSchema` end-to-end.

    The runner owns the input DataFrame, all output writers, the logger,
    and the asyncio semaphore used to cap concurrent LLM calls. It does not
    own any LLM-call logic: every per-turn call goes through the
    appropriate processor class from :mod:`src.processors`.

    Supported step types: every id whose category is ``processor`` in
    :mod:`src.node_registry`'s default registry
    (``config/node_types.yaml``). As of this revision that covers:

    - ``conversation_summary_first`` / ``conversation_summary_update``
    - ``single_summary``
    - ``classification``
    - ``label_extraction`` / ``label_summary`` (hybrid and full_async)

    Attributes:
        schema (FlowSchema): The validated flow definition.
        resolved_resources (Dict[str, LLMResource]): Resolved resources
            keyed by ``id``, each with ``api_base`` and ``api_key``
            populated.
        clients_by_id (Dict[str, AsyncOpenAI]): One AsyncOpenAI client per
            resource id.
        processor_configs (Dict[str, Dict[str, Any]]): Base processor
            runtime config per resource id. This dict carries only the
            resource-level keys (``model``, ``processing``, ``prompts``,
            ``logging``); step-level overrides are layered on top by
            :meth:`_resolve_processor_config_for_step` at dispatch time.
        taxonomy (Dict[str, Any]): Parsed taxonomy JSON.
        prompts (Dict[str, Any]): Parsed prompts JSON.
        registry (NodeTypeRegistry): Node-type registry used to resolve
            step-level :attr:`src.node_registry.NodeTypeEntry.default_io_schema`
            and :attr:`NodeTypeEntry.default_prompt_ref`.
        logger (logging.Logger): Logger configured for this flow.
        resume (bool): When ``True`` entity-level checkpoints are loaded
            at dispatch time and already-completed entities are skipped.

    Methods:
        run: Execute the flow synchronously by wrapping
            :meth:`run_async` in :func:`asyncio.run`.
        run_async: Execute every step of the flow on the current event
            loop.
        _resolve_processor_config_for_step: Build a per-step processor
            runtime config with ``io_schema_resolved`` and
            ``prompt_resolved`` layered onto the resource-level base.
    """

    def __init__(
        self,
        schema: FlowSchema,
        resolved_resources: Dict[str, LLMResource],
        clients_by_id: Dict[str, AsyncOpenAI],
        processor_configs: Dict[str, Dict[str, Any]],
        taxonomy: Dict[str, Any],
        prompts: Dict[str, Any],
        registry: NodeTypeRegistry,
        logger: logging.Logger,
        resume: bool = False,
    ) -> None:
        """Store the wired objects produced by :func:`build_flow`.

        Args:
            schema (FlowSchema): The validated flow definition.
            resolved_resources (Dict[str, LLMResource]): Resolved resources
                keyed by ``id``.
            clients_by_id (Dict[str, AsyncOpenAI]): One AsyncOpenAI client
                per resource id.
            processor_configs (Dict[str, Dict[str, Any]]): Base processor
                runtime config per resource id (step-level overrides
                applied lazily).
            taxonomy (Dict[str, Any]): Parsed taxonomy JSON.
            prompts (Dict[str, Any]): Parsed prompts JSON.
            registry (NodeTypeRegistry): Node-type registry used to
                resolve step-level overrides against the
                :class:`NodeTypeEntry` defaults.
            logger (logging.Logger): Logger configured for this flow.
            resume (bool): When ``True`` the runner loads entity-level
                checkpoints and skips already-completed entities.

        Returns:
            None.
        """
        self.schema = schema
        self.resolved_resources = resolved_resources
        self.clients_by_id = clients_by_id
        self.processor_configs = processor_configs
        self.taxonomy = taxonomy
        self.prompts = prompts
        self.registry = registry
        self.logger = logger
        self.resume = resume

        self._flow_prompts_path: str = schema.flow.prompts

        output_dir = Path(schema.flow.output.summary_csv).parent
        self._checkpoint = _Checkpoint(output_dir, schema.flow.name)

    def run(self) -> None:
        """Execute the flow synchronously.

        Wraps :meth:`run_async` in :func:`asyncio.run`. Suitable as the
        top-level call from a script.

        Returns:
            None.
        """
        asyncio.run(self.run_async())

    async def run_async(self) -> None:
        """Execute every step of the flow on the current event loop.

        Returns:
            None.

        Raises:
            FileNotFoundError: If the input CSV does not exist.
            KeyError: If a role column is missing from the CSV.
            NotImplementedError: If the flow declares an unimplemented step.
        """
        flow = self.schema.flow
        input_df = self._load_input_data()
        model_name = (
            self.resolved_resources["default"].model
            if "default" in self.resolved_resources
            else next(iter(self.resolved_resources.values())).model
        )

        column_roles = flow.data.column_roles
        has_entity_grouping = any(
            s.type
            in {
                "conversation_summary_first",
                "conversation_summary_update",
                "label_extraction",
                "label_summary",
            }
            or s.unit in {"document", "entity"}
            for s in flow.steps
        )

        if flow.processing_limit is not None:
            if has_entity_grouping:
                entity_ids = input_df[column_roles.entity_id].unique()[: flow.processing_limit]
                input_df = input_df[input_df[column_roles.entity_id].isin(entity_ids)]
            else:
                input_df = input_df.head(flow.processing_limit)
            self.logger.info(
                "Processing limit applied: %d %s",
                len(input_df[column_roles.entity_id].unique()) if has_entity_grouping else len(input_df),
                "entities" if has_entity_grouping else "rows",
            )

        conversation_plan = _ConversationSummaryPlan()
        label_plan = _LabelPlan()
        entity_states: List[Tuple[Any, MessyTextConversationState]] = []
        processed_df = input_df.copy()
        if "summary_all_context" not in processed_df.columns:
            processed_df["summary_all_context"] = ""

        for step_index, step in enumerate(flow.steps):
            self.logger.info(
                "Dispatching step %d/%d: type=%s unit=%s",
                step_index + 1,
                len(flow.steps),
                step.type,
                step.unit,
            )

            if step.type in {"conversation_summary_first", "conversation_summary_update"}:
                if conversation_plan.executed:
                    continue
                processed_df, entity_states = await self._run_conversation_summary(
                    df=processed_df, step=step,
                )
                conversation_plan.executed = True

            elif step.type == "single_summary":
                processed_df = await self._run_single_summary(
                    df=processed_df, step=step,
                )

            elif step.type == "classification":
                processed_df = await self._run_classification(
                    df=processed_df, step=step,
                )

            elif step.type == "label_extraction":
                if label_plan.executed:
                    continue
                label_summary_step = next(
                    (s for s in flow.steps if s.type == "label_summary"), None,
                )
                mode = "hybrid"
                if label_summary_step is not None and label_summary_step.mode == "full_async":
                    mode = "full_async"

                if mode == "full_async":
                    processed_df, entity_states = await self._run_label_full_async(
                        df=processed_df, extraction_step=step,
                        summary_step=label_summary_step,
                    )
                else:
                    processed_df, entity_states = await self._run_label_hybrid(
                        df=processed_df, extraction_step=step,
                        summary_step=label_summary_step,
                    )
                label_plan.executed = True

            elif step.type == "label_summary":
                if label_plan.executed:
                    continue
                self.logger.warning(
                    "label_summary without a preceding label_extraction step; skipping.",
                )

            else:
                raise NotImplementedError(
                    f"Step type {step.type!r} is not recognised by the runner."
                )

        self._write_outputs(
            processed_df=processed_df,
            entity_states=entity_states,
            model_name=model_name,
        )

    def _load_input_data(self) -> pd.DataFrame:
        """Load the input data file and validate that every role column exists.

        Dispatches to the appropriate pandas reader based on file extension:
        ``.csv`` uses :func:`pandas.read_csv`, ``.json`` uses
        :func:`pandas.read_json` with ``orient="records"``, and ``.jsonl``
        uses :func:`pandas.read_json` with ``lines=True``.

        Returns:
            pd.DataFrame: The loaded DataFrame.

        Raises:
            FileNotFoundError: If the data file does not exist.
            KeyError: If a role column from
                :attr:`src.flow_loader.ColumnRoles` is missing.
            ValueError: If the file extension is not supported.
        """
        data_config = self.schema.flow.data
        input_path = Path(data_config.input_csv)
        if not input_path.exists():
            raise FileNotFoundError(f"Input data file not found: {input_path}")

        extension = input_path.suffix.lower()
        if extension == ".csv":
            input_df = pd.read_csv(input_path, encoding="utf-8")
        elif extension == ".json":
            input_df = pd.read_json(input_path, orient="records", encoding="utf-8")
        elif extension == ".jsonl":
            input_df = pd.read_json(input_path, lines=True, encoding="utf-8")
        else:
            raise ValueError(
                f"Unsupported input file extension {extension!r} for "
                f"{input_path}. Supported: .csv, .json, .jsonl"
            )

        required_columns = {
            data_config.column_roles.text,
            data_config.column_roles.entity_id,
            data_config.column_roles.doc_id,
            data_config.column_roles.sort_by,
        }
        missing_columns = required_columns - set(input_df.columns)
        if missing_columns:
            raise KeyError(
                f"Input file {input_path} is missing role columns: "
                f"{sorted(missing_columns)}"
            )

        passthrough_columns = data_config.column_roles.passthrough
        if passthrough_columns:
            missing_passthrough = set(passthrough_columns) - set(input_df.columns)
            if missing_passthrough:
                raise KeyError(
                    f"Input file {input_path} is missing passthrough columns: "
                    f"{sorted(missing_passthrough)}"
                )

        return input_df

    def _select_resource_id_for_step(self, step: StepConfig) -> str:
        """Resolve the LLM resource id used by a step.

        Args:
            step (StepConfig): The step whose resource id is being resolved.

        Returns:
            str: The resource id. Falls back to ``"default"`` when the
            step does not declare ``llm``.

        Raises:
            KeyError: If the resolved id is not among the loaded resources.
        """
        resource_id = step.llm or "default"
        if resource_id not in self.resolved_resources:
            raise KeyError(
                f"Step references llm={resource_id!r}, but no resource with "
                f"that id is loaded. Available ids: "
                f"{sorted(self.resolved_resources)}"
            )
        return resource_id

    def _resolve_processor_config_for_step(
        self, step: StepConfig,
    ) -> Dict[str, Any]:
        """Return a per-step processor runtime config.

        Delegates to :func:`_build_processor_runtime_config` with the
        step, registry, and flow-level prompts path wired in so the
        returned dict carries the same base keys as
        :attr:`processor_configs` plus the resolved step-level overrides
        under ``io_schema_resolved`` and ``prompt_resolved``. Dispatchers
        pass the resulting dict straight to their processor constructors.

        Args:
            step (StepConfig): The step being dispatched. Its
                :attr:`StepConfig.llm` selects the resource; its
                :attr:`StepConfig.io_schema`, :attr:`StepConfig.prompt`,
                :attr:`StepConfig.prompts_ref`, and
                :attr:`StepConfig.prompt_overrides` feed the resolution.

        Returns:
            Dict[str, Any]: The per-step config shaped as documented by
            :func:`_build_processor_runtime_config`.

        Raises:
            KeyError: If ``step.llm`` references an unknown resource, or
                if ``step.type`` is not a registered processor step-type.
            ValueError: If ``step``'s inline prompt and ``prompts_ref``
                are both set, or if ``prompt_overrides`` is set without
                ``prompts_ref``.
        """
        resource_id = self._select_resource_id_for_step(step)
        resource = self.resolved_resources[resource_id]
        return _build_processor_runtime_config(
            resource=resource,
            prompts_payload=self.prompts,
            logging_config=self.schema.flow.logging,
            step=step,
            registry=self.registry,
            flow_prompts_path=self._flow_prompts_path,
        )

    async def _run_conversation_summary(
        self,
        df: pd.DataFrame,
        step: StepConfig,
    ) -> Tuple[pd.DataFrame, List[Tuple[Any, MessyTextConversationState]]]:
        """Run the conversation summary flow over every entity in ``df``.

        Mirrors :func:`scripts.run_summary_conversation._process_dataframe_conversation_async`:
        each entity's documents are processed sequentially with
        ``previous_summary`` threading, only informative turns update the
        running summary, and entities are processed concurrently up to
        :attr:`src.flow_loader.AsyncConfig.max_concurrent_rows`.

        Args:
            df (pd.DataFrame): The input DataFrame. Must contain the role
                columns declared in
                :attr:`src.flow_loader.ColumnRoles`.
            step (StepConfig): The step config. Used to select the LLM
                resource via :meth:`_select_resource_id_for_step`.

        Returns:
            Tuple[pd.DataFrame, List[Tuple[Any, MessyTextConversationState]]]:
            The DataFrame with ``summary_all_context`` populated, and the
            list of per-entity conversation states in completion order.

        Raises:
            KeyError: If a role column is missing after CSV load.
        """
        flow = self.schema.flow
        column_roles = flow.data.column_roles
        async_config = flow.async_config

        resource_id = self._select_resource_id_for_step(step)
        client = self.clients_by_id[resource_id]
        processor_config = self._resolve_processor_config_for_step(step)

        llm_semaphore: Optional[asyncio.Semaphore] = None
        if async_config.max_concurrent_llm_calls > 0:
            llm_semaphore = asyncio.Semaphore(async_config.max_concurrent_llm_calls)

        processor = AsyncMessyTextProcessor(
            client=client,
            config=processor_config,
            taxonomy=self.taxonomy,
            logger=self.logger,
            llm_semaphore=llm_semaphore,
        )
        turn_processor = AsyncMessyTextConversationTurnProcessor(processor)

        processed_df = df.copy()
        if "summary_all_context" not in processed_df.columns:
            processed_df["summary_all_context"] = ""

        entity_groups = list(processed_df.groupby(column_roles.entity_id))

        skip_ids: Set[str] = set()
        if self.resume:
            skip_ids = self._checkpoint.completed_entity_ids()
            if skip_ids:
                self.logger.info(
                    "Resuming: skipping %d already-completed entities.", len(skip_ids),
                )

        concurrency_semaphore = asyncio.Semaphore(async_config.max_concurrent_rows)
        tasks: List[asyncio.Future] = []
        for entity_id, group_df in entity_groups:
            if str(entity_id) in skip_ids:
                continue
            tasks.append(
                self._bounded_entity_task(
                    concurrency_semaphore=concurrency_semaphore,
                    entity_id=entity_id,
                    group_df=group_df,
                    turn_processor=turn_processor,
                    text_column=column_roles.text,
                    doc_id_column=column_roles.doc_id,
                    sort_column=column_roles.sort_by,
                )
            )

        use_progress_bar = flow.display.use_progress_bar
        entity_results: List[Tuple[Any, Dict[int, str], MessyTextConversationState]] = []
        for completed in tqdm_async.as_completed(
            tasks,
            total=len(tasks),
            desc="Processing entities (conversation)",
            disable=not use_progress_bar,
        ):
            entity_results.append(await completed)

        for _entity_id, index_to_summary, _state in entity_results:
            for row_index, running_summary in index_to_summary.items():
                processed_df.at[row_index, "summary_all_context"] = running_summary
            self._checkpoint.mark_completed(_entity_id)

        entity_states: List[Tuple[Any, MessyTextConversationState]] = [
            (entity_id, state) for entity_id, _index_to_summary, state in entity_results
        ]
        return processed_df, entity_states

    async def _bounded_entity_task(
        self,
        concurrency_semaphore: asyncio.Semaphore,
        entity_id: Any,
        group_df: pd.DataFrame,
        turn_processor: AsyncMessyTextConversationTurnProcessor,
        text_column: str,
        doc_id_column: str,
        sort_column: str,
    ) -> Tuple[Any, Dict[int, str], MessyTextConversationState]:
        """Run :meth:`_process_entity` under the outer concurrency cap.

        Args:
            concurrency_semaphore (asyncio.Semaphore): Caps the number of
                entities processed in parallel.
            entity_id (Any): The entity identifier from the groupby.
            group_df (pd.DataFrame): All rows that belong to this entity.
            turn_processor (AsyncMessyTextConversationTurnProcessor):
                Per-turn processor shared across entities.
            text_column (str): Name of the text column in ``group_df``.
            doc_id_column (str): Name of the document-id column.
            sort_column (str): Name of the ordering column.

        Returns:
            Tuple[Any, Dict[int, str], MessyTextConversationState]: The
            entity id, the row-index-to-running-summary mapping, and the
            final conversation state.
        """
        async with concurrency_semaphore:
            return await self._process_entity(
                entity_id=entity_id,
                group_df=group_df,
                turn_processor=turn_processor,
                text_column=text_column,
                doc_id_column=doc_id_column,
                sort_column=sort_column,
            )

    async def _process_entity(
        self,
        entity_id: Any,
        group_df: pd.DataFrame,
        turn_processor: AsyncMessyTextConversationTurnProcessor,
        text_column: str,
        doc_id_column: str,
        sort_column: str,
    ) -> Tuple[Any, Dict[int, str], MessyTextConversationState]:
        """Sequentially process every document belonging to one entity.

        Each turn calls
        :meth:`src.processors.AsyncMessyTextConversationTurnProcessor.process_turn`
        with the current running summary as ``previous_summary``. Only
        turns whose ``info_found`` flag is truthy (or, as a fallback, whose
        summary text passes :func:`src.utils.is_informative_summary`)
        update the running summary, matching the behaviour of
        :mod:`scripts.run_summary_conversation`.

        Args:
            entity_id (Any): The entity identifier from the groupby.
            group_df (pd.DataFrame): Rows for this entity.
            turn_processor (AsyncMessyTextConversationTurnProcessor):
                Per-turn processor.
            text_column (str): Name of the text column.
            doc_id_column (str): Name of the document-id column.
            sort_column (str): Name of the ordering column.

        Returns:
            Tuple[Any, Dict[int, str], MessyTextConversationState]: The
            entity id, a mapping from the DataFrame row index to the
            running summary as of that turn, and the final conversation
            state containing every per-turn
            :class:`src.processors.ProcessorResult`.
        """
        group_sorted = group_df.sort_values(by=sort_column)
        dataframe_indices: List[int] = group_sorted.index.tolist()
        document_texts: List[str] = [str(text) for text in group_sorted[text_column]]
        document_ids: List[Any] = list(group_sorted[doc_id_column])

        running_summary: str = ""
        conversation_state = MessyTextConversationState(turn_index=0)
        per_row_running_summaries: List[str] = []

        for document_id, raw_text in zip(document_ids, document_texts):
            candidate_summary, turn_state = await turn_processor.process_turn(
                raw_text=raw_text,
                state=conversation_state,
                doc_id=document_id,
            )

            turn_result = getattr(turn_state, "last_result", None)

            has_info = False
            if turn_result is not None and hasattr(turn_result, "has_field") and turn_result.has_field("info_found"):
                info_flag = str(turn_result.get("info_found") or "").strip().lower()
                has_info = info_flag not in {"", "false", "0", "no"}
            elif turn_result is not None and hasattr(turn_result, "is_no_info"):
                has_info = not turn_result.is_no_info()
            else:
                has_info = is_informative_summary(candidate_summary)

            if has_info:
                structured_summary = (
                    turn_result.get("summary") if turn_result is not None else candidate_summary
                )
                running_summary = (structured_summary or "").strip()

            per_row_running_summaries.append(running_summary)
            conversation_state = turn_state

        index_to_running_summary: Dict[int, str] = {
            row_index: summary
            for row_index, summary in zip(dataframe_indices, per_row_running_summaries)
        }
        return entity_id, index_to_running_summary, conversation_state

    # ------------------------------------------------------------------
    # single_summary dispatcher  (matches run_summary.py)
    # ------------------------------------------------------------------

    async def _run_single_summary(
        self,
        df: pd.DataFrame,
        step: StepConfig,
    ) -> pd.DataFrame:
        """Summarise every row independently (no entity grouping).

        Mirrors the async path in ``scripts/run_summary.py``: each row
        passes through ``AsyncMessyTextProcessor.summarize_text`` with
        concurrency capped by ``max_concurrent_rows``.

        Args:
            df (pd.DataFrame): Input DataFrame.
            step (StepConfig): Step config for resource selection.

        Returns:
            pd.DataFrame: DataFrame with ``summary_all_context`` populated.
        """
        flow = self.schema.flow
        column_roles = flow.data.column_roles
        async_config = flow.async_config

        resource_id = self._select_resource_id_for_step(step)
        client = self.clients_by_id[resource_id]
        processor_config = self._resolve_processor_config_for_step(step)

        llm_semaphore: Optional[asyncio.Semaphore] = None
        if async_config.max_concurrent_llm_calls > 0:
            llm_semaphore = asyncio.Semaphore(async_config.max_concurrent_llm_calls)

        processor = AsyncMessyTextProcessor(
            client=client, config=processor_config,
            taxonomy=self.taxonomy, logger=self.logger,
            llm_semaphore=llm_semaphore,
        )

        processed_df = df.copy()
        if "summary_all_context" not in processed_df.columns:
            processed_df["summary_all_context"] = ""

        semaphore = asyncio.Semaphore(async_config.max_concurrent_rows)

        async def _summarise_row(row_index: int, text: str, doc_id: Any) -> Tuple[int, str]:
            async with semaphore:
                cleaned = processor.clean_text(text)
                if cleaned.strip():
                    summary = await processor.summarize_text(cleaned, doc_id=doc_id)
                else:
                    summary = "No relevant information found"
                return row_index, summary

        tasks = []
        for row in processed_df.itertuples():
            text = str(getattr(row, column_roles.text, ""))
            doc_id = getattr(row, column_roles.doc_id, row.Index)
            tasks.append(_summarise_row(row.Index, text, doc_id))

        use_pb = flow.display.use_progress_bar
        for completed in tqdm_async.as_completed(
            tasks, total=len(tasks),
            desc="Summarising rows", disable=not use_pb,
        ):
            row_index, summary = await completed
            processed_df.at[row_index, "summary_all_context"] = summary

        return processed_df

    # ------------------------------------------------------------------
    # classification dispatcher  (matches run_classification.py)
    # ------------------------------------------------------------------

    async def _run_classification(
        self,
        df: pd.DataFrame,
        step: StepConfig,
    ) -> pd.DataFrame:
        """Classify every row using its existing ``summary_all_context``.

        Mirrors the async path in ``scripts/run_classification.py``: each
        row's summary is classified per taxonomy key concurrently.

        Args:
            df (pd.DataFrame): Input DataFrame (must have
                ``summary_all_context``).
            step (StepConfig): Step config; ``step.keys`` can restrict
                the taxonomy keys to a subset.

        Returns:
            pd.DataFrame: DataFrame with ``{key}_classification`` columns.
        """
        flow = self.schema.flow
        async_config = flow.async_config

        resource_id = self._select_resource_id_for_step(step)
        client = self.clients_by_id[resource_id]
        processor_config = self._resolve_processor_config_for_step(step)

        llm_semaphore: Optional[asyncio.Semaphore] = None
        if async_config.max_concurrent_llm_calls > 0:
            llm_semaphore = asyncio.Semaphore(async_config.max_concurrent_llm_calls)

        processor = AsyncMessyTextProcessor(
            client=client, config=processor_config,
            taxonomy=self.taxonomy, logger=self.logger,
            llm_semaphore=llm_semaphore,
        )

        all_keys = list(self.taxonomy.get("context_definitions", {}).keys())
        if step.keys is not None and step.keys != "all":
            keys_to_classify = [k for k in step.keys if k in all_keys]
        else:
            keys_to_classify = all_keys

        processed_df = df.copy()
        for key in all_keys:
            col = f"{key}_classification"
            if col not in processed_df.columns:
                processed_df[col] = ""

        semaphore = asyncio.Semaphore(async_config.max_concurrent_rows)

        async def _classify_row(row_index: int, summary: str, doc_id: Any) -> Tuple[int, Dict[str, str]]:
            async with semaphore:
                results: Dict[str, str] = {}
                if summary and summary != "No relevant information found":
                    cls_tasks = [processor.classify_summary(summary, key) for key in keys_to_classify]
                    cls_results = await asyncio.gather(*cls_tasks)
                    for key, cls_value in zip(keys_to_classify, cls_results):
                        results[f"{key}_classification"] = cls_value
                return row_index, results

        column_roles = flow.data.column_roles
        tasks = []
        for row in processed_df.itertuples():
            summary = getattr(row, "summary_all_context", "")
            doc_id = getattr(row, column_roles.doc_id, row.Index)
            tasks.append(_classify_row(row.Index, summary, doc_id))

        use_pb = flow.display.use_progress_bar
        for completed in tqdm_async.as_completed(
            tasks, total=len(tasks),
            desc="Classifying rows", disable=not use_pb,
        ):
            row_index, cls_results = await completed
            for col, val in cls_results.items():
                processed_df.at[row_index, col] = val

        return processed_df

    # ------------------------------------------------------------------
    # label_extraction + label_summary (hybrid) dispatcher
    # ------------------------------------------------------------------

    def _build_extractors(
        self,
        step: StepConfig,
    ) -> Tuple[Dict[str, AsyncLabelExtractor], Optional[asyncio.Semaphore]]:
        """Build one ``AsyncLabelExtractor`` per taxonomy label.

        Args:
            step (StepConfig): Step config for resource selection.

        Returns:
            Tuple[Dict[str, AsyncLabelExtractor], Optional[asyncio.Semaphore]]:
            Extractor dict keyed by taxonomy label, plus the shared LLM
            semaphore (or ``None``).
        """
        flow = self.schema.flow
        async_config = flow.async_config

        resource_id = self._select_resource_id_for_step(step)
        client = self.clients_by_id[resource_id]
        processor_config = self._resolve_processor_config_for_step(step)

        llm_semaphore: Optional[asyncio.Semaphore] = None
        if async_config.max_concurrent_llm_calls > 0:
            llm_semaphore = asyncio.Semaphore(async_config.max_concurrent_llm_calls)

        context_definitions: Dict[str, str] = self.taxonomy.get("context_definitions", {})
        extractors: Dict[str, AsyncLabelExtractor] = {}
        for label_key, label_definition in context_definitions.items():
            extractors[label_key] = AsyncLabelExtractor(
                client=client, config=processor_config,
                label_key=label_key, label_definition=label_definition,
                logger=self.logger, llm_semaphore=llm_semaphore,
            )
        return extractors, llm_semaphore

    async def _run_label_hybrid(
        self,
        df: pd.DataFrame,
        extraction_step: StepConfig,
        summary_step: Optional[StepConfig],
    ) -> Tuple[pd.DataFrame, List[Tuple[Any, MessyTextConversationState]]]:
        """Hybrid label pipeline: sequential docs, concurrent labels.

        Mirrors ``_process_dataframe_hybrid`` in
        ``scripts/run_summary_conversation_by_label.py``.

        Args:
            df (pd.DataFrame): Input DataFrame.
            extraction_step (StepConfig): Config for label_extraction.
            summary_step (Optional[StepConfig]): Config for label_summary.

        Returns:
            Tuple of processed DataFrame and entity states.
        """
        flow = self.schema.flow
        column_roles = flow.data.column_roles
        async_config = flow.async_config

        extractors, llm_semaphore = self._build_extractors(extraction_step)

        effective_summary_step = summary_step or extraction_step
        summary_resource_id = self._select_resource_id_for_step(
            effective_summary_step
        )
        summary_client = self.clients_by_id[summary_resource_id]
        summary_config = self._resolve_processor_config_for_step(
            effective_summary_step
        )

        summary_processor = AsyncTextLabelsSummaryProcessor(
            client=summary_client, config=summary_config,
            taxonomy=self.taxonomy, logger=self.logger,
            llm_semaphore=llm_semaphore,
        )

        processed_df = df.copy()
        if "summary_all_context" not in processed_df.columns:
            processed_df["summary_all_context"] = ""

        entity_groups = list(processed_df.groupby(column_roles.entity_id))

        skip_ids: Set[str] = set()
        if self.resume:
            skip_ids = self._checkpoint.completed_entity_ids()
            if skip_ids:
                self.logger.info(
                    "Resuming (label hybrid): skipping %d entities.", len(skip_ids),
                )
            entity_groups = [
                (eid, gdf) for eid, gdf in entity_groups if str(eid) not in skip_ids
            ]

        concurrency_sem = asyncio.Semaphore(async_config.max_concurrent_rows)

        async def _process_entity_hybrid(
            entity_id: Any, group_df: pd.DataFrame,
        ) -> Tuple[Any, Dict[int, str], MessyTextConversationState]:
            async with concurrency_sem:
                group_sorted = group_df.sort_values(by=column_roles.sort_by)
                index_list = group_sorted.index.tolist()
                texts = [str(t) for t in group_sorted[column_roles.text]]
                doc_ids = list(group_sorted[column_roles.doc_id])

                state = MessyTextConversationState(turn_index=0)
                per_row_summaries: List[str] = []

                for doc_id, raw_text in zip(doc_ids, texts):
                    label_keys = list(extractors.keys())
                    extract_tasks = [
                        extractors[k].extract_label(text=raw_text, doc_id=doc_id)
                        for k in label_keys
                    ]
                    extract_results = await asyncio.gather(*extract_tasks)
                    label_results: Dict[str, ProcessorResult] = dict(
                        zip(label_keys, extract_results)
                    )

                    result = await summary_processor.summarize_from_labels(
                        text=raw_text, label_results=label_results,
                        previous_summary=state.last_summary, doc_id=doc_id,
                    )

                    new_results = state.results.copy()
                    new_results.append(result)
                    state = MessyTextConversationState(
                        turn_index=state.turn_index + 1, results=new_results,
                    )
                    per_row_summaries.append(result.get("summary") or "")

                idx_to_summary = dict(zip(index_list, per_row_summaries))
                return entity_id, idx_to_summary, state

        tasks = [_process_entity_hybrid(eid, gdf) for eid, gdf in entity_groups]
        use_pb = flow.display.use_progress_bar
        entity_results: List[Tuple[Any, Dict[int, str], MessyTextConversationState]] = []
        for completed in tqdm_async.as_completed(
            tasks, total=len(tasks),
            desc="Processing entities (label hybrid)", disable=not use_pb,
        ):
            entity_results.append(await completed)

        for _eid, idx_to_summary, _st in entity_results:
            for row_idx, summary in idx_to_summary.items():
                processed_df.at[row_idx, "summary_all_context"] = summary
            self._checkpoint.mark_completed(_eid)

        entity_states = [(eid, st) for eid, _, st in entity_results]
        return processed_df, entity_states

    # ------------------------------------------------------------------
    # label_extraction + label_summary (full_async) dispatcher
    # ------------------------------------------------------------------

    async def _run_label_full_async(
        self,
        df: pd.DataFrame,
        extraction_step: StepConfig,
        summary_step: Optional[StepConfig],
    ) -> Tuple[pd.DataFrame, List[Tuple[Any, MessyTextConversationState]]]:
        """Full-async label pipeline: all docs concurrent, then synthesis.

        Mirrors ``_process_dataframe_full_async`` in
        ``scripts/run_summary_conversation_by_label.py``.

        Args:
            df (pd.DataFrame): Input DataFrame.
            extraction_step (StepConfig): Config for label_extraction.
            summary_step (Optional[StepConfig]): Config for label_summary.

        Returns:
            Tuple of processed DataFrame and entity states.
        """
        flow = self.schema.flow
        column_roles = flow.data.column_roles
        async_config = flow.async_config

        extractors, llm_semaphore = self._build_extractors(extraction_step)

        effective_summary_step = summary_step or extraction_step
        summary_resource_id = self._select_resource_id_for_step(
            effective_summary_step
        )
        summary_client = self.clients_by_id[summary_resource_id]
        summary_config = self._resolve_processor_config_for_step(
            effective_summary_step
        )

        summary_processor = AsyncTextLabelsSummaryProcessor(
            client=summary_client, config=summary_config,
            taxonomy=self.taxonomy, logger=self.logger,
            llm_semaphore=llm_semaphore,
        )
        orchestrator = AsyncTextConversationOrchestrator(summary_processor)

        processed_df = df.copy()
        if "summary_all_context" not in processed_df.columns:
            processed_df["summary_all_context"] = ""

        entity_groups = list(processed_df.groupby(column_roles.entity_id))

        skip_ids: Set[str] = set()
        if self.resume:
            skip_ids = self._checkpoint.completed_entity_ids()
            if skip_ids:
                self.logger.info(
                    "Resuming (label full-async): skipping %d entities.", len(skip_ids),
                )
            entity_groups = [
                (eid, gdf) for eid, gdf in entity_groups if str(eid) not in skip_ids
            ]

        concurrency_sem = asyncio.Semaphore(async_config.max_concurrent_rows)

        async def _process_entity_full_async(
            entity_id: Any, group_df: pd.DataFrame,
        ) -> Tuple[Any, Dict[int, str], MessyTextConversationState]:
            async with concurrency_sem:
                group_sorted = group_df.sort_values(by=column_roles.sort_by)
                index_list = group_sorted.index.tolist()
                texts = [str(t) for t in group_sorted[column_roles.text]]
                doc_ids = list(group_sorted[column_roles.doc_id])

                label_keys = list(extractors.keys())
                n_labels = len(label_keys)
                all_extract_tasks = []
                for doc_id, text in zip(doc_ids, texts):
                    for k in label_keys:
                        all_extract_tasks.append(
                            extractors[k].extract_label(text=text, doc_id=doc_id)
                        )
                all_extract_results = await asyncio.gather(*all_extract_tasks)

                per_doc_label_results: List[Dict[str, ProcessorResult]] = []
                for i in range(len(texts)):
                    offset = i * n_labels
                    per_doc_label_results.append({
                        label_keys[j]: all_extract_results[offset + j]
                        for j in range(n_labels)
                    })

                documents: List[Tuple[str, Dict[str, ProcessorResult], Any]] = [
                    (text, lr, did)
                    for text, lr, did in zip(texts, per_doc_label_results, doc_ids)
                ]

                _summaries, state = await orchestrator.run_conversation(
                    documents=documents,
                    use_progress_bar=False,
                )

                per_doc_summaries = [
                    str(r.get("summary") or "") for r in state.results
                ]
                synthesis_result = await summary_processor.synthesize_from_summaries(
                    per_doc_summaries=per_doc_summaries, doc_id=entity_id,
                )

                new_results = state.results.copy()
                new_results.append(synthesis_result)
                state = MessyTextConversationState(
                    turn_index=state.turn_index + 1, results=new_results,
                )

                final_summary = synthesis_result.get("summary") or ""
                idx_to_summary = {row_idx: final_summary for row_idx in index_list}
                return entity_id, idx_to_summary, state

        tasks = [_process_entity_full_async(eid, gdf) for eid, gdf in entity_groups]
        use_pb = flow.display.use_progress_bar
        entity_results: List[Tuple[Any, Dict[int, str], MessyTextConversationState]] = []
        for completed in tqdm_async.as_completed(
            tasks, total=len(tasks),
            desc="Processing entities (label full-async)", disable=not use_pb,
        ):
            entity_results.append(await completed)

        for _eid, idx_to_summary, _st in entity_results:
            for row_idx, summary in idx_to_summary.items():
                processed_df.at[row_idx, "summary_all_context"] = summary
            self._checkpoint.mark_completed(_eid)

        entity_states = [(eid, st) for eid, _, st in entity_results]
        return processed_df, entity_states

    def _write_outputs(
        self,
        processed_df: pd.DataFrame,
        entity_states: List[Tuple[Any, MessyTextConversationState]],
        model_name: str,
    ) -> None:
        """Write every output CSV declared in :class:`src.flow_loader.OutputConfig`.

        Creates parent directories as needed. The per-row summary CSV is
        always written. The per-turn results, per-entity states, and
        flattened spans CSVs are written only when their output paths are
        configured.

        Args:
            processed_df (pd.DataFrame): DataFrame augmented with
                ``summary_all_context`` and ``model``.
            entity_states (List[Tuple[Any, MessyTextConversationState]]):
                Per-entity conversation states.
            model_name (str): Model identifier used for the ``model``
                column and the extend-mode replacement key.

        Returns:
            None.
        """
        output_config = self.schema.flow.output
        passthrough_columns = self.schema.flow.data.column_roles.passthrough
        processed_df = processed_df.copy()
        processed_df["model"] = model_name
        if "summary_all_context" in processed_df.columns:
            processed_df["summary_all_context"] = processed_df["summary_all_context"].replace(
                ["No information", "No relevant information found"],
                "",
            )

        if passthrough_columns:
            dropped_passthrough = [
                col for col in passthrough_columns
                if col not in processed_df.columns
            ]
            if dropped_passthrough:
                self.logger.warning(
                    "Passthrough columns dropped during processing: %s. "
                    "Re-adding them from the input DataFrame is not possible "
                    "at this stage.",
                    dropped_passthrough,
                )
            else:
                self.logger.info(
                    "Passthrough columns preserved in output: %s",
                    passthrough_columns,
                )

        summary_path = Path(output_config.summary_csv)
        summary_path.parent.mkdir(parents=True, exist_ok=True)

        if output_config.extend and summary_path.exists():
            existing_df = pd.read_csv(summary_path, encoding="utf-8")
            if "model" in existing_df.columns:
                existing_df = existing_df[existing_df["model"] != model_name]
            combined_df = pd.concat([existing_df, processed_df], ignore_index=True)
            combined_df.to_csv(summary_path, index=False, encoding="utf-8")
            self.logger.info(
                "Summary output extended: %d existing + %d new = %d total rows",
                len(existing_df),
                len(processed_df),
                len(combined_df),
            )
        else:
            processed_df.to_csv(summary_path, index=False, encoding="utf-8")
            self.logger.info(
                "Summary output saved to %s (%d rows)",
                summary_path,
                len(processed_df),
            )

        if not entity_states:
            return

        results_rows: List[Dict[str, Any]] = []
        states_rows: List[Dict[str, Any]] = []
        spans_rows: List[Dict[str, Any]] = []

        passthrough_lookup: Dict[Any, Dict[str, Any]] = {}
        if passthrough_columns:
            doc_id_column = self.schema.flow.data.column_roles.doc_id
            for row in processed_df.itertuples():
                row_doc_id = getattr(row, doc_id_column, None)
                passthrough_lookup[row_doc_id] = {
                    col: getattr(row, col, None) for col in passthrough_columns
                }

        for entity_id, state in entity_states:
            states_rows.append(
                serialize_state_entry(
                    state=state,
                    victim_id=str(entity_id),
                    model_name=model_name,
                )
            )
            spans_rows.extend(
                flatten_spans_from_state(
                    state=state,
                    victim_id=str(entity_id),
                    model_name=model_name,
                )
            )
            for turn_index, turn_result in enumerate(state.results):
                result_row = serialize_result_entry(
                    result=turn_result,
                    victim_id=str(entity_id),
                    model_name=model_name,
                    turn_index=turn_index,
                )
                if passthrough_columns and turn_result.doc_id in passthrough_lookup:
                    result_row.update(passthrough_lookup[turn_result.doc_id])
                results_rows.append(result_row)

        if output_config.results_csv is not None:
            results_path = Path(output_config.results_csv)
            results_path.parent.mkdir(parents=True, exist_ok=True)
            write_results(
                rows=results_rows,
                path=results_path,
                extend=output_config.extend,
                model_name=model_name,
            )
            self.logger.info(
                "Results records saved to %s (%d rows)",
                results_path,
                len(results_rows),
            )

        if output_config.states_csv is not None:
            states_path = Path(output_config.states_csv)
            states_path.parent.mkdir(parents=True, exist_ok=True)
            write_states(
                rows=states_rows,
                path=states_path,
                extend=output_config.extend,
                model_name=model_name,
            )
            self.logger.info(
                "State records saved to %s (%d rows)",
                states_path,
                len(states_rows),
            )

        if output_config.spans_csv is not None:
            spans_path = Path(output_config.spans_csv)
            spans_path.parent.mkdir(parents=True, exist_ok=True)
            write_spans(
                rows=spans_rows,
                path=spans_path,
                extend=output_config.extend,
                model_name=model_name,
            )
            self.logger.info(
                "Span records saved to %s (%d rows)",
                spans_path,
                len(spans_rows),
            )


TAXONOMY_URI_PREFIX: str = "taxonomy://"
"""Prefix used by the GUI to reference server-managed taxonomies by id."""


def _is_taxonomy_uri(taxonomy_value: str) -> bool:
    """Check whether ``taxonomy_value`` is a ``taxonomy://`` URI.

    Args:
        taxonomy_value (str): The raw taxonomy string from the flow YAML.

    Returns:
        bool: ``True`` when the string starts with :data:`TAXONOMY_URI_PREFIX`.
    """
    return taxonomy_value.startswith(TAXONOMY_URI_PREFIX)


def _parse_taxonomy_id_from_uri(taxonomy_uri: str) -> str:
    """Extract the taxonomy id from a ``taxonomy://<id>`` URI.

    Args:
        taxonomy_uri (str): A string that starts with
            :data:`TAXONOMY_URI_PREFIX`.

    Returns:
        str: The id portion after the prefix.

    Raises:
        ValueError: If the id portion is empty.
    """
    taxonomy_id = taxonomy_uri[len(TAXONOMY_URI_PREFIX):]
    if not taxonomy_id:
        raise ValueError(
            f"taxonomy URI {taxonomy_uri!r} has no id after the "
            f"{TAXONOMY_URI_PREFIX!r} prefix."
        )
    return taxonomy_id


def build_flow(
    flow_yaml_path: Path,
    resume: bool = False,
    *,
    taxonomy_override: Optional[Dict[str, Any]] = None,
) -> FlowRunner:
    """Build a :class:`FlowRunner` from a flow YAML file.

    Args:
        flow_yaml_path (Path): Path to the flow YAML file on disk.
        resume (bool): When ``True`` the runner loads entity-level
            checkpoints and skips already-completed entities.
        taxonomy_override (Optional[Dict[str, Any]]): Pre-loaded taxonomy
            payload. When supplied, the builder uses this dict directly
            instead of loading from the filesystem path in
            ``flow_config.taxonomy``. Used by the server's Celery worker
            to inject taxonomy data resolved from a ``taxonomy://<id>``
            URI via :class:`server.services.taxonomy_repository.TaxonomyRepository`.

    Returns:
        FlowRunner: The configured runner.

    Raises:
        FileNotFoundError: If the flow YAML, taxonomy, or prompts file is
            missing.
        ValueError: If schema validation fails, an ``api_key_env``
            variable is not present in the environment, or a
            ``taxonomy://`` URI is encountered without a
            ``taxonomy_override``.
    """
    _load_dotenv_into_environ(_PROJECT_ROOT)

    schema = FlowSchema.load_from_path(Path(flow_yaml_path))
    flow_config = schema.flow

    if taxonomy_override is not None:
        taxonomy_payload = taxonomy_override
    elif _is_taxonomy_uri(flow_config.taxonomy):
        raise ValueError(
            f"Flow references taxonomy URI {flow_config.taxonomy!r}, but no "
            "taxonomy_override was supplied. taxonomy:// URIs require the "
            "server's TaxonomyRepository to resolve. When running from the "
            "CLI, use a filesystem path instead."
        )
    else:
        taxonomy_payload = _load_json_file(Path(flow_config.taxonomy))
    prompts_payload = _load_json_file(Path(flow_config.prompts))

    registry = get_default_registry()

    logger = setup_logger(log_file=flow_config.logging.file)

    resolved_resources: Dict[str, LLMResource] = {}
    clients_by_id: Dict[str, AsyncOpenAI] = {}
    processor_configs: Dict[str, Dict[str, Any]] = {}

    for raw_resource in flow_config.resources:
        resolved_resource = _resolve_resource_credentials(raw_resource)
        resolved_resources[resolved_resource.id] = resolved_resource
        clients_by_id[resolved_resource.id] = _build_async_client(
            resource=resolved_resource,
            max_retries=flow_config.async_config.max_retries,
        )
        processor_configs[resolved_resource.id] = _build_processor_runtime_config(
            resource=resolved_resource,
            prompts_payload=prompts_payload,
            logging_config=flow_config.logging,
        )

    logger.info(
        "Flow %r loaded with %d resource(s) and %d step(s).",
        flow_config.name,
        len(resolved_resources),
        len(flow_config.steps),
    )

    return FlowRunner(
        schema=schema,
        resolved_resources=resolved_resources,
        clients_by_id=clients_by_id,
        processor_configs=processor_configs,
        taxonomy=taxonomy_payload,
        prompts=prompts_payload,
        registry=registry,
        logger=logger,
        resume=resume,
    )
