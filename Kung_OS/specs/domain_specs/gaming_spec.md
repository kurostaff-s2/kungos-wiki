# Gaming Domain Specification

**Status:** Spec — TARGET (Phase 3b, Deferred)  
**Date:** 2026-05-17  
**Source:** `KungOS_v2.md`, `KungOS_Endpoint_Design.md`, `kungos_v2_db.md`  
**Purpose:** Authoritative spec for gaming domain — tournaments, players, teams, esports integration

---

## 1. Domain Overview

The gaming domain manages esports operations: tournaments, players, teams, rankings, and gaming backend integration.

### 1.1 Domain Boundaries

| Boundary | Inside Domain | Outside Domain |
|---|---|---|
| **Identity** | Player profiles, team memberships | Auth, RBAC, employee management |
| **Tournaments** | Tournament creation, registration, brackets | Cafe sessions, station management |
| **Players** | Player profiles, rankings, stats | Customer profiles, employee profiles |
| **Teams** | Team rosters, coach info, tournament history | Vendor management, organization registry |

### 1.2 Gaming Backend Integration (Phase 3b)

The `kuro-gaming-dj-backend` codebase provides e-commerce functionality for custom/prebuilt PC sales. Integration adds:

| Component | Count | Notes |
|---|---|---|
| **Django apps** | 5 | `accounts`, `products`, `orders`, `payment`, `games` |
| **MongoDB collections** | 12 | `prods`, `builds`, `kgbuilds`, `custombuilds`, `components`, `accessories`, `monitors`, `networking`, `external`, `games`, `kurodata`, `lists`, `presets` |
| **API endpoints** | 25 | Product catalog, cart, wishlist, addresses, orders, payments, game catalog |

### 1.3 Gaming Backend Issues (from `KungOS_v2.md`)

| Issue | Severity | Notes |
|---|---|---|
| Hardcoded credentials | 9+ | Critical security risk |
| Django 4.1.13 (EOL) | HIGH | Upgrade to 5.2.x |
| `djongo` (deprecated) | HIGH | Replace with PyMongo |
| No multi-tenant support | HIGH | Add `bg_code`/`div_code` to all collections |
| No DRF serializers | MEDIUM | Add serializers for products/games |
| No auth on admin endpoints | HIGH | Add JWT authentication |

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

## 5. Gaming Backend Collections (MongoDB, Phase 3b)

### 5.1 Collection Inventory

| Collection | Purpose | Notes |
|---|---|---|
| `prods` | Product catalog | |
| `builds` | Pre-built PC builds | |
| `kgbuilds` | Kuro Gaming builds | |
| `custombuilds` | Custom PC builds (ordered) | Immutable copies |
| `components` | Hardware components | |
| `accessories` | PC accessories | |
| `monitors` | Monitor catalog | |
| `networking` | Networking equipment | |
| `external` | External products | |
| `games` | Game catalog | |
| `kurodata` | CMS content (hero banners) | |
| `lists` | Preset lists | |
| `presets` | Preset configurations | |

### 5.2 Integration Requirements

1. **Add tenant fields** — `bg_code`, `div_code`, `branch_code` to all documents
2. **Create tenant indexes** — `(bg_code, div_code)` compound indexes
3. **Enable schema validation** — JSON Schema requires tenant fields
4. **Deploy TenantCollection wrapper** — all queries through tenant-isolated wrapper
5. **Migrate from djongo** — replace with PyMongo + `TenantCollection`
6. **Add DRF serializers** — for products, games, builds
7. **Add JWT authentication** — on all admin endpoints
8. **Remove hardcoded credentials** — use environment variables + secrets manager

---

## 6. API Contract

### 6.1 Gaming Endpoints

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/gaming/tournaments` | List tournaments | Public |
| `GET` | `/api/v1/gaming/tournaments/{id}` | Tournament detail | Public |
| `POST` | `/api/v1/gaming/tournaments/{id}/register` | Team registration | JWT |
| `GET` | `/api/v1/gaming/players` | List players | JWT |
| `GET` | `/api/v1/gaming/players/{id}` | Player detail | JWT |
| `GET` | `/api/v1/gaming/teams` | List teams | Public |
| `GET` | `/api/v1/gaming/teams/{id}` | Team detail | Public |
| `GET` | `/api/v1/gaming/games` | Game catalog | Public |
| `GET` | `/api/v1/gaming/products` | Product catalog | Public |
| `GET` | `/api/v1/gaming/builds` | PC builds | Public |

---

## 7. Guardrails

### 7.1 Tenant Isolation

All gaming queries must include tenant context (`bg_code`, `div_code`):

```python
# Via TenantCollection wrapper
collection = get_collection('games')
games = collection.find({})  # bg_code auto-injected
```

### 7.2 Protocol Enforcement

All domains must use protocol interfaces, not direct DB queries:

```python
from gaming.protocols import IGamingTournamentService

class GamingTournamentService(IGamingTournamentService):
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

> **Implementation state:** Gaming domain is deferred to Phase 3b. Player/team data currently in MongoDB (`players`, `teams` collections). Tournament management not yet implemented. Gaming backend integration requires djongo removal, tenant field addition, and DRF serializer creation. Security remediation (hardcoded credentials, EOL Django) is critical prerequisite.
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |