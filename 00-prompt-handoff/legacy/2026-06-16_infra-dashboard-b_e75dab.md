# Infra Dashboard for VK Frontend — Option B

**Date:** 2026-06-16
**Entity:** `infra-dashboard-b`
**Entity Type:** `work_item`
**Status:** `done`
**Project:** `super-council`

---

## Goal

Add an `/infra` dashboard page to the VK frontend showing real-time health, latency, and status of all Council infrastructure services. Single aggregated backend endpoint, full dashboard frontend page.

---

## Services to Monitor

| Tier | Service | Port | Probe Method | Key Metrics |
|------|---------|------|--------------|-------------|
| Critical | Council API | 8000 | self | PID, uptime |
| Critical | PostgreSQL | 5432 | psycopg2 (reuse) | connected, latency, outbox |
| Critical | ARC LLM | 18095 | HTTP + psutil CPU% | reachable, model, latency, ⚠️>80% |
| Supporting | Memory Service | 18097 | process + consolidation mtime | running, last consolidation |
| Supporting | Milvus | 19530 | HTTP (not pymilvus) | connected, chunk count |
| Supporting | MongoDB | 27017 | TCP connect | alive, latency |
| Supporting | Embeddings | 18099 | HTTP only | container health, latency |
| Supporting | Qwen s2s | 8091 | HTTP `/v1/models` | reachable, model, latency |

**Removed vs original:** AppFlowy (not in use), Docker probe (HTTP suffices), pymilvus/pymongo heavy imports (HTTP/TCP only)

---

## Implementation Units

### Unit 1: Backend — `/v1/infra/status` endpoint

**Files:** `super_council/api/infra_status.py` (new), `super_council/server.py` (modify)

**What it does:**
- Single GET endpoint that probes all 9 services with 5s timeout each
- Returns aggregated JSON with status, latency, and service-specific details
- Runs probes concurrently (asyncio.gather) for ~5s total wall time

**Response shape:**
```json
{
  "timestamp": "2026-06-16T...",
  "overall": "ok|degraded|error",
  "services": {
    "council_api": {
      "status": "ok",
      "pid": 10868,
      "uptime_seconds": 3600
    },
    "arc_llm": {
      "status": "ok",
      "port": 18095,
      "model": "LFM2.5-8B-Q4_K_XL",
      "latency_ms": 45,
      "cpu_percent": 23.5
    },
    "qwen_s2s": {
      "status": "ok",
      "port": 8091,
      "model": "qwen-160k-UD-fast",
      "latency_ms": 120
    },
    "memory_service": {
      "status": "ok",
      "pid": 2140,
      "consolidation": {
        "daily": "ok",
        "short": "overdue",
        "weekly": "ok",
        "bimonthly": "ok"
      }
    },
    "embedding_service": {
      "status": "ok",
      "port": 18099,
      "container_name": "magical_goldberg",
      "latency_ms": 12
    },
    "milvus": {
      "status": "ok",
      "port": 19530,
      "collections": 1,
      "chunk_count": 2095
    },
    "mongodb": {
      "status": "ok",
      "port": 27017,
      "latency_ms": 2
    },
    "postgresql": {
      "status": "ok",
      "port": 5432,
      "latency_ms": 1.8,
      "outbox_pending": 14
    },
    "appflowy": {
      "status": "ok",
      "port": 8080,
      "latency_ms": 30
    }
  }
}
```

**Probe details per service:**

```python
# ARC LLM + Qwen s2s: HTTP GET /v1/models with timing
async def probe_llm(port: int, label: str) -> dict:
    start = time.monotonic()
    resp = await httpx.AsyncClient(timeout=5).get(f"http://127.0.0.1:{port}/v1/models")
    latency = round((time.monotonic() - start) * 1000, 1)
    models = resp.json()["data"]
    cpu = psutil.Process(pid).cpu_percent()  # if pid found
    return {"status": "ok", "model": models[0]["id"], "latency_ms": latency, "cpu_percent": cpu}

# Memory service: process check + read consolidation state from files
async def probe_memory_service() -> dict:
    # Check if process is running
    pid = find_pid_by_port(18097)
    # Read consolidation metrics from ~/.council-memory/
    # Parse last consolidation timestamps
    return {"status": "ok" if pid else "error", "consolidation": {...}}

# Embedding service: Docker + HTTP
async def probe_embedding() -> dict:
    # Docker: docker ps --filter publish=18099
    # HTTP: GET http://127.0.0.1:18099/
    return {"status": ..., "container_name": ...}

# Milvus: pymilvus connection
async def probe_milvus() -> dict:
    from pymilvus import connections, utility
    connections.connect(host="127.0.0.1", port=19530)
    collections = utility.list_collections()
    # Count entities in each collection
    return {"status": "ok", "collections": len(collections), "chunk_count": ...}

# MongoDB: pymongo ping
async def probe_mongodb() -> dict:
    client = pymongo.MongoClient("localhost", 27017, serverSelectionTimeoutMS=5000)
    latency = (await client.admin.command("ping")).get("ok")
    return {"status": "ok", "latency_ms": ...}

# PostgreSQL: reuse existing logic from /health
# AppFlowy: reuse existing logic from /health
```

**Concurrent execution:**
```python
results = await asyncio.gather(
    probe_council_api(),
    probe_llm(18095, "arc"),
    probe_llm(8091, "qwen"),
    probe_memory_service(),
    probe_embedding(),
    probe_milvus(),
    probe_mongodb(),
    probe_postgresql(),
    probe_appflowy(),
    return_exceptions=True,
)
```

**Edge cases:**
- Each probe wrapped in try/except with 5s timeout → returns `{"status": "error", "error": "..."}`
- `overall` = "error" if council_api or postgresql is down
- `overall` = "degraded" if any non-critical service is down (embeddings, appflowy)
- `overall` = "ok" if all green

---

### Unit 2: Frontend — InfraDashboard page

**Files:**
- `frontend/packages/web-core/src/pages/infra/InfraDashboard.tsx` (new)
- `frontend/packages/local-web/src/routes/infra.tsx` (new route)
- `frontend/packages/web-core/src/shared/hooks/council/useInfraStatus.ts` (new hook)
- `frontend/packages/web-core/src/shared/hooks/council/index.ts` (modify — export)

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  Infrastructure Dashboard                    [↻ Refresh]     │
│                                                              │
│  Overall: ● OK  (updated 2s ago, auto-refresh 30s)           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Service           Status  Latency    Details            │  │
│  ├────────────────────────────────────────────────────────┤  │
│  │ Council API       ● ok    —          PID 10868         │  │
│  │ ARC LLM           ● ok    45ms       LFM2.5-8B 23% CPU │  │
│  │ Qwen s2s          ● ok    120ms      qwen-160k-UD-fast │  │
│  │ Memory Service    ● ok    —          daily:ok           │  │
│  │                               short:⚠️ OVERDUE          │  │
│  │ Embeddings        ● ok    12ms       magical_goldberg   │  │
│  │ Milvus            ● ok    —          1 coll, 2095 chunks│  │
│  │ MongoDB           ● ok    2ms        connected          │  │
│  │ PostgreSQL        ● ok    1.8ms      outbox: 14 pending │  │
│  │ AppFlowy          ● ok    30ms       connected          │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  [📋 Live Logs]  [🔄 Restart ARC LLM]                       │
└──────────────────────────────────────────────────────────────┘
```

**Component structure:**
```tsx
<InfraDashboard>
  <StatusHeader overall={status} lastUpdated={ts} onRefresh={refresh} />
  <ServiceTable services={services} />
  <ActionBar onShowLogs={toggleLogs} onRestartArc={restartArc} />
  {showLogs && <LogPanel streamUrl="/v1/logs/stream" />}
</InfraDashboard>
```

**Hook:**
```typescript
export function useInfraStatus(refreshMs = 30000) {
  // Polls GET /v1/infra/status every refreshMs
  // Returns { data, isLoading, error, lastUpdated, refresh }
  // Auto-refresh with interval, manual refresh button
}
```

**Status indicators:**
- `ok` → green dot (`bg-green-500`)
- `degraded` → yellow dot (`bg-yellow-500`)
- `error` → red dot (`bg-red-500`)
- `overdue` → yellow warning icon for consolidation tiers

---

### Unit 3: Sidebar navigation + wire-up

**Files:** `frontend/packages/local-web/src/routes/_app.tsx` (modify)

**Changes:**
- Add "Infra" nav item to sidebar (below Memory, above projects)
- Icon: `MonitorIcon` or `GlobeIcon` from phosphor-icons
- Route: `/infra`

```tsx
<button onClick={() => navigate({ to: '/infra' })}>
  <MonitorIcon className="h-4 w-4" weight="fill" />
  Infra
</button>
```

---

## Constraints

- No schema changes
- No changes to existing `/health` or `/v1/council/status` endpoints
- All probes must timeout after 5s — never block the API
- Frontend must handle partial failures (some services down, page still renders)
- Auto-refresh interval configurable (default 30s)

## Success Criteria

1. `GET /v1/infra/status` returns all 9 services with status + latency
2. `/infra` page renders with service table, status dots, auto-refresh
3. Consolidation OVERDUE warnings visible (short tier)
4. Live logs panel accessible from the page
5. Restart ARC LLM button functional

## Dependencies

- `httpx` (installed) — HTTP probes
- `psutil` (installed) — process/CPU info
- `pymongo` (installed) — MongoDB ping
- `pymilvus` (installed) — Milvus collections
- `psycopg2` (installed) — PostgreSQL (reuse existing)

## Estimated Effort

| Unit | Estimated | Actual |
|------|-----------|--------|
| Unit 1: Backend endpoint | 45 min | 30 min |
| Unit 2: Frontend page + hook | 45 min | 35 min |
| Unit 3: Sidebar nav | 10 min | 5 min |
| **Total** | **~1.5 hours** | **~1 hour** |

---

## Caveats

1. **Memory service consolidation metrics** — no HTTP endpoint exists. Need to either:
   - Parse `~/.council-memory/` files directly (fragile)
   - Or add a lightweight `/health` endpoint to the memory service itself (better, but requires memory service changes)
   - **Recommendation:** Parse files for now, add memory service health endpoint later

2. **Docker probing** — `docker ps` requires docker socket access. If the API runs as non-root, this might fail. Fallback: just HTTP probe port 18099.

3. **Milvus connection** — pymilvus may block on connect if Milvus is down. Need async wrapper with timeout.

4. **Concurrent probes** — 9 services × 5s timeout = could spike CPU. Consider sequential probes for heavy ones (Milvus, MongoDB) and parallel for HTTP ones.

5. **Restart ARC LLM button** — already exists at `POST /v1/council/restart`. Just needs frontend wiring.
