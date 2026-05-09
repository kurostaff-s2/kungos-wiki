# Council Pipeline — Architecture

**Date:** 2026-05-07  
**Status:** VALIDATED — slot persistence working, rotation tested, Gemma-4-31B on disk  
**Based on:** OP's 7-step pipeline (Reddit r/LocalLLM, May 2026) + research findings (R1-R5)  
**Implementation:** See `council-implementation.md`

---

## 1. Council Composition

### 1.1 Full Council (7 Members)

| # | Role | Model | GGUF | VRAM (Q4) | Context | Lineage | Arch |
|---|---|---|---|---|---|---|---|
| 1 | **Chair** | Qwen3.6-27B | `Qwen3.6-27B-UD-Q4_K_XL.gguf` | 13.2GB | 130K | Alibaba | Dense |
| 2 | **Builder** | Qwen3-Coder-30B | `Qwen3-Coder-30B-A3B-Instruct-IQ4_XS.gguf` | 12.5GB | 50K | Alibaba | MoE |
| 3 | **Reviewer-Arch** | Gemma-4-31B | `gemma-4-31B-it-UD-Q4_K_XL.gguf` | 17.3GB | 20K | Google | Dense |
| 4 | **Reviewer-Logic** | Nemotron-Cascade-2-30B | `nvidia_Nemotron-Cascade-2-30B-A3B-IQ4_XS.gguf` | 13.5GB | 20K | NVIDIA | MoE |
| 5 | **Reviewer-Diversity** | GPT-OSS-20B | `gpt-oss-20b-Q4_K_M.gguf` | 11.5GB | 20K | OpenAI | Dense |
| 6 | **Reviewer-Authority** | Qwen3.6-35B | `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` | 16.5GB | 20K | Alibaba | MoE |
| 7 | **Tiny Council** | Ministral-8B + Nemotron-Nano-4B + Qwen3-4B | Q6_K each | ~11GB | 10K each | 3 lineages | Mixed |

### 1.2 VRAM Budget (24GB Single GPU)

| Group | Models | VRAM | Swap Behavior |
|---|---|---|---|
| **Tiny Council** | Ministral + Nemotron-Nano + Qwen3-4B | ~11GB | `swap: false, exclusive: true` — co-resident, never evicted |
| **Solo Workers** | Any one of Chair/Builder/Reviewers | 11-17GB | `swap: true, exclusive: true` — mutual eviction |
| **Tiny + Solo** | Tiny Council + one worker | 22-28GB | Worker loads alongside Tiny if <13GB free |

**Constraint:** All models serialize through one GPU. "Parallel" from the Chair's perspective = sequential execution via `llama-swap`.

### 1.3 Research Validation (R1-R5)

| Principle | Source | How This Council Satisfies It |
|---|---|---|
| **Diversity > size** | NEO (R1) | 4 lineages: Alibaba, Google, NVIDIA, OpenAI |
| **Code-trained ≠ reviewer** | arXiv (R2) | Qwen3-Coder is Builder only, never Reviewer |
| **Simple prompts** | arXiv (R2) | Review prompts: "flag or pass" — no explanations |
| **Architecture-strict reviewer** | Springer (R3) | Gemma-4-31B dedicated to architecture/structure |
| **Builder/Reviewer separation** | Fireworks (R4) | Qwen3-Coder generates; 4 other models review |

---

## 2. Pipeline: 7-Step Council-Build-Council

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: SPEC                                               │
│  Tiny Council (3-way parallel critique)                     │
│  → Ministral-8B: structured checks, tool-use                │
│  → Nemotron-Nano-4B: logic/sanity checks                    │
│  → Qwen3-4B: broad coverage, third perspective              │
│  Duration: ~20s (co-resident, no swap cost)                 │
└──────────────────┬──────────────────────────────────────────┘
                   │ synthesize
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: REVIEW                                             │
│  Gemma-4-31B (architecture/structure review)                │
│  → Flag structural inconsistencies                          │
│  → Flag architectural anti-patterns                         │
│  Duration: ~2s restore + ~30s gen                           │
└──────────────────┬──────────────────────────────────────────┘
                   │ synthesize
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: PLAN                                               │
│  Chair (Qwen3.6-27B, 130K ctx)                              │
│  → Synthesize spec + review findings                        │
│  → Generate execution plan                                  │
│  Duration: ~5s restore + gen                                │
└──────────────────┬──────────────────────────────────────────┘
                   │ dispatch
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: BUILD                                              │
│  Builder (Qwen3-Coder-30B, 50K ctx)                         │
│  → Generate code/config/scripts                             │
│  → Can fan out to 3 worktrees for parallel builds           │
│  Duration: ~2s restore + ~60s gen                           │
└──────────────────┬──────────────────────────────────────────┘
                   │ review
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: CODE REVIEW                                        │
│  3-way fanout:                                              │
│  → Nemotron-Cascade-2-30B: logic errors, edge cases         │
│  → GPT-OSS-20B: different tokenizer, different failures     │
│  → Qwen3.6-35B: subtle bugs, final authority                │
│  Duration: 3 x (~2s restore + ~20s gen) = ~66s              │
└──────────────────┬──────────────────────────────────────────┘
                   │ synthesize
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 6: SECURITY REVIEW                                    │
│  Qwen3.6-35B (final authority on security)                  │
│  → Auth bypass, injection, privilege escalation             │
│  → Data exposure, tenant isolation                          │
│  Duration: ~2s restore + ~25s gen                           │
└──────────────────┬──────────────────────────────────────────┘
                   │ synthesize
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 7: UAT REVIEW                                         │
│  Chair (Qwen3.6-27B)                                        │
│  → Accept/reject/modify                                     │
│  → If reject → remediation cycle (back to Step 4)           │
│  Duration: ~5s restore + gen                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 Performance Estimate (with slot persistence)

| Step | Swap (restore) | Generation | Total |
|---|---|---|---|
| 1. Spec (Tiny, co-resident) | 0s | ~20s | ~20s |
| 2. Review (Gemma) | ~2s | ~30s | ~32s |
| 3. Plan (Chair) | ~5s | ~15s | ~20s |
| 4. Build (Coder) | ~2s | ~60s | ~62s |
| 5. Code Review (3-way) | 3×2s | 3×20s | ~66s |
| 6. Security (Qwen3.6-35B) | ~2s | ~25s | ~27s |
| 7. UAT (Chair) | ~5s | ~15s | ~20s |
| **Total (1 cycle)** | **~28s** | **~185s** | **~213s (3.5 min)** |

**Without slots:** ~22 min prefill + 185s gen = **~25.5 min**

**Savings:** ~22 min of prefill overhead eliminated.

### 2.2 Remediation Cycles

If UAT rejects, loop back to Step 4 (Build). Each remediation cycle:

| Step | With Slots | Without Slots |
|---|---|---|
| Build + Chair-return | ~67s | ~195s |
| Code Review (3-way) + Chair-return | ~71s | ~255s |
| Security + Chair-return | ~32s | ~195s |
| UAT | ~20s | ~195s |
| **Per cycle** | **~190s** | **~840s (14 min)** |

---

## 3. Prompt Discipline (per arXiv R2)

### 3.1 Review Prompts — Simple "Flag or Pass"

**DO:**
```
Review the following [specification / code / plan].
Flag any issues as: [ISSUE] <one-line description>
If no issues, respond: [PASS]
Do not explain. Do not propose fixes.
```

**DON'T:**
```
Review the following code. Explain any issues you find.
Propose corrections for each issue. Justify your reasoning.
Consider edge cases and provide a detailed analysis.
```

The arXiv paper (R2) shows that detailed prompts **increase** misjudgment rates by 15-30%. Simple prompts keep false positives low.

### 3.2 Chair Synthesis Prompt

```
Synthesize the following reviews into a decision:
- Accept: no flags from any reviewer
- Modify: flags exist but are resolvable
- Reject: fundamental issues that require rework

List each [ISSUE] and whether it's resolved.
Output: [ACCEPT] / [MODIFY: <changes>] / [REJECT: <reasons>]
```

---

## 4. Model Directory Mapping

| Alias | Path | Size |
|---|---|---|
| `chair` | `/home/chief/models/Qwen3.6-27B/Qwen3.6-27B-UD-Q4_K_XL.gguf` | 13.2GB |
| `builder` | `/home/chief/models/qwen3/Qwen3-Coder-30B-A3B-Instruct-IQ4_XS.gguf` | 12.5GB |
| `reviewer-arch` | `/home/chief/models/gemma-4-31b/gemma-4-31B-it-UD-Q4_K_XL.gguf` | 17.3GB ✅ |
| `reviewer-logic` | `/home/chief/models/nvidia/nvidia_Nemotron-Cascade-2-30B-A3B-IQ4_XS.gguf` | 13.5GB |
| `reviewer-diversity` | `/home/chief/models/openai/gpt-oss-20b-Q4_K_M.gguf` | 11.5GB |
| `reviewer-authority` | `/home/chief/models/qwen3.6-35b/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` | 16.5GB |
| `ministral` | `/home/chief/models/mistral/Ministral-8B-Instruct-2410-Q6_K.gguf` | 7.2GB |
| `nemotron-nano` | `/home/chief/models/nvidia/NVIDIA-Nemotron-3-Nano-4B-Q6_K.gguf` | 3.3GB ⚠️ thinking always-on |
| `qwen3-4b` | `/home/chief/models/qwen3/Qwen3-4B-Instruct-2507-Q6_K.gguf` | 3.0GB |

---

## 5. Chat Template Reference

All 9 council models have `tokenizer.chat_template` embedded in their GGUF. Extracted and verified 2026-05-07 via `gguf-dump`.

### 5.1 Summary

| Alias | Architecture | Template Size | Thinking | Toggleable? | Jinja Macros | Tools | Multimodal |
|---|---|---|---|---|---|---|---|
| `ministral` | llama | 3,945 chars | ❌ NO | N/A | ❌ | ✅ | ❌ |
| `nemotron-nano` | nemotron_h | 10,486 chars | ⚠️ ALWAYS ON | ❌ ignored | ✅ | ✅ | ❌ |
| `qwen3-4b` | qwen3 | 4,051 chars | ❌ NO | N/A | ❌ | ✅ | ❌ |
| `chair` | qwen35 | 8,057 chars | ⚠️ ON (default) | ✅ `enable_thinking` | ✅ | ✅ | ✅ |
| `builder` | qwen3moe | 6,896 chars | ❌ NO | N/A | ✅ | ✅ | ❌ |
| `reviewer-arch` | gemma4 | 16,934 chars | OFF (default) | ✅ `enable_thinking` | ✅ | ✅ | ✅ |
| `reviewer-logic` | nemotron_h_moe | 10,925 chars | ⚠️ ALWAYS ON | ❌ ignored | ✅ | ✅ | ❌ |
| `reviewer-diversity` | gpt-oss | 17,221 chars | ⚠️ ALWAYS ON | ❌ `reasoning_effort` only | ✅ | ✅ | ❌ |
| `reviewer-authority` | qwen35moe | 8,057 chars | ⚠️ ON (default) | ✅ `enable_thinking` | ✅ | ✅ | ✅ |

### 5.2 Thinking Behavior by Family

**No thinking (plain `@assistant\n` generation prompt):**
- `ministral` — standard Mistral-style template, no reasoning tokens
- `qwen3-4b` — handles `reasoning_content` in message history but doesn't inject thinking prefix on generation
- `builder` (Qwen3-Coder) — Unsloth-patched template, no thinking

**Thinking ON by default, toggleable (`enable_thinking=False` works):**
- `chair` (Qwen3.6-27B) — `@assistant\n<think>\n` unless `enable_thinking is false`
- `reviewer-authority` (Qwen3.6-35B) — identical template to chair

**Thinking OFF by default, toggleable (`enable_thinking=True` to enable):**
- `reviewer-arch` (Gemma-4-31B) — `enable_thinking | default(false)`. Uses `<|think|>` token and `<|channel|>thought` format. Opposite semantics from Qwen.

**Thinking ALWAYS ON (parameter ignored by llama.cpp):**
- `nemotron-nano` — `enable_thinking if defined else True`; llama.cpp doesn't pass the variable
- `reviewer-logic` (Nemotron-Cascade-2-30B) — same pattern as Nano, plus `reasoning_budget` support
- `reviewer-diversity` (GPT-OSS-20B) — uses `reasoning_effort` (defaults `"medium"`), no on/off toggle. Injects `Reasoning: medium` into system prompt.

### 5.3 Per-Model Details

#### ministral (llama)
- **Tokenizer:** gpt2 / tekken
- **BOS:** 1, **EOS:** 2, **add_bos:** True
- **Template style:** Standard Mistral Instruct — `{%- if messages[0]["role"] == "system" %}` pattern
- **Generation prompt:** `@assistant\n`
- **Macros:** None — simple Jinja, no rendering concerns
- **Status:** ✅ Clean, no issues

#### nemotron-nano (nemotron_h)
- **Tokenizer:** gpt2 / pixtral
- **BOS:** 1, **EOS:** 11, **add_bos:** True
- **Template style:** NVIDIA reasoning — `render_extra_keys` macro, `</think>`/`</think>` tags
- **Generation prompt:** `@assistant\n<think>\n` (thinking always injected)
- **Thinking tokens:** `</think>` / `</think>` (HTML-like, not `<think>`)
- **Special features:** `truncate_history_thinking`, `reasoning_budget`
- **Status:** ⚠️ Requires `max_tokens ≥ 50`; check `reasoning_content` + `content`

#### qwen3-4b (qwen3)
- **Tokenizer:** gpt2 / qwen2
- **EOS:** 151645, **add_bos:** False
- **Template style:** Qwen3 Instruct — `@system`, `@user`, `@assistant` markers
- **Generation prompt:** `@assistant\n` (no thinking prefix)
- **Reasoning handling:** Accepts `reasoning_content` in message history, reformats with `</think>`/`</think>` tags. Does NOT inject thinking on generation.
- **Status:** ✅ Clean, no issues

#### chair — Qwen3.6-27B (qwen35)
- **Tokenizer:** gpt2 / qwen35
- **BOS:** 248044, **EOS:** 248046, **add_bos:** False
- **Template style:** Qwen3.5 multimodal — `render_content` macro, image/video counting
- **Generation prompt:** `@assistant\n<think>\n` (thinking ON) or `@assistant\n<think>\n\n</think>\n\n` (thinking OFF)
- **Toggle:** `{%- if enable_thinking is defined and enable_thinking is false %}` — pass `enable_thinking: false` to disable
- **Multimodal:** Yes — `image_count`, `video_count` namespace tracking
- **Status:** ⚠️ Thinking ON by default; use `enable_thinking: false` if you want plain responses

#### builder — Qwen3-Coder-30B (qwen3moe)
- **Tokenizer:** gpt2 / qwen2
- **EOS:** 151645, **add_bos:** False
- **Template style:** Unsloth-patched Qwen2.5-Coder — `render_item_list` macro, `@system`/`@user`/`@assistant`
- **Generation prompt:** `@assistant\n` (no thinking)
- **Special:** Handles `tool` role with `@tool` markers; `loop.previtem`/`loop.nextitem` for tool grouping
- **Status:** ✅ Clean, no thinking issues

#### reviewer-arch — Gemma-4-31B (gemma4)
- **Tokenizer:** gemma4 / gemma4
- **BOS:** 2, **EOS:** 106, **add_bos:** True
- **Template style:** Google Gemma 4 — `format_parameters` macro, `<|channel|>` routing
- **Generation prompt:** `<|im_start|>model<|heading|>reply<|message|>` (no thinking) or `<|im_start|>model<|heading|>think<|message|>` (thinking ON)
- **Toggle:** `enable_thinking | default(false)` — **OFF by default**, opposite of Qwen
- **Thinking token:** `<|think|>` (not `</think>`)
- **Thinking channel:** `<|channel|>thought\n` + `<channel|>`
- **Multimodal:** Yes — image/video support via `content` array
- **Status:** ⚠️ Thinking OFF by default; different toggle semantics than Qwen; uses unique `<|think|>` token

#### reviewer-logic — Nemotron-Cascade-2-30B (nemotron_h_moe)
- **Tokenizer:** gpt2 / tekken
- **BOS:** 1, **EOS:** 11, **add_bos:** False
- **Template style:** Same as Nemotron-Nano (NVIDIA reasoning family) — `render_extra_keys` macro
- **Generation prompt:** `@assistant\n<think>\n` (thinking always injected)
- **Thinking tokens:** `</think>` / `</think>`
- **Special features:** `reasoning_budget` — can inject `{thinking token budget: N}` into last user message
- **Status:** ⚠️ Same as Nemotron-Nano: thinking always-on, needs `max_tokens ≥ 50`

#### reviewer-diversity — GPT-OSS-20B (gpt-oss)
- **Tokenizer:** gpt2 / gpt-4o
- **BOS:** 199998, **EOS:** 200002, **add_bos:** True
- **Template style:** OpenAI-compatible — `<|start|>`, `<|end|>`, `<|channel|>`, `<|message|>` tags
- **Generation prompt:** `<|start|>assistant<|channel|>final<|message|>` (after analysis channel)
- **Reasoning:** `reasoning_effort` parameter (defaults `"medium"`). Injects `Reasoning: medium\n\n` into system prompt. No on/off toggle.
- **Thinking channels:** `<|channel|>analysis<|message|>` for thinking, `<|channel|>final<|message|>` for answer
- **Special:** Supports `builtin_tools` ("browser", "code_interpreter"); `thinking` field in messages (not `reasoning_content`)
- **Status:** ⚠️ Reasoning always active; uses `thinking` field (not `reasoning_content`); channels-based format

#### reviewer-authority — Qwen3.6-35B (qwen35moe)
- **Tokenizer:** gpt2 / qwen35
- **BOS:** 248044, **EOS:** 248046, **add_bos:** False
- **Template:** Identical to chair (Qwen3.6-27B) — same `render_content` macro, same thinking toggle
- **Status:** ⚠️ Same as chair: thinking ON by default

### 5.4 Compatibility Concerns

| Concern | Affected Models | Impact | Mitigation |
|---|---|---|---|
| **Thinking always-on** | nemotron-nano, reviewer-logic, reviewer-diversity | Burns token budget; `content` may be empty with low `max_tokens` | Use `max_tokens ≥ 50`; check `reasoning_content` + `content` |
| **Thinking ON by default** | chair, reviewer-authority | Extra tokens in every response | Pass `enable_thinking: false` if plain output needed |
| **Gemma opposite toggle** | reviewer-arch | `enable_thinking: false` has no effect (already OFF); `enable_thinking: true` enables | Don't assume Qwen semantics; Gemma defaults to OFF |
| **Jinja macros** | 7 of 9 models | May not render correctly in older llama.cpp versions | Test with current build; macros work in cherry-picked version |
| **Multimodal templates** | chair, reviewer-arch, reviewer-authority | Template handles image/video but we send text only | Harmless — image_count stays 0, text path executes |
| **GPT-OSS `thinking` field** | reviewer-diversity | Uses `message.thinking` not `message.reasoning_content` | Send `thinking` field for GPT-OSS, `reasoning_content` for others |

### 5.5 Recommended Defaults per Model

| Alias | `max_tokens` min | `enable_thinking` | Special fields |
|---|---|---|---|
| `ministral` | any | N/A | none |
| `nemotron-nano` | **50** | ignored (always ON) | check `reasoning_content` |
| `qwen3-4b` | any | N/A | none |
| `chair` | any | `false` (if plain output) | none |
| `builder` | any | N/A | none |
| `reviewer-arch` | any | `false` (default, no action) | none |
| `reviewer-logic` | **50** | ignored (always ON) | check `reasoning_content` |
| `reviewer-diversity` | **50** | ignored (always ON) | use `thinking` field, not `reasoning_content` |
| `reviewer-authority` | any | `false` (if plain output) | none |

---

## 6. Inference Engine: Speculative Decoding & Slot Strategy

**Date:** 2026-05-08
**Status:** RESEARCH — crash audit complete, integration paths mapped

#### 6.1 Options Evaluated

| Approach | Repo | Spec Type | MTP? | DFlash? | TCQ? | Stars | Upstream? |
|---|---|---|---|---|---|---|---|
| **buun-llama-cpp** | `spiritbuun/buun-llama-cpp` | DFlash (built-in) | ❌ not yet | ✅ native | ✅ native | 571 | Fork |
| **llama-cpp-turboquant** | `TheTom/llama-cpp-turboquant` | ngram/external drafter | ❌ not yet | ❌ | ✅ native | — | Fork |
| **llama.cpp upstream** | `ggml-org/llama.cpp` | ngram/external drafter | ⏳ PR #22673 | ❌ | ❌ | — | Mainline |
| **llama.cpp-dgx** | `croll83/llama.cpp-dgx` | DFlash + MTP | ✅ experimental | ✅ | ✅ | 3 | Fork |
| **Luce DFlash** | `iexcalibur/lucebox/dflash` | DFlash + DDTree | ❌ | ✅ standalone | ❌ | 0 | Standalone |

**Upstream PR status (all open, none merged as of May 8):**
- **MTP:** PR #22673 — created May 4, ggerganov has review comments (architectural concerns)
- **DFlash:** PR #22105 — created Apr 19, blocked on Eagle3 PR #18039 merge first
- **Eagle3:** PR #18039 — API refactoring prerequisite for both DFlash and MTP upstream paths

#### 6.2 MTP (Multi-Token Prediction)

MTP uses auxiliary heads **baked into the model** to predict multiple tokens ahead — no separate drafter model needed.

- **Upstream status:** PR #22673 open. ggerganov flagged: logic must be extracted into server/speculative contexts; multi-modal position handling incomplete; prompt cache restore broken for embeddings
- **Tested on:** Qwen3.6-27B, Qwen3.6-35BA3B
- **Performance:** ~2x speedup, ~72% acceptance at 3 draft tokens. Verified reproducible by multiple users
- **User report (buun #45):** "Every time I use MTP, speed improves 2x+. DFlash basically makes it slower" — suggests DFlash may not deliver on paper claims for all hardware
- **Invocation:** `--spec-type mtp --spec-draft-n-max 3`
- **GGUF requirement:** Model must include MTP tensors (converted via modified `convert_hf_to_gguf.py`)
- **Available GGUFs:** `am17an/Qwen3.6-27B-MTP-GGUF`, `am17an/Qwen3.6-35BA3B-MTP-GGUF`

**Port effort to buun-llama-cpp:**

| File | Changes | Conflict risk |
|---|---|---|
| `common/speculative.cpp` | +189 lines (new MTP speculative class) | Low — additive alongside DFlash |
| `src/llama-context.cpp` | +161 lines (MTP head loading, KV cache) | Medium — DFlash tape_replay in same area |
| `src/llama-graph.cpp/.h` | Graph builder for MTP heads | Medium — TCQ custom graph |
| `src/llama-arch.cpp` | Architecture parsing for MTP layers | Low |
| `ggml/` backends (CPU, CUDA, Metal, Vulkan) | Gated Delta Net ops | High — buun has heavy CUDA customizations |
| `convert_hf_to_gguf.py` | GGUF conversion for MTP tensors | Low |

#### 6.3 DFlash (Block Diffusion Speculative Decoding)

DFlash uses a lightweight block diffusion model for **parallel drafting** — generates entire blocks of tokens in a single forward pass.

- **Paper:** arXiv:2602.06036 — claims up to 6x acceleration
- **Reality check:** Paper claims not consistently reproduced. User reports show wide variance:
  - **Best case:** Luce DFlash reports 207 tok/s on Qwen3.5-27B (RTX 3090) with DDTree
  - **Worst case:** buun #35 — 3.4 tok/s on RTX 5090M (sm_120), verify pass 1500ms vs expected 15-25ms
  - **Typical buun master:** ~74 tok/s on RTX 3090 (per Luce benchmark comparison)
- **Invocation:** `--spec-type dflash` (buun-llama-cpp only)
- **GGUF requirement:** DFlash drafter weights bundled in GGUF
- **Available GGUFs:** `spiritbuun/Qwen3.6-27B-DFlash-GGUF`, `z-lab/Qwen3.6-27B-DFlash`, `z-lab/Qwen3.6-35B-A3B-DFlash`

#### 6.4 Crash & Instability Audit

**buun-llama-cpp open issues (16 open, 16 closed):**

| # | Issue | Severity | Status | Impact on Council |
|---|---|---|---|---|
| **#22** | `GGML_ASSERT(ggml_can_repeat)` crash: DFlash + TurboQuant together | **CRITICAL** | Open | ❌ Can't use DFlash + TCQ simultaneously |
| **#21** | DFlash crashes: `n_ubatch` assertion + `logits nullptr` on 2nd request | **CRITICAL** | Open | ❌ DFlash unstable beyond first request |
| **#28** | CUDA illegal memory access: dual GPU + DFlash + turbo4 TCQ | **HIGH** | Open | ⚠️ Dual-GPU setups crash |
| **#29** | `GET_ROWS` failed with turbo3 + DFlash | **HIGH** | Open | ⚠️ turbo3 TCQ + DFlash incompatible |
| **#32** | DFlash RoPE extrapolates past 4096 → accept collapses at long ctx | **HIGH** | Open | ❌ **130K context broken** — acceptance drops from 73% to 13% past 4K tokens. Patch attached, not merged |
| **#34** | DFlash bug on heterogeneous dual GPU (16G + 6G, different gens) | **MEDIUM** | Open | ⚠️ Mixed GPU setups affected |
| **#38** | DFlash + mmproj (vision) simultaneous use → CUDA crash | **MEDIUM** | Open | ⚠️ Not relevant (no vision in council) |
| **#40** | TQ3/TQ4 numerically degraded output on sm_87 (Jetson Orin Nano) | **MEDIUM** | Open | ⚠️ Older Ampere GPUs affected |
| **#41** | Tool-call JSON generation truncates (May 1 commits regression) | **MEDIUM** | Open | ⚠️ Affects tool-use models |

**Closed (fixed) issues of note:**
- #44: DFlash tape_replay crash with partial GPU offload → **Fixed May 6**
- #39: cublasSgemm crash with zero-dim matrices in spec decoding → **Fixed May 5**
- #35: DFlash verify 1500ms/token on sm_120 → **Closed** (status unclear, no linked commit)
- #36: ROCm regression segfault → **Fixed May 1**
- #27: CUDA build fails on RTX 3090 (sm_86) → **Fixed Apr 26**

**llama-cpp-turboquant open issues (20+ open):**

| # | Issue | Severity | Impact on Council |
|---|---|---|---|
| **#102** | turbo4/turbo4 severe gen slowdown at large contexts (4 tok/s at 250K) | **HIGH** | ❌ turbo4 unusable at long context |
| **#119** | cublasSgemm_v2 INVALID_VALUE during prompt-cache invalidation (turbo3 + MoE) | **HIGH** | ⚠️ Affects Builder (MoE) + Reviewer-Authority (MoE) |
| **#128** | q8_0/q8_0 KV fails on Qwen3.5 9B hybrid (head_dim=256) | **MEDIUM** | ⚠️ Hybrid models affected |
| **#131/132** | CUDA turbo2 decode regression on MoE — VEC/MMA dispatch gap | **MEDIUM** | ⚠️ MoE models (Builder, Reviewer-Logic, Reviewer-Authority) |

**Key finding:** Both forks have **unresolved critical crashes** when combining their specialty features:
- buun: DFlash + TCQ = crash (#22, #29)
- turboquant: turbo4 at long context = unusable slowdown (#102)
- buun: DFlash at long context (>4K) = acceptance collapse (#32)

#### 6.5 Slot Persistence

**Already works in llama.cpp server — no modification needed.**

The server manages per-slot KV cache with controls for persistence across requests:

| Parameter | Purpose | Council relevance |
|---|---|---|
| `n_keep` | Tokens to keep at slot start (system prompt, prefix) | Keep system prompt + role definition |
| `n_discard` | Tokens to discard from slot end before new request | Free space for new turns |
| `n_ctx` | Total context per slot | Must fit full conversation |
| `n_batch` / `n_ubatch` | Batch sizing for prefill/decode | Tuning for 24GB GPU |
| Prompt caching | Automatic KV cache reuse for shared prefixes | Eliminates ~22 min prefill overhead |

**Council impact:** Slot persistence is what enables the 3.5-minute cycle time (Section 2.1). Without it, each model swap costs full prefill (~25.5 min total).

Recent buun commit (May 3): `server: fix prompt caching for hybrid models (Qwen3.6-35B-A3B)` — confirms hybrid/MoE prompt caching is actively maintained.

#### 6.6 Integration Paths

**Path A: buun-llama-cpp with TCQ only (no DFlash)** — *Recommended starting point*

```
./llama-server -m model.gguf -ngl 99 -fa \
  -ctk turbo4 -ctv turbo4 \
  -c 131072 \
  --parallel 1
```

- **Pros:** TCQ works reliably without DFlash. Gives 130K+ context. No crash risks from #22/#29. Actively maintained.
- **Cons:** No speculative decoding speedup. Standard decode speed only.
- **Stability:** ✅ TCQ alone has no open critical crashes
- **Council benefit:** ALL models get long context. Steps 1-7 all benefit from slot persistence.

**Path B: buun-llama-cpp with DFlash (no TCQ)** — *If decode speed is the bottleneck*

```
./llama-server -m target.gguf -md dflash-draft.gguf -ngl 99 -ngld 99 \
  --spec-type dflash \
  -c 32768 -cd 512 \
  -b 256 -ub 64
```

- **Pros:** Up to 2x decode speed on Qwen3.6 models (Steps 3, 6, 7)
- **Cons:** Context limited to ~4K before acceptance collapse (#32). Can't combine with TCQ (#22). Unstable on 2nd+ requests (#21). Hardware-dependent (broken on sm_120, #35).
- **Stability:** ❌ 3 open critical crashes block production use
- **Council benefit:** Only Chair + Reviewer-Authority (Steps 3, 6, 7). Not worth instability risk.

**Path C: Cherry-pick MTP PR #22673 into buun-llama-cpp** — *Best long-term target*

- **Pros:** 2x speed, verified reproducible, no separate drafter GGUF needed, works at any context length, no DFlash crash risks
- **Cons:** PR not merged (ggerganov has architectural concerns). Cherry-pick against moving target. CUDA backend conflicts with buun's customizations.
- **Stability:** ⚠️ Unknown until cherry-picked and tested
- **Council benefit:** Chair + Reviewer-Authority at 2x speed, full 130K context preserved

**Path D: llama-cpp-turboquant with ngram speculative decoding** — *Safest but modest gain*

```
./llama-server -m model.gguf -ngl 99 -fa \
  -ctk turbo4 -ctv turbo4 \
  --spec-type ngram-mod --spec-draft-n-max 64 \
  -c 131072
```

- **Pros:** No DFlash crash risks. TCQ for long context. ngram spec works with any GGUF.
- **Cons:** ngram gives only 1.2-1.5x speedup (vs 2x for MTP). turbo4 has slowdown at very long context (#102).
- **Stability:** ⚠️ turbo4 slowdown at 250K+; use q4_0 or turbo3 for long context
- **Council benefit:** ALL models get TCQ + modest speed boost

**Path E: Wait for upstream merges** — *Lowest risk, highest delay*

- Eagle3 PR #18039 → DFlash PR #22105 → MTP PR #22673 (all blocked on each other)
- No timeline. ggml-org moves slowly on speculative decoding API.
- Risk: API changes could break any fork cherry-picks in progress.

#### 6.7 Recommendation Matrix (Updated with Crash Data)

| If you want... | Use | Crash risk | Production-ready? |
|---|---|---|---|
| **130K context, stable** | **Path A: buun + TCQ only** | Low | ✅ Yes |
| **Maximum decode speed now** | **Path B: buun + DFlash** | **HIGH** | ❌ No — 3 critical crashes |
| **Best quality × speed (future)** | **Path C: cherry-pick MTP** | Medium | ⚠️ Needs build + test |
| **Safe + modest speed + long ctx** | **Path D: turboquant + ngram** | Low | ✅ Yes (avoid turbo4 at 250K+) |
| **Zero risk** | **Path E: wait for upstream** | None | ⚠️ No timeline |

#### 6.8 Risks & Uncertainties

1. **DFlash + TCQ = crash** — Issue #22 (`GGML_ASSERT(ggml_can_repeat)`) means you cannot combine buun's two flagship features. Pick one.
2. **DFlash at long context = broken** — Issue #32: acceptance collapses from 73% to 13% past 4K tokens. Patch exists but not merged. **This directly conflicts with the 130K context requirement.**
3. **PR #22673 not merged** — ggerganov's review comments flag architectural concerns (multi-modal position handling, prompt cache restore). MTP GGUF format may change.
4. **turbo4 slowdown at long context** — Issue #102: turbo4 drops to 4 tok/s at 250K. Use `turbo3` or `q4_0` for contexts >100K.
5. **MoE + turbo3 crashes** — Issue #119: prompt-cache invalidation crashes with MoE models. Affects Builder and Reviewer-Authority.
6. **Council models and MTP/DFlash compatibility** — Only Qwen3.6 family (chair, reviewer-authority) have MTP/DFlash GGUFs. Other council members get no spec benefit.
7. **Hardware-specific DFlash failures** — sm_120 (RTX 5090M) verify pass 60x slower than expected (#35). sm_87 (Jetson Orin) produces degraded output (#40). Test on your actual GPU before committing.

#### 6.9 Corrected KV Cache Analysis (May 8, v2)

**Previous calculation was wrong** — forgot to multiply by number of layers (64). Corrected with actual HuggingFace config data:

Qwen3.6-27B actual arch: `hidden_size=5120, layers=64, kv_heads=4, head_dim=256`

KV values per token = 2 × kv_heads × head_dim × layers = 2 × 4 × 256 × 64 = **131,072**

| Cache type | Bytes/value | Per token | 130K total | + weights (16.8GB) | Fits 24GB? |
|---|---|---|---|---|---|
| fp16 | 2 | 256 KB | 33.3 GB | 50.1 GB | ❌ |
| q8_0 | 1 | 128 KB | 16.6 GB | 33.4 GB | ❌ |
| **q4_0** | **0.5** | **64 KB** | **8.2 GB** | **25.0 GB** | **❌ Does NOT fit** |
| **turbo4** | ~0.13 | ~16 KB | ~2.1 GB | ~18.9 GB | ✅ |
| **turbo3** | ~0.10 | ~12 KB | ~1.6 GB | ~18.4 GB | ✅ |

**TCQ is REQUIRED for 130K context.** Standard q4_0 KV cache overflows 24GB by ~1GB.

#### 6.10 All Council Models — TCQ Needed?

| Model | Context | Layers | KV heads | Head dim | q4_0 KV | Total (q4_0) | TCQ needed? |
|---|---|---|---|---|---|---|---|
| Chair (Qwen3.6-27B) | 130K | 64 | 4 | 256 | 8.2 GB | 25.0 GB | **YES** |
| Builder (Qwen3-Coder-30B) | 50K | 48 | 4 | 128 | 1.2 GB | 13.7 GB | No |
| Reviewer-Arch (Gemma-4-31B) | 20K | ~48 | ~8 | ~160 | ~1.2 GB | ~18.5 GB | No |
| Reviewer-Logic (Nemotron-30B) | 20K | 52 | 2 | 128 | 0.3 GB | 13.8 GB | No |
| Reviewer-Diversity (GPT-OSS-20B) | 20K | 24 | 8 | 64 | 0.1 GB | 11.6 GB | No |
| Reviewer-Authority (Qwen3.6-35B) | 20K | 40 | 2 | 256 | 0.4 GB | 16.9 GB | No |
| Tiny Council (3 models) | 10K each | varies | varies | varies | ~0.5 GB | ~11 GB | No |

**Only the Chair needs TCQ.** All other models fit comfortably with q4_0.

#### 6.11 Council-Specific Impact & Recommended Path

For the 7-member council on 24GB GPU:

**Phase 1 — Immediate (this week):** llama-cpp-turboquant + TCQ — **required**
- Build `TheTom/llama-cpp-turboquant` master
- **Chair KV strategy:** Start with `-ctk turbo4 -ctv turbo4` at 130K (18.9 GB). Validate quality via `llama-perplexity` vs q8_0 baseline. If turbo4/turbo4 degrades on head_dim=256 (per bug #47 pattern), fall back to `-ctk q8_0 -ctv turbo4` at 80K (22.7 GB). Set `TURBO_AUTO_ASYMMETRIC=0` to prevent silent K→q8_0 upgrade at 130K (would OOM).
- All other models fit with standard q4_0 KV
- Cherry-pick `server: fix prompt caching for hybrid models` from buun (commit on May 3) — needed for MoE models (Builder, Reviewer-Authority)
- No speculative decoding — accept standard decode speed
- **Expected cycle time:** ~3.5 min (same as Section 2.1, no speedup but stable)
- **Why turboquant over buun:** DFlash is too buggy to use (#22, #21, #32). Without DFlash, buun offers only marginal TCQ CUDA optimizations over turboquant. turboquant has less upstream divergence = fewer conflicts for Phase 2 MTP cherry-pick. The buun TCQ optimizations (`set_rows`, Ada MMQ tile cap) can be cherry-picked later if benchmarking shows they matter.

**Phase 2 — When ready (1-2 weeks):** Cherry-pick MTP PR #22673 into turboquant
- Port MTP into llama-cpp-turboquant (conflicts in `llama-context.cpp`, CUDA backends — but fewer than buun due to less divergence)
- Convert Chair + Reviewer-Authority GGUFs to MTP format
- **Expected gain:** Steps 3, 6, 7 at 2x speed → ~1.8 min cycle time
- **Risk:** Cherry-pick may break on PR changes; needs thorough testing

**Do NOT pursue DFlash (buun-llama-cpp)** for the council:
- Can't combine with TCQ (crash #22) — and TCQ is required for the Chair
- Breaks at long context (issue #32) — directly conflicts with 130K requirement
- User reports show it can make things slower (#45)
- 3 open critical crashes make it unsuitable for production pipeline

#### 6.12 buun vs turboquant Decision Note

**Question:** Why not buun-llama-cpp if we need TCQ?

**Answer:** buun's only advantage over turboquant is DFlash + marginal TCQ CUDA optimizations. DFlash is unusable (crashes, long context broken). The TCQ optimizations (`turbo3 set_rows`, Ada MMQ tile cap) are performance tweaks, not correctness fixes — cherry-pickable if needed.

| Factor | turboquant | buun |
|---|---|---|
| TCQ support | ✅ | ✅ |
| DFlash | ❌ | ✅ (but buggy, unusable) |
| Upstream divergence | Lower (TCQ only) | Higher (TCQ + DFlash) |
| MTP cherry-pick conflicts | Fewer | More (DFlash in same files) |
| TCQ CUDA optimizations | Baseline | +`set_rows`, +Ada MMQ |
| Hybrid prompt caching fix | ❌ (cherry-pick from buun) | ✅ |
| Upstream sync date | Apr 23 (64 commits) | Apr 30 (325 commits) |

**Decision:** turboquant is the cleaner base. Less code, fewer conflicts, same TCQ functionality. Cherry-pick buun's hybrid prompt caching fix (1 commit) and TCQ optimizations (if benchmarked worthwhile).

#### 6.13 Asymmetric KV Cache — Research Findings (May 8)

**Source:** TheTom/turboquant_plus paper (`asymmetric-kv-compression.md`), llama-cpp-turboquant issues #47, #54, #115

**The discovery (TheTom, Mar 2026):** "V compression is essentially free. K compression is catastrophic."

The attention mechanism is inherently asymmetric:
```
O = softmax(QK^T/√d) · V
```
- **K errors** → amplified **exponentially** by softmax (routing decision)
- **V errors** → scale **linearly**, vanish for low-attention positions (content carrier)

**Evidence across 7 models, 3 backends (Metal, CUDA, HIP):**

| K | V | Qwen2.5-7B Q4_K_M PPL | Status |
|---|---|---|---|
| q8_0 | q8_0 | 6.58 (baseline) | healthy |
| q8_0 | turbo4 | 6.64 (+1.0%) | healthy |
| q8_0 | turbo3 | 6.71 (+2.0%) | healthy |
| q8_0 | turbo2 | 6.91 (+5.1%) | healthy |
| turbo4 | turbo4 | 218 | **CATASTROPHIC** |
| turbo3 | turbo3 | 3,556 | **CATASTROPHIC** |

Same total bits, **500x PPL difference** depending on which side you compress.

**Paper recommendation:** "Compress V maximally, spend bits on K."

#### 6.14 Asymmetric KV — Known Bugs & Headroom

**Bug #47: q8_0-K + turbo3-V → corrupt output on head_dim=256 models**
- Every validated asymmetric test used head_dim=128
- Qwen3.5-122B (head_dim=256): outputs literal `?` characters at full speed
- **Qwen3.6-27B also has head_dim=256** ← affects our Chair
- turbo4-V path may be fine (Reddit user reports q8_0/turbo4 working on Qwen3.5-35B-A3B, head_dim=256)

**Bug #54: Symmetric turbo3 catastrophic on GQA ≥6:1**
- Qwen2.5-7B (GQA 7:1): turbo3/turbo3 PPL = 2,887
- **Fix merged (#115):** auto-asymmetric upgrade — K silently upgraded to q8_0 when GQA ≥6:1
- Opt-out via `TURBO_AUTO_ASYMMETRIC=0`
- **Qwen3.6-27B: GQA = 24/4 = 6:1** ← right at the threshold

#### 6.15 Asymmetric KV — VRAM Reality for Chair at 130K

| Config | K cache | V cache | Total KV | + weights | Fits 24GB? |
|---|---|---|---|---|---|
| q8_0 / turbo4 | 8.5 GB | 1.1 GB | 9.6 GB | 26.4 GB | **❌ No** |
| q8_0 / turbo3 | 8.5 GB | 0.85 GB | 9.4 GB | 26.2 GB | **❌ No** |
| turbo4 / turbo4 | 1.1 GB | 1.1 GB | 2.1 GB | 18.9 GB | ✅ |
| turbo3 / turbo4 | 0.85 GB | 1.1 GB | 1.95 GB | 18.75 GB | ✅ |
| turbo4 / turbo3 | 1.1 GB | 0.85 GB | 1.95 GB | 18.75 GB | ✅ |

**q8_0/turbo4 is the quality king but needs 26.4 GB.** Doesn't fit on RTX 3090 at 130K.

**At lower context (80K):**

| Config | Total KV | + weights | Fits 24GB? |
|---|---|---|---|
| q8_0 / turbo4 @ 80K | 5.9 GB | 22.7 GB | ✅ |
| turbo4 / turbo4 @ 80K | 1.3 GB | 18.1 GB | ✅ |

#### 6.16 Revised Phase 1 Strategy (with asymmetric findings)

**Configurations to test on Chair (Qwen3.6-27B, head_dim=256, GQA 6:1):**

| Priority | Config | Context | VRAM | Rationale |
|---|---|---|---|---|
| **1** | `turbo4/turbo4` | 130K | 18.9 GB | Baseline — fits, quality unknown for head_dim=256 |
| **2** | `q8_0/turbo4` | 80K | 22.7 GB | Quality king — if 80K context is acceptable |
| **3** | `turbo3/turbo4` | 130K | 18.75 GB | Asymmetric TCQ — saves 0.15 GB, quality unknown |
| **4** | `q8_0/turbo3` | 80K | 22.5 GB | Max compression V — if 80K context is acceptable |

**Test procedure (after build):**

```bash
# 1. Baseline — does symmetric turbo4 work on head_dim=256?
llama-perplexity -m chair.gguf -ctk turbo4 -ctv turbo4 -ngl 99 -fa -c 8192

# 2. Compare with q8_0 baseline
llama-perplexity -m chair.gguf -ctk q8_0 -ctv q8_0 -ngl 99 -fa -c 8192

# 3. If turbo4/turbo4 PPL is within 5% of q8_0 → use at 130K
#    If turbo4/turbo4 PPL is degraded → test q8_0/turbo4 at 80K
llama-server -m chair.gguf -ctk q8_0 -ctv turbo4 -ngl 99 -fa -c 81920

# 4. Disable auto-asymmetric to control behavior explicitly
export TURBO_AUTO_ASYMMETRIC=0
```

**Auto-asymmetric caveat:** If `TURBO_AUTO_ASYMMETRIC=1` (default) and GQA ≥6:1, the server will silently upgrade K to q8_0. For Chair at 130K this means `turbo4/turbo4` → `q8_0/turbo4` → 26.4 GB → **OOM**. Set `TURBO_AUTO_ASYMMETRIC=0` to prevent this at 130K.
