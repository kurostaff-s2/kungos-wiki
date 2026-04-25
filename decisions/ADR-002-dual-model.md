---
tags: [decision, llm, architecture, workflow]
created: 2026-04-20
updated: 2026-04-20
status: stable
---

# ADR-002: Dual Model Strategy

## Context

Single local LLM may not handle all task types well. Fast models are good for boilerplate but struggle with complex reasoning. Reasoning models are slow but better at architecture and hard bugs.

## Decision

Use two models in a dual strategy:
- **Fast model** (Qwen3.6-35B-A3B, 3B active): For boilerplate, routine code, simple tasks
- **Reasoning model** (DeepSeek-R1-Distill-Qwen-32B): For hard bugs, architecture, complex decisions

## Rationale

- Fast model handles ~80% of tasks quickly
- Reasoning model reserved for the 20% that need deep analysis
- Optimizes for both speed and quality
- Both served via llama.cpp on same hardware

## Consequences

- Need to manage two model downloads
- Switching between models requires service restart or multi-port setup
- Fast model on port 11434, reasoning model on port 11435

## Related

- [[ADR-001-local-llm]]
- [[Qwen3.6-35B-A3B]]
- [[DeepSeek-R1-Distill-Qwen-32B]]
