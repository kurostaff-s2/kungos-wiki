---
tags: [llm, local-model, qwen, moe, vision, llama-cpp]
created: 2026-04-20
updated: 2026-04-20
sources: [~/models/qwen3.6-35b-a3b-hf/, ~/llama.cpp/]
related: [[Qwen3.5-35B-A3B]], [[DeepSeek-R1-Distill-Qwen-32B]], [[llama.cpp]], [[RTX 3090]], [[CUDA 12.8]], [[Local AI Stack]]
status: stable
---

# Qwen3.6-35B-A3B

## Summary

Primary fast LLM for the local AI stack. A 35 billion parameter Mixture-of-Experts model with only 3 billion active parameters per forward pass, enabling fast inference on consumer hardware. Supports multimodal (vision) inputs via a dedicated mmproj projector file. Served locally via [[llama.cpp]] on port 11434.

## Architecture

**Model type:** MoE (Mixture of Experts) with dense routing
- **Total parameters:** 35B
- **Active parameters:** 3B per token (highly efficient sparse activation)
- **Architecture class:** `Qwen3_5MoeForConditionalGeneration`
- **Vision encoder:** `qwen3vl` (CLIP-based graph encoder)
- **Weight sharding:** 26 safetensors shards (`model-XXXXX-of-00026.safetensors`)
- **Total model size:** ~20-25GB (FP16)

The MoE design activates only a subset of expert networks per token, providing near-35B quality at 3B compute cost. The qwen3vl vision encoder enables image understanding alongside text generation.

## Hardware

| Component | Specification | Role |
|-----------|--------------|------|
| GPU | NVIDIA RTX 3090 (24GB VRAM) | Primary inference device |
| CUDA | 12.8 | GPU compute toolkit for llama.cpp |
| System RAM | 96GB DDR5 | Buffer for model loading, context |

**VRAM estimates:**
- Full FP16 model: ~70GB (exceeds 3090, requires quantization)
- Q4_K_M quantized: ~20GB VRAM (fits on 3090)
- mmproj projector: ~1-2GB VRAM
- Context window: scales with sequence length, ~2-4GB for 32K context at Q4

## GGUF Conversion

Convert the HuggingFace safetensors to GGUF format using llama.cpp's conversion script:

```bash
python3 ~/llama.cpp/convert_hf_to_gguf.py \
  ~/models/qwen3.6-35b-a3b-hf/ \
  --outtype q4_k_m \
  -o ~/models/qwen3.6-35b-a3b-gguf/qwen3.6-35b-a3b-q4_k_m.gguf
```

**Prerequisites:** `transformers` and `accelerate` Python packages must be installed.

**Output location:** `~/models/qwen3.6-35b-a3b-gguf/`

**Supported quantization methods:** Q4_K_M (recommended), Q5_K_M, Q6_K, Q8_0

## mmproj Regeneration

**Critical:** The multimodal projector (`mmproj`) must be regenerated whenever llama.cpp is updated. A breaking change in commit `19124078b` modified the mmproj format (`mtmd_image_tokens_get_decoder_pos` API change). Loading an old mmproj with a new llama.cpp version causes a segmentation fault in `clip_graph_qwen3vl::build()` during M-RoPE encoding.

**Regeneration command:**
```bash
python3 ~/llama.cpp/convert_hf_to_gguf.py \
  ~/models/qwen3.6-35b-a3b-hf/ \
  --mmproj \
  --outtype f16 \
  -o ~/models/qwen3.6-35b-a3b-gguf/mmproj-F16.gguf
```

This produces `mmproj-F16.gguf` compatible with the current llama.cpp build. The mmproj file (~1-2GB) encodes the vision encoder weights needed for image understanding.

**After updating llama.cpp:** Always regenerate mmproj before attempting vision inference.

## llama.cpp Serving

**Server binary:** `~/llama.cpp/build/bin/llama-server`

**Basic command (text only):**
```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/qwen3.6-35b-a3b-gguf/qwen3.6-35b-a3b-q4_k_m.gguf \
  --host 127.0.0.1 --port 11434 \
  -c 32768 --ctx-shift \
  --tensor-split 1.0
```

**With vision (multimodal):**
```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/qwen3.6-35b-a3b-gguf/qwen3.6-35b-a3b-q4_k_m.gguf \
  --mmproj ~/models/qwen3.6-35b-a3b-gguf/mmproj-F16.gguf \
  --host 127.0.0.1 --port 11434 \
  -c 32768 --ctx-shift \
  --tensor-split 1.0
```

**Key flags:**
- `-c 32768` — 32K context window
- `--ctx-shift` — Context shifting for long sequences when context overflows
- `--tensor-split 1.0` — Full model on RTX 3090 (single GPU)

## Vision Capabilities

Vision support requires both the GGUF model file and the mmproj projector file. The vision system uses:
- **mtmd** (Multi-Token Multi-Modal) backend in llama.cpp
- **M-RoPE** (Multimodal Rotary Positional Embeddings) for positional encoding across text and image tokens
- **CLIP graph encoder** for image feature extraction

**Supported inputs:** Images, documents with embedded images

**Known issue:** Segmentation fault on vision requests if mmproj was built with an older llama.cpp version. Fix: regenerate mmproj after any llama.cpp update.

## Files & Paths

| File | Path | Size | Purpose |
|------|------|------|---------|
| HF safetensors | `~/models/qwen3.6-35b-a3b-hf/` | ~20-25GB | Original model weights (26 shards) |
| GGUF model | `~/models/qwen3.6-35b-a3b-gguf/qwen3.6-35b-a3b-q4_k_m.gguf` | ~20GB | Quantized model for inference |
| mmproj | `~/models/qwen3.6-35b-a3b-gguf/mmproj-F16.gguf` | ~1-2GB | Vision projector (FP16) |
| llama.cpp | `~/llama.cpp/` | — | Inference engine |
| Server binary | `~/llama.cpp/build/bin/llama-server` | — | HTTP API server |

## References

- [[llama.cpp]] — Inference engine documentation
- [[Local AI Stack]] — Full local AI setup overview
- [[ADR-003-llama-cpp]] — Decision to use llama.cpp over vLLM/Ollama
- [[Qwen3.5-35B-A3B]] — Secondary fast model
