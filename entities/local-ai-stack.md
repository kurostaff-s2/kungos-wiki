---
tags: [llm, local-inference, qwen, llama-cpp]
created: 2026-04-20
updated: 2026-05-02
sources: [setup_local_ai.sh, llama.cpp/, models/]
related: [[llm-setup-analysis]], [[qwen3.6-35b-a3b]], [[ADR-001-local-llm]], [[ADR-003-llama-cpp]]
status: active
---

# Local AI Stack

## Summary

Local LLM inference on RTX 3090 via llama.cpp. See [[llm-setup-analysis]] for hardware specs, performance data, and optimization recommendations.

## Endpoints

| Endpoint | Port | Model | Status |
|---|---|---|---|
| Local proxy (coding agents) | 8001 | Qwen3.6-27B-Q4 | Active |
| Turboquant (coding agents) | 8002 | Qwen3.6-35B turbo | Needs fix |

## Models

| Model | Quant | Size | Notes |
|---|---|---|---|
| Qwen3.6-27B-UD-Q4_K_XL | Q4 | 17 GB | Primary (port 8001) |
| Qwen3.6-27B-UD-Q5_K_XL | Q5 | 19 GB | Higher quality alternative |
| Qwen3.6-35B-A3B-UD-Q4_K_XL | Q4 | 21 GB | Too large for 24GB VRAM + useful context |
| Qwen3.6-35B-A3B-UD-Q6_K_XL | Q6 | 30 GB | Exceeds VRAM |
| Gemma-4-26B-A4B-it-UD-Q4_K_M | Q4 | 16 GB | Multi-modal |

## RAG & Search

- **RAGFlow** — Self-hosted RAG (Elasticsearch, MinIO, Redis, MySQL, Qwen3-Embedding-0.6B)
- **SearXNG** — Self-hosted metasearch engine

## Setup

- Install: `~/setup_local_ai.sh` (legacy — ports/models outdated)
- Current server started manually (no systemd service — see [[llm-setup-analysis]])
