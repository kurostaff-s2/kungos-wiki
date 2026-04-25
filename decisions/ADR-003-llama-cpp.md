---
tags: [decision, llm, inference, architecture]
created: 2026-04-20
updated: 2026-04-20
status: stable
---

# ADR-003: Use llama.cpp with CUDA for Inference

## Context

Multiple options for running local LLMs: llama.cpp, vLLM, Ollama, text-generation-webui. Need to choose inference engine.

## Decision

Use llama.cpp with CUDA 12.8 for all local LLM inference.

## Rationale

- **Hardware compatibility**: Best support for RTX 3090 (NVIDIA GPU)
- **Quantization support**: GGUF format with various quant levels (Q4_K_M, Q5_K_M, etc.)
- **Streaming**: Native streaming support for progressive output
- **Multi-model**: Can serve multiple models simultaneously on different ports
- **Low overhead**: Minimal dependencies, fast startup
- **Speculative decoding**: Supports draft models for speedup (used with DeepSeek-R1)

## Alternatives Considered

- **vLLM**: Better throughput for serving, but heavier setup, less flexible for multi-model
- **Ollama**: Easier setup but less control over parameters and model management
- **text-generation-webui**: Web UI is nice but unnecessary overhead for agent use

## Consequences

- Models must be in GGUF format (quantized)
- CUDA 12.8 required for optimal GPU acceleration
- Model downloads from Hugging Face Hub
- Inference served via OpenAI-compatible API endpoint

## Related

- [[ADR-001-local-llm]]
- [[ADR-002-dual-model]]
- [[llama.cpp]]
- [[CUDA 12.8]]
