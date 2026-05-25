"""HTTP DTOs for the provider model-list proxy.

``GET /api/models/{provider}`` returns the list of models advertised by
an upstream LLM provider (OpenRouter or OpenAI), stripped down to the
fields the GUI's ``LLMProviderNode`` actually renders. The proxy
caches the upstream response in Redis for ten minutes so clicks on the
model picker do not hammer the provider.

Contents and relationships
--------------------------

- :class:`ProviderName` — closed enum of supported providers.
- :class:`ProviderModel` — one upstream model entry.
- :class:`ProviderModelsResponse` — response of
  ``GET /api/models/{provider}``.

How the rest of the system uses this module
-------------------------------------------

- :class:`server.services.model_list_proxy.ModelListProxy` returns
  :class:`ProviderModelsResponse` from :meth:`ModelListProxy.read`.
- The GUI's ``LLMProviderNode`` consumes the DTO to render the
  model-picker select.

Invariants enforced by this module
----------------------------------

- :class:`ProviderName` covers exactly the providers the proxy knows
  how to fetch. Adding a new provider requires both a new enum member
  and a matching upstream-fetch branch in
  :class:`server.services.model_list_proxy.ModelListProxy`.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProviderName(str, Enum):
    """Closed enum of LLM providers the proxy can fetch.

    Members:
        OPENROUTER: OpenRouter's public model catalogue.
        OPENAI: OpenAI's authenticated model catalogue.
        CLAUDE: Anthropic's model catalogue.
        GOOGLE: Google's Gemini model catalogue.
        OLLAMA: Local Ollama server.
        VLLM: Local vLLM server.
        LLAMA_CPP: Local llama.cpp server.
    """

    OPENROUTER = "openrouter"
    OPENAI = "openai"
    CLAUDE = "claude"
    GOOGLE = "google"
    OLLAMA = "ollama"
    VLLM = "vllm"
    LLAMA_CPP = "llama_cpp"


class ProviderModel(BaseModel):
    """One upstream model entry, normalised across providers.

    Attributes:
        id (str): Model identifier sent to the provider as
            ``chat.completions.create(model=<id>)``. This is the
            value users paste into :attr:`src.flow_loader.LLMResource.model`.
        label (str): Human-readable display name. Falls back to
            :attr:`id` when the provider does not supply a separate
            friendly name.
        description (Optional[str]): Longer description supplied by
            the provider (OpenRouter only; ``None`` for OpenAI).
        context_length (Optional[int]): Maximum context length in
            tokens (OpenRouter only; ``None`` for OpenAI).
        max_output_tokens (Optional[int]): Maximum output tokens the
            model can generate per response. Extracted from the
            upstream catalogue when available.
        prompt_price_per_million (Optional[float]): Input/prompt cost
            per 1 M tokens in USD (OpenRouter; ``None`` when the
            upstream does not report pricing).
        completion_price_per_million (Optional[float]): Output/completion
            cost per 1 M tokens in USD.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: Optional[str] = None
    context_length: Optional[int] = None
    max_output_tokens: Optional[int] = None
    prompt_price_per_million: Optional[float] = None
    completion_price_per_million: Optional[float] = None


class ProviderModelsResponse(BaseModel):
    """Response of ``GET /api/models/{provider}``.

    Attributes:
        provider (ProviderName): Which provider the ``models`` list
            comes from.
        fetched_at (str): ISO-8601 UTC timestamp recording when the
            upstream list was last fetched. The GUI uses this to
            display "last updated N minutes ago".
        models (List[ProviderModel]): The normalised model list.
    """

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    fetched_at: str
    models: List[ProviderModel] = Field(default_factory=list)
