# Tournaments Domain Specification

**Status:** Spec — ACTIVE (Phase 3b, Partial)  
**Date:** 2026-05-17  
**Source:** `KungOS_v2.md`, `kungos_v2_db.md`  
**Purpose:** Authoritative spec for tournaments domain — tournaments, players, teams, esports integration
**Package:** `domains/tournaments/` (canonical, not brand-locked)

### Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Basic endpoints (tournaments, players, teams, registration) | ✅ Implemented | `domains/tournaments/views.py` |
| URL routing (`/api/v1/tournaments/`) | ✅ Implemented | Generic namespace, not brand-locked |
| Tenant scoping (`bg_code`/`div_code`) | ✅ Implemented | Via `get_collection()` wrapper |
| Protocol interfaces (`protocols.py`) | ⏳ Planned | Target pattern, not yet implemented |
| PostgreSQL migration (players, teams) | ⏳ Planned | Currently MongoDB collections |

---

## 1. Domain Overview

The tournaments domain manages esports operations: tournaments, players, teams, rankings, and match brackets.

### 1.1 Domain Boundaries

| Boundary | Inside Domain | Outside Domain |
|---|---|---|
| **Identity** | Player profiles, team memberships | Auth, RBAC, employee management |
| **Tournaments** | Tournament creation, registration, brackets | Cafe sessions, station management |
| **Players** | Player profiles, rankings, stats | Customer profiles, employee profiles |
| **Teams** | Team rosters, coach info, tournament history | Vendor management, organization registry |

### 1.2 E-Commerce Backend Integration (Phase 3b)

The legacy `kuro-gaming-dj-backend` codebase (e-commerce backend) provides product catalog, cart, and payment functionality. That integration is owned by the [E-Commerce spec](./ecommerce_spec.md) — not this domain. The tournaments domain has no dependency on those collections.

---

## 2. Player Management

### 2.1 `users_player` — Player Extension

**Replaces:** `players` collection (MongoDB, 117 docs, 59 unique)

| Field | Type | Notes |
|---|---|---|
| `identity_id` | char(20) | **PRIMARY KEY**, FK → `users_identity.identity_id` |
| `player_id` | varchar(20) | Player ID (e.g. `REPL000001`), UNIQUE |
| `team_id` | varchar(20) | FK → `users_organization.org_id` |
| `riot_id` | varchar(100) | Riot Games ID (for Valorant/LoL) |
| `rank` | varchar(50) | Current rank (e.g. Diamond, Immortal) |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

**Indexes:** `player_id`, `team_id`, `rank`

### 2.2 `team_memberships` — Team-to-Person Mapping

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | **PRIMARY KEY** |
| `team_id` | varchar(20) | FK → `users_team_profile.org_id` |
| `identity_id` | char(20) | FK → `users_identity.identity_id`, SET_NULL |
| `phone` | varchar | For unregistered members |
| `name` | varchar(200) | For unregistered members |
| `role_in_team` | varchar(20) | `captain`/`member`/`substitute` |
| `bg_code` | varchar(10) | Tenant scoping |
| `created_at` | timestamptz | |

**Constraints:**
- `chk_membership_has_reference`: CHECK `(identity_id IS NOT NULL) OR (phone IS NOT NULL)`
- `uq_team_identity`: UNIQUE `(team_id, identity_id)` WHERE `identity_id IS NOT NULL`
- `uq_team_phone`: UNIQUE `(team_id, phone)` WHERE `phone IS NOT NULL`

---

## 3. Team Management

### 3.1 `users_team_profile` — Team Extension

**Replaces:** `teams` collection (MongoDB, 14 docs)

| Field | Type | Notes |
|---|---|---|
| `org_id` | char(20) | **PRIMARY KEY**, FK → `users_organization.org_id` |
| `team_id` | varchar(20) | UNIQUE |
| `coach` | varchar(150) | |

### 3.2 `users_organization` — Organization Core

| Field | Type | Notes |
|---|---|---|
| `org_id` | char(20) | **PRIMARY KEY**, sequential (`ORG00001`) |
| `org_type` | varchar(20) | `team`/`vendor`, indexed |
| `name` | varchar(200) | |
| `bg_code` | varchar(10) | FK → `tenant_business_groups.bg_code` |
| `div_code` | varchar(20) | FK → `tenant_divisions.div_code` |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

---

## 4. Tournament Management

### 4.1 Tournament Lifecycle

```
Tournament Created (registration open)
       │
       ▼
Teams Register (player verification, slot allocation)
       │
       ▼
Tournament Active (matches, brackets, scoring)
       │
       ▼
Tournament Completed (results, prizes, rankings)
       │
       ▼
Tournament Archived (historical record)
```

### 4.2 Tournament Data Model (TARGET)

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `tournament_id` | varchar(20) | UNIQUE, sequential |
| `name` | varchar(200) | |
| `game` | varchar(100) | Game title (e.g. Valorant, LoL) |
| `format` | varchar(50) | `single_elim`/`double_elim`/`round_robin` |
| `max_teams` | integer | |
| `registered_teams` | integer | |
| `status` | varchar(20) | `draft`/`open`/`active`/`completed`/`archived` |
| `bg_code` | varchar(10) | FK → `tenant_business_groups.bg_code` |
| `div_code` | varchar(20) | FK → `tenant_divisions.div_code` |
| `start_time` | timestamptz | |
| `end_time` | timestamptz | NULL |
| `prize_pool` | decimal(12,2) | |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

### 4.3 Tournament Registration

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `tournament_id` | bigint | FK → `tournaments.id` |
| `team_id` | varchar(20) | FK → `users_team_profile.org_id` |
| `captain_id` | char(20) | FK → `users_identity.identity_id` |
| `status` | varchar(20) | `pending`/`confirmed`/`cancelled` |
| `created_at` | timestamptz | |

### 4.4 Match Data

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `tournament_id` | bigint | FK → `tournaments.id` |
| `round` | integer | Round number |
| `team_a_id` | varchar(20) | FK → `users_team_profile.org_id` |
| `team_b_id` | varchar(20) | FK → `users_team_profile.org_id` |
| `team_a_score` | integer | |
| `team_b_score` | integer | |
| `winner_id` | varchar(20) | FK → `users_team_profile.org_id` |
| `status` | varchar(20) | `scheduled`/`in_progress`/`completed` |
| `scheduled_time` | timestamptz | |
| `completed_time` | timestamptz | NULL |

---

## 5. API Contract

### 6.1 Current Endpoints (Implemented)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/tournaments/tournaments` | List tournaments | Public |
| `GET` | `/api/v1/tournaments/players` | List players | JWT |
| `GET` | `/api/v1/tournaments/teams` | List teams | Public |
| `POST` | `/api/v1/tournaments/tourneyregister` | Team registration | JWT |

### 6.2 Target Endpoints (Phase 3b)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/tournaments/` | List tournaments | Public |
| `GET` | `/api/v1/tournaments/{id}` | Tournament detail | Public |
| `POST` | `/api/v1/tournaments/{id}/register` | Team registration | JWT |
| `GET` | `/api/v1/tournaments/players/{id}` | Player detail | JWT |
| `GET` | `/api/v1/tournaments/teams/{id}` | Team detail | Public |
| `GET` | `/api/v1/tournaments/games` | Game catalog | Public |

---

## 6. Guardrails

### 7.1 Tenant Isolation

All tournaments queries must include tenant context (`bg_code`, `div_code`):

```python
# Via TenantCollection wrapper
collection = get_collection('games')
games = collection.find({})  # bg_code auto-injected
```

### 7.2 Protocol Enforcement

All domains must use protocol interfaces, not direct DB queries:

```python
# Protocol enforcement: use domain protocols, not direct DB queries
# Package: domains/tournaments/

class TournamentsService:
    def create_tournament(self, name: str, game: str, format: str) -> Tournament:
        # Implementation
        pass

    def register_team(self, tournament_id: int, team_id: str) -> Registration:
        # Implementation
        pass
```

### 7.3 Security

- JWT authentication on all admin endpoints
- No hardcoded credentials — use environment variables
- Input validation on all tournament/registration endpoints
- Rate limiting on public endpoints

---

> **Implementation state:** Basic endpoints (tournaments, players, teams, registration) are implemented in `domains/tournaments/views.py`. Player/team data currently in MongoDB (`players`, `teams` collections). E-commerce backend integration (products, builds, game catalog) is owned by the [E-Commerce spec](./ecommerce_spec.md) and deferred to Phase 3b.