---
tags: [decision, llm, architecture, privacy]
created: 2026-04-20
updated: 2026-04-20
status: stable
---

# ADR-001: Use Local LLMs Instead of Cloud APIs

## Context

The project needs AI/LLM capabilities for various tasks (code generation, analysis, automation). Options include cloud APIs (OpenAI, Anthropic, Google) vs. local self-hosted models.

## Decision

Use local LLMs served via llama.cpp instead of cloud APIs.

## Rationale

- **Privacy**: Code and data never leave the local machine
- **Cost**: No per-token billing
- **Availability**: Works offline, no rate limits
- **Control**: Full control over model version, parameters, and serving

## Consequences

- Hardware requirements: RTX 3090 (24GB VRAM) + 96GB DDR5 RAM
- Model quality limited by local model size (35B params max on current hardware)
- Inference speed slower than cloud APIs for equivalent quality
- Need to manage model downloads and updates manually

## Related

- [[ADR-002-dual-model]]
- [[ADR-003-llama-cpp]]
