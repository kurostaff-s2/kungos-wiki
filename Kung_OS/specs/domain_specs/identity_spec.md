# Identity Domain Specification

**Status:** Spec — TARGET  
**Date:** 2026-05-17  
**Source:** `KungOS_Identity_Design.md`, `identity_layer.md`, `alignment_audit.md`  
**Purpose:** Authoritative spec for identity domain — unified identity, lookup, extension tables, auth linkage

---

## 1. Domain Overview

The identity domain manages one canonical identity record per person, with type-specific data in extension tables. Organizations (teams, vendors) are separate from people.

### 1.1 Design Principles

| Principle | Description |
|---|---|
| **One identity per person** | `identity_id` is the stable PK. Phone is the universal lookup key. |
| **Extension tables, not polymorphic** | Type-specific data in separate tables with type-specific constraints. |
| **Phone as lookup, not PK** | Phones change. `identity_id` is immutable and sequential. |
| **Tenant-scoped uniqueness** | `(bg_code, phone)` composite unique — same number in different tenants. |
| **No `identity_type` column** | Roles derived from which extension tables have rows. |
| **Auth preserved, not replaced** | `CustomUser` remains Django auth model. Linked via nullable OneToOne. |
| **Organizations separate from people** | Teams/vendors have different schemas, growth rates, query patterns. |

### 1.2 Identity Types

| Type | Extension Table | Source | Count |
|---|---|---|---|
| **Employee** | `users_employee` | `KuroUser` + `employee_attendance` | 31 |
| **Customer** | `users_customer` | `reb_users` + `misc` + `orders.user.phone` + `serviceRequest` | ~4,500 |
| **Player** | `users_player` | `players` (Mongo) | 59 |
| **Walk-in** | `users_identity` (no extension) | `caf_platform_walkins` | TBD |
| **Vendor** | `users_vendor_profile` | `vendors` (Mongo) | 409 |
| **Team** | `users_team_profile` | `teams` (Mongo) | 14 |

---

## 2. Core Identity Table — `users_identity`

### 2.1 Schema

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `identity_id` | char(20) | NOT NULL | — | **PRIMARY KEY**, sequential (`ID000001`) |
| `phone` | varchar | NOT NULL | — | UNIQUE per tenant, E.164 normalized |
| `name` | varchar(200) | NOT NULL | — | Full display name |
| `email` | varchar | NULL | — | UNIQUE, indexed |
| `bg_code` | varchar(10) | NOT NULL | — | FK → `tenant_business_groups.bg_code` |
| `div_code` | varchar(20) | NOT NULL | — | FK → `tenant_divisions.div_code` |
| `branch_code` | varchar(30) | NULL | — | FK → `tenant_branches.branch_code` |
| `status` | varchar(20) | NOT NULL | `'active'` | `active`/`suspended`/`inactive` |
| `phone_verified` | boolean | NOT NULL | `false` | After OTP verification |
| `idproof_type` | varchar(50) | NULL | — | `aadhaar`/`pan`/`passport`/`voter_id` |
| `idproof_number` | varchar(50) | NULL | — | |
| `user` | varchar | NULL | — | **OneToOne** → `users_customuser.userid` |
| `created_at` | timestamptz | NOT NULL | — | |
| `updated_at` | timestamptz | NOT NULL | — | |

### 2.2 Indexes

| Index | Fields | Purpose |
|---|---|---|
| `idx_identity_tenant_phone` | `(bg_code, phone)` | Universal lookup by normalized phone |
| `idx_identity_tenant` | `(bg_code, div_code)` | Tenant-scoped identity queries |
| `idx_identity_email` | `(email)` | Email lookup |
| `idx_identity_status` | `(status)` | Status filtering |

### 2.3 Constraints

| Constraint | Type | Fields | Purpose |
|---|---|---|---|
| `uq_identity_tenant_phone` | UNIQUE | `(bg_code, phone)` | Phone uniqueness within tenant |
| `chk_identity_status` | CHECK | `status` | Valid status values |

### 2.4 Role Derivation

Roles are derived from which extension tables have rows:

```python
@property
def roles(self):
    """Derive roles from which extension tables have rows."""
    roles = []
    if hasattr(self, 'employee_profile'):
        roles.append('employee')
    if hasattr(self, 'customer_profile'):
        roles.append('customer')
    if hasattr(self, 'player_profile'):
        roles.append('player')
    return roles

@property
def primary_role(self):
    """Primary role for display/sorting (employee > customer > player)."""
    priority = {'employee': 1, 'customer': 2, 'player': 3}
    return min(self.roles, key=lambda r: priority.get(r, 99)) if self.roles else 'unknown'
```

---

## 3. Extension Tables

### 3.1 `users_employee` — Employee Extension

**Replaces:** `KuroUser` (employee fields), `employee_attendance.userid` (Mongo)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `identity_id` | char(20) | NOT NULL | **PRIMARY KEY**, FK → `users_identity` |
| `userid` | varchar(20) | NOT NULL | Employee ID (e.g. `KCTM006`), UNIQUE |
| `role` | varchar(20) | NOT NULL | `tech`/`admin`/`staff`/`manager` |
| `department` | varchar(100) | NULL | |
| `joining_date` | date | NOT NULL | |
| `salary` | decimal(12,2) | NULL | |
| `bank_*` | varchar | NULL | 4 bank detail fields |
| `bfc_*` | varchar(200) | NULL | 5 BFC fields |
| `gender` | varchar(20) | NULL | |
| `dob` | date | NULL | |
| `pan` | varchar(10) | NULL | |
| `perm_address_*` | varchar(150) | NULL | 5 permanent address fields |
| `pres_address_*` | varchar(150) | NULL | 5 present address fields |
| `emerg_name` | varchar(150) | NULL | |
| `emerg_phone` | varchar | NULL | |
| `paid_offs` | integer | NOT NULL | Default `0` |
| `available_offs` | integer | NOT NULL | Default `0` |
| `festival_offs` | integer | NOT NULL | Default `0` |
| `created_by` | varchar(150) | NULL | |
| `approved_by` | varchar(150) | NULL | |
| `approved_date` | timestamptz | NULL | |

**Design decisions:**
- 39 of 42 `KuroUser` fields mapped — no data loss
- `businessgroups` JSON → `Identity.bg_code` (single BG, enforced by tenant context)
- `roles` JSON → `rbac_user_roles` table
- `phone_verified`, `idproof_*` → `users_identity` (identity-level, not employee-only)
- `edit` dropped — dead code

### 3.2 `users_customer` — Customer Extension

**Merges:** `reb_users` (1,979), `misc` (1,979 duplicate), `orders.user.phone` (727 unregistered), `serviceRequest.phone` (1,328 requestors)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `identity_id` | char(20) | NOT NULL | **PRIMARY KEY**, FK → `users_identity` |
| `registered` | boolean | NOT NULL | Default `false` |
| `is_requestor` | boolean | NOT NULL | Default `false` |
| `order_count` | integer | NOT NULL | Default `0`, updated via outbox events |
| `total_spent` | decimal(12,2) | NOT NULL | Default `0`, updated via outbox events |
| `last_order_date` | date | NULL | |
| `service_count` | integer | NOT NULL | Default `0`, updated via outbox events |
| `last_service_date` | date | NULL | |

**Design decisions:**
- `registered` + `is_requestor` replaces two separate collections
- `order_count` and `total_spent` are denormalized — updated via outbox events

### 3.3 `users_player` — Player Extension

**Replaces:** `players` collection (MongoDB, 117 docs, 59 unique)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `identity_id` | char(20) | NOT NULL | **PRIMARY KEY**, FK → `users_identity` |
| `player_id` | varchar(20) | NOT NULL | Player ID (e.g. `REPL000001`), UNIQUE |
| `team_id` | varchar(20) | NULL | FK → `users_organization.org_id` |
| `riot_id` | varchar(100) | NULL | Riot Games ID |
| `rank` | varchar(50) | NULL | Current rank |

### 3.4 `users_organization` — Organizations

**Merges:** `teams` (14), `vendors` (409)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `org_id` | char(20) | NOT NULL | **PRIMARY KEY**, sequential (`ORG00001`) |
| `org_type` | varchar(20) | NOT NULL | `team`/`vendor`, indexed |
| `name` | varchar(200) | NOT NULL | |
| `bg_code` | varchar(10) | NOT NULL | FK → `tenant_business_groups` |
| `div_code` | varchar(20) | NOT NULL | FK → `tenant_divisions` |

### 3.5 `users_vendor_profile` — Vendor Extension

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `org_id` | char(20) | NOT NULL | **PRIMARY KEY**, FK → `users_organization` |
| `gstin` | varchar(15) | NOT NULL | UNIQUE |
| `pan` | varchar(10) | NULL | |
| `address` | text | NULL | |
| `payment_type` | varchar(50) | NULL | |
| `contact_phone` | varchar | NULL | |
| `contact_email` | varchar | NULL | |

### 3.6 `users_team_profile` — Team Extension

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `org_id` | char(20) | NOT NULL | **PRIMARY KEY**, FK → `users_organization` |
| `team_id` | varchar(20) | NOT NULL | UNIQUE |
| `coach` | varchar(150) | NULL | |

### 3.7 `team_memberships` — Team-to-Person Mapping

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | bigint | NOT NULL | **PRIMARY KEY** |
| `team_id` | varchar(20) | NOT NULL | FK → `users_team_profile.org_id` |
| `identity_id` | char(20) | NULL | FK → `users_identity.identity_id`, SET_NULL |
| `phone` | varchar | NULL | For unregistered members |
| `name` | varchar(200) | NULL | For unregistered members |
| `role_in_team` | varchar(20) | NOT NULL | `captain`/`member`/`substitute` |
| `bg_code` | varchar(10) | NOT NULL | Tenant scoping |

---

## 4. Identity Lookup Protocol

### 4.1 Universal Lookup Path

All domains route identity lookups through `users_identity.phone` → `identity_id`.

```
Before (per-domain, no dedup):
  orders:      lookup by embedded phone string (no normalization)
  employees:   lookup by userid (KCTM006) → CustomUser → KuroUser
  players:     lookup by playerid (REPL000001) → players collection
  customers:   lookup by phone → reb_users (no normalization)
  requestors:  lookup by phone → serviceRequest (no normalization)

After (single path, normalized):
  all domains: normalize phone → users_identity.lookup(phone) → identity_id
               → join ALL extension tables, return populated profiles
```

### 4.2 Lookup Flow

```
Incoming request with phone number
         │
         ▼
   Normalize phone (+91XXXXXXXXXX)
         │
         ▼
   users_identity.lookup(phone) ──NOT FOUND──► Create walk-in identity
         │
    FOUND
         │
         ▼
   Return identity_id + roles (derived from extensions)
         │
         └─ Join ALL extension tables, return whatever exists:
            ├─ users_employee (if row exists)
            ├─ users_customer (if row exists)
            └─ users_player (if row exists)
```

### 4.3 Phone Normalization

```python
def normalize_phone(raw_phone: str, region: str = 'IN') -> str:
    """Normalize phone to E.164 format."""
    cleaned = re.sub(r'[^\d+]', '', raw_phone)
    parsed = phonenumbers.parse(cleaned, region)
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)

# Test cases
assert normalize_phone("9876543210") == "+919876543210"
assert normalize_phone("+919876543210") == "+919876543210"
assert normalize_phone("02223456789") == "+912223456789"  # landline
assert normalize_phone("00919876543210") == "+919876543210"  # intl format
```

---

## 5. Domain Protocol Updates

### 5.1 Per-Domain Changes

| Domain | Before | After |
|---|---|---|
| **Orders** | `orders.user.phone` (embedded string) | `orders.customer_id` → `users_identity.identity_id` |
| **Employee Attendance** | `employee_attendance.userid` (KCTM006) | `employee_attendance.identity_id` → `users_identity.identity_id` |
| **Service Requests** | `serviceRequest.phone` (embedded string) | `serviceRequest.identity_id` → `users_identity.identity_id` |
| **Players** | `players` collection (Mongo) | `users_player` (PG) + `users_identity` (PG) |
| **Customers** | `reb_users` + `misc` (Mongo) | `users_customer` (PG) + `users_identity` (PG) |
| **Vendors** | `vendors` collection (Mongo) | `users_vendor_profile` (PG) + `users_organization` (PG) |
| **Teams** | `teams` collection (Mongo) | `users_team_profile` (PG) + `users_organization` (PG) |
| **Cafe Walk-ins** | `caf_platform_walkins` (PG) | `CafeWalkin.identity` → `users_identity.identity_id` (FK) |

### 5.2 Outbox Event Contract

Denormalized fields (`order_count`, `total_spent`, `service_count`) are updated via outbox events:

```python
@outbox_handler(event_type='order.placed')
def update_customer_order_metrics(event: dict):
    identity_id = event['customer_id']
    identity = Identity.objects.get(identity_id=identity_id)
    if hasattr(identity, 'customer_profile'):
        customer = identity.customer_profile
        customer.order_count += 1
        customer.total_spent += event['total_amount']
        customer.last_order_date = event['order_date']
        customer.save(update_fields=['order_count', 'total_spent', 'last_order_date'])
```

---

## 6. Cafe Platform Alignment

### 6.1 Current Problems

- `CafeWalkin.phone` is `unique=True` — conflicts with `CustomUser.phone` uniqueness
- `CafeUser` is a thin projection of `CustomUser` — redundant data
- `CafeWallet.customer` FK → `CustomUser` — but walk-ins have wallets too

### 6.2 Resolution

- `CafeWalkin` links to `users_identity` via FK (phone uniqueness dropped)
- `CafeUser` replaced by `users_identity`
- **Wallet links to `users_identity`** (not `CustomUser`) — allows walk-ins to have wallets

**Critical decision:** The Constitution's design is correct. The wallet **must** link directly to `users_identity.identity_id`. This allows both registered users (with credentials) and walk-in customers (unregistered) to utilize wallets seamlessly.

---

## 7. API Contract

### 7.1 Identity Endpoints

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/users/me` | Current user identity + extensions | JWT |
| `GET` | `/api/v1/users/lookup?phone=+91...` | Lookup identity by phone | JWT |
| `POST` | `/api/v1/users/identity` | Create identity (walk-in) | JWT |
| `PATCH` | `/api/v1/users/identity/{id}` | Update identity | JWT |

### 7.2 Response Contract

```json
{
    "identity_id": "ID000001",
    "phone": "+919876543210",
    "name": "John Doe",
    "email": "john@example.com",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001",
    "status": "active",
    "roles": ["employee", "customer"],
    "primary_role": "employee",
    "employee_profile": {
        "userid": "KCTM006",
        "role": "tech",
        "department": "Engineering"
    },
    "customer_profile": {
        "registered": true,
        "order_count": 15,
        "total_spent": 25000.00
    }
}
```

---

## 8. Guardrails

### 8.1 Database Constraints

- `uq_identity_tenant_phone`: UNIQUE `(bg_code, phone)` — phone uniqueness within tenant
- `chk_identity_status`: CHECK `status IN ('active', 'suspended', 'inactive')`
- FK cascade on all extension tables — deleting identity deletes extensions

### 8.2 Application Guardrails

- All identity lookups route through `users_identity.phone` → `identity_id`
- Phone normalization enforced on all writes
- Tenant context required on all queries
- `TenantCollection` wrapper for MongoDB queries

### 8.3 CI/CD Gates

- Phone normalization tests (E.164 format validation)
- Tenant isolation tests (cross-tenant data leak prevention)
- FK integrity tests (no orphaned extension rows)
- Dedup review tests (no duplicate identities)

---

> **Implementation state:** Target architecture only. Current state uses `CustomUser` + `KuroUser`. Migration tracked in `migration_spec.md` (M1). Cafe schema changes tracked in `migration_spec.md` (M2).
