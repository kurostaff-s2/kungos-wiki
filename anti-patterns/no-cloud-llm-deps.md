---
tags: [anti-pattern, llm, architecture, dependency]
created: 2026-04-20
updated: 2026-04-20
status: active
---

# No Cloud LLM Dependencies

## What

Avoid adding dependencies on cloud LLM APIs (OpenAI, Anthropic, Google, etc.) to project codebases.

## Why

- **Privacy**: Code, data, and prompts should not leave the local machine
- **Cost**: Cloud APIs have ongoing per-token costs
- **Availability**: Local models work offline, no rate limits
- **Consistency**: All agents use the same local model stack
- **Control**: Full control over model version and parameters

## Context

This is an explicit architectural decision (ADR-001). The infrastructure is set up for local-only LLM inference via llama.cpp.

## Exceptions

None currently. All AI/LLM tasks should use the local model stack.

## Related

- [[ADR-001-local-llm]]
- [[Local AI Stack]]
