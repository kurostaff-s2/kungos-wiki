---
tags: [llm, qwen, local-model, fast-model]
created: 2026-04-20
updated: 2026-04-20
sources: [setup_local_ai.sh, models/]
related: [[local-ai-stack]], [[qwen3.5-35b-a3b]], [[deepseek-r1-distill-qwen-32b]]
status: stable
---

# Qwen3.6-35B-A3B

## Summary

Primary/fast LLM model used by all coding agents. 35B total parameters with 3B active (Mixture-of-Experts). Served via llama.cpp with CUDA on RTX 3090.

## Usage

- **Primary role:** Code generation, boilerplate, CRUD operations, frontend generation
- **Endpoint:** `http://127.0.0.1:8001` (via local proxy)
- **Models using it:** Claude Code, OpenCode, Codex CLI, Cursor, OpenClaw
- **Context window:** 65536 tokens (per setup_local_ai.sh)
- **Max output tokens:** 4096 (OpenClaw config)

## Specs

- **Architecture:** MoE (Mixture of Experts)
- **Total params:** 35B
- **Active params:** 3B
- **Format:** GGUF
- **Inference:** llama.cpp + CUDA 12.8

## Comparison

- Faster than DeepSeek-R1-Distill-Qwen-32B (reasoning model)
- Less reasoning capability but better for routine code tasks
- Primary model for day-to-day code generation
