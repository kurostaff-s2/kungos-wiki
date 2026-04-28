# Comprehensive Test Plan for KungOS v2 and Cafe Platform

**Last Revised:** 2026-04-28  
**Ground-truthed against:** Actual codebase (kteam-dj-chief + kteam-fe-chief)  
**Previous version:** Original AI-generated plan (incorrect file paths, model fields, and auth approaches)

## Overview

This document defines a release-grade full-stack test plan for KungOS v2 and the Cafe Platform across Django backend, React frontend, MongoDB and PostgreSQL data layers, platform primitives, migration tooling, and the Station Desktop Platform.

It incorporates corrections from the 2026-04-28 assessment: actual model field names, correct file paths, Playwright `request` fixture auth patterns, and the distinction between existing vs. planned model fields.

## Coverage map

| Platform area | Primary stack | Core risks | Required test levels |
|---|---|---|---|
| Core KungOS backend | Django, DRF, PostgreSQL, MongoDB | Tenant leakage, auth regression, cross-store inconsistency, schema drift. | Unit, integration, API CRUD, data-flow, security, migration. |
| Cafe manager web | React 19, Redux, React Query | Incorrect operator workflows, stale state, permission bypass, billing display errors. | Unit, component, integration, E2E. |
| Gaming e-shop | Django, React, MongoDB, payment integrations | Cart/order corruption, webhook duplication, SMS side effects, BG scope leakage. | Unit, CRUD, integration, E2E. |
| Platform primitives | TenantCollection, RLS, outbox, event bus, observability, TenantConfig | Silent policy failure, duplicate events, broken tracing, feature-surface leaks. | Unit, contract, integration, fault injection. |
| Station Desktop Platform | Tauri/React shell, Rust Windows service, SQLite, IPC, WebSocket | Timer drift, offline queue loss, kiosk bypass, reconnect bugs, lease corruption. | Unit, integration, system, soak, offline-resilience. |
| Migration and cutover | Django management commands, restore flows, auth reconciliation | Bad restore, wrong entity population, duplicate identities, unsafe rollback. | Command tests, reconciliation, dry-run, cutover smoke. |

## Test levels and tools

| Test level | Purpose | Recommended tools |
|---|---|---|
| Unit | Validate isolated functions, serializers, reducers, services, Rust modules, IPC helpers, and utility contracts. | `pytest`, `pytest-django`, `unittest.mock`, `freezegun`, `Vitest`, `React Testing Library`, Rust `cargo test`. |
| Integration | Validate component boundaries across API, DB, queue, WebSocket, IPC, and SQLite/PostgreSQL/Mongo interactions. | DRF API client, dedicated test DBs, `mongomock` plus real test Mongo, Channels test helpers, MSW, Rust integration tests. |
| E2E | Validate business journeys across browser UI and backend services. | Playwright (preferred), Cypress acceptable for browser-only cases. |
| Contract | Validate all brand implementations against shared domain protocols. | `pytest` parametrized suites over adapter fixtures. |
| Data flow | Validate all critical definition-use paths and fail-closed behavior. | Coverage tooling, targeted instrumentation, mutation testing where useful. |
| Non-functional | Validate load, soak, reconnect, concurrency, security, and observability. | k6/Locust, OWASP ZAP, browser profiling, structured-log assertion helpers, soak scripts. |

---

## ⚠️ Ground-Truth Corrections (from 2026-04-28 assessment)

Before executing any task from this plan, be aware of these corrections made to the original AI-generated plan:

### 1. Model: `Accesslevel` (lowercase L, not `AccessLevel`)
- **Actual model:** `users.models.Accesslevel` — fields are business operation permissions: `orders`, `products`, `inventory`, `estimates`, `audit`, `stock`, `sales`, `tp_builds`, `service_request`, `hr`, `analytics`, `employees`, `bg_group`, etc.
- **No `kungosadmin` field exists.** The fields `kungosadmin`, `cafedashboard`, `stationmanagement`, `walletmanagement`, `cafesessions`, `walletrecharge`, `pricingmanagement`, `cafepayments` are **planned additions** that require a Django migration before they can be referenced.
- **`USERNAME_FIELD = 'phone'`** — Django's `authenticate()` uses phone, not userid or username. The login view has a fallback that looks up by `phone | email | userid`.

### 2. File Paths (verified against codebase)
| Wrong (AI-generated) | Correct (ground-truth) |
|---|---|
| `src/pages/InvoicesList.jsx` | `src/pages/Accounts/InvoicesList.jsx` |
| `src/components/layout/Sidebar.jsx` | `src/components/layout/AppSidebar.jsx` |
| `users/permissions.py` | Does not exist as separate file — permissions are inline in views or in the `teams` app |
| `test_pages.py` (root) | `kteam-fe-chief/test_pages.py` and `kteam-fe-chief/test_dynamic_pages.py` |
| `rebellion/views.py` tournaments | `rebellion/esports/views.py` — `tournaments()` and `gamers()` functions |

### 3. Auth Fix: Use `request` fixture, not browser cookies
- The 8 outbox test failures are caused by 403 responses, not by missing auth headers per se.
- **Correct approach:** Use `request.post('/auth/login/', { data: { username: ..., password: ... } })` in `beforeAll` — Playwright's `request` fixture auto-stores the `jwt_token` cookie and sends it on all subsequent calls. No manual cookie extraction needed.
- **Wrong approach:** Creating `e2e/helpers/auth.js` with `page.context().cookies()` — this only works with browser `page` fixture, not the `request` HTTP client fixture used by the failing tests.

### 4. `tournaments()` and `gamers()` 500 bug
- These functions in `rebellion/esports/views.py` are **bare Python functions** (no `@api_view` decorator).
- Django passes a plain `HttpRequest`, but the code uses `request.query_params` (DRF `Request` attribute) → `AttributeError` → 500.
- **Fix:** Add `@api_view(['GET'])` decorator above each function. No full DRF rewrite needed — the functions already use `Response` in try/except blocks.

### 5. `gamers()` has no auth decorators
- Both `tournaments()` and `gamers()` are missing `@authentication_classes` and `@permission_classes`.
- **Fix:** Add `@authentication_classes([CookieJWTAuthentication])` and `@permission_classes([IsAuthenticated])`.

### 6. Outbox has no views.py / API endpoints
- `plat/outbox/` contains only `service.py`, `worker.py`, and `models.py` — **no views.py, no URL routes**.
- The E2E tests call endpoints like `/api/v1/outbox/events/` that **do not exist yet**.
- Outbox testing must first create API endpoints, or test via the service layer directly.

---

## Core backend and API coverage

### Backend unit and schema tests

| Area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| `TenantConfig` | Create configs with `features`, `paymentcfg`, `walletcfg`, `pricingcfg`, `themingcfg`, and `integrationcfg`. | Defaults apply correctly, invalid shapes fail validation, and serialization remains stable. | `pytest-django` |
| Tenant-scoped models | Create wallets, member plans, pricing rules, session records, and brand-scoped rows. | Constraints, defaults, foreign keys, and ordering behave as designed. | `pytest-django` |
| Mongo document schema | Validate required `bgcode`, `entity`, and `branch` fields on migrated collections and cafe collections. | All new and migrated docs are tenant-addressable by query. | Real Mongo tests |
| RLS helpers | Execute tenant-scoped PostgreSQL reads after `SET LOCAL app.currentbgcode`. | Out-of-scope rows are blocked even if application filtering is bypassed. | SQL integration tests |
| `OutboxEvent` | Create pending, processed, failed, and replayed rows. | Status transitions, retry counts, timestamps, and error capture are correct. | `pytest-django` |
| Observability context | Request ID and tenant context storage in ContextVars. | Context survives service entry points and is isolated between requests. | `pytest` |

### Core API CRUD matrix

| Domain | CRUD focus | Key scenarios | Expected outcomes | Tools |
|---|---|---|---|---|
| Auth | Login (password + OTP), refresh, logout, invalid token, blacklisted token, cookie-only flow. | JWT claims include tenant scope and Knox-era flows are rejected on the unified backend. | DRF test client |
| Tenant bootstrap | Fetch active tenant, switch BG/entity/branch, wrong scope, missing context. | Valid combinations resolve; invalid combinations fail closed. | DRF test client |
| Finance/docs | Invoices, estimates, voucher creation and export. | CRUD works within access rules and tenant scope. | DRF test client |
| Orders/products/payments | Create/read/update/delete product and order entities, record payments, retrieve timelines. | Standardized response envelopes and correct scope behavior hold. | DRF test client |
| Health | `health/live`, `health/ready` with healthy and degraded dependencies. | Live remains lightweight; ready reflects PostgreSQL, MongoDB, MeiliSearch, Redis, and Celery dependency state correctly. | Integration tests |
| PDF export | Estimate/invoice PDF generation and parse validation. | `weasyprint` plus `pypdf` output is structurally valid and includes tenant-correct content. | DRF client, PDF parsing |

---

## Cafe manager web and API coverage

### Cafe API CRUD matrix

| Endpoint group | CRUD focus | Key scenarios | Expected outcomes |
|---|---|---|---|
| Customer | Register customer, lookup customer, get profile. | New user, existing user, invalid phone, active session present, rate-limited lookup. | Identity and wallet resolution match the phone-as-universal-key model. |
| Wallet | Balance, recharge, transaction history, membership upgrade effects. | Cash/card/UPI recharge, duplicate callback, frozen wallet, insufficient balance, cross-tenant request. | Ledger integrity, balance correctness, and scope isolation hold. |
| Stations | List, detail, update status. | Zone filter, branch filter, status transitions, wrong-branch access, maintenance conflicts. | Station state is accurate and permission-gated. |
| Sessions | Start, pause, resume, extend, end, active sessions list, food add-on. | Walk-in flow, JWT user, insufficient balance, station unavailable, duplicate end, invalid transitions. | Session lifecycle is valid, billing is deterministic, and station release is correct. |
| Dashboard | Overview, revenue, utilization. | Polling, stale data, empty branch, permission denial. | Aggregated data matches persisted state and permissions. |
| Pricing, games, payments, plans | List rules, calculate charges, list games, record payments, list plans, upgrade tiers. | Valid rules, invalid payloads, wrong tenant, duplicate payment IDs. | Calculation and configuration remain tenant-correct. |

### Frontend component and page tests

| UI area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| `TenantContext` and selector | Bootstrap, switch BG/entity/branch, invalid combination, keyboard navigation. | Single source of truth for active scope with safe fallbacks. | Vitest, RTL |
| `CafeDashboard.jsx` | Initial load, 10-second polling, permission denial, cleanup on unmount. | No duplicate polling, correct empty and error states. | RTL, fake timers |
| `SessionStart.jsx` | Customer lookup, payment modal on insufficient balance, station selection, retry after recharge. | Error flows follow the design matrix exactly. | RTL, MSW |
| `SessionActive.jsx` and `SessionEnd.jsx` | Pause/resume, extend, food order, end session, reconciliation of billing totals. | UI state mirrors API state and clears safely on completion. | RTL, fake timers |
| Wallet and pricing pages | Balance, history, recharge, pricing rules, membership plans, payment history. | Mutations refresh dependent views and show permission-aware UI. | RTL, MSW |
| Shared components | `StationCard`, `SessionTimer`, `RevenueChart`, `ZoneUtilization`, `CustomerLookup`, `FoodOrderModal`, `PaymentModal`. | Prop-driven behavior, render stability, and callback contracts hold. | RTL |

---

## Gaming commerce coverage

### Gaming backend tests

| Area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| Cart CRUD | Add item, list items, update quantity, delete item, duplicate add, cross-BG access. | Cart remains tenant-scoped and mutations are idempotent where required. | `pytest-django`, DRF client |
| Wishlist CRUD | Add, list, remove, duplicate add, cross-BG access. | Wishlist operations are scoped and stable. | `pytest-django` |
| Address CRUD | Create, list, update default, delete, malformed address, cross-tenant attempt. | Address ownership and default-selection rules are enforced. | `pytest-django` |
| Product listing | BG-scoped catalog, pagination, projections, branch-specific visibility. | Product/game lists respect `bgcode`, field projection, and pagination. | `pytest-django`, Mongo tests |
| Order lifecycle | Validate all 11 stages from created through delivered/cancelled, including invalid jumps and rollback edges. | Only allowed transitions occur and audit state remains coherent. | `pytest-django` |
| Payment webhooks | Success, failure, cancelled, replay, wrong signature, duplicate payload. | Idempotent processing with correct order/payment updates. | `pytest-django` |
| SMS integration | Mock TextLocal on order fulfillment changes and other notifications. | Side effects trigger once, errors are captured, and business state does not roll back incorrectly. | `pytest`, mocked provider |
| Mongo tenant filtering | Test all 12 migrated collections with correct BG/entity/branch and wrong scope. | No cross-BG leakage exists in gaming collections. | Real Mongo integration |

### Gaming frontend tests

| Page area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| Product catalog | Filters, pagination, tenant-scoped visibility, empty and error states. | Catalog data matches active tenant context. | RTL, Playwright |
| Prebuilt/custom PC builder | Component selection, validation, price recalculation, save/update flows. | Builder state and total-price calculations remain correct. | RTL, Playwright |
| Cart/wishlist/checkout | Add/remove/update items, move between wishlist and cart, checkout success/failure. | UI and backend remain consistent under retry and refresh. | Playwright |
| Order tracking | 11-stage order rendering, status-stepper transitions, payment states. | Visual pipeline reflects backend truth. | RTL, Playwright |
| Payment pages | Payment initiation, callback return handling, duplicate callback resilience. | Payment UI does not double-confirm or misreport state. | Playwright |

---

## Brand contract tests

### Domain protocol contract matrix

| Protocol | Implementations under test | Contract assertions | Tools |
|---|---|---|---|
| `ICafeSessionService` | All brand adapters exposing cafe behavior. | Start/end/calculate APIs return canonical structures, enforce tenant input, and reject invalid transitions consistently. | `pytest` parametrized contract suite |
| `IWalletService` | Shared wallet or brand-specific wallet adapters. | Credit/debit/get-balance semantics, idempotency, and error contracts are identical across implementations. | `pytest` |
| `IOrderService` | Kuro, Rebellion, RenderEdge or future brand adapters. | Create/get/update-status outputs and error behavior match protocol requirements. | `pytest` |
| `IPrizePayoutService` | Esports/cafe payout implementations. | Prize award behavior credits wallet and emits expected events safely. | `pytest` |
| `ICatalogService` | Brand-specific catalog providers. | `getProducts` and `getProduct` enforce tenant scope and consistent shapes. | `pytest` |

### Contract test scenarios

| Scenario type | Test cases | Expected outcomes |
|---|---|---|
| Happy path | Valid inputs for all protocol methods. | Every adapter returns the same structural contract and key business guarantees. |
| Invalid input | Missing bgcode, malformed IDs, invalid transition/state inputs. | Every adapter fails consistently with the expected domain error. |
| Tenant safety | Wrong BG/entity/branch across protocol calls. | No adapter leaks or mutates out-of-scope data. |
| Idempotency | Replay recharge, webhook, payout, or status-change flows. | Repeat calls do not duplicate side effects. |
| Extensibility | Add a new brand fixture and rerun all suites. | New adapters inherit baseline safety automatically. |

---

## Platform primitives tests

### Tenant enforcement and feature gates

| Area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| `TenantCollection` | Missing context, valid BG, wrong BG, branch-limited queries, explicit filter merge behavior. | Context is mandatory and auto-scoping cannot be bypassed accidentally. | `pytest`, Mongo tests |
| RLS | Correct and incorrect `app.currentbgcode`, joins, pagination queries. | PostgreSQL row-level security blocks illegal reads and writes. | SQL integration tests |
| `TenantConfig.features` gating | `features.cafe=false`, `features.esports=false`, `features.eshop=false`. | Disabled features hide routes, block API access, and suppress navigation entries. | Backend + frontend integration |
| Tenant metadata refresh | `tenant.configchanged` event after config update. | Cache invalidates and frontend metadata refreshes without stale access. | Integration tests |

### Event bus and outbox tests

| Area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| Event registration | Register handlers for `wallet.recharged`, `session.started`, `session.ended`, `order.placed`, `order.fulfillmentchanged`, `tournament.prizeawarded`, `payment.webhookreceived`, `user.registered`, `tenant.configchanged`. | Handlers bind to the correct event keys and missing registrations are detectable. | `pytest` |
| Sync dispatch | Emit low-cost local events. | All sync handlers receive correct payloads in deterministic order where required. | `pytest` |
| Async dispatch | Route events through Celery-backed paths where configured. | Async handlers enqueue once and preserve idempotency keys. | `pytest-django`, mocked task queue |
| Retry and dead-letter | Force handler failure, exceed retry thresholds, requeue from dead-letter view. | Failed events become inspectable, retryable, and replay-safe. | Fault-injection tests |
| Outbox coupling | Publish event inside same transaction as wallet/session/order change. | Database commit and outbox write are atomic. | Transaction tests |
| Reconciliation | Detect wallet-session mismatches and missing Mongo side effects. | Repair events are emitted and convergence is verifiable. | Command integration tests |
| **Outbox API endpoints** | Create GET/POST endpoints for outbox event listing and processing. | **Currently missing** — must be built before E2E outbox tests can pass. | DRF + Playwright |

> **NOTE:** As of 2026-04-28, `plat/outbox/` has no `views.py` or URL routes. The service layer (`service.py`) and worker (`worker.py`) exist and are tested at the unit level, but there are no API endpoints for E2E testing. This is a prerequisite for outbox E2E coverage.

### Observability and correlation tests

| Area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| Correlation middleware | Request without request ID, request with propagated ID, error response path. | `X-Request-ID` is always present and matches log context. | Integration tests |
| Structured logs | Validate required fields `ts`, `level`, `rid`, `userid`, `bgcode`, `entity`, `branch`, `service`, `action`, `durationms`, `outcome`, `errorclass`, `payloadsummary`. | Every log event matches the schema and omits no mandatory fields. | JSON log assertions |
| Context propagation | Service call chain and background task execution. | Tenant and request context survive across boundaries or explicitly reset safely. | Integration tests |
| Sentry tagging | Success and error paths. | Sentry receives tenant and request tags without leaking PII improperly. | Mocked Sentry tests |
| UI traceability | Debug-visible request ID shown in admin builds. | UI request IDs map to backend logs for support debugging. | Playwright |

### Health, search, and shared-utility tests

| Area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| Health endpoints | PostgreSQL/Mongo ready, MeiliSearch unavailable, Redis unavailable when optional, Celery degraded. | `live` and `ready` distinguish degraded but alive from fully ready states correctly. | Integration tests |
| MeiliSearch indexing | Build indexes after migration, verify tenant-scoped search results, rebuild after restore. | Search remains correct, complete, and tenant-safe. | Search integration tests |
| `platformshared` purity | Static scan for forbidden business logic or side-effectful imports in `platformshared`. | CI fails when business ownership leaks into the shared utility layer. | CI grep/lint rule |

---

## Station Desktop Platform tests

### station-service (Rust Windows service)

| Area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| Timer engine | Start, tick, pause, resume, extend, end, clock skew, process restart recovery. | Timer remains authoritative and reconstructs state correctly from persisted lease data. | `cargo test`, integration tests |
| SQLite lease state | Persist active lease, corrupt row, partial write, recovery after reboot. | Lease data is durable, validated, and repairable. | Rust integration, temp SQLite DB |
| Offline queue | Queue commands while disconnected, flush on reconnect, duplicate delivery, out-of-order replay. | No command loss and idempotent replay behavior. | Integration/soak tests |
| Game launcher | Launch allowed process, block forbidden process, detect game exit. | Launcher respects policy and reports lifecycle correctly. | System tests on Windows runner |
| Process watchdog | Kill monitored process, hang process, repeated crash loop. | Watchdog detects and reports correctly without orphaning session state. | System tests |
| Kiosk policy | Attempt shell escape, unauthorized app launch, Windows key bypass. | Kiosk restrictions hold under supported attack attempts. | Manual + scripted system tests |
| IPC server | Named-pipe connection, malformed envelope, reconnect, multi-message sequencing. | Pipe protocol is stable and resilient to malformed messages. | Integration tests |

### station-shell (Tauri/React)

| Area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| QR login | Token display, expiry at 60s, refresh, successful scan, invalid scan. | Login handoff works and expired codes cannot be reused. | Playwright/Tauri tests |
| WebSocket client | Connect, heartbeat every 15s, reconnect after 30s drop, duplicate event, stale command. | Client reconnects cleanly and handles heartbeat rules correctly. | Integration tests |
| IPC client | Receive `sessiontick`, `gamelaunched`, `gameexited`, kiosk commands. | UI updates match incoming envelopes without stale state. | Tauri integration tests |
| Session UI | Current session render, countdown, reconnect banner, end summary. | User-facing state stays correct under reconnect and resume scenarios. | Playwright |
| Local state store | Persist and restore session state after app restart. | Shell resumes safely from persisted state. | Tauri integration tests |

### Station end-to-end and soak tests

| Journey | Steps | Expected outcomes |
|---|---|---|
| Cloud to station start session | Operator starts session from manager web, cloud sends command, station starts timer and UI updates. | Browser, backend, WebSocket, IPC, and timer authority stay in sync. |
| Network outage recovery | Disconnect station during active session, continue local timer, reconnect later. | Offline queue and lease state reconcile without lost billing minutes. |
| Station reboot mid-session | Reboot host during active session. | Service restores active lease and shell resumes display correctly. |
| Long soak | Eight-hour active session with periodic reconnects and game launches. | No timer drift, memory leak, or queue corruption emerges. |

---

## Migration, legacy, and cutover tests

### Management command tests

| Command | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| `restorekuropurchase` | Dry run, real restore, duplicate IDs, entity population, `--verify`, custom host/port, S3 source. | Restore report is correct, duplicates are skipped safely, and entity fields are populated accurately. | Command integration tests |
| `backupkuropurchase` | Backup creation, overwrite handling, verification of JSON dump content. | Backup is complete and restorable. | Command tests |
| `deployrestore` | Orchestrated backup + restore + verify sequence. | Command sequence is safe, ordered, and aborts on failed verification. | Staging drill |
| `verifytenantisolation` | Healthy data set, cross-tenant contamination sample. | Command detects leakage and returns actionable diagnostics. | Command tests |
| `reconcileusermodels` | Kteam and gaming users with overlaps, null fields, conflicting attributes. | Unified users reconcile without data loss and with correct identity linkage. | Command tests |
| `migrategamerstoenhanced` | Legacy gamer docs, mixed legacy shapes, missing fields. | Output documents gain required enhanced fields and remain tenant-scoped. | Mongo integration tests |
| `checkexpiredsessions` | Sessions beyond max duration, already ended sessions, near-threshold sessions. | Only expired sessions are auto-closed and billed according to policy. | Command/scheduler tests |
| Seed commands | `seedpricing`, `seedstations`, `seedgames`, `seedmemberplans`. | Commands are idempotent and produce valid starter data. | Command tests |

### Legacy endpoint deprecation tests

| Legacy path | Test scenarios | Expected outcomes |
|---|---|---|
| `gamers` legacy endpoint | Existing insecure path, secure replacement path, unauthenticated access attempt after remediation. | Insecure unauthenticated behavior is removed or tightly replaced, and critical gaps are closed. |
| `rbpackages` mapping | Legacy package format request after new pricing rules are active. | Response maps correctly from `cafepricingrules` without pricing drift. |
| API dual-path support | Legacy and `/api/v1` paths active during transition. | Compatibility holds until deprecation deadline without contract mismatch. |

### Auth migration regression tests

| Area | Test scenarios | Expected outcomes |
|---|---|---|
| Knox invalidation | Present old Knox token after cutover. | Requests return 401 and no legacy session remains accepted. |
| JWT parity | Kteam and gaming users authenticate into unified session flows. | Claims, cookie behavior, and scope resolution are consistent. |
| Reconciled identities | Users merged by `reconcileusermodels` access orders, wallets, and histories. | No orphaned records or wrong-user data exposure occurs. |
| Cross-domain login | Unified session spans intended gaming and main-app domains where configured. | Auth continuity works without duplicate or conflicting session state. |

---

## Navigation, shared UI, and document regression tests

| Area | Test scenarios | Expected outcomes | Tools |
|---|---|---|---|
| Order restructure | Consolidated list/detail pages replacing multiple legacy routes. | Redirects preserve bookmarks, permissions, and tenant context. | Playwright |
| Shared order components | `OrderStatusStepper`, `OrderAddressBlock`, `OrderProductsTable`, `OrderBuildsTable`, `OrderActionsBar`, `OrderStatCards`, `OrderPaymentSummary`, `OrderPaymentSection`, `RecordPaymentDialog`. | Shared components render all supported order channels correctly. | RTL |
| Estimate/SR flows | `EstimateStatusStepper`, `SRStatusStepper`, `SRWarrantyDecision`, `ConvertToOrderDialog`. | Estimate-to-order and SR-to-order conversions work correctly and preserve audit state. | RTL, Playwright |
| PDF regression | New PDF stack on estimates, SR summaries, invoices, and payment documents. | Output remains readable, parseable, and content-correct after dependency consolidation. | PDF tests |

---

## Data integrity and all-DU-paths coverage

### Critical integrity matrix

| Risk | Test scenarios | Expected outcomes |
|---|---|---|
| Wallet double-spend | Concurrent end-session or spend operations on same wallet. | Row locking or equivalent protection prevents double debit. |
| Cross-store partial write | Failure after Postgres commit but before Mongo side effect. | Outbox ensures replayable recovery to eventual consistency. |
| Cross-tenant leakage | Wrong BG/entity/branch or missing context on reads and writes. | No leakage; all failures are explicit and fail closed. |
| Search drift | Search results after migration or restore. | MeiliSearch indexes are rebuilt and results match source-of-truth data. |
| Restore drift | Post-restore counts and entity distributions. | Restored datasets match verification reports and expected tenant distribution. |

### All-DU-paths targets

| Data object | Definition points | Use points | Mandatory path coverage |
|---|---|---|---|
| `tenant_context` | Middleware, token claims, tenant selector. | RLS, TenantCollection, permissions, feature gates, navigation. | Cover correct scope, wrong BG, wrong entity, branch-limited, and missing context. |
| `wallet.balance` | Wallet init, recharge, refund, prize, spend. | Can-spend checks, session start, session end, upgrade eligibility, UI display. | Cover all define-to-use chains including concurrent updates. |
| `session.status` | Start, pause, resume, end, expire, restore from lease. | Timer UI, allowed actions, billing, station release, command routing. | Cover all valid and invalid transitions. |
| `station.status` | Seed/create, operator update, session occupancy, service recovery. | Availability filters, dashboard utilization, assignment, station shell commands. | Cover all state definitions through UI and backend consumption. |
| `pricing inputs` | Zone, tenant config, peak window, weekend multiplier, tier, grace rules. | Price preview, session billing, dashboard revenue, legacy package mapping. | Cover each feasible define-use combination with boundary timestamps. |
| `request_id` | Correlation middleware generation or propagation. | Response header, logs, Sentry tags, admin debug display. | Cover generation, propagation, error, and async-use paths. |
| `outbox.status` | Pending, failed, processed, requeued. | Reconciliation, admin dead-letter, replay processor. | Cover full lifecycle through repair. |
| `feature_flags` | TenantConfig update or seed. | Navigation, route guards, API permissioning, metadata bootstrap. | Cover enabled, disabled, and live-refresh paths. |

---

## Security and abuse tests

| Area | Test scenarios | Expected outcomes |
|---|---|---|
| Auth and session | Expired JWT, blacklisted JWT, old Knox token, bad cookie, wrong tenant claim. | Unauthorized requests are rejected uniformly. |
| Permission gating | Missing access level on dashboard, stations, sessions, wallet recharge, pricing, payments. | UI redirects and API 403 rules stay aligned. |
| Rate limiting | Customer lookup, login/OTP, recharge initiation, vulnerable anonymous or walk-in paths. | Abuse windows are enforced and recover correctly. |
| Injection and malformed input | SQL/NoSQL injection probes, XSS payloads, oversized JSON, malformed WebSocket/IPC envelopes. | Inputs are rejected or sanitized without state corruption. |
| Kiosk hardening | Attempt shell escape or unauthorized process launch on station desktop. | Platform remains locked down under supported test conditions. |

---

## Performance, soak, and reliability tests

| Area | Test scenarios | Expected outcomes |
|---|---|---|
| Dashboard polling | Many operators polling every 10 seconds. | Response time, DB load, and cache behavior remain acceptable. |
| Wallet debit concurrency | Simultaneous spend/session-end requests. | Exactly-once financial mutation semantics hold. |
| Outbox backlog | Large pending queue with retries and dead-letter cases. | Processor throughput remains stable and observable. |
| Search indexing | Rebuild MeiliSearch after migration or restore. | Index completes within operational bounds and search correctness remains intact. |
| Station soak | Long sessions with reconnects, reboots, game launches, and offline queue churn. | No timer drift, queue loss, or UI desynchronization appears. |

---

## CI and release gates

| Stage | Suites | Merge/release gate |
|---|---|---|
| Fast pre-merge | Lint, type-check, reducers, serializers, utility tests, Rust unit tests, `platformshared` purity scan. | Must pass on every PR. |
| Backend critical | Auth, tenant isolation, wallet, pricing, session lifecycle, order lifecycle, health, outbox, event bus, observability schema. | Required for protected branches. |
| Frontend critical | Tenant selector, auth bootstrap, dashboard, session start/end, wallet recharge, order tracking, permission gates. | Required for protected branches. |
| Contract suites | All domain protocols against every brand adapter. | Required before release branch cut. |
| Migration suites | Restore, backup, verify, reconciliation, expired-session scheduler, legacy endpoint mapping. | Required before staging and cutover rehearsal. |
| Station suites | IPC, WebSocket, QR login, offline queue, lease recovery, soak smoke. | Required before station rollout. |
| E2E smoke | Login, tenant switch, customer lookup, wallet recharge, session lifecycle, cart/checkout, order tracking, request-ID visibility. | Required before production cutover. |
| Release-only non-functional | Load, concurrency, security scans, rollback drill, search rebuild verification. | Required for final sign-off. |

---

## Exit criteria

The test plan is complete when every API surface has CRUD and negative-path coverage, every critical tenant-scoped path has isolation tests, every domain protocol has contract tests across brand implementations, every migration command has deterministic validation, and every station runtime flow has dedicated service, shell, and end-to-end coverage.

Release readiness additionally requires passing critical-path tests, protected-branch CI gates, observability validation, search and PDF regression checks, auth-cutover regressions, request-tracing verification, rollback rehearsal, and smoke validation of storefront, admin, and station parity before go-live.

---

## 📋 Current Test Status (2026-04-28 ground-truth)

### What's passing (181/203 tested)

| Suite | Tests | Pass | Fail | Notes |
|---|---|---|---|---|
| Backend unit (pytest) | 49 | 49 | 0 | Auth, access control, outbox service, events, tenant scope, webhooks |
| E2E — Cafe Platform API | 24 | 24 | 0 | Full pass: customer, wallet, stations, sessions, dashboard, pricing, games, payments |
| E2E — React Query Pages | 19 | 19 | 0 | All authenticated pages load with data |
| E2E — Entity/BG Switching | 13 | 13 | 0 | Full pass: entity filtering, JWT persistence, analytics |
| E2E — Detail Pages (Param Safety) | 26 | 26 | 0 | Zero 500 errors across 13 detail page endpoints |
| E2E — Auth & Session | 16 | 15 | 1 | 1 false-positive assertion (cookie check) |
| E2E — Navigation | 17 | 15 | 2 | Selector issues after kuroadmin→teams rename |

### What needs fixing (22 failures)

| Issue | Severity | Fix |
|---|---|---|
| Outbox events 403 failures (8/15) | High | Fix auth header propagation — use `request.post('/auth/login/')` in `beforeAll` |
| Backend API 11 failures | High | 3× 403 (templates/domains/api-keys), 1× 500 (tournaments — missing `@api_view`), 7× status range mismatch |
| Auth cookie false positive | Medium | Replace `toBeGreaterThanOrEqual(0)` with specific cookie property checks |
| Navigation selectors | Medium | Add `data-testid` to `AppSidebar.jsx` |
| Static page test stale | High | Re-run `test_pages.py` with dev server up (was 57/57 on Apr 25) |

### What's missing entirely

| Area | Status | Priority |
|---|---|---|
| Outbox API endpoints | **No views.py / URLs exist** | 🔴 Critical — must build before E2E outbox tests |
| Gaming backend integration | Separate repo, not merged | 🟡 Phase 3 |
| Gaming E2E tests | No tests exist | 🟡 After backend merge |
| WebSocket real-time tests | Channels bootstrapped, untested | 🔴 High |
| Cafe session lifecycle E2E | No atomic flow test | 🔴 High |
| Station Desktop tests | Not implemented | 🟡 Phase 4 |
| Load/soak/security tests | Not implemented | 🟢 Medium |
| Migration command tests | Not implemented | 🟡 Medium |
| CI/CD pipeline | Not implemented | 🔴 High |
| Correlation ID middleware | Exists but not wired | 🟡 Medium |
| Sentry SDK | Not wired | 🟡 Medium |
| `kungosadmin` permission field | Not in model yet | 🟡 Needs migration |
