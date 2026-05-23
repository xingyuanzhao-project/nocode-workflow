"""Configuration-driven flow builder and runner.

Turns a validated :class:`src.flow_loader.FlowSchema` into a ready-to-execute
pipeline using :class:`src.processors.GenericProcessor`. The processor receives
user-configured io_schema and prompt instructions, calls the LLM, and returns
all response fields dynamically — no hardcoded field names.

The flow YAML stores an explicit graph (``flow.nodes[]`` / ``flow.edges[]``);
:class:`src.flow_loader.FlowSchema.load_from_path` compiles the graph into a
runtime :class:`src.flow_loader.FlowConfig` exposed as ``schema.flow``.

Public API:
- :func:`build_flow` — loads YAML, resolves credentials, returns a FlowRunner.
- :class:`FlowRunner` — owns execution. Dispatches each processor step via
  ``_run_generic()`` which fires all rows concurrently.
"""

from __future__ import annotations

import asyncio
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
    LOCAL_PROVIDERS,
    LoggingConfig,
    PROVIDER_DEFAULT_API_BASE,
    StepConfig,
)
from src.io_schema import IOSchema
from src.node_registry import NodeTypeRegistry, get_default_registry
from src.processors import GenericProcessor
from src.prompt_resolver import ResolvedPrompt, resolve_step_prompt
from src.utils import setup_logger


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
    elif resource.provider in LOCAL_PROVIDERS:
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
        self._input_columns = self._read_input_columns()
        self._output_fields = self._resolve_output_fields()
        self._output_col = self._output_fields[0]

        output_dir = Path(schema.flow.output.summary_csv).parent
        self._checkpoint = _Checkpoint(output_dir, schema.flow.name)

    def _read_input_columns(self) -> List[str]:
        """Read the list of selected input columns from the data input node.

        Supports three formats for backward compatibility:
        - New: ``input_columns: ["col1", "col2"]`` (plain list of strings)
        - Legacy object: ``input_columns: [{role: "text", column: "col1"}]``
        - Legacy flat: ``column_roles: {text: "col1"}``

        Returns an empty list if nothing is configured (caller will default
        to all DataFrame columns).
        """
        for node in self.schema.document.nodes:
            if node.type in {"csv_input", "json_input"}:
                input_columns = node.config.get("input_columns", [])
                if isinstance(input_columns, list):
                    result: List[str] = []
                    for entry in input_columns:
                        if isinstance(entry, str) and entry:
                            result.append(entry)
                        elif (
                            isinstance(entry, dict)
                            and "column" in entry
                            and entry["column"]
                        ):
                            result.append(str(entry["column"]))
                    if result:
                        return result
                raw = node.config.get("column_roles", {})
                if isinstance(raw, dict) and raw:
                    return [str(v) for v in raw.values() if v]
        return []

    def _resolve_output_fields(self) -> List[str]:
        """Read ``output_fields`` from the first output node's config.

        Falls back to ``["summary_all_context"]`` when no output node
        declares the field, preserving backward compatibility with flows
        authored before this feature was added.
        """
        for node in self.schema.document.nodes:
            if node.type in {"csv_output", "json_output"}:
                raw = node.config.get("output_fields")
                if isinstance(raw, list) and raw:
                    fields = [str(f) for f in raw if f]
                    if fields:
                        return fields
        return ["summary_all_context"]

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
            NotImplementedError: If the flow declares an unimplemented step.
        """
        flow = self.schema.flow
        input_df = self._load_input_data()
        model_name = (
            self.resolved_resources["default"].model
            if "default" in self.resolved_resources
            else next(iter(self.resolved_resources.values())).model
        )

        if flow.processing_limit is not None:
            input_df = input_df.head(flow.processing_limit)
            self.logger.info(
                "Processing limit applied: %d rows", len(input_df),
            )

        processed_df = input_df.copy()
        for _field in self._output_fields:
            if _field not in processed_df.columns:
                processed_df[_field] = ""

        for step_index, step in enumerate(flow.steps):
            self.logger.info(
                "Dispatching step %d/%d: type=%s",
                step_index + 1, len(flow.steps), step.type,
            )

            if step.type == "processor":
                processed_df = await self._run_generic(
                    df=processed_df, step=step,
                )
            else:
                raise NotImplementedError(
                    f"Step type {step.type!r} is not recognised by the runner."
                )

        self._write_outputs(processed_df=processed_df, model_name=model_name)

    def _load_input_data(self) -> pd.DataFrame:
        """Load the input data file.

        Dispatches to the appropriate pandas reader based on file extension:
        ``.csv`` uses :func:`pandas.read_csv`, ``.json`` uses
        :func:`pandas.read_json` with ``orient="records"``, and ``.jsonl``
        uses :func:`pandas.read_json` with ``lines=True``.

        Returns:
            pd.DataFrame: The loaded DataFrame with all columns passed through.

        Raises:
            FileNotFoundError: If the data file does not exist.
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

    async def _run_generic(
        self,
        df: pd.DataFrame,
        step: StepConfig,
    ) -> pd.DataFrame:
        """Run the generic processor on every row concurrently.

        Builds a :class:`GenericProcessor` from the step's resolved
        io_schema and prompt, then fires all rows in parallel bounded
        by ``max_concurrent_rows``. Each row's result dict is spread
        into the DataFrame's output columns.
        """
        flow = self.schema.flow
        async_config = flow.async_config

        resource_id = self._select_resource_id_for_step(step)
        client = self.clients_by_id[resource_id]
        processor_config = self._resolve_processor_config_for_step(step)

        io_schema: Optional[IOSchema] = processor_config.get("io_schema_resolved")
        if io_schema is None or not io_schema.output:
            raise ValueError(
                "Step has no io_schema with output fields. "
                "Configure output fields in the processor's config panel."
            )

        prompt_resolved = processor_config.get("prompt_resolved")
        if prompt_resolved is None or not prompt_resolved.instructions:
            raise ValueError(
                "Step has no prompt instructions. "
                "Configure instructions in the processor's config panel."
            )

        llm_semaphore: Optional[asyncio.Semaphore] = None
        if async_config.max_concurrent_llm_calls > 0:
            llm_semaphore = asyncio.Semaphore(async_config.max_concurrent_llm_calls)

        model_name = processor_config["model"]["name"]
        temperature = processor_config["processing"].get("temperature", 0.3)
        max_tokens = processor_config["processing"].get("max_tokens_summary", 4096)

        processor = GenericProcessor(
            client=client,
            io_schema=io_schema,
            instructions=prompt_resolved.instructions,
            model_name=model_name,
            logger=self.logger,
            temperature=temperature,
            max_tokens=max_tokens,
            llm_semaphore=llm_semaphore,
        )

        processed_df = df.copy()
        row_semaphore = asyncio.Semaphore(async_config.max_concurrent_rows)
        output_keys = list(io_schema.output.keys())

        selected_columns = self._input_columns
        if not selected_columns:
            selected_columns = [
                c for c in processed_df.columns if c not in output_keys
            ]

        async def _process_row(
            row_index: int, input_fields: Dict[str, str],
        ) -> Tuple[int, Dict[str, Any]]:
            async with row_semaphore:
                cleaned_fields = {
                    k: processor.clean_text(v) for k, v in input_fields.items()
                }
                if all(not v.strip() for v in cleaned_fields.values()):
                    return row_index, {k: "" for k in output_keys}
                result = await processor.execute(cleaned_fields, row_index=row_index)
                return row_index, result

        tasks = []
        for row in processed_df.itertuples():
            input_fields = {
                col: str(getattr(row, col, "")) for col in selected_columns
            }
            tasks.append(_process_row(row.Index, input_fields))

        use_pb = flow.display.use_progress_bar
        for completed in tqdm_async.as_completed(
            tasks, total=len(tasks),
            desc="Processing rows", disable=not use_pb,
        ):
            row_index, result_dict = await completed
            for key, value in result_dict.items():
                if key in processed_df.columns or key in output_keys:
                    processed_df.at[row_index, key] = value
            self._checkpoint.mark_completed(row_index)

        return processed_df

    def _write_outputs(self, processed_df: pd.DataFrame, model_name: str) -> None:
        """Write the processed DataFrame to the configured output path."""
        output_config = self.schema.flow.output
        processed_df = processed_df.copy()
        processed_df["model"] = model_name

        summary_path = Path(output_config.summary_csv)
        summary_path.parent.mkdir(parents=True, exist_ok=True)

        if output_config.extend and summary_path.exists():
            existing_df = pd.read_csv(summary_path, encoding="utf-8")
            if "model" in existing_df.columns:
                existing_df = existing_df[existing_df["model"] != model_name]
            combined_df = pd.concat([existing_df, processed_df], ignore_index=True)
            combined_df.to_csv(summary_path, index=False, encoding="utf-8")
            self.logger.info(
                "Output extended: %d existing + %d new = %d total rows",
                len(existing_df), len(processed_df), len(combined_df),
            )
        else:
            processed_df.to_csv(summary_path, index=False, encoding="utf-8")
            self.logger.info(
                "Output saved to %s (%d rows)", summary_path, len(processed_df),
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
    elif not flow_config.taxonomy or not Path(flow_config.taxonomy).exists():
        taxonomy_payload: Dict[str, Any] = {
            "context_definitions": {},
            "label_options": {},
        }
        logging.getLogger(__name__).warning(
            "Taxonomy file %r not found or not configured; "
            "proceeding with empty taxonomy.",
            flow_config.taxonomy,
        )
    else:
        taxonomy_payload = _load_json_file(Path(flow_config.taxonomy))

    prompts_path = Path(flow_config.prompts)
    if prompts_path.exists():
        prompts_payload = _load_json_file(prompts_path)
    else:
        prompts_payload: Dict[str, Any] = {}
        logging.getLogger(__name__).warning(
            "Prompts file %r not found; proceeding without prompts.json fallback.",
            flow_config.prompts,
        )

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
