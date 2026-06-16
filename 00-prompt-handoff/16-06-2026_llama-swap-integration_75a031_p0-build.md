# Phase 0: Go Build Verification

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Entity ID | `75a031-p0` |
| Entity Type | `work_item` |
| Status | `proposed` |
| Parent | `75a031` |

---

## Goal

Verify all Go code compiles and tests pass in both standard (upstream) and council (extension) build modes.

## Prerequisites

- Go 1.26+ installed
- llama-swap repository at `/home/chief/llama-swap/`

## Build Commands

```bash
cd /home/chief/llama-swap

# 1. Standard build — must compile without council features
go build ./...

# 2. Council build — must compile with KV cache persistence
go build -tags council ./...

# 3. Run tests (standard mode)
go test ./internal/router/ -v -count=1
go test ./internal/config/ -v -count=1

# 4. Run tests (council mode)
go test -tags council ./internal/slotstore/ -v -count=1
go test -tags council ./internal/router/ -v -count=1
go test -tags council ./internal/config/ -v -count=1

# 5. Vet for common mistakes
go vet ./...
go vet -tags council ./...
```

## Expected Results

### Standard Build
- `go build ./...` — compiles cleanly, no errors
- `internal/slotstore/store.go` — NOT compiled (build tag `council`)
- `internal/slotstore/store_stub.go` — compiled (build tag `!council`)
- `internal/router/hook_default.go` — compiled (returns nil)
- `internal/router/hook_council.go` — NOT compiled
- `internal/server/slots_stub.go` — compiled (no-op)
- `internal/server/slots_routes.go` — NOT compiled

### Council Build
- `go build -tags council ./...` — compiles cleanly, no errors
- `internal/slotstore/store.go` — compiled (full implementation)
- `internal/slotstore/store_stub.go` — NOT compiled
- `internal/router/hook_default.go` — NOT compiled
- `internal/router/hook_council.go` — compiled (wires slotstore hook)
- `internal/server/slots_stub.go` — NOT compiled
- `internal/server/slots_routes.go` — compiled (registers slot routes)

### Tests
All tests must pass in both modes:
- `internal/router/hook_test.go` — SwapHook interface tests (standard)
- `internal/config/slotstore_test.go` — Config extension tests (standard)
- `internal/slotstore/store_test.go` — SlotStore tests (council only)
- `internal/slotstore/hook_test.go` — Hook tests (council only)

## Files Modified/Created

### New Files (14)
```
internal/router/hook.go              — SwapHook interface
internal/router/hook_default.go      — No-op hook (!council)
internal/router/hook_council.go      — Council hook wiring (council)
internal/router/hook_test.go         — SwapHook tests
internal/slotstore/store.go          — KV cache persistence (council)
internal/slotstore/store_stub.go     — No-op stub (!council)
internal/slotstore/store_test.go     — SlotStore tests (council)
internal/slotstore/hook.go           — SwapHook impl (council)
internal/slotstore/hook_test.go      — Hook tests (council)
internal/server/slots.go             — Slot REST endpoints (council)
internal/server/slots_stub.go        — No-op routes (!council)
internal/server/slots_routes.go      — Route registration (council)
internal/config/slotstore_test.go    — Config extension tests
docs/council-slotstore.md            — Documentation
```

### Modified Files (3)
```
internal/router/base.go              — +hook field, +2 conditional calls
internal/config/model_config.go      — +SlotStoreConfig struct
internal/server/server.go            — +registerSlotRoutes() call
```

## Verification Checklist

- [ ] `go build ./...` succeeds (standard)
- [ ] `go build -tags council ./...` succeeds (council)
- [ ] `go test ./internal/router/ -v` passes (standard)
- [ ] `go test ./internal/config/ -v` passes (standard)
- [ ] `go test -tags council ./internal/slotstore/ -v` passes (council)
- [ ] `go test -tags council ./internal/router/ -v` passes (council)
- [ ] `go vet ./...` reports no issues (standard)
- [ ] `go vet -tags council ./...` reports no issues (council)
- [ ] Binary size difference is reasonable (council binary includes slotstore)

## Known Issues

1. **Go not installed** — Requires Go 1.26+ installation on the system.
2. **llama-server slot API** — Slot save/restore calls to llama-server are TODO stubs. Full implementation requires testing against actual llama-server instance.

## Next Steps

After Phase 0 passes:
1. Proceed to Phase 2 (frontend types + SSE hook)
2. Phase 1A (Python client) is already complete — proceed to integration
