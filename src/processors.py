"""LLM-backed text processors for summarisation, classification, and label extraction.

Every processor class in this module follows the same contract: it receives a
runtime config dict (model name, generation parameters, prompt payload, and
optional per-step overrides from the flow runner), an OpenAI-compatible client,
and a taxonomy dict.  It exposes one or more public methods that accept cleaned
text and return either a plain string (backward-compatible callers) or a
:class:`ProcessorResult` (structured audit trail).

Processor families
------------------

**Summary / classification** — :class:`MessyTextLogicMixin` holds the shared
prompt-construction logic; :class:`MessyTextProcessor` (sync) and
:class:`AsyncMessyTextProcessor` (async) add the client call.

**Conversation-turn wrappers** — :class:`MessyTextConversationTurnProcessor`
and :class:`AsyncMessyTextConversationTurnProcessor` wrap the base processors
to manage per-turn state threading, span-offset attachment, and response
logging.  :class:`MessyTextConversationOrchestrator` /
:class:`AsyncMessyTextConversationOrchestrator` drive the multi-turn loop.

**Label extraction** — :class:`LabelExtractorLogicMixin` builds the single-
label span extraction prompt; :class:`LabelExtractor` (sync) and
:class:`AsyncLabelExtractor` (async) add the client call.

**Label-based summary** — :class:`TextLabelsSummaryLogicMixin` builds a
summary prompt from pre-extracted label evidence;
:class:`TextLabelsSummaryProcessor` (sync) and
:class:`AsyncTextLabelsSummaryProcessor` (async) add the client call.
:class:`TextConversationOrchestrator` /
:class:`AsyncTextConversationOrchestrator` drive the sequential or concurrent
document loop that feeds these processors.
"""

import asyncio
import json
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from json_repair import repair_json
from tqdm.asyncio import tqdm as tqdm_async
from src.io_schema import (
    IOSchema,
    to_prompt_output_format_text,
    to_response_format,
)
from src.prompt_resolver import ResolvedPrompt
from src.utils import compute_span_offsets


@dataclass
class ProcessorResult:
    """
    Generic result container object for a single LLM-backed processor call.

    This object is intentionally task-agnostic: it can represent summary,
    classification, or any future task that uses the response_format interface.

    Attributes:
        task_name: Logical name of the task, e.g. "summary", "classification".
        model_name: Identifier of the model that produced this result.
        declared_fields: Schema of expected output fields, taken from the
            response_format schema properties (field name -> property spec).
        values: Parsed values for the declared_fields, extracted from the
            model's JSON output.
        input_text: Raw text sent to the model (messages[0].content).
        input_struct: Best-effort parsed structure of the input prompt
            (after repair_json), or None if parsing failed.
        output_text: Raw text returned by the model.
        output_struct: Parsed JSON output (after repair_json), or None if
            parsing failed.
        doc_id: Optional identifier for the logical unit of work (row index,
            document id, victim id, etc.).
        error: Optional error message captured during parsing or construction.
        metadata: Free-form dictionary for additional audit fields (timings,
            request ids, etc.).
    """
    task_name: str
    model_name: str

    declared_fields: Dict[str, Any]
    values: Dict[str, Any]

    input_text: str
    input_struct: Optional[Dict[str, Any]]

    output_text: str
    output_struct: Optional[Dict[str, Any]]

    doc_id: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_llm_call(
        cls,
        *,
        task_name: str,
        model_name: str,
        request_kwargs: Dict[str, Any],
        response: Any,
        doc_id: Optional[Any] = None,
    ) -> "ProcessorResult":
        """Parse an LLM response into a structured :class:`ProcessorResult`.

        Extracts input text from the first user message, parses the output
        JSON via :func:`json_repair.repair_json`, reads declared fields
        from the ``response_format`` schema, and populates ``values``
        accordingly.  Partial failures (unparseable JSON, missing fields)
        are recorded in ``error`` while raw text remains available.

        Args:
            task_name: Logical task label (e.g. ``"summary"``,
                ``"classification"``).
            model_name: Model identifier written into the result.
            request_kwargs: The ``**kwargs`` dict passed to
                ``chat.completions.create``, used to recover input text
                and declared fields from ``response_format``.
            response: The raw ``ChatCompletion`` object returned by the
                client.
            doc_id: Optional document identifier for traceability.

        Returns:
            A fully populated result. ``error`` is ``None`` when every
            parsing step succeeds.
        """
        error_messages: List[str] = []

        # Extract input text (first user message content) and try to parse it.
        input_text = ""
        input_struct: Optional[Dict[str, Any]] = None
        try:
            messages = request_kwargs.get("messages") or []
            if messages:
                input_text = str(messages[0].get("content", ""))
                try:
                    repaired = repair_json(input_text)
                    input_struct = json.loads(repaired)
                except Exception as exc:  # noqa: BLE001
                    error_messages.append(f"Failed to parse input_struct: {exc}")
        except Exception as exc:  # noqa: BLE001
            error_messages.append(f"Failed to extract input_text: {exc}")

        # Extract raw output text.
        output_text = ""
        output_struct: Optional[Dict[str, Any]] = None
        try:
            output_text = response.choices[0].message.content
            if output_text:
                output_text = re.sub(r'[\ud800-\udfff]', '', output_text)
            try:
                repaired_out = repair_json(output_text)
                _parsed = json.loads(repaired_out)
                if isinstance(_parsed, dict):
                    output_struct = _parsed
                elif isinstance(_parsed, list) and len(_parsed) == 1 and isinstance(_parsed[0], dict):
                    output_struct = _parsed[0]
                    error_messages.append("output_struct was a single-element list; unwrapped to dict")
                elif isinstance(_parsed, list):
                    _merged: Dict[str, Any] = {}
                    for _item in _parsed:
                        if isinstance(_item, dict):
                            _merged.update(_item)
                    output_struct = _merged if _merged else None
                    error_messages.append(
                        f"output_struct was a list of {len(_parsed)} items; merged dict fields"
                    )
                else:
                    output_struct = None
                    error_messages.append(
                        f"output_struct is {type(_parsed).__name__}, expected dict; skipping field extraction"
                    )
            except Exception as exc:  # noqa: BLE001
                error_messages.append(f"Failed to parse output_struct: {exc}")
        except Exception as exc:  # noqa: BLE001
            error_messages.append(f"Failed to extract output_text: {exc}")

        # Determine declared fields from response_format schema if available.
        declared_fields: Dict[str, Any] = {}
        try:
            guided = (
                request_kwargs.get("response_format", {})
                .get("json_schema", {})
                .get("schema", {})
                .get("properties", {})
            )
            if isinstance(guided, dict):
                declared_fields = guided
        except Exception as exc:  # noqa: BLE001
            error_messages.append(f"Failed to read response_format properties: {exc}")

        # Extract values for the declared fields from the parsed output.
        values: Dict[str, Any] = {}
        if output_struct is not None:
            for field_name in declared_fields.keys():
                values[field_name] = output_struct.get(field_name)

        error = "; ".join(error_messages) if error_messages else None

        return cls(
            task_name=task_name,
            model_name=model_name,
            declared_fields=declared_fields,
            values=values,
            input_text=input_text,
            input_struct=input_struct,
            output_text=output_text,
            output_struct=output_struct,
            doc_id=doc_id,
            error=error,
            metadata={},
        )

    def has_field(self, name: str) -> bool:
        """Return True if this result declares the given field."""
        return name in self.declared_fields

    def get(self, name: str, default: Any = None) -> Any:
        """Convenience accessor for a field value."""
        return self.values.get(name, default)

    def is_no_info(self) -> bool:
        """
        Heuristic check for a "no information" style result.

        This intentionally stays generic and relies on commonly used fields:
        - For summary-like tasks, an empty or missing 'summary' suggests
          no information.
        - For classification-like tasks, an empty or missing 'result'
          suggests no information.
        """
        if "summary" in self.values:
            summary = (self.values.get("summary") or "").strip()
            return not summary
        if "result" in self.values:
            result = (self.values.get("result") or "").strip()
            return not result
        return False


@dataclass
class MessyTextConversationState:
    """
    Holds state for a multi-turn MessyText conversation.

    This object tracks all results across turns, enabling traceback to original
    spans and document sources. It provides properties for convenient access to
    the most recent result and summary.

    Attributes:
        turn_index (int): Number of turns that have been processed so far.
        results (List[ProcessorResult]): All structured results from each turn,
            preserving the full conversation history including spans and doc_ids.
    """
    turn_index: int = 0
    results: List[ProcessorResult] = field(default_factory=list)

    @property
    def last_result(self) -> Optional[ProcessorResult]:
        """Return the most recent ProcessorResult, or None if no turns processed."""
        return self.results[-1] if self.results else None

    @property
    def last_summary(self) -> str:
        """Return the summary from the most recent turn, or empty string."""
        if not self.results:
            return ""
        return self.results[-1].get("summary") or ""

class MessyTextLogicMixin:
    """Shared prompt-construction and text-cleaning logic for summary/classification.

    Subclassed by :class:`MessyTextProcessor` (sync) and
    :class:`AsyncMessyTextProcessor` (async), which add the actual client
    calls.  This mixin holds no client reference and performs no I/O.

    Attributes:
        config: Runtime config dict carrying ``model``, ``processing``,
            ``prompts``, ``logging``, and optional per-step overrides
            (``io_schema_resolved``, ``prompt_resolved``).
        definitions: Taxonomy ``context_definitions`` dict mapping label
            keys to human-readable definitions.
        labels: Taxonomy ``label_options`` dict mapping label keys to
            lists of valid values.
        logger: Logger instance.
        model_name: Model identifier read from ``config['model']['name']``.
        last_summary_result: Most recent summary :class:`ProcessorResult`.
        last_classification_result: Most recent classification
            :class:`ProcessorResult`.
    """
    def __init__(self, config: Dict[str, Any], taxonomy: Dict[str, Any], logger: logging.Logger):
        """Initialise with runtime config, taxonomy, and logger.

        Args:
            config: Runtime settings dict (model name, generation
                parameters, prompt payload, optional step overrides).
            taxonomy: Parsed taxonomy JSON with ``context_definitions``
                and ``label_options`` keys.
            logger: Logger instance.
        """
        self.config = config
        self.definitions = taxonomy['context_definitions']
        self.labels = taxonomy['label_options']
        self.logger = logger
        self.model_name = config['model']['name']

        # Storage for the most recent per-call results.
        # These are additive: they do not replace any existing state or behavior.
        self.last_summary_result: Optional[ProcessorResult] = None
        self.last_classification_result: Optional[ProcessorResult] = None

    def clean_text(self, text: str) -> str:
        """
        Applies regex cleaning to input text.

        Args:
            text (str): The raw input text to clean.

        Returns:
            str: The cleaned text with URLs removed and whitespace normalized.
        """
        if not isinstance(text, str):
            return str(text)
            
        # Regex from opr_3.1
        # 1. Remove URLs, parenthetical metadata, emojis, date patterns like d/d
        text = re.sub(r'https?://\S+|\([^)]*/[^)]*\)|[\ue000-\uf8ff]|\b\d/\d\b', '', text)
        # 2. Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _get_summary_args(self, text: str) -> Dict[str, Any]:
        """Constructs arguments for the summary API call.

        Honours the per-step overrides that
        :meth:`src.flow_builder.FlowRunner._resolve_processor_config_for_step`
        may have injected into ``self.config``:

        - ``self.config['prompt_resolved']`` (:class:`src.prompt_resolver.ResolvedPrompt` or ``None``):
          when set, its :attr:`~src.prompt_resolver.ResolvedPrompt.instructions`
          replace the base instruction list read from ``prompts.json``, and
          its :attr:`~src.prompt_resolver.ResolvedPrompt.output_format`
          replaces the base ``output_format`` when present.
        - ``self.config['io_schema_resolved']`` (:class:`src.io_schema.IOSchema`
          or ``None``): when set, its output half is rendered via
          :func:`src.io_schema.to_prompt_output_format_text` and used as
          the prompt-body ``output_format`` (if no prompt-level override
          is supplied), and it is converted via
          :func:`src.io_schema.to_response_format` into the
          ``response_format`` argument sent to the LLM, replacing the
          method's historical hardcoded dict.

        When neither key is set (direct callers outside the flow runner),
        the method falls back to its historical behavior of reading
        ``self.config['prompts']['summary']`` and emitting the hardcoded
        ``summary`` response schema, byte-for-byte identical to the
        pre-registry runtime.

        Args:
            text (str): The cleaned text to summarize.

        Returns:
            Dict[str, Any]: A dictionary containing model arguments (model,
            messages, temperature, max_tokens, response_format). The
            ``response_format`` is either derived from ``io_schema_resolved``
            or the hardcoded ``summary`` schema, depending on what the
            flow runner injected.
        """
        prompts_cfg = self.config.get("prompts") or {}
        summary_cfg = prompts_cfg.get("summary") or {}
        prompt_resolved: Optional[ResolvedPrompt] = self.config.get("prompt_resolved")
        io_schema_resolved: Optional[IOSchema] = self.config.get("io_schema_resolved")

        if prompt_resolved is not None:
            instructions_template = list(prompt_resolved.instructions)
        else:
            instructions_template = summary_cfg.get("instructions")

        if prompt_resolved is not None and prompt_resolved.output_format is not None:
            output_format = prompt_resolved.output_format
        elif io_schema_resolved is not None:
            output_format = to_prompt_output_format_text(io_schema_resolved)
        else:
            output_format = summary_cfg.get("output_format")

        if output_format is None or instructions_template is None:
            raise ValueError(
                "Summary prompt configuration must provide 'output_format' and 'instructions'."
            )

        instructions = [
            instr.format(
                info_found_label="info_found",
                relevant_context_label="relevant_context",
                summary_label="summary",
                input_text_label="input_text",
            )
            for instr in instructions_template
        ]

        prompt_structure = {
            'input_text': text,
            'related_context': self.definitions,
            'output_format': output_format,
            'instructions': instructions,
        }

        # We cast to string to mimic notebook behavior of passing stringified dict
        prompt_content = str(prompt_structure)

        if io_schema_resolved is not None:
            response_format = to_response_format(io_schema_resolved, schema_name="summary")
        else:
            response_format = {"type": "json_schema", "json_schema": {
                "name": "summary",
                "schema": {
                    "type": "object",
                    "properties": {
                        "info_found": {"type": "string"},
                        "relevant_context": {"type": "array"},
                        "summary": {"type": "string"}
                    },
                    "required": ["info_found", "relevant_context", "summary"]
                }
            }}

        return {
            "model": self.model_name,
            "messages": [{'role': 'user', 'content': prompt_content}],
            "temperature": self.config['processing']['temperature'],
            "max_tokens": self.config['processing']['max_tokens_summary'],
            "response_format": response_format,
        }

    def _get_conversation_summary_args(
        self,
        previous_summary: Optional[str],
        text: str,
    ) -> Dict[str, Any]:
        """Constructs arguments for a conversation-style summary API call.

        This method selects between first-turn and update prompts based on
        the ``previous_summary`` value and exposes both the previous
        summary and the new document to the model.

        Honours the per-step overrides that
        :meth:`src.flow_builder.FlowRunner._resolve_processor_config_for_step`
        may have injected into ``self.config``:

        - ``self.config['prompt_resolved']`` (:class:`src.prompt_resolver.ResolvedPrompt`
          or ``None``): when set, its instructions and ``output_format``
          replace both first-turn and update-turn base prompts uniformly.
          The flow runner picks exactly one prompt per step, so the
          first-vs-update switch built in below only fires when no
          override is supplied.
        - ``self.config['io_schema_resolved']`` (:class:`src.io_schema.IOSchema`
          or ``None``): when set, used to derive the prompt-body
          ``output_format`` (if no prompt-level override sets one) and
          the LLM ``response_format`` dict.

        When neither key is set the method falls back to the historical
        ``prompts.json`` lookup (``summary_update`` > ``summary_first`` >
        ``summary``) and the hardcoded ``conversation_summary`` response
        schema, byte-for-byte identical to the pre-registry runtime.

        Args:
            previous_summary (Optional[str]): The running summary from earlier
                turns, or None/empty string for the first turn.
            text (str): The cleaned text of the new document to integrate.

        Returns:
            Dict[str, Any]: A dictionary containing model arguments (model,
            messages, etc.) suitable for chat.completions.create. The
            ``response_format`` is either derived from
            ``io_schema_resolved`` or the hardcoded
            ``conversation_summary`` schema, depending on what the flow
            runner injected.
        """
        prompts_cfg = self.config.get("prompts") or {}
        prompt_resolved: Optional[ResolvedPrompt] = self.config.get("prompt_resolved")
        io_schema_resolved: Optional[IOSchema] = self.config.get("io_schema_resolved")

        has_previous = bool(previous_summary and previous_summary.strip())
        if has_previous:
            summary_cfg = (
                prompts_cfg.get("summary_update")
                or prompts_cfg.get("summary_first")
                or prompts_cfg.get("summary")
                or {}
            )
        else:
            summary_cfg = (
                prompts_cfg.get("summary_first")
                or prompts_cfg.get("summary")
                or {}
            )

        # Derive previous_relevant_context and previous_summary_by_item from the last
        # structured conversation result, if available. This allows prompt templates
        # to reference {previous_relevant_context} and {previous_summary_by_item}
        # without changing the public interface.
        previous_relevant_context_list = []
        previous_summary_by_item_dict = {}

        previous_result = getattr(self, "last_summary_result", None)
        if has_previous and isinstance(previous_result, ProcessorResult):
            raw_ctx = previous_result.get("relevant_context")
            if isinstance(raw_ctx, list):
                previous_relevant_context_list = raw_ctx

            raw_summary_by_item = previous_result.get("summary_by_item")
            if isinstance(raw_summary_by_item, dict):
                previous_summary_by_item_dict = raw_summary_by_item

        previous_relevant_context_str = json.dumps(
            previous_relevant_context_list, ensure_ascii=False
        )
        previous_summary_by_item_str = json.dumps(
            previous_summary_by_item_dict, ensure_ascii=False
        )

        if prompt_resolved is not None:
            instructions_template = list(prompt_resolved.instructions)
        else:
            instructions_template = summary_cfg.get("instructions")

        if prompt_resolved is not None and prompt_resolved.output_format is not None:
            output_format = prompt_resolved.output_format
        elif io_schema_resolved is not None:
            output_format = to_prompt_output_format_text(io_schema_resolved)
        else:
            output_format = summary_cfg.get("output_format")

        if output_format is None or instructions_template is None:
            raise ValueError(
                "Conversation summary prompt configuration must provide "
                "'output_format' and 'instructions'."
            )

        # Allow prompt templates to reference previous_summary, previous structured
        # fields, and label names dynamically.
        class _SafeFormatDict(dict):
            def __missing__(self, key: str) -> str:
                # Preserve unknown placeholders literally, e.g. {previous_relevant_context}
                return "{" + key + "}"

        format_vars = _SafeFormatDict(
            previous_summary=previous_summary or "",
            previous_relevant_context=previous_relevant_context_str,
            previous_summary_by_item=previous_summary_by_item_str,
            info_found_label="info_found",
            relevant_context_label="relevant_context",
            summary_label="summary",
            input_text_label="input_text",
            related_context_label="related_context",
        )

        instructions = [
            instr.format_map(format_vars)
            for instr in instructions_template
        ]

        prompt_structure = {
            'previous_summary': previous_summary or "",
            'input_text': text,
            'related_context': self.definitions,
            'output_format': output_format,
            'instructions': instructions,
        }

        prompt_content = str(prompt_structure)

        if io_schema_resolved is not None:
            response_format = to_response_format(
                io_schema_resolved, schema_name="conversation_summary",
            )
        else:
            response_format = {"type": "json_schema", "json_schema": {
                "name": "conversation_summary",
                "schema": {
                    "type": "object",
                    "properties": {
                        "info_found": {"type": "string"},
                        "relevant_context": {"type": "array"},
                        "summary_by_item": {
                            "type": "object",
                            "description": "Per-label extractive spans for traceback",
                            "additionalProperties": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "span": {"type": "string"}
                                    },
                                    "required": ["span"]
                                }
                            }
                        },
                        "summary": {"type": "string"}
                    },
                    "required": ["info_found", "relevant_context", "summary_by_item", "summary"]
                }
            }}

        return {
            "model": self.model_name,
            "messages": [{'role': 'user', 'content': prompt_content}],
            "temperature": self.config['processing']['temperature'],
            "max_tokens": self.config['processing']['max_tokens_summary'],
            "response_format": response_format,
        }

    def _extract_summary_from_response(self, response: Any) -> str:
        """
        Parses the summary API response.

        Args:
            response (Any): The raw response object from the API call.

        Returns:
            str: The extracted summary text, or 'No relevant information found'.
        """
        content = response.choices[0].message.content
        parsed = json.loads(repair_json(content))
        summary = parsed.get('summary', 'No relevant information found')
        return summary if summary else 'No relevant information found'

    def _get_classification_args(self, summary: str, key: str) -> Optional[Dict[str, Any]]:
        """Constructs arguments for the classification API call.

        Honours the per-step overrides that
        :meth:`src.flow_builder.FlowRunner._resolve_processor_config_for_step`
        may have injected into ``self.config``:

        - ``self.config['prompt_resolved']`` (:class:`src.prompt_resolver.ResolvedPrompt`
          or ``None``): when set, its :attr:`~src.prompt_resolver.ResolvedPrompt.instructions`
          replace the base instruction list read from ``prompts.json``.
          The classification prompt body has no ``output_format`` slot so
          the resolver's ``output_format`` field is intentionally ignored.
        - ``self.config['io_schema_resolved']`` (:class:`src.io_schema.IOSchema`
          or ``None``): when set, converted via
          :func:`src.io_schema.to_response_format` into the
          ``response_format`` argument sent to the LLM, replacing the
          method's historical hardcoded ``classification`` schema.

        When neither key is set (direct callers outside the flow runner),
        the method falls back to the historical
        ``self.config['prompts']['classification']['instructions']``
        lookup and the hardcoded ``classification`` response schema.

        Args:
            summary (str): The summarized text to classify.
            key (str): The taxonomy key (e.g. 'vic_grupo_social').

        Returns:
            Optional[Dict[str, Any]]: A dictionary of model arguments, or
            ``None`` when the summary is empty / sentinel or the taxonomy
            ``key`` has no definition. The ``response_format`` is either
            derived from ``io_schema_resolved`` or the hardcoded
            ``classification`` schema, depending on what the flow runner
            injected.
        """
        if not summary or summary == 'No relevant information found':
            return None
        
        question = self.definitions.get(key, '')
        possible_values = self.labels.get(key, [])
        
        if not question:
            self.logger.error(f"Key '{key}' not found in definitions")
            return None

        prompts_cfg = self.config.get("prompts") or {}
        classification_cfg = prompts_cfg.get("classification") or {}
        prompt_resolved: Optional[ResolvedPrompt] = self.config.get("prompt_resolved")
        io_schema_resolved: Optional[IOSchema] = self.config.get("io_schema_resolved")

        if prompt_resolved is not None:
            instructions_template = list(prompt_resolved.instructions)
        else:
            instructions_template = classification_cfg.get("instructions")

        if not instructions_template:
            raise ValueError(
                "Classification prompt configuration must provide 'instructions' list."
            )

        # Apply formatting uniformly so any placeholder like {possible_values}
        # can be replaced, while literal JSON braces are preserved via {{ }} in
        # the template strings.
        instructions = [
            instr.format(possible_values=possible_values)
            for instr in instructions_template
        ]

        prompt_structure = {
            'input_text': summary,
            'question': question,
            'possible_values': possible_values,
            'instructions': instructions,
        }
        
        prompt_content = str(prompt_structure)

        if io_schema_resolved is not None:
            response_format = to_response_format(
                io_schema_resolved, schema_name="classification",
            )
        else:
            response_format = {"type": "json_schema", "json_schema": {
                "name": "classification",
                "schema": {
                    "type": "object",
                    "properties": {
                        "evidence": {"type": "string"},
                        "result": {"type": "string"}
                    },
                    "required": ["evidence", "result"]
                }
            }}

        return {
            "model": self.model_name,
            "messages": [{'role': 'user', 'content': prompt_content}],
            "temperature": self.config['processing']['temperature'],
            "max_tokens": self.config['processing']['max_tokens_classification'],
            "response_format": response_format,
        }

    def _extract_classification_from_response(self, response: Any) -> str:
        """
        Parses the classification API response.

        Args:
            response (Any): The raw response object from the API call.

        Returns:
            str: The extracted classification result, or 'No information'.
        """
        content = response.choices[0].message.content
        parsed = json.loads(repair_json(content))
        result = parsed.get('result', 'No information')
        return result if result else 'No information'


def _attach_span_offsets_to_result(
    result: Optional[ProcessorResult],
    source_text: str,
    doc_id: Optional[Any],
) -> Optional[ProcessorResult]:
    """Enrich ``summary_by_item`` span entries with character offsets.

    For every span dict inside ``result.values["summary_by_item"]``,
    searches *source_text* for the span string and writes the character
    offset (or ``-1``) into the ``offset`` key.  Also stamps each span
    with *doc_id* so downstream records stay aligned with the input.

    Args:
        result: The processor result to enrich.  ``None`` is returned
            as-is.
        source_text: The cleaned document text to search for spans.
        doc_id: Document identifier written into every span dict.

    Returns:
        The same *result* instance with offsets attached, or ``None``
        when *result* is ``None``.
    """
    if result is None:
        return None

    summary_by_item = result.get("summary_by_item")
    if not isinstance(summary_by_item, dict):
        return result

    # Ensure doc_id is propagated from the runner, not the model output.
    # This keeps span records aligned with the input index and avoids model-
    # injected identifiers.
    for spans in summary_by_item.values():
        if not isinstance(spans, list):
            continue
        for item in spans:
            if isinstance(item, dict):
                item["doc_id"] = doc_id

    def _get_source_text(target_doc_id: Any) -> str:
        if doc_id is not None and target_doc_id == doc_id:
            return source_text
        return ""

    updated_summary_by_item = compute_span_offsets(summary_by_item, _get_source_text)
    result.values["summary_by_item"] = updated_summary_by_item
    return result


class MessyTextProcessor(MessyTextLogicMixin):
    """Synchronous summary and classification processor.

    Wraps a synchronous ``OpenAI`` client and exposes :meth:`summarize_text`
    and :meth:`classify_summary` as the public API.  Each call stores a
    :class:`ProcessorResult` on the instance for richer consumers.

    Attributes:
        client: Synchronous ``OpenAI`` or vLLM client instance.
    """
    def __init__(self, client: Any, config: Dict[str, Any], taxonomy: Dict[str, Any], logger: logging.Logger):
        """Initialise the synchronous processor.

        Args:
            client: Synchronous ``OpenAI`` client instance.
            config: Runtime settings dict (model, processing, prompts,
                logging, optional step overrides).
            taxonomy: Parsed taxonomy JSON.
            logger: Logger instance.
        """
        super().__init__(config, taxonomy, logger)
        self.client = client

    def summarize_text(self, text: str, doc_id: Optional[Any] = None) -> str:
        """Summarise *text* via one LLM call and return the summary string.

        Stores the full :class:`ProcessorResult` in
        :attr:`last_summary_result` for callers that need structured
        access.

        Args:
            text: Cleaned document text.  Empty input short-circuits to
                ``"No relevant information found"``.
            doc_id: Optional document identifier for traceability.

        Returns:
            The ``summary`` field extracted from the LLM response, or
            ``"No relevant information found"`` on empty input or error.
        """
        # Empty input: record a trivial "no information" result and return sentinel.
        if not text:
            self.last_summary_result = ProcessorResult(
                task_name="summary",
                model_name=self.model_name,
                declared_fields={},
                values={},
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={},
            )
            return "No relevant information found"

        kwargs = self._get_summary_args(text)
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Summarization failed: {e}")
            # Store an error result so callers can still inspect input.
            messages = kwargs.get("messages", []) or [{}]
            input_text = str(messages[0].get("content", ""))
            self.last_summary_result = ProcessorResult(
                task_name="summary",
                model_name=self.model_name,
                declared_fields={},
                values={},
                input_text=input_text,
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=str(e),
                metadata={},
            )
            return "No relevant information found"

        # Normal path: construct and store the full result, then return summary text.
        self.last_summary_result = ProcessorResult.from_llm_call(
            task_name="summary",
            model_name=self.model_name,
            request_kwargs=kwargs,
            response=response,
            doc_id=doc_id,
        )
        summary = self.last_summary_result.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary
        return "No relevant information found"

    def classify_summary(
        self,
        summary: str,
        key: str,
        doc_id: Optional[Any] = None,
    ) -> str:
        """Classify *summary* against taxonomy *key* and return the label.

        Stores the full :class:`ProcessorResult` in
        :attr:`last_classification_result`.

        Args:
            summary: Summary text to classify.
            key: Taxonomy key (e.g. ``"vic_grupo_social"``).
            doc_id: Optional document identifier for traceability.

        Returns:
            The ``result`` field from the LLM response, or
            ``"No information"`` when the summary is empty or the key
            has no definition.
        """
        kwargs = self._get_classification_args(summary, key)
        if kwargs is None:
            # Nothing to classify (e.g. no summary): record an empty result.
            self.last_classification_result = ProcessorResult(
                task_name="classification",
                model_name=self.model_name,
                declared_fields={},
                values={},
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={},
            )
            return "No information"

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Classification failed for {key}: {e}")
            messages = kwargs.get("messages", []) or [{}]
            input_text = str(messages[0].get("content", ""))
            self.last_classification_result = ProcessorResult(
                task_name="classification",
                model_name=self.model_name,
                declared_fields={},
                values={},
                input_text=input_text,
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=str(e),
                metadata={},
            )
            return "No information"

        self.last_classification_result = ProcessorResult.from_llm_call(
            task_name="classification",
            model_name=self.model_name,
            request_kwargs=kwargs,
            response=response,
            doc_id=doc_id,
        )
        classification = self.last_classification_result.get("result")
        if isinstance(classification, str) and classification.strip():
            return classification
        return "No information"


class AsyncMessyTextProcessor(MessyTextLogicMixin):
    """Asynchronous summary and classification processor.

    Wraps an ``AsyncOpenAI`` client and exposes async
    :meth:`summarize_text` and :meth:`classify_summary`.  Each call
    stores a :class:`ProcessorResult` on the instance.

    Attributes:
        client: Asynchronous ``AsyncOpenAI`` client instance.
        _llm_semaphore: Optional semaphore capping concurrent in-flight
            LLM requests.
    """
    def __init__(
        self,
        client: Any,
        config: Dict[str, Any],
        taxonomy: Dict[str, Any],
        logger: logging.Logger,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ):
        """Initialise the asynchronous processor.

        Args:
            client: Asynchronous ``AsyncOpenAI`` client instance.
            config: Runtime settings dict.
            taxonomy: Parsed taxonomy JSON.
            logger: Logger instance.
            llm_semaphore: When provided, each LLM call acquires this
                semaphore to cap concurrent in-flight requests.
        """
        super().__init__(config, taxonomy, logger)
        self.client = client
        self._llm_semaphore = llm_semaphore

    async def summarize_text(self, text: str, doc_id: Optional[Any] = None) -> str:
        """Summarise *text* via one async LLM call and return the summary.

        Async counterpart of :meth:`MessyTextProcessor.summarize_text`.

        Args:
            text: Cleaned document text.
            doc_id: Optional document identifier for traceability.

        Returns:
            The ``summary`` field from the LLM response, or
            ``"No relevant information found"`` on empty input or error.
        """
        if not text:
            self.last_summary_result = ProcessorResult(
                task_name="summary",
                model_name=self.model_name,
                declared_fields={},
                values={},
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={},
            )
            return "No relevant information found"

        kwargs = self._get_summary_args(text)
        try:
            if self._llm_semaphore:
                async with self._llm_semaphore:
                    response = await self.client.chat.completions.create(**kwargs)
            else:
                response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Summarization failed: {e}")
            messages = kwargs.get("messages", []) or [{}]
            input_text = str(messages[0].get("content", ""))
            self.last_summary_result = ProcessorResult(
                task_name="summary",
                model_name=self.model_name,
                declared_fields={},
                values={},
                input_text=input_text,
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=str(e),
                metadata={},
            )
            return "No relevant information found"

        self.last_summary_result = ProcessorResult.from_llm_call(
            task_name="summary",
            model_name=self.model_name,
            request_kwargs=kwargs,
            response=response,
            doc_id=doc_id,
        )
        summary = self.last_summary_result.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary
        return "No relevant information found"

    async def classify_summary(
        self,
        summary: str,
        key: str,
        doc_id: Optional[Any] = None,
    ) -> str:
        """Classify *summary* against taxonomy *key* asynchronously.

        Async counterpart of :meth:`MessyTextProcessor.classify_summary`.

        Args:
            summary: Summary text to classify.
            key: Taxonomy key (e.g. ``"vic_grupo_social"``).
            doc_id: Optional document identifier for traceability.

        Returns:
            The ``result`` field from the LLM response, or
            ``"No information"`` when the summary is empty or the key
            has no definition.
        """
        kwargs = self._get_classification_args(summary, key)
        if kwargs is None:
            self.last_classification_result = ProcessorResult(
                task_name="classification",
                model_name=self.model_name,
                declared_fields={},
                values={},
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={},
            )
            return "No information"

        try:
            if self._llm_semaphore:
                async with self._llm_semaphore:
                    response = await self.client.chat.completions.create(**kwargs)
            else:
                response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Classification failed for {key}: {e}")
            messages = kwargs.get("messages", []) or [{}]
            input_text = str(messages[0].get("content", ""))
            self.last_classification_result = ProcessorResult(
                task_name="classification",
                model_name=self.model_name,
                declared_fields={},
                values={},
                input_text=input_text,
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=str(e),
                metadata={},
            )
            return "No information"

        self.last_classification_result = ProcessorResult.from_llm_call(
            task_name="classification",
            model_name=self.model_name,
            request_kwargs=kwargs,
            response=response,
            doc_id=doc_id,
        )
        classification = self.last_classification_result.get("result")
        if isinstance(classification, str) and classification.strip():
            return classification
        return "No information"



class MessyTextConversationTurnProcessor:
    """
    Performs a single sequential summarization turn with optional conversation state.

    This class wraps a synchronous MessyTextProcessor and provides a higher-level
    interface that:

    1. Accepts raw input text and an optional MessyTextConversationState.
    2. Cleans the text using the shared regex logic.
    3. Calls summarize_text to obtain a per-turn summary (using the current
       prompt design as a placeholder for future, memory-aware prompts).
    4. Returns both the summary for this turn and an updated conversation state.

    The current implementation does not yet inject the previous state into the
    underlying prompt. That behavior can be added later by updating the logic in
    this class and/or _get_summary_args without changing the public interface.
    """

    def __init__(self, processor: MessyTextProcessor) -> None:
        """
        Initializes the turn processor.

        Args:
            processor (MessyTextProcessor): The underlying synchronous processor
                responsible for cleaning, prompt construction, and LLM calls.
        """
        self.processor = processor

    def process_turn(
        self,
        raw_text: str,
        state: Optional[MessyTextConversationState] = None,
        doc_id: Optional[Any] = None,
    ) -> Tuple[str, MessyTextConversationState]:
        """
        Processes a single document as one conversation turn.

        Args:
            raw_text (str): The raw document text for this turn.
            state (Optional[MessyTextConversationState]): Existing conversation
                state to carry over between turns. If None, a new state is created.

        Returns:
            Tuple[str, MessyTextConversationState]:
                - The summary generated for this turn.
                - The updated conversation state including the latest summary and
                  incremented turn index, plus the structured ProcessorResult for
                  this turn in state.last_result.
        """
        conversation_state = state or MessyTextConversationState()

        cleaned_text = self.processor.clean_text(raw_text)
        result: Optional[ProcessorResult] = None

        if not cleaned_text.strip():
            # No input text: record an explicit "no information" result and use
            # an empty summary string so callers can rely on info_found/summary
            # instead of sentinel phrases.
            result = ProcessorResult(
                task_name="conversation_summary",
                model_name=self.processor.model_name,
                declared_fields={},
                values={"info_found": "FALSE", "summary": "", "relevant_context": []},
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={},
            )
            summary = ""
        else:
            kwargs = self.processor._get_conversation_summary_args(
                previous_summary=conversation_state.last_summary,
                text=cleaned_text,
            )
            try:
                response = self.processor.client.chat.completions.create(**kwargs)
                # Construct a structured result from the guided JSON output.
                result = ProcessorResult.from_llm_call(
                    task_name="conversation_summary",
                    model_name=self.processor.model_name,
                    request_kwargs=kwargs,
                    response=response,
                    doc_id=doc_id,
                )
                summary_value = result.get("summary")
                if isinstance(summary_value, str) and summary_value.strip():
                    summary = summary_value
                else:
                    summary = ""
            except Exception as e:
                self.processor.logger.error(f"Summarization (conversation) failed: {e}")
                result = ProcessorResult(
                    task_name="conversation_summary",
                    model_name=self.processor.model_name,
                    declared_fields={},
                    values={"info_found": "FALSE", "summary": "", "relevant_context": []},
                    input_text="",
                    input_struct=None,
                    output_text="",
                    output_struct=None,
                    doc_id=doc_id,
                    error=str(e),
                    metadata={},
                )
                summary = ""

        # Expose the most recent conversation result on the underlying processor
        # for debugging or richer consumers.
        result = _attach_span_offsets_to_result(result, cleaned_text, doc_id)
        self.processor.last_summary_result = result

        # Optional: per-turn logging when log_response is enabled
        log_cfg = (getattr(self.processor, "config", {}) or {}).get("logging", {}) or {}
        if log_cfg.get("log_response") and result is not None:
            # 1) one line: input prompt
            self.processor.logger.info(
                "conversation_input sync turn=%d doc_id=%r has_summary=%s INPUT=%r",
                conversation_state.turn_index,
                result.doc_id,
                bool(summary),
                result.input_text,
            )
            # 2) one line: raw model output
            self.processor.logger.info(
                "conversation_output sync turn=%d doc_id=%r OUTPUT=%r",
                conversation_state.turn_index,
                result.doc_id,
                result.output_text,
            )
            # 3) one line: full ProcessorResult object
            self.processor.logger.info(
                "conversation_result sync turn=%d doc_id=%r result=%r",
                conversation_state.turn_index,
                result.doc_id,
                result,
            )

        # Build updated state: append result to history list
        new_results = conversation_state.results.copy()
        if result is not None:
            new_results.append(result)

        updated_state = MessyTextConversationState(
            turn_index=conversation_state.turn_index + 1,
            results=new_results,
        )
        return summary, updated_state


class MessyTextConversationOrchestrator:
    """
    Orchestrates a multi-turn MessyText conversation over a sequence of documents.

    This class is responsible for:

    - Deciding where to start (initial state).
    - Stepping through documents sequentially.
    - Passing the updated MessyTextConversationState between turns.
    - Applying optional stopping criteria (e.g., maximum turns or a custom
      stop condition callback).

    It does not perform any I/O or DataFrame operations; callers are expected
    to adapt their own data structures (e.g., lists of strings, DataFrame rows)
    to the `texts` iterable interface.
    """

    def __init__(self, turn_processor: MessyTextConversationTurnProcessor) -> None:
        """
        Initializes the orchestrator.

        Args:
            turn_processor (MessyTextConversationTurnProcessor): The per-turn
                processor used to handle individual documents.
        """
        self.turn_processor = turn_processor

    def run_conversation(
        self,
        texts: Iterable[str],
        initial_state: Optional[MessyTextConversationState] = None,
        stop_condition: Optional[
            Callable[[MessyTextConversationState, str], bool]
        ] = None,
    ) -> Tuple[List[str], MessyTextConversationState]:
        """
        Runs a sequential conversation over a collection of texts.

        Args:
            texts (Iterable[str]): Iterable of raw document texts to process
                sequentially (one per turn).
            initial_state (Optional[MessyTextConversationState]): Starting
                conversation state. If None, a new empty state is created.
            stop_condition (Optional[Callable[[MessyTextConversationState, str], bool]]):
                Optional callback that receives the current state and the most
                recent summary. If it returns True, the conversation stops after
                that turn.

        Returns:
            Tuple[List[str], MessyTextConversationState]:
                - List of per-turn summaries in the order they were processed.
                - Final conversation state after the last processed turn.
        """
        state = initial_state or MessyTextConversationState()
        summaries: List[str] = []

        for raw_text in texts:
            summary, state = self.turn_processor.process_turn(raw_text, state)
            summaries.append(summary)

            if stop_condition is not None and stop_condition(state, summary):
                break

        return summaries, state


class AsyncMessyTextConversationTurnProcessor:
    """Async single-turn conversation processor wrapping :class:`AsyncMessyTextProcessor`.

    Cleans text, calls the underlying processor's conversation-summary
    method, attaches span offsets, logs the turn when ``log_response`` is
    enabled, and returns an updated :class:`MessyTextConversationState`.

    Attributes:
        processor: The underlying :class:`AsyncMessyTextProcessor`.
    """

    def __init__(self, processor: AsyncMessyTextProcessor) -> None:
        """Initialise the async turn processor.

        Args:
            processor: The underlying async processor responsible for
                cleaning, prompt construction, and LLM calls.
        """
        self.processor = processor

    async def process_turn(
        self,
        raw_text: str,
        state: Optional[MessyTextConversationState] = None,
        doc_id: Optional[Any] = None,
    ) -> Tuple[str, MessyTextConversationState]:
        """
        Asynchronously processes a single document as one conversation turn.

        Args:
            raw_text (str): The raw document text for this turn.
            state (Optional[MessyTextConversationState]): Existing conversation
                state to carry over between turns. If None, a new state is created.

        Returns:
            Tuple[str, MessyTextConversationState]:
                - The summary generated for this turn.
                - The updated conversation state including the latest summary and
                  incremented turn index, plus the structured ProcessorResult for
                  this turn in state.last_result.
        """
        conversation_state = state or MessyTextConversationState()

        cleaned_text = self.processor.clean_text(raw_text)
        result: Optional[ProcessorResult] = None

        if not cleaned_text.strip():
            result = ProcessorResult(
                task_name="conversation_summary",
                model_name=self.processor.model_name,
                declared_fields={},
                values={"info_found": "FALSE", "summary": "", "relevant_context": []},
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={},
            )
            summary = ""
        else:
            kwargs = self.processor._get_conversation_summary_args(
                previous_summary=conversation_state.last_summary,
                text=cleaned_text,
            )
            try:
                response = await self.processor.client.chat.completions.create(**kwargs)
                result = ProcessorResult.from_llm_call(
                    task_name="conversation_summary",
                    model_name=self.processor.model_name,
                    request_kwargs=kwargs,
                    response=response,
                    doc_id=doc_id,
                )
                summary_value = result.get("summary")
                if isinstance(summary_value, str) and summary_value.strip():
                    summary = summary_value
                else:
                    summary = ""
            except Exception as e:
                self.processor.logger.error(f"Summarization (conversation) failed: {e}")
                result = ProcessorResult(
                    task_name="conversation_summary",
                    model_name=self.processor.model_name,
                    declared_fields={},
                    values={"info_found": "FALSE", "summary": "", "relevant_context": []},
                    input_text="",
                    input_struct=None,
                    output_text="",
                    output_struct=None,
                    doc_id=doc_id,
                    error=str(e),
                    metadata={},
                )
                summary = ""

        result = _attach_span_offsets_to_result(result, cleaned_text, doc_id)
        self.processor.last_summary_result = result

        log_cfg = (getattr(self.processor, "config", {}) or {}).get("logging", {}) or {}
        if log_cfg.get("log_response") and result is not None:
            # 1) one line: input prompt
            self.processor.logger.info(
                "conversation_input async turn=%d doc_id=%r has_summary=%s INPUT=%r",
                conversation_state.turn_index,
                result.doc_id,
                bool(summary),
                result.input_text,
            )
            # 2) one line: raw model output
            self.processor.logger.info(
                "conversation_output async turn=%d doc_id=%r OUTPUT=%r",
                conversation_state.turn_index,
                result.doc_id,
                result.output_text,
            )
            # 3) one line: full ProcessorResult object
            self.processor.logger.info(
                "conversation_result async turn=%d doc_id=%r result=%r",
                conversation_state.turn_index,
                result.doc_id,
                result,
            )

        # Build updated state: append result to history list
        new_results = conversation_state.results.copy()
        if result is not None:
            new_results.append(result)

        updated_state = MessyTextConversationState(
            turn_index=conversation_state.turn_index + 1,
            results=new_results,
        )
        return summary, updated_state


class AsyncMessyTextConversationOrchestrator:
    """
    Asynchronous orchestrator for multi-turn MessyText conversations.

    This class mirrors MessyTextConversationOrchestrator but exposes an async
    run_conversation method so that multiple conversations can be executed
    concurrently by higher-level pipelines.
    """

    def __init__(self, turn_processor: AsyncMessyTextConversationTurnProcessor) -> None:
        """
        Initializes the async orchestrator.

        Args:
            turn_processor (AsyncMessyTextConversationTurnProcessor): The per-turn
                processor used to handle individual documents asynchronously.
        """
        self.turn_processor = turn_processor

    async def run_conversation(
        self,
        texts: Iterable[str],
        initial_state: Optional[MessyTextConversationState] = None,
        stop_condition: Optional[
            Callable[[MessyTextConversationState, str], bool]
        ] = None,
    ) -> Tuple[List[str], MessyTextConversationState]:
        """
        Asynchronously runs a sequential conversation over a collection of texts.

        Args:
            texts (Iterable[str]): Iterable of raw document texts to process
                sequentially (one per turn).
            initial_state (Optional[MessyTextConversationState]): Starting
                conversation state. If None, a new empty state is created.
            stop_condition (Optional[Callable[[MessyTextConversationState, str], bool]]):
                Optional callback that receives the current state and the most
                recent summary. If it returns True, the conversation stops after
                that turn.

        Returns:
            Tuple[List[str], MessyTextConversationState]:
                - List of per-turn summaries in the order they were processed.
                - Final conversation state after the last processed turn.
        """
        state = initial_state or MessyTextConversationState()
        summaries: List[str] = []

        for raw_text in texts:
            summary, state = await self.turn_processor.process_turn(raw_text, state)
            summaries.append(summary)

            if stop_condition is not None and stop_condition(state, summary):
                break

        return summaries, state


# ---------------------------------------------------------------------------
# Per-label extraction processor (base, sync, async)
# ---------------------------------------------------------------------------


class LabelExtractorLogicMixin:
    """
    Contains pure logic for single-label span extraction from document text.

    Handles text cleaning and prompt construction for extracting spans
    relevant to exactly one taxonomy label from a single document.
    Decoupled from I/O (client calls).

    This mixin reads prompt configuration from the following keys:

        prompts.label_extract_first  — first-turn extraction (no previous spans).
        prompts.label_extract_update — update-turn extraction (has previous spans).

    These are independent of the prompt keys used by the existing
    MessyTextLogicMixin so that old prompts remain untouched.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        label_key: str,
        label_definition: str,
        logger: logging.Logger,
    ):
        """
        Initializes the label extractor logic mixin.

        Args:
            config (Dict[str, Any]): Runtime settings. Expected keys include
                model.name, processing.temperature, processing.max_tokens_summary,
                and prompts with label_extract_first / label_extract_update.
            label_key (str): The taxonomy key this extractor is bound to
                (e.g. 'vic_grupo_social'). Selected by the caller before
                construction; not looked up internally.
            label_definition (str): The human-readable definition for
                label_key. Provided by the caller; not looked up internally.
            logger (logging.Logger): Logger instance.
        """
        self.config = config
        self.label_key = label_key
        self.label_definition = label_definition
        self.logger = logger
        self.model_name = config['model']['name']

    def clean_text(self, text: str) -> str:
        """
        Applies regex cleaning to input text.

        Args:
            text (str): The raw input text to clean.

        Returns:
            str: The cleaned text with URLs removed and whitespace normalized.
        """
        if not isinstance(text, str):
            return str(text)
        text = re.sub(
            r'https?://\S+|\([^)]*/[^)]*\)|[\ue000-\uf8ff]|\b\d/\d\b', '', text
        )
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _get_label_extract_args(
        self,
        text: str,
        previous_spans: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Constructs arguments for a single-label extraction API call.

        Uses ``self.label_key`` and ``self.label_definition`` bound at
        construction time. The built-in first-turn vs. update-turn switch
        (based on whether ``previous_spans`` is supplied) only drives the
        fallback base-prompt lookup; step-level overrides apply uniformly
        regardless of which turn.

        Honours the per-step overrides that
        :meth:`src.flow_builder.FlowRunner._resolve_processor_config_for_step`
        may have injected into ``self.config``:

        - ``self.config['prompt_resolved']`` (:class:`src.prompt_resolver.ResolvedPrompt`
          or ``None``): when set, its instructions replace the base
          instruction list and its ``output_format`` (when not ``None``)
          replaces the base ``output_format``.
        - ``self.config['io_schema_resolved']`` (:class:`src.io_schema.IOSchema`
          or ``None``): when set, used to derive the prompt-body
          ``output_format`` (if no prompt-level override sets one) and
          the LLM ``response_format`` dict, replacing the method's
          historical hardcoded ``label_extract`` schema.

        When neither key is set the method falls back to the historical
        ``self.config['prompts']['label_spans_extract']`` lookup and the
        hardcoded ``label_extract`` response schema.

        Args:
            text (str): The cleaned document text.
            previous_spans (Optional[List[Dict[str, Any]]]): Spans extracted for
                this label in previous turns, or None for the first turn.

        Returns:
            Dict[str, Any]: A dictionary containing model arguments (model,
            messages, etc.) suitable for chat.completions.create. The
            ``response_format`` is either derived from
            ``io_schema_resolved`` or the hardcoded ``label_extract``
            schema, depending on what the flow runner injected.
        """
        prompts_cfg = self.config.get("prompts") or {}
        prompt_resolved: Optional[ResolvedPrompt] = self.config.get("prompt_resolved")
        io_schema_resolved: Optional[IOSchema] = self.config.get("io_schema_resolved")

        has_previous = previous_spans is not None and len(previous_spans) > 0
        extract_cfg = prompts_cfg.get("label_spans_extract") or {}

        if prompt_resolved is not None:
            instructions_template = list(prompt_resolved.instructions)
        else:
            instructions_template = extract_cfg.get("instructions")

        if prompt_resolved is not None and prompt_resolved.output_format is not None:
            output_format = prompt_resolved.output_format
        elif io_schema_resolved is not None:
            output_format = to_prompt_output_format_text(io_schema_resolved)
        else:
            output_format = extract_cfg.get("output_format")

        if output_format is None or instructions_template is None:
            raise ValueError(
                "Label extraction prompt configuration must provide "
                "'output_format' and 'instructions'."
            )

        previous_spans_str = json.dumps(
            previous_spans or [], ensure_ascii=False
        )

        class _SafeFormatDict(dict):
            def __missing__(self, key: str) -> str:
                return "{" + key + "}"

        format_vars = _SafeFormatDict(
            label=self.label_key,
            label_key=self.label_key,
            label_definition=self.label_definition,
            previous_spans=previous_spans_str,
            info_found_label="info_found",
            spans_label="spans",
            input_text_label="input_text",
        )

        instructions = [
            instr.format_map(format_vars)
            for instr in instructions_template
        ]

        prompt_structure = {
            'input_text': text,
            'label_key': self.label_key,
            'label_definition': self.label_definition,
            'previous_spans': previous_spans or [],
            'output_format': output_format,
            'instructions': instructions,
        }

        prompt_content = str(prompt_structure)

        if io_schema_resolved is not None:
            response_format = to_response_format(
                io_schema_resolved, schema_name="label_extract",
            )
        else:
            response_format = {"type": "json_schema", "json_schema": {
                "name": "label_extract",
                "schema": {
                    "type": "object",
                    "properties": {
                        "info_found": {"type": "string"},
                        "spans": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "span": {"type": "string"}
                                },
                                "required": ["span"]
                            }
                        },
                        "confidence_score": {"type": "string"}
                    },
                    "required": ["info_found", "spans", "confidence_score"]
                }
            }}

        return {
            "model": self.model_name,
            "messages": [{'role': 'user', 'content': prompt_content}],
            "temperature": self.config['processing']['temperature'],
            "max_tokens": self.config['processing']['max_tokens_summary'],
            "response_format": response_format,
        }


class LabelExtractor(LabelExtractorLogicMixin):
    """
    Synchronous single-label extraction processor.

    Processes one taxonomy label against one document text, returning a
    ProcessorResult with the extraction output for that label.

    The label_key and label_definition are bound at construction time by
    the caller (runner loop). This object has no access to the full taxonomy.
    """

    def __init__(
        self,
        client: Any,
        config: Dict[str, Any],
        label_key: str,
        label_definition: str,
        logger: logging.Logger,
    ):
        """
        Initializes the synchronous label extractor.

        Args:
            client (OpenAI): The synchronous OpenAI/vLLM client instance.
            config (Dict[str, Any]): Runtime settings (model name, tokens, etc).
            label_key (str): The taxonomy key this extractor is bound to.
            label_definition (str): The human-readable definition for label_key.
            logger (logging.Logger): Logger instance.
        """
        super().__init__(config, label_key, label_definition, logger)
        self.client = client

    def extract_label(
        self,
        text: str,
        previous_spans: Optional[List[Dict[str, Any]]] = None,
        doc_id: Optional[Any] = None,
    ) -> ProcessorResult:
        """
        Run a single-label extraction call and return the ProcessorResult.

        Uses self.label_key and self.label_definition bound at construction.

        Args:
            text (str): The cleaned document text.
            previous_spans (Optional[List[Dict[str, Any]]]): Spans from previous
                turns for this label, or None for the first turn.
            doc_id (Optional[Any]): Document identifier for traceback.

        Returns:
            ProcessorResult: Structured result containing info_found, spans,
            and summary for this single label.
        """
        if not text or not text.strip():
            return ProcessorResult(
                task_name="label_extract",
                model_name=self.model_name,
                declared_fields={},
                values={"info_found": "FALSE", "spans": [], "summary": ""},
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={"label_key": self.label_key},
            )

        kwargs = self._get_label_extract_args(
            text=text,
            previous_spans=previous_spans,
        )

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Label extraction failed for {self.label_key}: {e}", exc_info=True)
            messages = kwargs.get("messages", []) or [{}]
            input_text = str(messages[0].get("content", ""))
            return ProcessorResult(
                task_name="label_extract",
                model_name=self.model_name,
                declared_fields={},
                values={"info_found": "FALSE", "spans": [], "summary": ""},
                input_text=input_text,
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=str(e),
                metadata={"label_key": self.label_key},
            )

        result = ProcessorResult.from_llm_call(
            task_name="label_extract",
            model_name=self.model_name,
            request_kwargs=kwargs,
            response=response,
            doc_id=doc_id,
        )
        result.metadata["label_key"] = self.label_key
        return result


class AsyncLabelExtractor(LabelExtractorLogicMixin):
    """
    Asynchronous single-label extraction processor.

    Processes one taxonomy label against one document text, returning a
    ProcessorResult with the extraction output for that label.
    Uses async/await patterns with AsyncOpenAI client.

    The label_key and label_definition are bound at construction time by
    the caller (runner loop). This object has no access to the full taxonomy.
    """

    def __init__(
        self,
        client: Any,
        config: Dict[str, Any],
        label_key: str,
        label_definition: str,
        logger: logging.Logger,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ):
        """
        Initializes the asynchronous label extractor.

        Args:
            client (AsyncOpenAI): The asynchronous OpenAI/vLLM client instance.
            config (Dict[str, Any]): Runtime settings (model name, tokens, etc).
            label_key (str): The taxonomy key this extractor is bound to.
            label_definition (str): The human-readable definition for label_key.
            logger (logging.Logger): Logger instance.
            llm_semaphore (Optional[asyncio.Semaphore]): If provided, each LLM
                call acquires this semaphore, capping in-flight requests globally.
        """
        super().__init__(config, label_key, label_definition, logger)
        self.client = client
        self._llm_semaphore = llm_semaphore

    async def extract_label(
        self,
        text: str,
        previous_spans: Optional[List[Dict[str, Any]]] = None,
        doc_id: Optional[Any] = None,
    ) -> ProcessorResult:
        """
        Asynchronously run a single-label extraction call.

        Uses self.label_key and self.label_definition bound at construction.

        Args:
            text (str): The cleaned document text.
            previous_spans (Optional[List[Dict[str, Any]]]): Spans from previous
                turns for this label, or None for the first turn.
            doc_id (Optional[Any]): Document identifier for traceback.

        Returns:
            ProcessorResult: Structured result containing info_found, spans,
            and summary for this single label.
        """
        if not text or not text.strip():
            return ProcessorResult(
                task_name="label_extract",
                model_name=self.model_name,
                declared_fields={},
                values={"info_found": "FALSE", "spans": [], "summary": ""},
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={"label_key": self.label_key},
            )

        kwargs = self._get_label_extract_args(
            text=text,
            previous_spans=previous_spans,
        )

        try:
            if self._llm_semaphore:
                async with self._llm_semaphore:
                    response = await self.client.chat.completions.create(**kwargs)
            else:
                response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Label extraction failed for {self.label_key}: {e}", exc_info=True)
            messages = kwargs.get("messages", []) or [{}]
            input_text = str(messages[0].get("content", ""))
            return ProcessorResult(
                task_name="label_extract",
                model_name=self.model_name,
                declared_fields={},
                values={"info_found": "FALSE", "spans": [], "summary": ""},
                input_text=input_text,
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=str(e),
                metadata={"label_key": self.label_key},
            )

        result = ProcessorResult.from_llm_call(
            task_name="label_extract",
            model_name=self.model_name,
            request_kwargs=kwargs,
            response=response,
            doc_id=doc_id,
        )
        result.metadata["label_key"] = self.label_key
        return result


# ---------------------------------------------------------------------------
# Label-based span extraction processor (base, sync, async)
# ---------------------------------------------------------------------------


class TextLabelsSummaryLogicMixin:
    """
    Contains pure logic for producing a document summary from per-label
    extraction results.

    Handles prompt construction for the summarization call that takes
    pre-extracted label evidence as input and produces a coherent
    document-level summary.
    Decoupled from I/O (client calls).

    This mixin reads prompt configuration from the following key:

        prompts.label_summary — summarization from per-label evidence.

    This is independent of the prompt keys used by the existing
    MessyTextLogicMixin so that old prompts remain untouched.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        taxonomy: Dict[str, Any],
        logger: logging.Logger,
    ):
        """
        Initializes the label summary logic mixin.

        Args:
            config (Dict[str, Any]): Runtime settings. Expected keys include
                model.name, processing.temperature, processing.max_tokens_summary,
                and prompts with label_summary.
            taxonomy (Dict[str, Any]): Static definitions (context_definitions,
                label_options).
            logger (logging.Logger): Logger instance.
        """
        self.config = config
        self.definitions = taxonomy['context_definitions']
        self.labels = taxonomy['label_options']
        self.logger = logger
        self.model_name = config['model']['name']

    def clean_text(self, text: str) -> str:
        """
        Applies regex cleaning to input text.

        Args:
            text (str): The raw input text to clean.

        Returns:
            str: The cleaned text with URLs removed and whitespace normalized.
        """
        if not isinstance(text, str):
            return str(text)
        text = re.sub(
            r'https?://\S+|\([^)]*/[^)]*\)|[\ue000-\uf8ff]|\b\d/\d\b', '', text
        )
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _get_label_summary_args(
        self,
        text: str,
        label_results: Dict[str, ProcessorResult],
        previous_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Constructs arguments for a label-based summary API call.

        Takes the original document text and the per-label extraction
        results, formatting them into a prompt that asks the model to
        produce a coherent summary from the extracted evidence. The
        built-in first-turn vs. update-turn switch (based on whether
        ``previous_summary`` is set) only drives the fallback base-prompt
        lookup; step-level overrides apply uniformly to both turns.

        Honours the per-step overrides that
        :meth:`src.flow_builder.FlowRunner._resolve_processor_config_for_step`
        may have injected into ``self.config``:

        - ``self.config['prompt_resolved']`` (:class:`src.prompt_resolver.ResolvedPrompt`
          or ``None``): when set, its instructions replace the base list
          and its ``output_format`` (when not ``None``) replaces the base
          ``output_format``.
        - ``self.config['io_schema_resolved']`` (:class:`src.io_schema.IOSchema`
          or ``None``): when set, used to derive the prompt-body
          ``output_format`` (if no prompt-level override sets one) and
          the LLM ``response_format`` dict, replacing the method's
          historical hardcoded ``label_summary`` schema.

        When neither key is set the method falls back to the historical
        ``prompts.json`` lookup (``label_summary_update`` >
        ``label_summary_first``) and the hardcoded ``label_summary``
        response schema, byte-for-byte identical to the pre-registry
        runtime.

        Args:
            text (str): The cleaned document text.
            label_results (Dict[str, ProcessorResult]): Mapping from label_key
                to the ProcessorResult returned by the label extractor for
                that key.
            previous_summary (Optional[str]): The running summary from earlier
                turns, or None/empty string for the first turn.

        Returns:
            Dict[str, Any]: A dictionary containing model arguments (model,
            messages, etc.) suitable for chat.completions.create. The
            ``response_format`` is either derived from
            ``io_schema_resolved`` or the hardcoded ``label_summary``
            schema, depending on what the flow runner injected.
        """
        prompts_cfg = self.config.get("prompts") or {}
        prompt_resolved: Optional[ResolvedPrompt] = self.config.get("prompt_resolved")
        io_schema_resolved: Optional[IOSchema] = self.config.get("io_schema_resolved")

        has_previous = bool(previous_summary and previous_summary.strip())
        if has_previous:
            summary_cfg = (
                prompts_cfg.get("label_summary_update")
                or prompts_cfg.get("label_summary_first")
                or {}
            )
        else:
            summary_cfg = (
                prompts_cfg.get("label_summary_first")
                or {}
            )

        if prompt_resolved is not None:
            instructions_template = list(prompt_resolved.instructions)
        else:
            instructions_template = summary_cfg.get("instructions")

        if prompt_resolved is not None and prompt_resolved.output_format is not None:
            output_format = prompt_resolved.output_format
        elif io_schema_resolved is not None:
            output_format = to_prompt_output_format_text(io_schema_resolved)
        else:
            output_format = summary_cfg.get("output_format")

        if output_format is None or instructions_template is None:
            raise ValueError(
                "Label summary prompt configuration must provide "
                "'output_format' and 'instructions'."
            )

        spans_by_item: Dict[str, Any] = {
            label_key: result.get("spans") or []
            for label_key, result in label_results.items()
        }

        spans_by_item_str = json.dumps(spans_by_item, ensure_ascii=False)

        class _SafeFormatDict(dict):
            def __missing__(self, key: str) -> str:
                return "{" + key + "}"

        format_vars = _SafeFormatDict(
            spans_by_item=spans_by_item_str,
            previous_summary=previous_summary or "",
            info_found_label="info_found",
        )

        instructions = [
            instr.format_map(format_vars)
            for instr in instructions_template
        ]

        prompt_structure = {
            'input_text': text,
            'spans_by_item': spans_by_item,
            'previous_summary': previous_summary or "",
            'output_format': output_format,
            'instructions': instructions,
        }

        prompt_content = str(prompt_structure)

        if io_schema_resolved is not None:
            response_format = to_response_format(
                io_schema_resolved, schema_name="label_summary",
            )
        else:
            response_format = {"type": "json_schema", "json_schema": {
                "name": "label_summary",
                "schema": {
                    "type": "object",
                    "properties": {
                        "info_found": {"type": "string"},
                        "spans_by_item": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "span": {"type": "string"}
                                    },
                                    "required": ["span"]
                                }
                            }
                        },
                        "summary": {"type": "string"}
                    },
                    "required": ["info_found", "spans_by_item", "summary"]
                }
            }}

        return {
            "model": self.model_name,
            "messages": [{'role': 'user', 'content': prompt_content}],
            "temperature": self.config['processing']['temperature'],
            "max_tokens": self.config['processing']['max_tokens_summary'],
            "response_format": response_format,
        }

    def _get_synthesis_args(
        self,
        per_doc_summaries: List[str],
    ) -> Dict[str, Any]:
        """Constructs arguments for a synthesis API call from per-document summaries.

        Unlike :meth:`_get_label_summary_args`, this method does not
        branch on ``previous_summary`` and always uses the
        ``label_synthesis`` prompt key. It is the reconciliation step of
        the concurrent pipeline: all per-document summaries have already
        been produced independently by the concurrent orchestrator, and
        this call merges them into a single coherent victim-level
        summary.

        Unlike the other ``_get_*_args`` methods in this module, this
        method deliberately does NOT consume the per-step
        ``self.config['io_schema_resolved']`` or
        ``self.config['prompt_resolved']`` keys that
        :class:`src.flow_builder.FlowRunner` injects. Those two keys
        describe the step-level contract (for example the ``label_summary``
        step), whose I/O shape differs from the synthesis contract:
        ``label_summary`` emits ``info_found``/``spans_by_item``/``summary``
        while ``label_synthesis`` emits only ``info_found``/``summary``.
        Binding the step-level override here would silently corrupt the
        reconciliation schema, so the method preserves the hardcoded
        ``label_synthesis`` ``response_format`` and reads the
        ``label_synthesis`` prompt entry from ``self.config['prompts']``
        verbatim. If future work exposes synthesis as a first-class step
        type with its own registry entry, it should be wired through a
        dedicated override key rather than piggybacking on the
        step-level keys consumed by the other methods.

        Args:
            per_doc_summaries (List[str]): Per-document summary strings produced
                by the concurrent summarization stage, one per document for this
                victim.

        Returns:
            Dict[str, Any]: A dictionary containing model arguments (model,
            messages, temperature, max_tokens, response_format) suitable
            for ``chat.completions.create``. ``response_format`` is
            always the hardcoded ``label_synthesis`` schema.
        """
        prompts_cfg = self.config.get("prompts") or {}
        synthesis_cfg = prompts_cfg.get("label_synthesis") or {}

        output_format = synthesis_cfg.get("output_format")
        instructions_template = synthesis_cfg.get("instructions")

        if output_format is None or instructions_template is None:
            raise ValueError(
                "Label synthesis prompt configuration must provide "
                "'output_format' and 'instructions'."
            )

        per_doc_summaries_str = json.dumps(per_doc_summaries, ensure_ascii=False)

        class _SafeFormatDict(dict):
            def __missing__(self, key: str) -> str:
                return "{" + key + "}"

        format_vars = _SafeFormatDict(
            per_doc_summaries=per_doc_summaries_str,
            info_found_label="info_found",
        )

        instructions = [
            instr.format_map(format_vars)
            for instr in instructions_template
        ]

        prompt_structure = {
            'per_doc_summaries': per_doc_summaries,
            'output_format': output_format,
            'instructions': instructions,
        }

        prompt_content = str(prompt_structure)

        return {
            "model": self.model_name,
            "messages": [{'role': 'user', 'content': prompt_content}],
            "temperature": self.config['processing']['temperature'],
            "max_tokens": self.config['processing']['max_tokens_summary'],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "label_synthesis",
                "schema": {
                    "type": "object",
                    "properties": {
                        "info_found": {"type": "string"},
                        "summary": {"type": "string"}
                    },
                    "required": ["info_found", "summary"]
                }
            }}
        }


class TextLabelsSummaryProcessor(TextLabelsSummaryLogicMixin):
    """
    Synchronous label-based summary processor.

    Takes pre-extracted per-label ProcessorResults and the original document
    text, makes a single LLM call, and returns a ProcessorResult whose values
    match the existing conversation summary contract (info_found,
    relevant_context, summary_by_item, summary).
    """

    def __init__(
        self,
        client: Any,
        config: Dict[str, Any],
        taxonomy: Dict[str, Any],
        logger: logging.Logger,
    ):
        """
        Initializes the synchronous label summary processor.

        Args:
            client (OpenAI): The synchronous OpenAI/vLLM client instance.
            config (Dict[str, Any]): Runtime settings (model name, tokens, etc).
            taxonomy (Dict[str, Any]): Static definitions (context_definitions,
                label_options).
            logger (logging.Logger): Logger instance.
        """
        super().__init__(config, taxonomy, logger)
        self.client = client

    def summarize_from_labels(
        self,
        text: str,
        label_results: Dict[str, ProcessorResult],
        previous_summary: Optional[str] = None,
        doc_id: Optional[Any] = None,
    ) -> ProcessorResult:
        """
        Run a summary call from per-label extraction results.

        Args:
            text (str): The cleaned document text.
            label_results (Dict[str, ProcessorResult]): Mapping from label_key
                to the ProcessorResult returned by the label extractor.
            previous_summary (Optional[str]): The running summary from earlier
                turns, or None for the first turn.
            doc_id (Optional[Any]): Document identifier for traceback.

        Returns:
            ProcessorResult: Structured result containing info_found,
            relevant_context, summary_by_item, and summary.
        """
        if not text or not text.strip():
            return ProcessorResult(
                task_name="label_summary",
                model_name=self.model_name,
                declared_fields={},
                values={
                    "info_found": "FALSE",
                    "relevant_context": [],
                    "summary_by_item": {},
                    "summary": "",
                },
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={},
            )

        kwargs = self._get_label_summary_args(
            text=text,
            label_results=label_results,
            previous_summary=previous_summary,
        )

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Label summary failed: {e}")
            messages = kwargs.get("messages", []) or [{}]
            input_text = str(messages[0].get("content", ""))
            return ProcessorResult(
                task_name="label_summary",
                model_name=self.model_name,
                declared_fields={},
                values={
                    "info_found": "FALSE",
                    "relevant_context": [],
                    "summary_by_item": {},
                    "summary": "",
                },
                input_text=input_text,
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=str(e),
                metadata={},
            )

        return ProcessorResult.from_llm_call(
            task_name="label_summary",
            model_name=self.model_name,
            request_kwargs=kwargs,
            response=response,
            doc_id=doc_id,
        )

    def synthesize_from_summaries(
        self,
        per_doc_summaries: List[str],
        doc_id: Optional[Any] = None,
    ) -> ProcessorResult:
        """
        Produces a single synthesized victim-level summary from per-document summaries.

        This is the reconciliation step for the concurrent pipeline: after all
        documents have been summarized independently by the concurrent
        orchestrator, this method makes one LLM call to merge them into a
        single coherent victim-level narrative.

        Args:
            per_doc_summaries (List[str]): Per-document summary strings produced
                by the concurrent summarization stage. Empty strings are allowed
                (they represent documents with no relevant information found).
            doc_id (Optional[Any]): Identifier for traceability (typically
                the victim_id).

        Returns:
            ProcessorResult: Structured result with info_found and summary.
        """
        coerced = [str(s) if not isinstance(s, str) else s for s in per_doc_summaries if s is not None]
        non_empty = [s for s in coerced if s and s.strip()]
        if not non_empty:
            return ProcessorResult(
                task_name="label_synthesis",
                model_name=self.model_name,
                declared_fields={},
                values={"info_found": "FALSE", "summary": ""},
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={},
            )

        kwargs = self._get_synthesis_args(per_doc_summaries=non_empty)

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Label synthesis failed: {e}")
            messages = kwargs.get("messages", []) or [{}]
            input_text = str(messages[0].get("content", ""))
            return ProcessorResult(
                task_name="label_synthesis",
                model_name=self.model_name,
                declared_fields={},
                values={"info_found": "FALSE", "summary": ""},
                input_text=input_text,
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=str(e),
                metadata={},
            )

        return ProcessorResult.from_llm_call(
            task_name="label_synthesis",
            model_name=self.model_name,
            request_kwargs=kwargs,
            response=response,
            doc_id=doc_id,
        )


class AsyncTextLabelsSummaryProcessor(TextLabelsSummaryLogicMixin):
    """
    Asynchronous label-based summary processor.

    Takes pre-extracted per-label ProcessorResults and the original document
    text, makes a single LLM call, and returns a ProcessorResult whose values
    match the existing conversation summary contract (info_found,
    relevant_context, summary_by_item, summary).
    Uses async/await patterns with AsyncOpenAI client.
    """

    def __init__(
        self,
        client: Any,
        config: Dict[str, Any],
        taxonomy: Dict[str, Any],
        logger: logging.Logger,
        llm_semaphore: Optional[asyncio.Semaphore] = None,
    ):
        """
        Initializes the asynchronous label summary processor.

        Args:
            client (AsyncOpenAI): The asynchronous OpenAI/vLLM client instance.
            config (Dict[str, Any]): Runtime settings (model name, tokens, etc).
            taxonomy (Dict[str, Any]): Static definitions (context_definitions,
                label_options).
            logger (logging.Logger): Logger instance.
            llm_semaphore (Optional[asyncio.Semaphore]): If provided, each LLM
                call acquires this semaphore, capping in-flight requests globally.
        """
        super().__init__(config, taxonomy, logger)
        self.client = client
        self._llm_semaphore = llm_semaphore

    async def summarize_from_labels(
        self,
        text: str,
        label_results: Dict[str, ProcessorResult],
        previous_summary: Optional[str] = None,
        doc_id: Optional[Any] = None,
    ) -> ProcessorResult:
        """
        Asynchronously run a summary call from per-label extraction results.

        Args:
            text (str): The cleaned document text.
            label_results (Dict[str, ProcessorResult]): Mapping from label_key
                to the ProcessorResult returned by the label extractor.
            previous_summary (Optional[str]): The running summary from earlier
                turns, or None for the first turn.
            doc_id (Optional[Any]): Document identifier for traceback.

        Returns:
            ProcessorResult: Structured result containing info_found,
            relevant_context, summary_by_item, and summary.
        """
        if not text or not text.strip():
            return ProcessorResult(
                task_name="label_summary",
                model_name=self.model_name,
                declared_fields={},
                values={
                    "info_found": "FALSE",
                    "relevant_context": [],
                    "summary_by_item": {},
                    "summary": "",
                },
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={},
            )

        kwargs = self._get_label_summary_args(
            text=text,
            label_results=label_results,
            previous_summary=previous_summary,
        )

        try:
            if self._llm_semaphore:
                async with self._llm_semaphore:
                    response = await self.client.chat.completions.create(**kwargs)
            else:
                response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Label summary failed: {e}")
            messages = kwargs.get("messages", []) or [{}]
            input_text = str(messages[0].get("content", ""))
            return ProcessorResult(
                task_name="label_summary",
                model_name=self.model_name,
                declared_fields={},
                values={
                    "info_found": "FALSE",
                    "relevant_context": [],
                    "summary_by_item": {},
                    "summary": "",
                },
                input_text=input_text,
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=str(e),
                metadata={},
            )

        return ProcessorResult.from_llm_call(
            task_name="label_summary",
            model_name=self.model_name,
            request_kwargs=kwargs,
            response=response,
            doc_id=doc_id,
        )

    async def synthesize_from_summaries(
        self,
        per_doc_summaries: List[str],
        doc_id: Optional[Any] = None,
    ) -> ProcessorResult:
        """
        Asynchronously produces a single synthesized victim-level summary from
        per-document summaries.

        This is the reconciliation step for the concurrent pipeline: after all
        documents have been summarized independently by the concurrent
        orchestrator, this method makes one LLM call to merge them into a
        single coherent victim-level narrative.

        Args:
            per_doc_summaries (List[str]): Per-document summary strings produced
                by the concurrent summarization stage. Empty strings are allowed
                (they represent documents with no relevant information found).
            doc_id (Optional[Any]): Identifier for traceability (typically
                the victim_id).

        Returns:
            ProcessorResult: Structured result with info_found and summary.
        """
        coerced = [str(s) if not isinstance(s, str) else s for s in per_doc_summaries if s is not None]
        non_empty = [s for s in coerced if s and s.strip()]
        if not non_empty:
            return ProcessorResult(
                task_name="label_synthesis",
                model_name=self.model_name,
                declared_fields={},
                values={"info_found": "FALSE", "summary": ""},
                input_text="",
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=None,
                metadata={},
            )

        kwargs = self._get_synthesis_args(per_doc_summaries=non_empty)

        try:
            if self._llm_semaphore:
                async with self._llm_semaphore:
                    response = await self.client.chat.completions.create(**kwargs)
            else:
                response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Label synthesis failed: {e}")
            messages = kwargs.get("messages", []) or [{}]
            input_text = str(messages[0].get("content", ""))
            return ProcessorResult(
                task_name="label_synthesis",
                model_name=self.model_name,
                declared_fields={},
                values={"info_found": "FALSE", "summary": ""},
                input_text=input_text,
                input_struct=None,
                output_text="",
                output_struct=None,
                doc_id=doc_id,
                error=str(e),
                metadata={},
            )

        return ProcessorResult.from_llm_call(
            task_name="label_synthesis",
            model_name=self.model_name,
            request_kwargs=kwargs,
            response=response,
            doc_id=doc_id,
        )


class TextConversationOrchestrator:
    """
    Orchestrates a multi-turn MessyText conversation over a sequence of documents.

    This class is responsible for:

    - Deciding where to start (initial state).
    - Stepping through documents sequentially.
    - Passing the updated MessyTextConversationState between turns.

    The summary processor is a pure call object. This orchestrator owns all
    state transitions: it reads state.last_summary to supply previous_summary,
    appends each result, and increments turn_index. The processor has no
    awareness of state.
    """

    def __init__(self, summary_processor: TextLabelsSummaryProcessor) -> None:
        """
        Args:
            summary_processor (TextLabelsSummaryProcessor): Processor that
                receives per-label extraction results and produces a
                consolidated summary via a single LLM call.
        """
        self.summary_processor = summary_processor

    def run_conversation(
        self,
        documents: Iterable[Tuple[str, Dict[str, ProcessorResult], Optional[Any]]],
        initial_state: Optional[MessyTextConversationState] = None,
        stop_condition: Optional[
            Callable[[MessyTextConversationState, str], bool]
        ] = None,
    ) -> Tuple[List[str], MessyTextConversationState]:
        """
        Runs a sequential conversation over a collection of pre-labelled documents.

        Args:
            documents: Each element is a 3-tuple of
                (text, label_results, doc_id). text is the raw document string.
                label_results maps label_key to its ProcessorResult from
                extraction. doc_id is an optional identifier for traceability.
            initial_state: Starting conversation state. If None, a new empty
                state is created.
            stop_condition: Optional callback receiving (state, summary). If it
                returns True the loop stops after that turn.

        Returns:
            Tuple of per-turn summary strings and the final conversation state.
        """
        state = initial_state or MessyTextConversationState()
        summaries: List[str] = []

        for text, label_results, doc_id in documents:
            result = self.summary_processor.summarize_from_labels(
                text=text,
                label_results=label_results,
                previous_summary=state.last_summary,
                doc_id=doc_id,
            )

            new_results = state.results.copy()
            new_results.append(result)
            state = MessyTextConversationState(
                turn_index=state.turn_index + 1,
                results=new_results,
            )

            summary = result.get("summary") or ""
            summaries.append(summary)

            if stop_condition is not None and stop_condition(state, summary):
                break

        return summaries, state


class AsyncTextConversationOrchestrator:
    """
    Asynchronous orchestrator that fires all document summary calls concurrently
    for a single victim, then assembles results into an ordered state.

    Unlike TextConversationOrchestrator, turns are not sequential within this
    class — all LLM calls are launched at once via asyncio.gather. Because
    there is no sequential dependency chain, each call receives the same
    previous_summary (from initial_state). Results are returned in submission
    order (asyncio.gather preserves order). The runner is responsible for any
    reconciliation across results (e.g. span union).

    This class is responsible for:

    - Deciding where to start (initial state).
    - Firing all document summary calls concurrently.
    - Storing results in submission order with turn_index tracking.
    - Passing doc_id through to each result for downstream traceability.
    """

    def __init__(self, summary_processor: AsyncTextLabelsSummaryProcessor) -> None:
        """
        Args:
            summary_processor (AsyncTextLabelsSummaryProcessor): Async processor
                that receives per-label extraction results and produces a
                consolidated summary via a single LLM call.
        """
        self.summary_processor = summary_processor

    async def run_conversation(
        self,
        documents: Iterable[Tuple[str, Dict[str, ProcessorResult], Optional[Any]]],
        initial_state: Optional[MessyTextConversationState] = None,
        use_progress_bar: bool = False,
    ) -> Tuple[List[str], MessyTextConversationState]:
        """
        Concurrently processes all documents, then assembles results in order.

        All LLM calls are launched simultaneously. Each call receives the same
        previous_summary from initial_state (no sequential chaining). Results
        arrive in submission order via asyncio.gather.

        Args:
            documents: Each element is a 3-tuple of (text, label_results, doc_id).
                text is the raw document string. label_results maps label_key to
                its ProcessorResult from extraction. doc_id is passed through to
                each result for traceability and indexing.
            initial_state: Starting conversation state. If None, a new empty
                state is created. Its last_summary is shared as previous_summary
                for all concurrent calls.
            use_progress_bar: Whether to display a tqdm progress bar tracking
                per-document summary completion.

        Returns:
            Tuple of per-document summary strings (in submission order) and the
            final conversation state with all results appended in submission
            order and turn_index reflecting the number of documents processed.
        """
        state = initial_state or MessyTextConversationState()
        previous_summary = state.last_summary

        doc_list = list(documents)

        tasks = [
            self.summary_processor.summarize_from_labels(
                text=text,
                label_results=label_results,
                previous_summary=previous_summary,
                doc_id=doc_id,
            )
            for text, label_results, doc_id in doc_list
        ]

        results: List[ProcessorResult] = list(
            await tqdm_async.gather(
                *tasks,
                desc=f"Summarising docs ({len(doc_list)} documents)",
                leave=False,
                disable=not use_progress_bar,
            )
        )

        summaries: List[str] = []
        new_results = state.results.copy()
        turn_index = state.turn_index

        for result in results:
            new_results.append(result)
            turn_index += 1
            summaries.append(result.get("summary") or "")

        final_state = MessyTextConversationState(
            turn_index=turn_index,
            results=new_results,
        )

        return summaries, final_state