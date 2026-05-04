---
tags: [cafe, gaming, GGleap, wallet, identity, rebellion, post-core]
created: 2026-04-27
updated: 2026-04-28
sources: [kteam-dj-chief/cafe-platform-plan, kteam-dj-chief/users/, kteam-dj-chief/rebellion/, kteam-dj-chief/backend/utils.py]
related: [[KungOS_v2]], [[kungos-log]], [[db-unification-log]], [[kteam-system-architecture]]
status: planned
---

# GGleap-Style Gaming Cafe Platform

**Project:** Kuro Gaming Cafe Management System (Rebellion brand)  
**Reference:** GGleap / Senet-style cafe platform architecture  
**Base System:** kteam-dj-chief (Django/DRF) + kteam-fe-chief (React 19)  
**Status:** Designed, awaiting post-core implementation  
**Estimated Effort:** 230–345 hours (12–18 weeks)
- Backend + Manager Web Dashboard: 120–180 hours
- Station Desktop Platform (Tauri/Rust): 110–165 hours

---

## Summary

This plan upgrades the existing **Rebellion esports platform** into a full **gaming cafe management system** (GGleap-style) while preserving all existing esports, PC sales, and inventory functionality. The core architectural change is introducing a **unified identity model** where `phone` is the universal key across all three brands (Kuro Gaming cafe, RenderEdge retail, Rebellion esports), with a **shared wallet** bridging all transactions.

### Key Design Decisions

1. **Phone is the universal key** — Every identity traces to `CustomUser.phone` in PostgreSQL
2. **Cafe data in PostgreSQL, esports data in MongoDB** — Station/sessions/wallets/games all in `caf_platform_*` PG tables; esports stays in `players`/`tournaments` MongoDB collections
3. **Shared wallet in PostgreSQL** — Bridges cafe sessions, tournament prizes, and retail purchases
4. **Walk-in mode (no login)** — Staff enters phone number → system finds/creates customer → starts session
5. **JWT mode (registered)** — Customer logs in on kiosk → auto-billing from wallet

### Ground-Truth Update (2026-04-28)

**The cafe platform was implemented entirely in PostgreSQL — NOT in MongoDB.**

The original design planned `stations`, `gamers`, `game_library`, `cafe_payments` as MongoDB collections. All were migrated to PostgreSQL `caf_platform_*` tables instead, because:
- Relational integrity (FKs between stations→sessions→wallets)
- ACID transactions for session billing + wallet deduction
- Complex queries (revenue reports, station utilization, session timelines)
- Row-level locking for wallet balance updates

The 4 planned MongoDB collections were replaced by 14 PostgreSQL tables:

### What Was Explicitly Rejected

- **Google Play Game Services (GPGS) integration** — user explicitly rejected this direction
- **Senet integration** — user explicitly rejected this direction
- **Migrating `reb_users` to PostgreSQL** — stays in MongoDB as lightweight staff lookup (confirmed)
- **Migrating `players` to PostgreSQL** — stays in MongoDB as esports data distinct from auth users (confirmed)
- **Cafe data in MongoDB** — all cafe data moved to PostgreSQL `caf_platform_*` tables (ground truth update)

---

## Architecture Overview

```
                    ┌─────────────────────────┐
                    │   CustomUser (PostgreSQL)  │
                    │   phone: +91XXXXXXXXXX     │
                    │   name: "Rahul Sharma"     │
                    │   usertype: null           │
                    │   (one per human)          │
                    └──────────┬────────────────┘
                               │ userid (FK)
                    ┌──────────┴────────────────┐
                    │   KuroUser (PostgreSQL)    │
                    │   (optional profile)       │
                    │   address, DOB, etc.       │
                    └──────────┬────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
    ┌────────────────┐ ┌──────────────┐ ┌──────────────┐
    │  reb_users     │ │   gamers     │ │  players     │
    │  (MongoDB)     │ │  (MongoDB)   │ │  (MongoDB)   │
    │                │ │              │ │              │
    │ Staff roster   │ │ Esports      │ │ Esports      │
    │ (staff role)   │ │ (legacy)     │ │ (riotid,     │
    └────────────────┘ │              │ │  rank, team) │
                       └──────────────┘ └──────────────┘
                                │                │
                                └────────────────┘
                                         │
                    ┌────────────────────┴────────────────┐
                    │   caf_platform_* (PostgreSQL)        │
                    │   14 tables: stations, sessions,     │
                    │   wallets, price_plans, member_plans,│
                    │   games, cafes, walkins, auth_tokens │
                    │   session_leases, station_commands,  │
                    │   station_events, wallet_transactions│
                    │   (shared wallet + cafe ops)         │
                    └─────────────────────────────────────┘
```

### Three Brands, One Phone Number

| Brand | Identity | Auth | Wallet | Cafe Data |
|---|---|---|---|---|
| **Kuro Gaming** (cafe) | `CustomUser.phone` | Walk-in (phone lookup) or JWT (registered) | `caf_platform_wallets` (shared) | `caf_platform_*` (14 PG tables) |
| **RenderEdge** (retail) | `CustomUser.phone` | Same as above | `caf_platform_wallets` (shared) — can redeem at retail | `caf_platform_*` (14 PG tables) |
| **Rebellion** (esports) | `CustomUser.phone` + `players` (MongoDB) | JWT required | `caf_platform_wallets` (shared) — tournament prizes | `caf_platform_*` (14 PG tables) + `players`/`tournaments` (MongoDB) |

### Three Layers of Delivery

| Layer | Stack | Role |
|---|---|---|
| **Cloud/Backend** | Django/DRF + PostgreSQL + MongoDB | Auth, billing, API, real-time WebSocket |
| **Manager Web Dashboard** | React 19 (kteam-fe-chief) | Operator-facing browser dashboard |
| **Station Desktop Platform** | Tauri/Rust | Desktop app + Windows service for timer authority, game launch, process watchdog |

The Station Desktop Platform consists of two co-located processes on every cafe PC:
1. **`station-shell`** (Tauri) — React UI: login, QR entry, time display, WebSocket sync
2. **`station-service`** (Rust) — Timer authority, game launcher, process watchdog, offline SQLite

Communication: Windows named pipes (`\\.\pipe\gaming-cafe-station`) with newline-delimited JSON.

See [`CAFE_PLATFORM.md`](../Coding-Projects/kteam-dj-chief/CAFE_PLATFORM.md) §15 for page-by-page wiring matrix and §16 for full station platform spec.

---

## Database Schema

**Ground truth (2026-04-28):** All 14 cafe platform tables are in PostgreSQL. No cafe data exists in MongoDB.

### PostgreSQL — `caf_platform_*` Tables (14 tables)

| Table | Cols | Purpose | Spec Name | Status |
|---|---|---|---|---|
| `caf_platform_cafes` | 10 | Cafe registry (name, code, timezone, currency) | — | ✅ Implemented |
| `caf_platform_stations` | 12 | Station inventory with specs, status, installed games | `stations` (was MongoDB) | ✅ Implemented |
| `caf_platform_sessions` | 17 | Session tracking with billing, wallet linkage | `gamers` (was MongoDB) | ✅ Implemented |
| `caf_platform_session_leases` | 8 | Lease versioning for station timer authority | — | ✅ Implemented |
| `caf_platform_station_commands` | 9 | Station remote control (lock, unlock, reboot) | — | ✅ Implemented |
| `caf_platform_station_events` | 8 | Station event log (heartbeat, game launch, errors) | — | ✅ Implemented |
| `caf_platform_wallets` | 11 | Shared wallet bridging cafe, esports, retail | `cafe_wallets` | ✅ Implemented |
| `caf_platform_wallet_transactions` | 9 | Audit trail for all wallet movements | `cafe_payments` (was MongoDB) + `cafe_wallet_transactions` | ✅ Implemented |
| `caf_platform_price_plans` | 15 | Zone-based pricing with peak/weekend multipliers | `cafe_pricing_rules` | ✅ Implemented |
| `caf_platform_member_plans` | 9 | Edge/Titan/S membership tiers with benefits | `cafe_member_plans` | ✅ Implemented |
| `caf_platform_games` | 13 | Game catalog with station assignments | `game_library` (was MongoDB) | ✅ Implemented |
| `caf_platform_users` | 8 | Cafe user profiles (wallet balance, status) | — | ✅ Implemented |
| `caf_platform_walkins` | 5 | Optional non-registered customer tracking | `cafe_walkins` | ✅ Implemented |
| `caf_platform_auth_tokens` | 7 | Auth token storage for cafe kiosk sessions | — | ✅ Implemented |

### MongoDB — No Cafe Collections

The 4 collections originally planned for MongoDB were all moved to PostgreSQL:

| Was Planned (MongoDB) | Now In (PostgreSQL) | Reason |
|---|---|---|
| `stations` | `caf_platform_stations` | FKs to cafes, sessions, station_commands/events |
| `gamers` (enhanced) | `caf_platform_sessions` + `caf_platform_users` | Relational billing, wallet FKs, session state machine |
| `game_library` | `caf_platform_games` | FK to cafes, cafe-specific game catalog |
| `cafe_payments` | `caf_platform_wallet_transactions` | FK to wallets, transaction audit trail |

### MongoDB — Existing Collections Unchanged

The following MongoDB collections were **not enhanced** for cafe use (the planned enhancements were abandoned when data moved to PostgreSQL):

| Collection | Was Planned Enhancement | Actual Status |
|---|---|---|
| `reb_users` | `station_role`, `customer_type`, `wallet_id`, `is_staff` | ❌ Not enhanced — staff lookup stays lightweight |
| `kgorders` | `order_type: cafe` | ❌ Not enhanced — cafe orders use PG sessions |
| `inwardpayments` | `session_id`, `payment_type` | ❌ Not enhanced — cafe payments in PG |
| `stock_register` | `product_type: food` | ❌ Not enhanced — cafe food orders separate |
| `gamers` | Full field expansion | ❌ Not enhanced — gamers → PG sessions |

### Accesslevel Cafe Permissions (Planned, Not Yet Implemented)

| Permission | Values | Purpose | Status |
|---|---|---|---|
| `station_management` | 0/1/2 | Station view/full control | ❌ Not in schema (varchar fields) |
| `wallet_management` | 0/1/2 | Wallet view/manage | ❌ Not in schema |
| `wallet_recharge` | 0/1 | Can recharge wallets | ❌ Not in schema |
| `pricing_management` | 0/1/2 | Pricing configure | ❌ Not in schema |
| `cafe_dashboard` | 0/1 | Dashboard view | ❌ Not in schema |
| `cafe_sessions` | 0/1/2 | Session manage | ❌ Not in schema |
| `cafe_payments` | 0/1/2 | Payment record | ❌ Not in schema |

**Note:** All 50+ permission fields on `Accesslevel` are `character varying` (strings), not integers. The cafe permission fields above are planned additions requiring a Django migration.

---

## API Endpoints (24+)

All under `/api/v1/cafe/`:

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/cafe/customer/register` | Register new cafe customer |
| POST | `/cafe/customer/lookup` | Look up by phone (walk-in, no auth) |
| GET | `/cafe/customer/profile` | Customer profile + wallet |
| GET | `/cafe/wallet/balance` | Wallet balance |
| POST | `/cafe/wallet/recharge` | Recharge wallet |
| GET | `/cafe/wallet/transactions` | Transaction history |
| GET | `/cafe/stations` | List stations |
| GET | `/cafe/stations/:id` | Station detail |
| PATCH | `/cafe/stations/:id/status` | Update station status |
| POST | `/cafe/sessions/start` | Start session |
| POST | `/cafe/sessions/pause` | Pause session |
| POST | `/cafe/sessions/resume` | Resume session |
| POST | `/cafe/sessions/end` | End session + calculate charges |
| POST | `/cafe/sessions/extend` | Extend session |
| GET | `/cafe/sessions/active` | Active sessions list |
| POST | `/cafe/sessions/:id/food` | Add food to session |
| GET | `/cafe/dashboard/overview` | Real-time dashboard (10s refresh) |
| GET | `/cafe/pricing/rules` | Pricing rules |
| POST | `/cafe/pricing/calculate` | Calculate session charges |
| GET | `/cafe/games` | Game library |
| GET | `/cafe/payments` | Payment history |
| POST | `/cafe/payments/record` | Record payment |
| GET | `/cafe/members/plans` | Membership tiers |
| POST | `/cafe/members/:tier/upgrade` | Upgrade membership |

---

## Frontend Pages (12)

All under `src/pages/cafe/`:

| Page | Purpose |
|---|---|
| `CafeDashboard.jsx` | Real-time overview with station grid |
| `StationsList.jsx` | Station grid with status filter |
| `StationDetail.jsx` | Single station view |
| `SessionStart.jsx` | Walk-in customer check-in |
| `SessionActive.jsx` | Active session timer |
| `SessionEnd.jsx` | End session + billing |
| `WalletBalance.jsx` | Customer wallet view |
| `WalletRecharge.jsx` | Recharge wallet |
| `GameLibrary.jsx` | Game catalog |
| `PricingConfig.jsx` | Admin pricing configuration |
| `CafePayments.jsx` | Payment history |
| `MemberPlans.jsx` | Membership tiers |

### Key Components (7)

- `StationCard` — Individual station tile with status badge
- `SessionTimer` — Active session countdown
- `CustomerLookup` — Phone lookup input (walk-in mode)
- `FoodOrderModal` — Add food to active session
- `PaymentModal` — Record payment dialog
- `RevenueChart` — Revenue analytics (Recharts)
- `ZoneUtilization` — Zone occupancy visualization

### Redux Store

New `cafeSlice` in `src/store/slices/cafeSlice.js`:
- `currentCustomer`, `customerLookupLoading`
- `walletBalance`, `walletHistory`
- `stations`, `selectedStation`
- `activeSessions`, `currentSession`
- `dashboardOverview`
- `pricingRules`, `gameLibrary`, `cafePayments`

### API Service Layer

New `src/api/cafeApi.js` with 30+ methods matching all backend endpoints.

---

## Customer Identity Flow

### Walk-in (No Registration)

```
1. Staff enters phone number
2. Lookup CustomUser by phone
   - If found → load profile + wallet
   - If not → create lightweight CustomUser
3. Lookup/create wallet
   - If found → load balance
   - If not → create WAL000001 (edge tier)
4. Check wallet balance
   - If > 0 → start session (auto-billing)
   - If = 0 → prompt payment (UPI/cash/card)
5. Session starts, station marked occupied
```

### Registered (JWT Auth)

```
1. Customer opens kiosk app on phone
2. Enters phone → OTP verification
3. JWT issued with wallet_id
4. At cafe: staff enters phone → auto-loads profile + balance
5. Session starts with auto-billing from wallet
6. Points earned, tier progression tracked
```

---

## Implementation Phases (6 Phases, 8 Weeks)

| Phase | Duration | Scope |
|---|---|---|
| **Phase 1: Foundation** | Week 1-2 | Backend: 5 PostgreSQL models, 4 management commands, 24 endpoints. MongoDB: enhanced collections. Frontend: API service, Redux slice, dashboard skeleton |
| **Phase 2: Core Cafe Ops** | Week 3-4 | Session start/end/pause/resume, wallet recharge, station CRUD, pricing calculation, dashboard aggregation. Frontend: all 12 pages + 7 components |
| **Phase 3: Esports Integration** | Week 5 | Tournament prizes → wallet, esports player → wallet, cross-brand membership tiers, loyalty points |
| **Phase 4: Retail Bridge** | Week 6 | RenderEdge wallet redemption, PC purchase payments from wallet, unified loyalty program |
| **Phase 5: Legacy Cleanup** | Week 7 | Remove unauthenticated `gamers()`, deprecate `rbpackages`, add rate limiting |
| **Phase 6: Production Deploy** | Week 8 | Backend tests (pytest-django), frontend tests (Vitest), production runbook, knowledge transfer |

---

## Data Migration from Legacy

| Legacy Source | Target | Transformation |
|---|---|---|
| `gamers` (existing) | `gamers` (enhanced) | Add `station_id`, `wallet_id`, `customer_name`; convert time strings to ISODate |
| `reb_users` (existing) | `reb_users` (enhanced) | Add `station_role`, `customer_type`, `wallet_id`, `is_staff` |
| `rbpackages` (misc) | `cafe_pricing_rules` (PostgreSQL) | Extract `price/postpkg` → `base_rate_per_hour` |
| `kgorders` (existing) | `kgorders` (enhanced) | Add `order_type: cafe` for food orders |
| `stock_register` (existing) | `stock_register` (enhanced) | Add `product_type: food` for consumables |
| `inwardpayments` (existing) | `inwardpayments` (enhanced) | Add `session_id`, `payment_type` where applicable |

---

## Key Learnings from Current Code Analysis

### 1. `gamers()` endpoint has NO auth (critical gap)

```python
#@authentication_classes([CookieJWTAuthentication])
#@permission_classes([IsAuthenticated])
def gamers(request):
```

This means **anyone** can create a session, start a timer, and rack up charges. The new walk-in mode replaces this but adds wallet balance checks.

### 2. `reb_users` is created implicitly on first order

```python
reb_usersData = decode_result(reb_users_collection.find({"userid": orderData['user']['phone']}))
if len(reb_usersData) == 0:
    create_reb_user(orderData=orderData, ...)
```

No registration flow exists. The new `register_customer` endpoint formalizes this.

### 3. Phone is already the universal key

Every identity in the system traces back to `CustomUser.phone`:
- `CustomUser.phone` (unique) — auth
- `reb_users.userid` = phone — staff lookup
- `kgorders.user.phone` — customer orders
- `players.userid` — esports players
- `gamers.userid` — cafe sessions

This means the unified identity model requires **zero schema changes to existing auth** — just new wallet + cafe tables that reference `CustomUser.userid`.

### 4. `reb_users` should stay in MongoDB

It is a lightweight staff lookup table queried per-tenant (`bg_code`) via `get_collection('reb_users')`. Migrating to PostgreSQL adds unnecessary joins for a simple roster.

### 5. `players` should stay in MongoDB

It stores gaming/esports data (riotid, rank, teamid) which is distinct from auth users.

---

## Dependencies on Core Phases

This cafe platform **cannot begin until Phase 4 (Testing/CI/CD) is complete** because:

1. Unified identity model (`CustomUser.phone` as universal key) depends on user model reconciliation (Phase 1)
2. Shared wallet requires PostgreSQL schema changes that must not interfere with core data
3. Tenant context (`bg_code`, `div_code`, `branch_code`) must be stable for cafe data scoping (Phase 1)
4. MongoDB consolidation with `bgcode` field must exist for new cafe collections (Phase 1)
5. React Query + cookie-ready auth must be in place for kiosk app and dashboard (Phase 2)
6. All core endpoints must be stable before extending the rebellion brand into cafe operations

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **Wallet double-spend** | Critical | PostgreSQL row-level locking on wallet balance; transaction log audit trail |
| **Cross-store partial write** | High | Outbox pattern: both writes in same PostgreSQL transaction, async Mongo side-effect |
| **Unauthenticated session creation** | Critical | Remove `#@authentication_classes` from `gamers()`; enforce phone lookup + wallet balance check |
| **Tenant data leakage** | High | `TenantCollection` wrapper enforces `bgcode`+`division`+`branch_code` filtering on all cafe collections |
| **Pricing calculation errors** | Medium | Unit tests for all pricing scenarios (peak hours, weekend, tier discounts) |
| **Dashboard performance** | Medium | Aggregate at DB level; use MongoDB aggregation pipeline |
| **Expired sessions** | Medium | Cron job `check_expired_sessions` to auto-close sessions > 8 hours |

---

## Related Documents

- [[KungOS_v2]] — Authoritative master plan (post-core expansion documented in §Post-Core — Cafe Platform)
- [[kungos-log]] — Approved departures from the plan
- [[db-unification-log]] — Database unification work (wallet model extends this)
- [[kteam-system-architecture]] — Current system architecture (identity model extends this)
- `kteam-dj-chief/CAFE_PLATFORM.md` — **Unified plan** (consolidates all cafe docs: implementation plan, changes, traceability)
