# Platform Primitives

**Status:** Constitution (stable, long-lived)
**Last updated:** 2026-05-16

---

## Principle

Cross-cutting concerns live in `plat/`. Domains never implement their own outbox, event bus, observability, or tenant isolation — they use the platform primitives.

---

## Module Inventory

### Outbox (`plat/outbox/`)

Cross-store consistency pattern. When a write spans PostgreSQL and MongoDB, the outbox ensures the second write happens even if the first succeeds and the second fails.

| File | Purpose |
|------|---------|
| `models.py` | Outbox entry model (action, payload, status, retry_count) |
| `service.py` | Outbox service API (create, process, retry) |
| `worker.py` | Background worker that processes pending outbox entries |

**Pattern:** Write to primary store → create outbox entry → commit transaction → worker processes outbox entry → writes to secondary store. Uses `transaction.on_commit` to ensure the outbox entry is only processed after the primary transaction succeeds.

### Events (`plat/events/`)

Domain event bus. Emit events from any domain, subscribe from any domain. Decouples domain logic.

| File | Purpose |
|------|---------|
| `bus.py` | Event bus (emit/on pattern) |
| `types.py` | Event type definitions |

**Pattern:** `emit(event_type, payload)` → all subscribers for `event_type` receive the payload synchronously.

### Observability (`plat/observability/`)

Request-level tracing and tenant context propagation.

| File | Purpose |
|------|---------|
| `context.py` | Thread-local context storage |
| `logging.py` | Structured logging with correlation ID |
| `middleware.py` | `CorrelationIDMiddleware`, `TenantContextMiddleware` |

**CorrelationIDMiddleware:** Generates `X-Correlation-ID` on every request. Propagates through logs, outbox entries, and downstream calls.

**TenantContextMiddleware:** Extracts tenant scope from JWT/session. Makes `bg_code`, `div_code`, `branch_code` available to views and services.

Both middleware classes are wired into `MIDDLEWARE` in settings.

### Tenant (`plat/tenant/`)

Tenant isolation utilities. See `architecture/multi_tenancy.md` for the full multi-tenancy design.

| File | Purpose |
|------|---------|
| `collection.py` | `TenantCollection` — auto-injects `bg_code` into MongoDB queries, raises `TenantContextMissing` |
| `config.py` | Tenant configuration loading |
| `exceptions.py` | `TenantContextMissing` exception |
| `rls.py` | PostgreSQL RLS enable/disable, policy management |
| `verify.py` | Tenant isolation verification |
| `management/commands/` | `enable_rls`, `mongo_schema_validate`, `mongo_create_views` |

### Health (`plat/health/`)

Health check endpoints.

| File | Purpose |
|------|---------|
| `urls.py` | Health check URL routing |
| `views.py` | Health check views (database, MongoDB, MeiliSearch) |

### Shared (`plat/shared/`)

Utility functions used across domains.

| File | Purpose |
|------|---------|
| `encoding.py` | Encoding utilities |
| `helpers.py` | General helpers |
| `validation.py` | Input validation utilities |

### Management (`plat/management/`)

Django management commands for platform operations.

| File | Purpose |
|------|---------|
| `commands/seed_tenant_config.py` | Tenant configuration seeding |

---

## MongoDB Connection Management

Singleton pattern: `get_collection()` uses a singleton `get_mongo_client()`. All `MongoClient()` calls outside `management/commands/` route through the singleton.

**Why singleton:** Prevents connection pool exhaustion. Multiple `MongoClient()` instances each create their own connection pool. A singleton shares one pool across all requests.

---

## Architecture Decisions

### Why Platform Primitives, Not Domain Responsibility?

Cross-cutting concerns (outbox, events, observability, tenant) are infrastructure. If each domain implements its own version, you get inconsistency, bugs, and maintenance overhead. Platform primitives enforce a single implementation.

### Why Outbox Pattern, Not Direct Dual-Write?

Direct dual-write (PostgreSQL + MongoDB in the same request) has no retry mechanism. If MongoDB is down, the PostgreSQL write succeeds and the data is inconsistent. The outbox pattern defers the MongoDB write to a background worker with retry logic.

### Why Synchronous Event Bus, Not Async?

The event bus is synchronous — subscribers run in the same request thread. This ensures event processing is part of the request lifecycle. For async processing, use the outbox pattern.

### Why Correlation ID in Middleware, Not Per-View?

Correlation IDs must be generated at the request boundary (middleware), not in individual views. This ensures every request has a correlation ID, even if the view doesn't explicitly use it.

---

> **Implementation state:** All platform primitives are implemented and wired. See `operations/` for deployment and monitoring tracking.
