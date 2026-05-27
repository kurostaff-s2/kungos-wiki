# Pipeline API

> REST endpoints for the super-council supervisor.

## Base URL

```
http://127.0.0.1:8090
```

## Health & Status

### GET /health

```json
{
  "ok": true,
  "supported_features": ["function_calling", "tool_use", "delegation", "fanout", "allowed_tools"]
}
```

### GET /status

```json
{
  "start_time": "2026-05-22T12:00:00Z",
  "total_requests": 1234,
  "cache_hits": 800,
  "cache_misses": 434,
  "swaps": 50,
  "restores": 45,
  "saves": 50,
  "errors": 2,
  "uptime_seconds": 3600,
  "cache_hit_rate": 0.65,
  "current_alias": "qwen3.6-27B-chair",
  "supported_features": {...}
}
```

### GET /metrics

Returns upstream llama-server metrics (token counts, timing, cache stats).

## Chat Completion

### POST /v1/chat/completions

```json
{
  "model": "reviewer-logic",
  "messages": [
    {"role": "system", "content": "You are a reviewer."},
    {"role": "user", "content": "Review this code..."}
  ],
  "max_tokens": 4096,
  "tools": [...]  // optional
}
```

**Response:** OpenAI-compatible chat completion with `choices[0].message.content` or `tool_calls`.

## Delegation

### POST /v1/council/delegate

```json
{
  "alias": "reviewer-logic",
  "task": "Review the code for issues.",
  "timeout": 300,
  "phase": "build",
  "pipeline_id": "pipe-abc123",
  "project_id": "my-project",
  "repo_path": "/path/to/repo",
  "test_command": "pytest tests/ -v",
  "use_worktree": true
}
```

**Response:**
```json
{
  "alias": "reviewer-logic",
  "status": "ok",
  "response": "Reviewer's analysis...",
  "blocked_tool_calls": []
}
```

**Errors:**
- `400` — Missing `alias` or `task`
- `404` — Unknown model alias
- `409` — Delegation already in progress
- `503` — System unstable (swap-back failed)

## Fanout

### POST /v1/council/fanout

```json
{
  "messages": [{"role": "user", "content": "Review this design..."}],
  "max_tokens": 2048,
  "async": true
}
```

**Response (async=true):**
```json
{
  "job_id": "abc123",
  "status": "pending"
}
```

**Response (async=false):**
```json
{
  "mode": "sequential",
  "results": {
    "ministral": {"status": "ok", "body": "..."},
    "nemotron-nano": {"status": "ok", "body": "..."},
    "qwen3-4b": {"status": "ok", "body": "..."}
  },
  "total_time_ms": 9000
}
```

### GET /v1/council/fanout/{job_id}

```json
{
  "job_id": "abc123",
  "status": "completed",
  "created_at": 1234567890,
  "started_at": 1234567891,
  "completed_at": 1234567900,
  "total_time_ms": 9000,
  "results": {...},
  "error": null
}
```

### GET /v1/council/fanout/jobs

List recent jobs (newest first, limit 20). Jobs TTL: 1 hour.

## Delegation Chain

### POST /v1/council/chain

```json
{
  "plan": {
    "chain_id": "auth-refactor",
    "batch_size": 3,
    "coder_alias": "specialist-coder",
    "reviewer_alias": "reviewer-logic",
    "max_retries": 1,
    "steps": [
      {
        "id": 1,
        "description": "Rename AuthService class",
        "files": ["auth/service.py"],
        "validation": "Class name changed, all methods preserved"
      }
    ]
  },
  "context": "Refactor AuthService → SessionManager"
}
```

**Response:**
```json
{
  "status": "completed",
  "chain_id": "auth-refactor",
  "completed_steps": 3,
  "total_steps": 3,
  "elapsed_seconds": 120.5,
  "results": [...]
}
```

**Errors:**
- `422` — Persistent review failure (returns `completed_steps`, `failed_steps`, feedback)

## Pipeline

### POST /v1/council/pipeline

```json
{
  "task": "Implement feature X",
  "project_id": "my-project",
  "pipeline_id": "pipe-abc123"  // optional, auto-generated if missing
}
```

**Response:**
```json
{
  "pipeline_id": "pipe-abc123",
  "phase": "PLAN",
  "status": "running",
  "result": {"ok": true, "plan": "..."},
  "transition": "Transitioned SCOUT → PLAN",
  "terminal": false,
  "remaining_global": 9,
  "remaining_phase": 3,
  "history": [...]
}
```

**Retreat response:**
```json
{
  "pipeline_id": "pipe-abc123",
  "phase": "SCOUT",
  "retreated": true,
  "reason": "Retreated from BUILD to SCOUT (retries exhausted)",
  "remaining_global": 7,
  "remaining_phase": 3
}
```

**Terminal response:**
```json
{
  "pipeline_id": "pipe-abc123",
  "phase": "DONE",
  "status": "done",
  "terminal": true,
  "history": [...]
}
```

## Session Summarization

### POST /v1/council/summarize

```json
{
  "model": "vice-granite",  // optional
  "messages": [...]          // optional: if provided, also runs chat summary
}
```

**Response:**
```json
{
  "session": {
    "status": "ok",
    "message": "Session summarized",
    "summary": "- 12 requests processed\n- 3 delegations..."
  },
  "chat": {
    "status": "ok",
    "message": "Chat summarized",
    "summary": "Topics: auth, API design...",
    "saved_to": "~/.council-memory/chat-summaries/20260522-120000-chair.md"
  }
}
```

## Active Recall

### POST /v1/council/recall

```json
{
  "query": "past solutions for auth module",
  "phase": "GREEN",
  "max_tokens": 512
}
```

**Response:**
```json
{
  "query": "past solutions for auth module",
  "phase": "GREEN",
  "hits": [
    {"text": "...", "score": 0.85, "source": "/path/to/file.md", "phase": "GREEN"}
  ],
  "formatted": "## Recall Hits\n\n1. ...",
  "found": true
}
```

## Memsearch

### POST /v1/council/index

```json
{
  "paths": ["/path/to/artifact.md"]
}
```

**Response:**
```json
{
  "status": 200,
  "indexed": ["/path/to/artifact.md"],
  "failed": []
}
```

### GET /v1/council/memsearch-stats

```json
{
  "available": true,
  "total_chunks": 470,
  "indexed_sources": ["/path/to/file1.md", ...]
}
```

## Restart Hooks

### POST /v1/council/restart

Restart llama-server only.

**Response:**
```json
{
  "status": "ok",
  "message": "Upstream restarted",
  "log": [
    {"phase": "save_slot", "message": "Slot saved", "ok": true, "timestamp": "..."},
    {"phase": "stop_upstream", "message": "Stopped", "ok": true, "timestamp": "..."},
    {"phase": "start_upstream", "message": "Started", "ok": true, "timestamp": "..."},
    {"phase": "wait_health", "message": "Healthy", "ok": true, "timestamp": "..."},
    {"phase": "restore_slot", "message": "Restored", "ok": true, "timestamp": "..."}
  ]
}
```

### POST /v1/council/supervisor-restart

Full process restart via `os.execv`.

**Response:** Same format as `/v1/council/restart`. Process exits after response.
