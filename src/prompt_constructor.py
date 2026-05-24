"""Structured prompt assembly for GenericProcessor.

Separates the user-written base instructions from runtime injection
layers (codebook, output format, future edge types).  Each layer is a
named pair of a fixed *instruction* string (written once by the
developer) and an adaptive *context* string (built at runtime from
data).  Layers are independently conditional — a layer that has no
context is simply absent.

Terminology used throughout the pipeline:

- **instruction** — a predesigned sentence telling the LLM *what to do
  with* the context that follows.  Static; lives in source code.
- **context** — adaptive payload derived from the codebook, the output
  schema, or any future data source.  Changes per flow / per run.
- **injection** — the act of appending a layer (instruction + context)
  to the base instructions at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class InjectionLayer:
    """One conditional block appended after the base instructions.

    Attributes:
        name: Developer-readable label (``"codebook"``,
            ``"output_format"``, …).  Used for logging / debugging.
        instruction: Static sentence describing *what the LLM should do*
            with the context.
        context: Runtime-built payload (codebook JSON, field specs, …).
    """

    name: str
    instruction: str
    context: str


@dataclass
class PromptConstructor:
    """Assembles the system message from base instructions + injection layers.

    Layers are ordered: the first layer appended appears first after the
    base instructions.  Each layer is independently present or absent.

    Attributes:
        base_instructions: Strings the user wrote in the Prompt tab.
            Never mutated by injection logic.
        layers: Ordered injection layers.
    """

    base_instructions: List[str] = field(default_factory=list)
    layers: List[InjectionLayer] = field(default_factory=list)

    def add_layer(
        self,
        name: str,
        instruction: str,
        context: Optional[str],
    ) -> None:
        """Conditionally append a layer.

        If *context* is ``None`` or empty the layer is silently skipped,
        so callers never need an outer ``if`` guard.
        """
        if not context:
            return
        self.layers.append(InjectionLayer(
            name=name,
            instruction=instruction,
            context=context,
        ))

    def build_system_message(self) -> str:
        """Join base instructions and active layers into one string."""
        parts = list(self.base_instructions)
        for layer in self.layers:
            parts.append(layer.instruction)
            parts.append(layer.context)
        return "\n".join(parts)
