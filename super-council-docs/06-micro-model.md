# MicroModel Enricher

> Async semantic enrichment engine using pplx-embed-v1-0.6B ONNX INT8 model with heuristic fallback.

## Overview

The `MicroModelEnricher` provides non-blocking semantic enrichment for pipeline artifacts, events, and failures. It operates in two modes:

1. **ONNX mode** (default when model available): Embedding-based nearest-neighbor classification
2. **Heuristic mode** (fallback): TF-IDF keywords, text pattern matching, template summaries

## Model

- **Model:** pplx-embed-v1-0.6B ONNX INT8
- **Location:** `~/models/embedding/pplx-embed-v1-0.6b-int8/`
- **Output:** 1024-dim FP32 pooler_output (mean-pooled sentence embeddings)
- **Max sequence length:** 512 tokens
- **Provider:** CPUExecutionProvider (no GPU required)

## Initialization

```python
from super_council.micro_model import MicroModelEnricher

enricher = MicroModelEnricher(
    store=relational_store,
    model_alias=None,  # Auto-resolve from MICRO_MODEL_DIR env or default path
    max_workers=2,     # ThreadPoolExecutor worker count
)

# Check if model loaded
if enricher._model_available:
    print("ONNX mode active")
else:
    print("Heuristic fallback mode")
```

## Artifact Enrichment

### Synchronous

```python
result = enricher.enrich_artifact(
    artifact_id="art-123",
    run_id="pipe-abc",
    phase="BUILD",
    content='{"code": "def hello(): pass"}',
)
# {
#   "summary": "[BUILD]: {keys: ['code']}… (30 chars, 1 lines)",
#   "tags": ["build", "json-object", "code"],
#   "keywords": ["code", "def", "hello", "pass"]
# }
```

### Asynchronous (Non-Blocking)

```python
future = enricher.enqueue_artifact(
    artifact_id="art-123",
    run_id="pipe-abc",
    phase="BUILD",
    content='...',
)
# Returns concurrent.futures.Future
# Never blocks the calling thread
# Errors logged via _handle_enrichment_error callback
```

### Heuristic Summary Generation

```python
_generate_summary(phase, content)
# JSON objects: "[PHASE]: {keys: ['key1', 'key2']}… (N chars, M lines)"
# JSON arrays:  "[PHASE]: [N items]… (N chars, M lines)"
# Plain text:   "[PHASE]: first 100 chars… (N chars, M lines)"
```

### Tag Generation

```python
_generate_tags(phase, content)
# Phase-based: ["build"]
# Content-type: ["json-object", "json-array", "code", "text", "xml-like"]
# Semantic: ["plan", "diagnostic", "error-report"]
```

### Keyword Extraction

```python
_extract_keywords(content, top_n=8)
# TF-based with stop-word filtering
# Returns: ["keyword1", "keyword2", ...]
```

## Failure Classification

### Known Categories

| Category | Patterns | Base Confidence |
|----------|----------|-----------------|
| `constraint_violation` | integrityerror, unique constraint, foreign key | 0.95 |
| `connection_error` | connectionrefused, connectionreset, network is unreachable | 0.9 |
| `syntax_error` | syntaxerror, invalid syntax, unexpected indent | 0.9 |
| `type_error` | typeerror, attributeerror, keyerror, indexerror | 0.85 |
| `resource_exhaustion` | memoryerror, disk full, no space left | 0.8 |
| `permission_error` | permissionerror, access denied, errno 13 | 0.85 |
| `timeout` | timeouterror, timed out, deadline exceeded | 0.85 |
| `import_error` | modulenotfounderror, importerror, no module named | 0.9 |
| `assertion_failure` | assertionerror, assert failed | 0.85 |
| `runtime_error` | recursionerror, overflowerror, zerodivisionerror | 0.7 |

### Classification Flow

```
1. Try embedding-based nearest-neighbor (if model available)
2. If similarity > 0.3 → return embedding result
3. Fallback to pattern matching
4. Return (failure_type, confidence)
```

### Usage

```python
result = enricher.enrich_failure(
    run_id="pipe-abc",
    error="IntegrityError: UNIQUE constraint failed",
)
# {
#   "failure_type": "constraint_violation",
#   "confidence": 0.95
# }
```

## Event Window Summarization

```python
events = [
    {"event_type": "transition", "severity": "info", "message": "SCOUT -> PLAN", "occurred_at": "2024-01-01T00:00:00Z"},
    {"event_type": "transition", "severity": "error", "message": "BUILD failed", "occurred_at": "2024-01-01T00:02:00Z"},
]

result = enricher.enrich_event_window(run_id="pipe-abc", events=events)
# {
#   "summary": "2 events total; 2 transitions; 1 errors; span 2024-01-01T00:00:00Z → 2024-01-01T00:02:00Z."
# }
```

## Full-Text Indexing Decision

```python
enricher.should_index_full_text(content)
# Returns True if:
#   len(content) >= 50
#   AND meaningful words (after stop-word removal) >= 5
```

## MCP-Facing Methods

### summarize_artifact

```python
summary = enricher.summarize_artifact(artifact_id="art-123")
# Returns stored summary or generates on-demand
```

### classify_failure

```python
result = enricher.classify_failure(run_id="pipe-abc", error="...")
# Classifies error, optionally looking up latest error for run
```

## Lifecycle

```python
enricher.shutdown(wait=True, timeout=5.0)
# Gracefully shuts down ThreadPoolExecutor
# Called on supervisor cleanup()
```

## Database Schema

```sql
artifact_summaries (
    artifact_id TEXT PRIMARY KEY REFERENCES artifacts(artifact_id),
    summary TEXT,
    tags TEXT,           -- JSON array
    keywords TEXT,       -- JSON array
    created_at TEXT
)

failure_classifications (
    classification_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES workflow_runs(run_id),
    error TEXT,
    failure_type TEXT,
    confidence REAL,
    created_at TEXT
)

event_window_summaries (
    summary_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES workflow_runs(run_id),
    event_start TEXT,
    event_end TEXT,
    summary TEXT,
    created_at TEXT
)
```

## Integration Points

- **Pipeline completion:** `_enqueue_artifact_enrichment()` called after each successful phase
- **Phase failure:** `_enqueue_failure_enrichment()` called on phase failure
- **Context handoff:** Enrichment data included in `ContextRouter.get_run_snapshot()`
- **MCP tools:** `summarize_artifact`, `classify_failure` exposed via MCP server
