---
tags: [llm, local-inference, qwen, llama-cpp]
created: 2026-04-20
updated: 2026-04-20
sources: [setup_local_ai.sh, llama.cpp/, models/]
related: [[qwen3.6-35b-a3b]], [[qwen3.5-35b-a3b]], [[deepseek-r1-distill-qwen-32b]], [[cuda-12.8]]
status: stable
---

# Local AI Stack

## Summary

Full local LLM inference stack running on RTX 3090 with CUDA 12.8. Uses llama.cpp as the inference engine with two model endpoints: a fast model for boilerplate/CRUD and a reasoning model with speculative decoding for hard bugs and architecture.

## Components

### Inference Engine
- **llama.cpp** — Built with CUDA 12.8 support
- **Fast model endpoint** — `http://localhost:11434` (Qwen3.5/3.6-35B-A3B)
- **Reasoning model endpoint** — `http://localhost:11435` (DeepSeek-R1-Distill-Qwen-32B with Qwen2.5-1.5B draft for speculative decoding)
- **Local proxy** — `http://127.0.0.1:8001` (OpenAI/Anthropic-compatible, used by all coding agents)
- **OpenClaw gateway** — `http://127.0.0.1:18789`

### Models
- **Qwen3.6-35B-A3B** (GGUF) — Primary/fast model, 35B params, 3B active
- **Qwen3.5-35B-A3B** (GGUF) — Secondary fast model
- **DeepSeek-R1-Distill-Qwen-32B** (GGUF) — Reasoning model
- **Qwen2.5-1.5B** (GGUF) — Draft model for speculative decoding
- **Gemma-4-26B** (GGUF) — Multi-modal with projector

### RAG & Search
- **RAGFlow** — Self-hosted RAG knowledge base (Elasticsearch, MinIO, Redis, MySQL, Qwen3-Embedding-0.6B via TEI)
  - API: port 9380, Web: ports 80/443
- **SearXNG** — Self-hosted metasearch engine

### Monitoring
- **llm-status.sh** — Script to check LLM service status

## Hardware
- GPU: RTX 3090 (24GB VRAM)
- RAM: 96GB DDR5

## Systemd Services
- `llama-fast.service` — Fast model, Restart=always, RestartSec=10
- `llama-reason.service` — Reasoning model, Restart=always, RestartSec=10

## Setup
Run `~/setup_local_ai.sh` to install the full stack.
