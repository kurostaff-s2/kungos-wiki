# Phase 1: Start pplx Embedding Server on :18099

**Parent plan:** `04-06-2026_embedding-consolidation-pplx_6b297d.md`
**Phase:** 1 of 6
**Dependencies:** None (can start immediately)
**Estimated effort:** ~30 min

---

## Project Context

**Project root:** `/home/chief/models/embedding/pplx-embed-v1-0.6b-int8/`
**Key files for this phase:**
- `server.py` — existing HTTP server, needs port change + health endpoint
- `model_quantized.onnx` — ONNX INT8 model (614 KB + 706 MB data)
- `config.json` — model config (1024d, 32K ctx, bidirectional)

---

## What This Phase Delivers

The pplx embedding server running on port 18099, serving OpenAI-compatible `/v1/embeddings` and `/v1/models` endpoints. Managed by systemd user service. Survives restarts. Health-checked.

---

## Pre-Flight Checklist

- [ ] Model files exist: `ls ~/models/embedding/pplx-embed-v1-0.6b-int8/model_quantized.onnx`
- [ ] Port 18099 is free: `ss -tlnp | grep 18099` (should return nothing)
- [ ] onnxruntime installed: `python3 -c "import onnxruntime; print(onnxruntime.__version__)"`
- [ ] transformers installed: `python3 -c "from transformers import AutoTokenizer; print('ok')"`

---

## Implementation Steps

### Step 1: Read existing server.py

```bash
cat ~/models/embedding/pplx-embed-v1-0.6b-int8/server.py
```

Note the current port (18097), the embedding function, and the HTTP handler structure.

### Step 2: Change port to 18099

Edit `server.py`:
- Change `EMBEDDING_SERVER_PORT = 18097` → `18099` (or wherever the default port is set)
- Change `--port` default in argparse from `18097` → `18099`

### Step 3: Add /health endpoint

Add to the `Handler.do_GET()` method:

```python
elif self.path == "/health":
    self._send(200, {
        "status": "ok",
        "model": MODEL_NAME,
        "dims": EMBEDDING_DIMS,
        "uptime": time.time() - start_time,
    })
```

Add `start_time = time.time()` at module level.

### Step 4: Add graceful error handling

In `do_POST` for `/v1/embeddings`:
- Wrap `embed(input_val)` in try/except
- Return 503 on failure: `self._send(503, {"error": str(e)})`

### Step 5: Test manually

```bash
cd ~/models/embedding/pplx-embed-v1-0.6b-int8/
python3 server.py --port 18099 &
sleep 10  # wait for model to load

# Health check
curl http://127.0.0.1:18099/health

# Embedding test
curl -X POST http://127.0.0.1:18099/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"input": ["hello world", "test embedding"]}'

# Models list
curl http://127.0.0.1:18099/v1/models

# Kill the background process
kill %1
```

### Step 6: Create systemd user service

Create `~/.config/systemd/user/pplx-embed.service`:

```ini
[Unit]
Description=pplx-embed-v1 Embedding Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/chief/models/embedding/pplx-embed-v1-0.6b-int8/server.py --port 18099
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
```

### Step 7: Enable and start

```bash
systemctl --user daemon-reload
systemctl --user enable --now pplx-embed.service
sleep 15  # wait for model to load
systemctl --user status pplx-embed.service
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `~/models/embedding/pplx-embed-v1-0.6b-int8/server.py` | Port 18099, /health, error handling |
| Create | `~/.config/systemd/user/pplx-embed.service` | Systemd user service |

---

## Phase-Specific Tests

1. **Health endpoint:** `curl http://127.0.0.1:18099/health` → `{"status": "ok", "model": "pplx-embed-v1-0.6b", "dims": 1024}`
2. **Embedding output:** POST to `/v1/embeddings` with `["test"]` → returns array of 1024 floats
3. **Batch embedding:** POST with 10 texts → returns 10 embeddings
4. **Service restart:** `systemctl --user restart pplx-embed.service` → health check passes after 15s
5. **Models list:** `curl http://127.0.0.1:18099/v1/models` → returns model list

---

## Completion Gate

- [ ] server.py modified (port 18099, /health, error handling)
- [ ] systemd service created and enabled
- [ ] Health endpoint returns 200 with correct dims
- [ ] Embedding endpoint returns 1024-dim vectors
- [ ] Service survives restart
- [ ] All phase-specific tests pass

---

## Notes for Next Phase

Phase 2 (Memsearch) expects the server running on `http://127.0.0.1:18099/v1/embeddings`. It will change the `embedding_provider` from `"onnx"` (bge-m3 direct) to HTTP URL.
