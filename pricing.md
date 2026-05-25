# LLM API Pricing Reference

Fetched: 2026-05-24

## Sources

1. **Google Gemini** — <https://ai.google.dev/gemini-api/docs/pricing>
2. **OpenAI** — <https://developers.openai.com/api/docs/pricing>
3. **Anthropic** — <https://docs.anthropic.com/en/docs/about-claude/pricing>
4. **OpenRouter** — <https://openrouter.ai/api/v1/models> (pass-through pricing, no inference markup)

---

## 1. Google Gemini (Paid Tier, Standard, per 1M tokens USD)

Source: <https://ai.google.dev/gemini-api/docs/pricing>

| Model | Input | Output |
| --- | ---: | ---: |
| gemini-3.5-flash | $1.50 | $9.00 |
| gemini-3.1-flash-lite | $0.25 | $1.50 |
| gemini-3.1-flash-lite-preview | $0.25 | $1.50 |
| gemini-3.1-pro-preview | $2.00 (<=200k) / $4.00 (>200k) | $12.00 (<=200k) / $18.00 (>200k) |
| gemini-3-flash-preview | $0.50 | $3.00 |
| gemini-2.5-pro | $1.25 (<=200k) / $2.50 (>200k) | $10.00 (<=200k) / $15.00 (>200k) |
| gemini-2.5-flash | $0.30 | $2.50 |
| gemini-2.5-flash-lite | $0.10 | $0.40 |
| gemini-2.0-flash | $0.10 | $0.40 |
| gemini-2.0-flash-lite | $0.075 | $0.30 |

### Google Batch pricing (50% of Standard)

| Model | Input | Output |
| --- | ---: | ---: |
| gemini-3.5-flash | $0.75 | $4.50 |
| gemini-3.1-flash-lite | $0.125 | $0.75 |
| gemini-3.1-pro-preview | $1.00 (<=200k) / $2.00 (>200k) | $6.00 (<=200k) / $9.00 (>200k) |
| gemini-3-flash-preview | $0.25 | $1.50 |
| gemini-2.5-pro | $0.625 (<=200k) / $1.25 (>200k) | $5.00 (<=200k) / $7.50 (>200k) |
| gemini-2.5-flash | $0.15 | $1.25 |
| gemini-2.5-flash-lite | $0.05 | $0.20 |
| gemini-2.0-flash | $0.05 | $0.20 |
| gemini-2.0-flash-lite | $0.0375 | $0.15 |

---

## 2. OpenAI (per 1M tokens USD)

Source: <https://developers.openai.com/api/docs/pricing>

| Model | Input | Cached Input | Output |
| --- | ---: | ---: | ---: |
| gpt-5.5-pro | $30.00 | — | $180.00 |
| gpt-5.5 | $5.00 | — | $30.00 |
| gpt-5.4 | $2.50 | $1.25 | $15.00 |
| gpt-5.4-mini | $0.75 | — | $4.50 |
| gpt-5.4-nano | $0.20 | — | $1.25 |
| gpt-5 | $1.25 | $0.125 | $10.00 |
| gpt-5-mini | $0.25 | $0.025 | $2.00 |
| gpt-5-nano | $0.05 | — | $0.40 |
| gpt-4.1 | $2.00 | $0.50 | $8.00 |
| gpt-4.1-mini | $0.40 | $0.10 | $1.60 |
| gpt-4.1-nano | $0.10 | $0.025 | $0.40 |
| gpt-4o | $2.50 | $1.25 | $10.00 |
| gpt-4o-mini | $0.15 | $0.075 | $0.60 |
| o3-pro | $20.00 | — | $80.00 |
| o3 | $2.00 | $0.50 | $8.00 |
| o4-mini | $1.10 | $0.275 | $4.40 |
| o3-mini | $1.10 | $0.55 | $4.40 |

### OpenAI Batch pricing (50% of Standard)

| Model | Input | Output |
| --- | ---: | ---: |
| gpt-4.1 | $1.00 | $4.00 |
| gpt-4.1-mini | $0.20 | $0.80 |
| gpt-4.1-nano | $0.05 | $0.20 |
| gpt-4o | $1.25 | $5.00 |
| gpt-4o-mini | $0.075 | $0.30 |
| o3 | $1.00 | $4.00 |
| o4-mini | $0.55 | $2.20 |
| o3-mini | $0.55 | $2.20 |

---

## 3. Anthropic (per 1M tokens USD)

Source: <https://docs.anthropic.com/en/docs/about-claude/pricing>

| Model | Input | Output | Cache Write (5m) | Cache Write (1h) | Cache Hit |
| --- | ---: | ---: | ---: | ---: | ---: |
| Claude Opus 4.7 | $5.00 | $25.00 | $6.25 | $10.00 | $0.50 |
| Claude Opus 4.6 | $5.00 | $25.00 | $6.25 | $10.00 | $0.50 |
| Claude Opus 4.5 | $5.00 | $25.00 | $6.25 | $10.00 | $0.50 |
| Claude Opus 4.1 | $15.00 | $75.00 | $18.75 | $30.00 | $1.50 |
| Claude Sonnet 4.6 | $3.00 | $15.00 | $3.75 | $6.00 | $0.30 |
| Claude Sonnet 4.5 | $3.00 | $15.00 | $3.75 | $6.00 | $0.30 |
| Claude Haiku 4.5 | $1.00 | $5.00 | $1.25 | $2.00 | $0.10 |
| Claude Haiku 3.5 | $0.80 | $4.00 | $1.00 | $1.60 | $0.08 |

### Anthropic Batch pricing (50% of Standard)

| Model | Batch Input | Batch Output |
| --- | ---: | ---: |
| Claude Opus 4.7 | $2.50 | $12.50 |
| Claude Opus 4.6 | $2.50 | $12.50 |
| Claude Opus 4.5 | $2.50 | $12.50 |
| Claude Opus 4.1 | $7.50 | $37.50 |
| Claude Sonnet 4.6 | $1.50 | $7.50 |
| Claude Sonnet 4.5 | $1.50 | $7.50 |
| Claude Haiku 4.5 | $0.50 | $2.50 |
| Claude Haiku 3.5 | $0.40 | $2.00 |

### Anthropic Fast Mode (Opus 4.6 / 4.7 only)

| Input | Output |
| ---: | ---: |
| $30.00 | $150.00 |

---

## 4. OpenRouter (per 1M tokens USD, sorted by input price)

Source: `GET https://openrouter.ai/api/v1/models` — 355 models with pricing, fetched 2026-05-24.
OpenRouter passes through provider pricing with no inference markup.

| Model | Input $/1M | Output $/1M | Context |
| --- | ---: | ---: | ---: |
| baidu/cobuddy:free | 0.0000 | 0.0000 | 131,072 |
| openrouter/owl-alpha | 0.0000 | 0.0000 | 1,048,756 |
| nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free | 0.0000 | 0.0000 | 256,000 |
| poolside/laguna-xs.2:free | 0.0000 | 0.0000 | 131,072 |
| poolside/laguna-m.1:free | 0.0000 | 0.0000 | 131,072 |
| deepseek/deepseek-v4-flash:free | 0.0000 | 0.0000 | 1,048,576 |
| google/gemma-4-26b-a4b-it:free | 0.0000 | 0.0000 | 262,144 |
| google/gemma-4-31b-it:free | 0.0000 | 0.0000 | 262,144 |
| arcee-ai/trinity-large-thinking:free | 0.0000 | 0.0000 | 262,144 |
| google/lyria-3-pro-preview | 0.0000 | 0.0000 | 1,048,576 |
| google/lyria-3-clip-preview | 0.0000 | 0.0000 | 1,048,576 |
| nvidia/nemotron-3-super-120b-a12b:free | 0.0000 | 0.0000 | 1,000,000 |
| minimax/minimax-m2.5:free | 0.0000 | 0.0000 | 204,800 |
| openrouter/free | 0.0000 | 0.0000 | 200,000 |
| liquid/lfm-2.5-1.2b-thinking:free | 0.0000 | 0.0000 | 32,768 |
| liquid/lfm-2.5-1.2b-instruct:free | 0.0000 | 0.0000 | 32,768 |
| nvidia/nemotron-3-nano-30b-a3b:free | 0.0000 | 0.0000 | 256,000 |
| nvidia/nemotron-nano-12b-v2-vl:free | 0.0000 | 0.0000 | 128,000 |
| qwen/qwen3-next-80b-a3b-instruct:free | 0.0000 | 0.0000 | 262,144 |
| nvidia/nemotron-nano-9b-v2:free | 0.0000 | 0.0000 | 128,000 |
| openai/gpt-oss-120b:free | 0.0000 | 0.0000 | 131,072 |
| openai/gpt-oss-20b:free | 0.0000 | 0.0000 | 131,072 |
| z-ai/glm-4.5-air:free | 0.0000 | 0.0000 | 131,072 |
| qwen/qwen3-coder:free | 0.0000 | 0.0000 | 1,048,576 |
| cognitivecomputations/dolphin-mistral-24b-venice-edition:free | 0.0000 | 0.0000 | 32,768 |
| meta-llama/llama-3.3-70b-instruct:free | 0.0000 | 0.0000 | 131,072 |
| meta-llama/llama-3.2-3b-instruct:free | 0.0000 | 0.0000 | 131,072 |
| nousresearch/hermes-3-llama-3.1-405b:free | 0.0000 | 0.0000 | 131,072 |
| inclusionai/ling-2.6-flash | 0.0100 | 0.0300 | 262,144 |
| ibm-granite/granite-4.0-h-micro | 0.0170 | 0.1120 | 131,000 |
| mistralai/mistral-nemo | 0.0200 | 0.0300 | 131,072 |
| meta-llama/llama-3.1-8b-instruct | 0.0200 | 0.0500 | 131,072 |
| meta-llama/llama-3.2-1b-instruct | 0.0270 | 0.2010 | 131,072 |
| liquid/lfm-2-24b-a2b | 0.0300 | 0.1200 | 128,000 |
| openai/gpt-oss-20b | 0.0300 | 0.1400 | 131,072 |
| amazon/nova-micro-v1 | 0.0350 | 0.1400 | 128,000 |
| cohere/command-r7b-12-2024 | 0.0375 | 0.1500 | 128,000 |
| openai/gpt-oss-120b | 0.0390 | 0.1800 | 131,072 |
| meta-llama/llama-3-8b-instruct | 0.0400 | 0.0400 | 8,192 |
| sao10k/l3-lunaris-8b | 0.0400 | 0.0500 | 8,192 |
| google/gemma-3-4b-it | 0.0400 | 0.0800 | 131,072 |
| qwen/qwen-2.5-7b-instruct | 0.0400 | 0.1000 | 131,072 |
| google/gemma-3-12b-it | 0.0400 | 0.1300 | 131,072 |
| qwen/qwen3.5-9b | 0.0400 | 0.1500 | 262,144 |
| nvidia/nemotron-nano-9b-v2 | 0.0400 | 0.1600 | 131,072 |
| arcee-ai/trinity-mini | 0.0450 | 0.1500 | 131,072 |
| mistralai/mistral-small-24b-instruct-2501 | 0.0500 | 0.0800 | 32,768 |
| ibm-granite/granite-4.1-8b | 0.0500 | 0.1000 | 131,072 |
| nvidia/nemotron-3-nano-30b-a3b | 0.0500 | 0.2000 | 262,144 |
| openai/gpt-5-nano | 0.0500 | 0.4000 | 400,000 |
| qwen/qwen3-8b | 0.0500 | 0.4000 | 131,072 |
| meta-llama/llama-3.2-3b-instruct | 0.0509 | 0.3350 | 131,072 |
| gryphe/mythomax-l2-13b | 0.0600 | 0.0600 | 4,096 |
| google/gemma-3n-e4b-it | 0.0600 | 0.1200 | 32,768 |
| amazon/nova-lite-v1 | 0.0600 | 0.2400 | 300,000 |
| google/gemma-4-26b-a4b-it | 0.0600 | 0.3300 | 262,144 |
| z-ai/glm-4.7-flash | 0.0600 | 0.4000 | 202,752 |
| microsoft/phi-4 | 0.0650 | 0.1400 | 16,384 |
| qwen/qwen3.5-flash-02-23 | 0.0650 | 0.2600 | 1,000,000 |
| tencent/hy3-preview | 0.0660 | 0.2600 | 262,144 |
| qwen/qwen3-coder-30b-a3b-instruct | 0.0700 | 0.2700 | 160,000 |
| baidu/ernie-4.5-21b-a3b-thinking | 0.0700 | 0.2800 | 131,072 |
| baidu/ernie-4.5-21b-a3b | 0.0700 | 0.2800 | 131,072 |
| qwen/qwen3-235b-a22b-2507 | 0.0710 | 0.1000 | 262,144 |
| mistralai/mistral-small-3.2-24b-instruct | 0.0750 | 0.2000 | 128,000 |
| bytedance-seed/seed-1.6-flash | 0.0750 | 0.3000 | 262,144 |
| openai/gpt-oss-safeguard-20b | 0.0750 | 0.3000 | 131,072 |
| google/gemini-2.0-flash-lite-001 | 0.0750 | 0.3000 | 1,048,576 |
| inclusionai/ring-2.6-1t | 0.0750 | 0.6250 | 262,144 |
| inclusionai/ling-2.6-1t | 0.0750 | 0.6250 | 262,144 |
| google/gemma-3-27b-it | 0.0800 | 0.1600 | 131,072 |
| qwen/qwen3-32b | 0.0800 | 0.2800 | 131,072 |
| meta-llama/llama-4-scout | 0.0800 | 0.3000 | 10,000,000 |
| microsoft/phi-4-mini-instruct | 0.0800 | 0.3500 | 131,072 |
| qwen/qwen3-30b-a3b-thinking-2507 | 0.0800 | 0.4000 | 131,072 |
| qwen/qwen3-vl-8b-instruct | 0.0800 | 0.5000 | 256,000 |
| stepfun/step-3.5-flash | 0.0900 | 0.3000 | 262,144 |
| qwen/qwen3-30b-a3b-instruct-2507 | 0.0900 | 0.3000 | 262,144 |
| nvidia/nemotron-3-super-120b-a12b | 0.0900 | 0.4500 | 1,000,000 |
| alibaba/tongyi-deepresearch-30b-a3b | 0.0900 | 0.4500 | 131,072 |
| qwen/qwen3-30b-a3b | 0.0900 | 0.4500 | 131,072 |
| qwen/qwen3-next-80b-a3b-instruct | 0.0900 | 1.1000 | 262,144 |
| qwen/qwen3-next-80b-a3b-thinking | 0.0975 | 0.7800 | 262,144 |
| rekaai/reka-edge | 0.1000 | 0.1000 | 16,384 |
| mistralai/ministral-3b-2512 | 0.1000 | 0.1000 | 131,072 |
| z-ai/glm-4-32b | 0.1000 | 0.1000 | 128,000 |
| deepseek/deepseek-v4-flash | 0.1000 | 0.2000 | 1,048,576 |
| bytedance/ui-tars-1.5-7b | 0.1000 | 0.2000 | 128,000 |
| rekaai/reka-flash-3 | 0.1000 | 0.2000 | 65,536 |
| qwen/qwen3-14b | 0.1000 | 0.2400 | 131,702 |
| xiaomi/mimo-v2-flash | 0.1000 | 0.3000 | 262,144 |
| mistralai/voxtral-small-24b-2507 | 0.1000 | 0.3000 | 32,000 |
| mistralai/devstral-small | 0.1000 | 0.3000 | 131,072 |
| meta-llama/llama-3.3-70b-instruct | 0.1000 | 0.3200 | 131,072 |
| bytedance-seed/seed-2.0-mini | 0.1000 | 0.4000 | 262,144 |
| nvidia/llama-3.3-nemotron-super-49b-v1.5 | 0.1000 | 0.4000 | 131,072 |
| google/gemini-2.5-flash-lite-preview-09-2025 | 0.1000 | 0.4000 | 1,048,576 |
| google/gemini-2.5-flash-lite | 0.1000 | 0.4000 | 1,048,576 |
| openai/gpt-4.1-nano | 0.1000 | 0.4000 | 1,047,576 |
| google/gemini-2.0-flash-001 | 0.1000 | 0.4000 | 1,000,000 |
| qwen/qwen3-vl-32b-instruct | 0.1040 | 0.4160 | 262,144 |
| mistralai/mistral-7b-instruct-v0.1 | 0.1100 | 0.1900 | 4,096 |
| qwen/qwen3-coder-next | 0.1100 | 0.8000 | 262,144 |
| qwen/qwen3-vl-8b-thinking | 0.1170 | 1.3650 | 256,000 |
| google/gemma-4-31b-it | 0.1200 | 0.3700 | 262,144 |
| nousresearch/hermes-4-70b | 0.1300 | 0.4000 | 131,072 |
| qwen/qwen3-vl-30b-a3b-instruct | 0.1300 | 0.5200 | 262,144 |
| z-ai/glm-4.5-air | 0.1300 | 0.8500 | 131,072 |
| qwen/qwen3-vl-30b-a3b-thinking | 0.1300 | 1.5600 | 131,072 |
| nex-agi/deepseek-v3.1-nex-n1 | 0.1350 | 0.5000 | 131,072 |
| qwen/qwen3.5-35b-a3b | 0.1390 | 1.0000 | 262,144 |
| nousresearch/hermes-2-pro-llama-3-8b | 0.1400 | 0.1400 | 8,192 |
| baidu/ernie-4.5-vl-28b-a3b | 0.1400 | 0.5600 | 131,072 |
| tencent/hunyuan-a13b-instruct | 0.1400 | 0.5700 | 131,072 |
| qwen/qwen3-235b-a22b-thinking-2507 | 0.1495 | 1.4950 | 262,144 |
| essentialai/rnj-1-instruct | 0.1500 | 0.1500 | 32,768 |
| mistralai/ministral-8b-2512 | 0.1500 | 0.1500 | 262,144 |
| allenai/olmo-3-32b-think | 0.1500 | 0.5000 | 65,536 |
| mistralai/mistral-small-2603 | 0.1500 | 0.6000 | 262,144 |
| upstage/solar-pro-3 | 0.1500 | 0.6000 | 128,000 |
| meta-llama/llama-4-maverick | 0.1500 | 0.6000 | 1,048,576 |
| openai/gpt-4o-mini-search-preview | 0.1500 | 0.6000 | 128,000 |
| cohere/command-r-08-2024 | 0.1500 | 0.6000 | 128,000 |
| openai/gpt-4o-mini-2024-07-18 | 0.1500 | 0.6000 | 128,000 |
| openai/gpt-4o-mini | 0.1500 | 0.6000 | 128,000 |
| qwen/qwen3.6-35b-a3b | 0.1500 | 1.0000 | 262,144 |
| minimax/minimax-m2.5 | 0.1500 | 1.1500 | 204,800 |
| perceptron/perceptron-mk1 | 0.1500 | 1.5000 | 32,768 |
| thedrummer/rocinante-12b | 0.1700 | 0.4300 | 32,768 |
| arcee-ai/spotlight | 0.1800 | 0.1800 | 131,072 |
| meta-llama/llama-guard-4-12b | 0.1800 | 0.1800 | 163,840 |
| qwen/qwen3.6-flash | 0.1875 | 1.1250 | 1,000,000 |
| qwen/qwen3-coder-flash | 0.1950 | 0.9750 | 1,000,000 |
| qwen/qwen3.5-27b | 0.1950 | 1.5600 | 262,144 |
| mistralai/ministral-14b-2512 | 0.2000 | 0.2000 | 262,144 |
| mistralai/mistral-saba | 0.2000 | 0.6000 | 32,768 |
| deepseek/deepseek-chat-v3-0324 | 0.2000 | 0.7700 | 163,840 |
| qwen/qwen3-vl-235b-a22b-instruct | 0.2000 | 0.8800 | 262,144 |
| prime-intellect/intellect-3 | 0.2000 | 1.1000 | 131,072 |
| minimax/minimax-01 | 0.2000 | 1.1000 | 1,000,192 |
| openai/gpt-5.4-nano | 0.2000 | 1.2500 | 400,000 |
| deepseek/deepseek-chat-v3.1 | 0.2100 | 0.7900 | 163,840 |
| arcee-ai/trinity-large-thinking | 0.2200 | 0.8500 | 262,144 |
| qwen/qwen3-coder | 0.2200 | 1.8000 | 1,048,576 |
| meta-llama/llama-3.2-11b-vision-instruct | 0.2450 | 0.2450 | 131,072 |
| inception/mercury-2 | 0.2500 | 0.7500 | 128,000 |
| qwen/qwen2.5-vl-72b-instruct | 0.2500 | 0.7500 | 131,072 |
| anthropic/claude-3-haiku | 0.2500 | 1.2500 | 200,000 |
| google/gemini-3.1-flash-lite | 0.2500 | 1.5000 | 1,048,576 |
| google/gemini-3.1-flash-lite-preview | 0.2500 | 1.5000 | 1,048,576 |
| bytedance-seed/seed-2.0-lite | 0.2500 | 2.0000 | 262,144 |
| bytedance-seed/seed-1.6 | 0.2500 | 2.0000 | 262,144 |
| openai/gpt-5.1-codex-mini | 0.2500 | 2.0000 | 400,000 |
| openai/gpt-5-mini | 0.2500 | 2.0000 | 400,000 |
| deepseek/deepseek-v3.2 | 0.2520 | 0.3780 | 131,072 |
| minimax/minimax-m2 | 0.2550 | 1.0000 | 204,800 |
| qwen/qwen-plus-2025-07-28:thinking | 0.2600 | 0.7800 | 1,000,000 |
| qwen/qwen-plus-2025-07-28 | 0.2600 | 0.7800 | 1,000,000 |
| qwen/qwen-plus | 0.2600 | 0.7800 | 1,000,000 |
| qwen/qwen3.5-plus-02-15 | 0.2600 | 1.5600 | 1,000,000 |
| qwen/qwen3.5-122b-a10b | 0.2600 | 2.0800 | 262,144 |
| qwen/qwen3-vl-235b-a22b-thinking | 0.2600 | 2.6000 | 131,072 |
| deepseek/deepseek-v3.2-exp | 0.2700 | 0.4100 | 163,840 |
| deepseek/deepseek-v3.1-terminus | 0.2700 | 0.9500 | 163,840 |
| minimax/minimax-m2.7 | 0.2790 | 1.2000 | 204,800 |
| baidu/ernie-4.5-300b-a47b | 0.2800 | 1.1000 | 131,072 |
| deepseek/deepseek-v3.2-speciale | 0.2870 | 0.4310 | 163,840 |
| deepseek/deepseek-r1-distill-qwen-32b | 0.2900 | 0.2900 | 128,000 |
| minimax/minimax-m2.1 | 0.2900 | 0.9500 | 204,800 |
| nousresearch/hermes-3-llama-3.1-70b | 0.3000 | 0.3000 | 131,072 |
| thedrummer/cydonia-24b-v4.1 | 0.3000 | 0.5000 | 131,072 |
| z-ai/glm-4.6v | 0.3000 | 0.9000 | 131,072 |
| mistralai/codestral-2508 | 0.3000 | 0.9000 | 256,000 |
| kwaipilot/kat-coder-pro-v2 | 0.3000 | 1.2000 | 256,000 |
| minimax/minimax-m2-her | 0.3000 | 1.2000 | 65,536 |
| qwen/qwen3.5-plus-20260420 | 0.3000 | 1.8000 | 1,000,000 |
| amazon/nova-2-lite-v1 | 0.3000 | 2.5000 | 1,000,000 |
| google/gemini-2.5-flash-image | 0.3000 | 2.5000 | 32,768 |
| google/gemini-2.5-flash | 0.3000 | 2.5000 | 1,048,576 |
| qwen/qwen3.6-27b | 0.3000 | 3.2000 | 262,144 |
| deepseek/deepseek-chat | 0.3200 | 0.8900 | 163,840 |
| qwen/qwen3.6-plus | 0.3250 | 1.9500 | 1,000,000 |
| mistralai/mistral-small-3.1-24b-instruct | 0.3510 | 0.5550 | 128,000 |
| qwen/qwen-2.5-72b-instruct | 0.3600 | 0.4000 | 131,072 |
| qwen/qwen3.5-397b-a17b | 0.3900 | 2.3400 | 262,144 |
| thedrummer/unslopnemo-12b | 0.4000 | 0.4000 | 32,768 |
| meta-llama/llama-3.1-70b-instruct | 0.4000 | 0.4000 | 131,072 |
| openai/gpt-4.1-mini | 0.4000 | 1.6000 | 1,047,576 |
| z-ai/glm-4.7 | 0.4000 | 1.7500 | 202,752 |
| moonshotai/kimi-k2.5 | 0.4000 | 1.9000 | 262,144 |
| xiaomi/mimo-v2.5 | 0.4000 | 2.0000 | 1,048,576 |
| xiaomi/mimo-v2-omni | 0.4000 | 2.0000 | 262,144 |
| mistralai/devstral-2512 | 0.4000 | 2.0000 | 262,144 |
| mistralai/mistral-medium-3.1 | 0.4000 | 2.0000 | 131,072 |
| mistralai/devstral-medium | 0.4000 | 2.0000 | 131,072 |
| mistralai/mistral-medium-3 | 0.4000 | 2.0000 | 131,072 |
| minimax/minimax-m1 | 0.4000 | 2.2000 | 1,000,000 |
| baidu/ernie-4.5-vl-424b-a47b | 0.4200 | 1.2500 | 131,072 |
| z-ai/glm-4.6 | 0.4300 | 1.7400 | 202,752 |
| deepseek/deepseek-v4-pro | 0.4350 | 0.8700 | 1,048,576 |
| undi95/remm-slerp-l2-13b | 0.4500 | 0.6500 | 6,144 |
| qwen/qwen3-235b-a22b | 0.4550 | 1.8200 | 131,072 |
| meta-llama/llama-guard-3-8b | 0.4840 | 0.0300 | 131,072 |
| arcee-ai/coder-large | 0.5000 | 0.8000 | 32,768 |
| mistralai/mistral-large-2512 | 0.5000 | 1.5000 | 262,144 |
| openai/gpt-3.5-turbo | 0.5000 | 1.5000 | 16,385 |
| deepseek/deepseek-r1-0528 | 0.5000 | 2.1500 | 163,840 |
| google/gemini-3.1-flash-image-preview | 0.5000 | 3.0000 | 131,072 |
| google/gemini-3-flash-preview | 0.5000 | 3.0000 | 1,048,576 |
| meta-llama/llama-3-70b-instruct | 0.5100 | 0.7400 | 8,192 |
| thedrummer/skyfall-36b-v2 | 0.5500 | 0.8000 | 32,768 |
| moonshotai/kimi-k2 | 0.5700 | 2.3000 | 131,072 |
| z-ai/glm-4.5v | 0.6000 | 1.8000 | 65,536 |
| z-ai/glm-5 | 0.6000 | 1.9200 | 202,752 |
| z-ai/glm-4.5 | 0.6000 | 2.2000 | 131,072 |
| openai/gpt-audio-mini | 0.6000 | 2.4000 | 128,000 |
| moonshotai/kimi-k2-thinking | 0.6000 | 2.5000 | 262,144 |
| moonshotai/kimi-k2-0905 | 0.6000 | 2.5000 | 262,144 |
| writer/palmyra-x5 | 0.6000 | 6.0000 | 1,040,000 |
| microsoft/wizardlm-2-8x22b | 0.6200 | 0.6200 | 65,536 |
| google/gemma-2-27b-it | 0.6500 | 0.6500 | 8,192 |
| sao10k/l3.3-euryale-70b | 0.6500 | 0.7500 | 131,072 |
| qwen/qwen3-coder-plus | 0.6500 | 3.2500 | 1,000,000 |
| qwen/qwen-2.5-coder-32b-instruct | 0.6600 | 1.0000 | 128,000 |
| baidu/qianfan-ocr-fast | 0.6800 | 2.8100 | 65,536 |
| deepseek/deepseek-r1-distill-llama-70b | 0.7000 | 0.8000 | 131,072 |
| aion-labs/aion-1.0-mini | 0.7000 | 1.4000 | 131,072 |
| deepseek/deepseek-r1 | 0.7000 | 2.5000 | 163,840 |
| moonshotai/kimi-k2.6 | 0.7300 | 3.4900 | 262,144 |
| mancer/weaver | 0.7500 | 1.0000 | 8,000 |
| arcee-ai/virtuoso-large | 0.7500 | 1.2000 | 131,072 |
| openai/gpt-5.4-mini | 0.7500 | 4.5000 | 400,000 |
| qwen/qwen3-max-thinking | 0.7800 | 3.9000 | 262,144 |
| qwen/qwen3-max | 0.7800 | 3.9000 | 262,144 |
| morph/morph-v3-fast | 0.8000 | 1.2000 | 81,920 |
| alfredpros/codellama-7b-instruct-solidity | 0.8000 | 1.2000 | 4,096 |
| aion-labs/aion-2.0 | 0.8000 | 1.6000 | 131,072 |
| aion-labs/aion-rp-llama-3.1-8b | 0.8000 | 1.6000 | 32,768 |
| amazon/nova-pro-v1 | 0.8000 | 3.2000 | 300,000 |
| anthropic/claude-3.5-haiku | 0.8000 | 4.0000 | 200,000 |
| sao10k/l3.1-euryale-70b | 0.8500 | 0.8500 | 131,072 |
| relace/relace-apply-3 | 0.8500 | 1.2500 | 256,000 |
| switchpoint/router | 0.8500 | 3.4000 | 131,072 |
| morph/morph-v3-large | 0.9000 | 1.9000 | 262,144 |
| arcee-ai/maestro-reasoning | 0.9000 | 3.3000 | 131,072 |
| z-ai/glm-5.1 | 0.9800 | 3.0800 | 202,752 |
| perplexity/sonar | 1.0000 | 1.0000 | 127,072 |
| nousresearch/hermes-3-llama-3.1-405b | 1.0000 | 1.0000 | 131,072 |
| x-ai/grok-build-0.1 | 1.0000 | 2.0000 | 256,000 |
| openai/gpt-3.5-turbo-0613 | 1.0000 | 2.0000 | 4,095 |
| xiaomi/mimo-v2.5-pro | 1.0000 | 3.0000 | 1,048,576 |
| xiaomi/mimo-v2-pro | 1.0000 | 3.0000 | 1,048,576 |
| relace/relace-search | 1.0000 | 3.0000 | 256,000 |
| nousresearch/hermes-4-405b | 1.0000 | 3.0000 | 131,072 |
| anthropic/claude-haiku-4.5 | 1.0000 | 5.0000 | 200,000 |
| qwen/qwen3.6-max-preview | 1.0400 | 6.2400 | 262,144 |
| openai/o4-mini-high | 1.1000 | 4.4000 | 200,000 |
| openai/o4-mini | 1.1000 | 4.4000 | 200,000 |
| openai/o3-mini-high | 1.1000 | 4.4000 | 200,000 |
| openai/o3-mini | 1.1000 | 4.4000 | 200,000 |
| z-ai/glm-5v-turbo | 1.2000 | 4.0000 | 202,752 |
| z-ai/glm-5-turbo | 1.2000 | 4.0000 | 202,752 |
| deepcogito/cogito-v2.1-671b | 1.2500 | 1.2500 | 128,000 |
| x-ai/grok-4.3 | 1.2500 | 2.5000 | 1,000,000 |
| x-ai/grok-4.20 | 1.2500 | 2.5000 | 2,000,000 |
| openai/gpt-5.1-codex-max | 1.2500 | 10.0000 | 400,000 |
| openai/gpt-5.1 | 1.2500 | 10.0000 | 400,000 |
| openai/gpt-5.1-chat | 1.2500 | 10.0000 | 128,000 |
| openai/gpt-5.1-codex | 1.2500 | 10.0000 | 400,000 |
| openai/gpt-5-codex | 1.2500 | 10.0000 | 400,000 |
| openai/gpt-5-chat | 1.2500 | 10.0000 | 128,000 |
| openai/gpt-5 | 1.2500 | 10.0000 | 400,000 |
| google/gemini-2.5-pro | 1.2500 | 10.0000 | 1,048,576 |
| google/gemini-2.5-pro-preview | 1.2500 | 10.0000 | 1,048,576 |
| google/gemini-2.5-pro-preview-05-06 | 1.2500 | 10.0000 | 1,048,576 |
| sao10k/l3-euryale-70b | 1.4800 | 1.4800 | 8,192 |
| openai/gpt-3.5-turbo-instruct | 1.5000 | 2.0000 | 4,095 |
| mistralai/mistral-medium-3-5 | 1.5000 | 7.5000 | 262,144 |
| google/gemini-3.5-flash | 1.5000 | 9.0000 | 1,048,576 |
| openai/gpt-5.3-chat | 1.7500 | 14.0000 | 128,000 |
| openai/gpt-5.3-codex | 1.7500 | 14.0000 | 400,000 |
| openai/gpt-5.2-codex | 1.7500 | 14.0000 | 400,000 |
| openai/gpt-5.2-chat | 1.7500 | 14.0000 | 128,000 |
| openai/gpt-5.2 | 1.7500 | 14.0000 | 400,000 |
| x-ai/grok-4.20-multi-agent | 2.0000 | 6.0000 | 2,000,000 |
| mistralai/mistral-large-2411 | 2.0000 | 6.0000 | 131,072 |
| mistralai/mistral-large-2407 | 2.0000 | 6.0000 | 131,072 |
| mistralai/pixtral-large-2411 | 2.0000 | 6.0000 | 131,072 |
| mistralai/mixtral-8x22b-instruct | 2.0000 | 6.0000 | 65,536 |
| mistralai/mistral-large | 2.0000 | 6.0000 | 128,000 |
| openai/o4-mini-deep-research | 2.0000 | 8.0000 | 200,000 |
| ai21/jamba-large-1.7 | 2.0000 | 8.0000 | 256,000 |
| openai/o3 | 2.0000 | 8.0000 | 200,000 |
| openai/gpt-4.1 | 2.0000 | 8.0000 | 1,047,576 |
| perplexity/sonar-reasoning-pro | 2.0000 | 8.0000 | 128,000 |
| perplexity/sonar-deep-research | 2.0000 | 8.0000 | 128,000 |
| google/gemini-3.1-pro-preview-customtools | 2.0000 | 12.0000 | 1,048,756 |
| google/gemini-3.1-pro-preview | 2.0000 | 12.0000 | 1,048,576 |
| google/gemini-3-pro-image-preview | 2.0000 | 12.0000 | 65,536 |
| openai/gpt-5-image-mini | 2.5000 | 2.0000 | 400,000 |
| qwen/qwen3.7-max | 2.5000 | 7.5000 | 1,000,000 |
| openai/gpt-audio | 2.5000 | 10.0000 | 128,000 |
| openai/gpt-4o-audio-preview | 2.5000 | 10.0000 | 128,000 |
| cohere/command-a | 2.5000 | 10.0000 | 256,000 |
| openai/gpt-4o-search-preview | 2.5000 | 10.0000 | 128,000 |
| openai/gpt-4o-2024-11-20 | 2.5000 | 10.0000 | 128,000 |
| inflection/inflection-3-productivity | 2.5000 | 10.0000 | 8,000 |
| inflection/inflection-3-pi | 2.5000 | 10.0000 | 8,000 |
| cohere/command-r-plus-08-2024 | 2.5000 | 10.0000 | 128,000 |
| openai/gpt-4o-2024-08-06 | 2.5000 | 10.0000 | 128,000 |
| openai/gpt-4o | 2.5000 | 10.0000 | 128,000 |
| amazon/nova-premier-v1 | 2.5000 | 12.5000 | 1,000,000 |
| openai/gpt-5.4 | 2.5000 | 15.0000 | 1,050,000 |
| sao10k/l3.1-70b-hanami-x1 | 3.0000 | 3.0000 | 16,000 |
| openai/gpt-3.5-turbo-16k | 3.0000 | 4.0000 | 16,385 |
| anthracite-org/magnum-v4-72b | 3.0000 | 5.0000 | 32,768 |
| anthropic/claude-sonnet-4.6 | 3.0000 | 15.0000 | 1,000,000 |
| perplexity/sonar-pro-search | 3.0000 | 15.0000 | 200,000 |
| anthropic/claude-sonnet-4.5 | 3.0000 | 15.0000 | 1,000,000 |
| anthropic/claude-sonnet-4 | 3.0000 | 15.0000 | 1,000,000 |
| perplexity/sonar-pro | 3.0000 | 15.0000 | 200,000 |
| aion-labs/aion-1.0 | 4.0000 | 8.0000 | 131,072 |
| openai/gpt-4o-2024-05-13 | 5.0000 | 15.0000 | 128,000 |
| anthropic/claude-opus-4.7 | 5.0000 | 25.0000 | 1,000,000 |
| anthropic/claude-opus-4.6 | 5.0000 | 25.0000 | 1,000,000 |
| anthropic/claude-opus-4.5 | 5.0000 | 25.0000 | 200,000 |
| openai/gpt-chat-latest | 5.0000 | 30.0000 | 400,000 |
| openai/gpt-5.5 | 5.0000 | 30.0000 | 1,050,000 |
| openai/gpt-5.4-image-2 | 8.0000 | 15.0000 | 272,000 |
| openai/gpt-5-image | 10.0000 | 10.0000 | 400,000 |
| openai/gpt-4-turbo | 10.0000 | 30.0000 | 128,000 |
| openai/gpt-4-turbo-preview | 10.0000 | 30.0000 | 128,000 |
| openai/gpt-4-1106-preview | 10.0000 | 30.0000 | 128,000 |
| openai/o3-deep-research | 10.0000 | 40.0000 | 200,000 |
| openai/o1 | 15.0000 | 60.0000 | 200,000 |
| anthropic/claude-opus-4.1 | 15.0000 | 75.0000 | 200,000 |
| anthropic/claude-opus-4 | 15.0000 | 75.0000 | 200,000 |
| openai/gpt-5-pro | 15.0000 | 120.0000 | 400,000 |
| openai/o3-pro | 20.0000 | 80.0000 | 200,000 |
| openai/gpt-5.2-pro | 21.0000 | 168.0000 | 400,000 |
| openai/gpt-4-0314 | 30.0000 | 60.0000 | 8,191 |
| openai/gpt-4 | 30.0000 | 60.0000 | 8,191 |
| anthropic/claude-opus-4.7-fast | 30.0000 | 150.0000 | 1,000,000 |
| anthropic/claude-opus-4.6-fast | 30.0000 | 150.0000 | 1,000,000 |
| openai/gpt-5.5-pro | 30.0000 | 180.0000 | 1,050,000 |
| openai/gpt-5.4-pro | 30.0000 | 180.0000 | 1,050,000 |
| openai/o1-pro | 150.0000 | 600.0000 | 200,000 |
