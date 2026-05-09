# Chief Station — Local LLM Workstation Reference

> Complete inventory of all settings, configurations, and tooling for the local LLM agent stack.
> Last updated: 2025-05-06

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Llama Server (llama-cpp-turboquant)](#llama-server-llama-cpp-turboquant)
- [Pi Agent](#pi-agent)
  - [Settings](#settings)
  - [Config](#config)
  - [Models](#models)
  - [Skills](#skills)
  - [Extensions](#extensions)
- [SearXNG](#searxng)
- [Web Search Extension](#web-search-extension)
- [Port Map](#port-map)
- [Startup Commands](#startup-commands)
- [Known Limitations](#known-limitations)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Pi Agent (TUI)                    │
│  Port: interactive (no fixed port)                   │
│  Transport: SSE                                      │
│  Default: llama-cpp-turboquant / qwen3.6-27B-Q4     │
├─────────────────────────────────────────────────────┤
│  Tools: read | write | edit | bash | web_search      │
├─────────────────────────────────────────────────────┴──┬───┐
│                                                        │   │
│                    Local Services                       │   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │ llama-server │  │  SearXNG     │  │  (future)    │  │   │
│  │ :8001        │  │  :8080       │  │              │  │   │
│  │ llama-cpp    │  │  Python/WSGI │  │              │  │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  ┌──────────────┐                                       │   │
│  │ llama-server │                                       │   │
│  │ :8002        │                                       │   │
│  │ turboquant   │                                       │   │
│  └──────────────┘                                       │   │
└────────────────────────────────────────────────────────┘   │
                                                             │
              External APIs (OpenAI-compatible)               │
              ┌──────────────┐                                │
              │  Anthropic   │                                │
              │  Google      │                                │
              │  OpenAI      │                                │
              │  Mistral     │                                │
              └──────────────┘                                │
```

---

## Llama Server (llama-cpp-turboquant)

**Binary:** `/home/chief/llama-cpp-turboquant/build/bin/llama-server`

### Active Instance (Port 8002)

```bash
llama-server \
  --host 127.0.0.1 \
  --port 8002 \
  --model /home/chief/models/Qwen3.6-27B/Qwen3.6-27B-UD-Q4_K_XL.gguf \
  --alias qwen3.6-27B-Q4-turbo \
  --jinja \
  --chat-template-kwargs '{"preserve_thinking":true}' \
  --ctx-size 131072 \
  --fit on \
  --fit-target 2048 \
  --flash-attn on \
  --no-mmap \
  --mlock \
  --cont-batching \
  -np 1 \
  -b 1024 \
  -ub 512 \
  --threads 16 \
  --threads-batch 16 \
  --ctx-checkpoints 16 \
  --checkpoint-every-n-tokens 8192 \
  --cache-reuse 1024 \
  --temp 0.6 \
  --top-p 0.95 \
  --top-k 20 \
  --min-p 0.05 \
  -ctk q8_0 \
  -ctv turbo4 \
  --presence-penalty 0.0 \
  --repeat-penalty 1.0 \
  --reasoning on \
  --reasoning-budget 16384 \
  --spec-type ngram-mod \
  --spec-ngram-size-n 16 \
  --draft-min 4 \
  --draft-max 16
```

### Parameter Reference

| Category | Parameter | Value | Purpose |
|---|---|---|---|
| **Network** | `--host` | `127.0.0.1` | Local-only binding |
| | `--port` | `8002` | Turboquant instance port |
| **Model** | `--model` | `Qwen3.6-27B-UD-Q4_K_XL.gguf` | 27B parameter, Q4 quantization |
| | `--alias` | `qwen3.6-27B-Q4-turbo` | Model ID for API |
| **Chat** | `--jinja` | *(set)* | Jinja2 chat template |
| | `--chat-template-kwargs` | `{"preserve_thinking":true}` | Preserve reasoning tags |
| **Context** | `--ctx-size` | `131072` | 128K context window |
| | `--fit on` | *(set)* | Auto-fit context to available memory |
| | `--fit-target` | `2048` | Target tokens to reserve for output |
| **Acceleration** | `--flash-attn on` | *(set)* | Flash attention for faster inference |
| | `--no-mmap` | *(set)* | Disable memory-mapped file I/O |
| | `--mlock` | *(set)* | Lock model in RAM (prevent swap) |
| | `--cont-batching` | *(set)* | Continuous batching for throughput |
| **Batching** | `-np` | `1` | Number of pipelines |
| | `-b` | `1024` | Batch size |
| | `-ub` | `512` | Unified batch size |
| **Threading** | `--threads` | `16` | Inference threads |
| | `--threads-batch` | `16` | Batch processing threads |
| **Checkpoints** | `--ctx-checkpoints` | `16` | Number of context checkpoints |
| | `--checkpoint-every-n-tokens` | `8192` | Checkpoint interval |
| | `--cache-reuse` | `1024` | KV cache reuse threshold |
| **Sampling** | `--temp` | `0.6` | Temperature (lower = more deterministic) |
| | `--top-p` | `0.95` | Nucleus sampling threshold |
| | `--top-k` | `20` | Top-k sampling |
| | `--min-p` | `0.05` | Minimum probability threshold |
| **KV Cache** | `-ctk` | `q8_0` | Key cache quantization |
| | `-ctv` | `turbo4` | Value cache quantization (turboquant) |
| **Penalties** | `--presence-penalty` | `0.0` | No presence penalty |
| | `--repeat-penalty` | `1.0` | No repetition penalty |
| **Reasoning** | `--reasoning on` | *(set)* | Enable chain-of-thought reasoning |
| | `--reasoning-budget` | `16384` | Max reasoning tokens |
| **Speculative** | `--spec-type` | `ngram-mod` | N-gram speculative decoding |
| | `--spec-ngram-size-n` | `16` | N-gram size |
| | `--draft-min` | `4` | Min draft tokens |
| | `--draft-max` | `16` | Max draft tokens |

### Secondary Instance (Port 8001)

Standard llama-cpp (non-turboquant) for comparison/fallback.

| Parameter | Value |
|---|---|
| `--host` | `127.0.0.1` |
| `--port` | `8001` |
| API | `openai-completions` |
| Compat | `thinkingFormat: qwen-chat-template` |

---

## Pi Agent

**Version:** 0.73.0+
**Binary:** `/home/chief/.nvm/versions/node/v24.15.0/bin/pi`
**Package:** `@mariozechner/pi-coding-agent`

### Settings

**File:** `~/.pi/agent/settings.json`

```json
{
  "lastChangelogVersion": "0.73.0",
  "defaultProvider": "llama-cpp-turboquant",
  "defaultModel": "qwen3.6-27B-Q4-turbo",
  "piCacheRetention": "long",
  "defaultThinkingLevel": "medium",
  "compaction": {
    "enabled": true
  },
  "autocompleteMaxVisible": 15,
  "enableInstallTelemetry": false,
  "transport": "sse",
  "treeFilterMode": "default"
}
```

| Setting | Value | Purpose |
|---|---|---|
| `defaultProvider` | `llama-cpp-turboquant` | Primary inference backend |
| `defaultModel` | `qwen3.6-27B-Q4-turbo` | Default model for new sessions |
| `piCacheRetention` | `long` | Extended session cache lifetime |
| `defaultThinkingLevel` | `medium` | Default reasoning depth |
| `compaction.enabled` | `true` | Automatic context compaction |
| `autocompleteMaxVisible` | `15` | Max autocomplete suggestions |
| `enableInstallTelemetry` | `false` | No telemetry |
| `transport` | `sse` | Server-Sent Events for streaming |
| `treeFilterMode` | `default` | File tree filtering mode |

### Config

**File:** `~/.pi/agent/config/settings.json`

```json
{
  "reserveTokens": 8192
}
```

| Setting | Value | Purpose |
|---|---|---|
| `reserveTokens` | `8192` | Tokens reserved for tool output / response |

### Models

**File:** `~/.pi/agent/models.json`

#### Provider: `llama-cpp-turboquant` (Primary)

| Model ID | Name | Context | Max Output | Reasoning |
|---|---|---|---|---|
| `qwen3.6-35b-turbo` | qwen3.6-35b-turbo | 192K | 16K | Yes |
| `qwen3.6-27B-Q5-turbo` | qwen3.6-27B-Q5-turbo | 120K | 32K | Yes |
| `qwen3.6-27B-Q4-turbo` | qwen3.6-27B-Q4-turbo | 131K | 32K | Yes |

**Endpoint:** `http://127.0.0.1:8002` (OpenAI-compatible)

#### Provider: `llama-cpp` (Secondary)

| Model ID | Name | Context | Max Output | Reasoning |
|---|---|---|---|---|
| `qwen3.6-35b-a3b` | qwen3.6-35b-a3b | 149K | 16K | Yes |
| `qwen3.6-27B-Q4` | qwen3.6-27B-Q4 | 66K | 16K | Yes |

**Endpoint:** `http://127.0.0.1:8001` (OpenAI-compatible)

**Compat settings (llama-cpp):**
- `thinkingFormat`: `qwen-chat-template`
- `supportsDeveloperRole`: `false`
- `supportsReasoningEffort`: `false`

### Skills

| Skill | Path | Purpose |
|---|---|---|
| `kungos` | `~/.pi/agent/skills/kungos/` | KungOS project modernization tasks |
| `kungos-review` | `~/.pi/agent/skills/kungos-review/` | KungOS status, metrics, phase tracking |
| `session-memory` | `~/.pi/agent/skills/session-memory/` | Cross-session MEMORY.md persistence |

### Extensions

**Directory:** `~/.pi/agent/extensions/`

| Extension | File | Purpose |
|---|---|---|
| `web_search` | `web-search.ts` | SearXNG-backed web search tool |

**Dependencies:** `typebox@^1.1.38`

### AGENTS.md (System Prompt Override)

**File:** `~/.pi/agent/AGENTS.md`

```markdown
- Make one tool call at a time and wait for results. Do not batch multiple tool calls in a single response.
```

Additional guidance:
- `web_search` for discovery (finding URLs/resources)
- `curl`/`wget` for fetching (known URLs)
- Prefer 1-3 focused queries over broad queries
- Target engines when useful (see [Web Search Extension](#web-search-extension))
- Cite source URLs in responses

---

## SearXNG

**Version:** 2026.5.6+330d56bba
**Config:** `/home/chief/searxng/settings.yml`
**Source:** `/home/chief/searxng/instance/searxng-src/`
**Runtime:** Python 3.12 + Granian (WSGI, 1 worker)

### Startup Command

```bash
cd /home/chief/searxng/instance && \
  ./searx-pyenv/bin/granian \
    searx.webapp:app \
    --interface wsgi \
    --host 127.0.0.1 \
    --port 8080 \
    --workers 1
```

### Server Configuration

| Setting | Value | Purpose |
|---|---|---|
| `bind_address` | `127.0.0.1` | Local-only |
| `port` | `8080` | HTTP API port |
| `limiter` | `false` | No rate limiting (local use) |
| `image_proxy` | `false` | No image proxying |
| `method` | `GET` | GET-based search API |

### Search Configuration

| Setting | Value | Purpose |
|---|---|---|
| `safe_search` | `0` | Disabled |
| `autocomplete` | `""` | No autocomplete |
| `formats` | `["json"]` | JSON-only output |

### Outgoing (Performance)

| Setting | Value | Purpose |
|---|---|---|
| `request_timeout` | `3.0s` | Default per-engine timeout |
| `max_request_timeout` | `10.0s` | Hard timeout ceiling |
| `pool_connections` | `100` | Total connection pool |
| `pool_maxsize` | `20` | Max concurrent connections |
| `enable_http2` | `true` | HTTP/2 for faster responses |

### Per-Engine Timeouts

| Engine | Timeout | Reason |
|---|---|---|
| `brave` | 4.0s | Slower than average |
| `github` | 3.0s | P95 response ~0.9s |
| `stackoverflow` | 3.0s | P95 response ~0.8s |
| `reddit` | 3.0s | Variable response times |

### Enabled Engines (keep_only)

| Category | Engines |
|---|---|
| **General** | google, duckduckgo, brave |
| **Code & Repos** | github, huggingface, huggingface datasets, huggingface spaces, ollama |
| **Q&A** | stackoverflow, reddit |
| **Reference** | wikipedia, wikidata |
| **Packages** | pypi, docker hub, npm |
| **Documentation** | mdn, mankier, arch linux wiki |
| **Tech News** | hackernews |

### Disabled / Excluded Engines

| Engine | Reason |
|---|---|
| `github_code` | Requires GitHub auth token (65% reliability without it) |
| All other defaults | Not in `keep_only` list |

### Plugins

| Plugin | Status |
|---|---|
| `tracker_url_remover` | Active — strips UTM/tracking params |

### API Usage

```
GET /search?q=QUERY&format=json&engines=COMMA,SEPARATED&language=en&safesearch=0
```

---

## Web Search Extension

**File:** `~/.pi/agent/extensions/web-search.ts`

### Tool Definition

| Field | Value |
|---|---|
| **Name** | `web_search` |
| **Label** | Web Search |
| **Parameters** | `queries[]`, `engines?`, `max_results?` |
| **Max queries** | 5 |
| **Max results/query** | 10 (default 5) |

### Query Rewriting

| Target | Behavior |
|---|---|
| `github_code` only | Strips noise: `github`, `issue`, `discussion`, `stackoverflow`, `reddit`, `help`, `tutorial`, `docs`, `example`, etc. |
| General (any other targeted) | Normalizes: `github_code` → `github`, `source code` → `github`, `repo code` → `github` |
| No engines specified | Whitespace normalization only |
| Mixed engines | General normalization (conservative) |

### Fallback Logic

When **all** targeted engines return 0 results (no errors):
1. Retry each query against **all enabled engines** (no engine filter)
2. Use **original query** (no rewriting) — general engines benefit from full context
3. Mark results with `fallback: true` in output
4. Clear any previous `error` flags on successful fallback

### Output Format

```
Query: original query text
Rewritten: rewritten query text          (only if rewritten)
Error: error message                      (only if error)
Targeted engines returned no results — fell back to all engines.  (only if fallback)
1. Result Title
URL: https://...
Engine: google
Snippet: ...
```

### Prompt Guidelines (as seen by the agent)

> Use this tool for discovery — finding information, URLs, or resources you don't already know.
> Use curl/wget only for fetching — getting content from URLs you already know.
> Typical workflow: web_search to find URLs, then curl to fetch full content.
> Prefer 1 to 3 focused queries over one broad query.
> Target engines when useful: pypi for Python packages, npm for Node packages, docker hub for containers, mdn for web docs. Avoid targeting github/stackoverflow directly; the tool can fall back to all engines.
> Cite source URLs in the response.

---

## Port Map

| Port | Service | Protocol | Binding |
|---|---|---|---|
| `8001` | llama-server (standard llama-cpp) | HTTP/OpenAI API | 127.0.0.1 |
| `8002` | llama-server (turboquant) | HTTP/OpenAI API | 127.0.0.1 |
| `8080` | SearXNG | HTTP/JSON | 127.0.0.1 |
| *(dynamic)* | Pi Agent TUI | SSE (internal) | N/A |

---

## Startup Commands

### Full Stack Startup

```bash
# 1. Llama server (turboquant, port 8002)
/home/chief/llama-cpp-turboquant/build/bin/llama-server \
  --host 127.0.0.1 --port 8002 \
  --model /home/chief/models/Qwen3.6-27B/Qwen3.6-27B-UD-Q4_K_XL.gguf \
  --alias qwen3.6-27B-Q4-turbo \
  --jinja \
  --chat-template-kwargs '{"preserve_thinking":true}' \
  --ctx-size 131072 \
  --fit on --fit-target 2048 \
  --flash-attn on \
  --no-mmap --mlock \
  --cont-batching \
  -np 1 -b 1024 -ub 512 \
  --threads 16 --threads-batch 16 \
  --ctx-checkpoints 16 \
  --checkpoint-every-n-tokens 8192 \
  --cache-reuse 1024 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.05 \
  -ctk q8_0 -ctv turbo4 \
  --presence-penalty 0.0 --repeat-penalty 1.0 \
  --reasoning on --reasoning-budget 16384 \
  --spec-type ngram-mod --spec-ngram-size-n 16 \
  --draft-min 4 --draft-max 16

# 2. SearXNG
cd /home/chief/searxng/instance && \
  ./searx-pyenv/bin/granian \
    searx.webapp:app \
    --interface wsgi \
    --host 127.0.0.1 \
    --port 8080 \
    --workers 1

# 3. Pi Agent
pi
```

### Health Checks

```bash
# Llama server
curl -s http://127.0.0.1:8002/v1/models | python3 -m json.tool

# SearXNG
curl -s "http://127.0.0.1:8080/search?q=test&format=json" | python3 -c \
  "import sys,json; d=json.loads(sys.stdin.read()); print(f'OK - {len(d.get(\"results\",[]))} results')"
```

---

## Known Limitations

| Issue | Status | Workaround |
|---|---|---|
| `github_code` engine unreliable (65%) | Requires GitHub auth token | Use `github` engine (repo search) + Google fallback |
| `github` engine searches repos only | By design | Issues/discussions found via Google/DuckDuckGo |
| `stackoverflow` often returns 0 for niche queries | By design | Fallback to all engines handles this |
| SearXNG not systemd-managed | Manual startup via nohup | Consider creating a systemd user service |
| Llama server not systemd-managed | Manual startup | Consider creating a systemd user service |
| No GitHub token configured | `github_code` needs `ghc_auth` | Add token to SearXNG `settings.yml` engines section |

---

## File Locations

| Component | Path |
|---|---|
| **Pi settings** | `~/.pi/agent/settings.json` |
| **Pi config** | `~/.pi/agent/config/settings.json` |
| **Pi models** | `~/.pi/agent/models.json` |
| **Pi skills** | `~/.pi/agent/skills/` |
| **Pi extensions** | `~/.pi/agent/extensions/` |
| **Pi AGENTS.md** | `~/.pi/agent/AGENTS.md` |
| **SearXNG config** | `/home/chief/searxng/settings.yml` |
| **SearXNG source** | `/home/chief/searxng/instance/searxng-src/` |
| **SearXNG venv** | `/home/chief/searxng/instance/searx-pyenv/` |
| **llama-cpp-turboquant** | `/home/chief/llama-cpp-turboquant/` |
| **llama-cpp (standard)** | `/home/chief/llama.cpp/` |
| **Models** | `/home/chief/models/` |
| **LLM Wiki** | `/home/chief/llm-wiki/` |
