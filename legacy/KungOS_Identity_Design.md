# KungOS Unified Identity Design

**Status:** Draft — pre-Phase 4  
**Date:** 2026-05-14  
**Scope:** Clean deployment of unified PostgreSQL identity system. Legacy data migrated one-time at go-live. No backward-compatibility layer.  
**Deployment Model:** Big-bang cutover — new schema + migrated data deployed together. No shadow mode, no dual-write, no feature flags.  
**Depends on:** KungOS v2 Phase 4 (testing, CI/CD, go-live)  
**Supersedes:** All prior user model reconciliation plans

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Current State — Anti-Patterns](#2-current-state--anti-patterns)
3. [Design Principles](#3-design-principles)
4. [Target Architecture](#4-target-architecture)
5. [Schema Design](#5-schema-design)
   - [5.1 `users_identity` — Core Identity](#51-users_identity--core-identity)
   - [5.1.1 `identity_phone_aliases` — Associated Numbers](#511-identity_phone_aliases--associated-numbers)
   - [5.1.2 `team_memberships` — Team-to-Person Mapping](#512-team_memberships--team-to-person-mapping)
   - [5.2 `users_employee` — Employee Extension](#52-users_employee--employee-extension)
   - [5.3 `users_customer` — Customer Extension](#53-users_customer--customer-extension)
   - [5.4 `users_player` — Player Extension](#54-users_player--player-extension)
   - [5.5 `users_organization` — Organizations](#55-users_organization--organizations)
6. [Domain Protocol Updates](#6-domain-protocol-updates)
7. [Migration Strategy](#7-migration-strategy)
8. [API Contract](#8-api-contract)
9. [Performance Characteristics](#9-performance-characteristics)
10. [Guardrail Compliance](#10-guardrail-compliance)
11. [Risk Register](#11-risk-register)
12. [Deployment & Rollback](#12-deployment--rollback)

---

## 1. Problem Statement

KungOS currently manages identity across **7 user types in 8 storage locations**:

| Type | Count | Storage | Key | Anti-Pattern |
|---|---|---|---|---|
| Employees | 31 | `employee_attendance` (Mongo) + `KuroUser` (PG) | `userid` (KCTM006) | Split across Mongo + PG, no canonical record |
| Players | 59 unique (117 docs) | `players` (Mongo) | `playerid` (REPL000001) | 50% duplication, no phone normalization |
| Customers (registered) | 1,979 | `reb_users` (Mongo) + `misc` (Mongo, 100% dup) | Phone number | 100% duplicate across 2 collections |
| Customers (unregistered) | 727 | Embedded in `orders.user.phone` (Mongo) | Phone number | No canonical record, phone-only lookup |
| Service Requestors | 1,328 | `serviceRequest` (Mongo) | Phone number | 2.3% overlap with customers — silent duplicates |
| Teams | 14 | `teams` (Mongo) | `teamid` | Mixed with players in query patterns |
| Vendors | 409 | `vendors` (Mongo) | GST/PAN | No relationship to customer/vendor orders |
| Auth Users | ~200 | `users_customuser` + `users_kurouser` (PG) | `userid` + `phone` | Two-table split, 42 fields in KuroUser (39 mapped, 3 dropped) |

**Critical overlaps:**
- `reb_users` ↔ `misc`: 100% duplicate (same phone, same userid)
- `orders.user.phone` ↔ `reb_users`: 73% match (727 customers ordered but never registered)
- `serviceRequest.phone` ↔ `reb_users`: 2.3% match (silent duplicates)
- `players.mobile` ↔ `reb_users.phone`: 20% match (same people, different records)
- `players.name` ↔ `reb_users.name`: 25% match (same people, different records)
- `employee_attendance.userid` ↔ `reb_users`: 0% match (different ID schemes)

**Root causes:**
1. **No canonical identity table** — every domain created its own user record
2. **Phone normalization absent** — `+91 98765 43210`, `9876543210`, `919876543210` = 3 different records
3. **MongoDB as identity store** — document store for relational identity data
4. **Two-table user model** — `CustomUser` (auth) + `KuroUser` (profile) = split identity
5. **No dedup strategy** — same person can have 4+ records across collections
6. **Tenant fields inconsistent** — some collections have `bgcode`, some have `bg_code`, some have neither

---

## 2. Current State — Anti-Patterns

### 2.1 Anti-Pattern: Dual-Table User Model

```
users_customuser (16 cols) ──1:1── users_kurouser (42 cols)
       │                              │
       │  userid (PK)                 │  userid (FK → CustomUser.userid)
       │  phone (UNIQUE)              │  gender, dob, bank details, salary, BFC info...
       │  USERNAME_FIELD = 'phone'    │  businessgroups (JSON), primary_bg, roles (JSON)
```

**Problems:**
- `KuroUser` has 42 fields — 39 mapped (31→employee, 3→identity, 4→replaced), 3 dropped (`edit` dead code, `idproof_*` moved to identity).
- `CustomUser.userid` is the PK but format varies (`KCTM006`, `RE000008`) — no neutral join key.
- `KuroUser.businessgroups` is JSON — can't enforce FK integrity to `tenant_business_groups`.
- `KuroUser.roles` is JSON — bypasses the new RBAC system (`rbac_user_roles`).
- No cascade delete: deleting `CustomUser` cascades to `KuroUser`, but orphaned Mongo records remain.

### 2.2 Anti-Pattern: MongoDB as Identity Store

```
reb_users (1,979) ──100% dup── misc (1,979)
players (117) ──50% dup── players (same collection)
employee_attendance (966) ──no profile── KuroUser (31 employees)
serviceRequest (1,625) ──2.3% overlap── reb_users
```

**Problems:**
- No referential integrity — `reb_users.userid` can reference a deleted `CustomUser`.
- No phone normalization — `+91 98765 43210` ≠ `9876543210` in MongoDB.
- No transactional consistency — writing to `reb_users` and `CustomUser` is two independent operations.
- Query performance — cross-collection lookups require application-level joins.
- Tenant filtering — `bgcode` field exists but no compound index on `(bgcode, phone)`.

### 2.3 Anti-Pattern: Cafe Platform Walk-ins

```
caf_platform_walkins (PG) ──phone── caf_platform_wallets (PG)
caf_platform_users (PG) ──FK── users_customuser (PG)
```

**Problems:**
- `CafeWalkin.phone` is `unique=True` — but `CustomUser.phone` is also `unique=True`. Same phone can't exist in both.
- `CafeUser` is a "thin projection" of `CustomUser` — redundant data, update anomalies.
- `CafeWallet.customer` FK → `CustomUser` — but walk-ins have wallets too (via `CafeWalkin`).
- No path from walk-in → registered customer (they're separate tables with no migration path).

**Resolution:** `CafeWalkin` becomes a cafe-specific profile linked to `users_identity` via FK. Phone uniqueness removed from `CafeWalkin` — phone lives in `users_identity` only. Wallet stays on `CustomUser` (auth-bound, not identity-bound).

### 2.4 Anti-Pattern: Orders Reference Customers by Embedded Phone

```json
{
  "user": {
    "phone": "9876543210",
    "name": "John Doe"
  }
}
```

**Problems:**
- No FK to identity table — can't enforce referential integrity.
- Denormalized customer data in every order — name changes require updating all historical orders.
- Phone format varies — `9876543210`, `+919876543210`, `919876543210` in different orders.

---

## 3. Design Principles

### 3.1 Identity Core + Extension Tables

**Not one polymorphic table.** PostgreSQL enforces constraints at the column level — a single table with `entity_type` discriminator can't enforce `gstin NOT NULL` for vendors only, or `player_id NOT NULL` for players only.

**Pattern:** One core identity table (common fields, universal lookup) + type-specific extension tables (type-specific constraints, type-specific indexes).

```
users_identity (core — 1 row per person)
├── users_employee (extension — employees only, NOT NULL on userid, role)
├── users_customer (extension — customers, NOT NULL on registered)
├── users_player (extension — players only, NOT NULL on player_id)
└── users_organization (separate — teams, vendors)
```

### 3.2 Phone as Universal Lookup, Not Primary Key

**Phone is the lookup key, not the identity key.** Reasons:
- Phone numbers change (portability, number recycling).
- Phone format varies (`+91 98765 43210` vs `9876543210`).
- A stable, immutable `identity_id` is the join key across all tables.

**Pattern:**
- `identity_id` (`ID000001`) — stable PK, sequential, zero-padded.
- `phone` — UNIQUE index, normalized to `+91XXXXXXXXXX` format.
- All FKs reference `identity_id`, not `phone`.

### 3.3 PostgreSQL as Identity Store, MongoDB for Operational Data

**Identity = PostgreSQL.** Reasons:
- ACID transactions for identity creation + auth record creation.
- FK constraints enforce referential integrity.
- RBAC tables are already in PostgreSQL — identity must be co-located.
- Wallet tables are already in PostgreSQL — identity must be co-located.

**MongoDB = operational documents.** Orders, invoices, attendance records, service requests — these are append-only or high-volume operational data. They reference `identity_id` but don't store identity data.

### 3.4 Tenant-First on Every Identity Record

Every identity record carries `bg_code`, `div_code`, `branch_code` — consistent with the tenant-first principle. This enables:
- Query-level tenant filtering without joins.
- Compound indexes on `(bg_code, div_code)` + extension table joins.
- Future RLS policies on identity tables.

### 3.5 Auth Layer Preserved, Not Replaced

`CustomUser` remains the Django auth model. The new `users_identity` table has a `OneToOneField` to `CustomUser` for login-capable identities. Phone-only identities (unregistered customers, walk-ins) don't have a `CustomUser` record.

**This is intentional:** Django's auth system requires a `AbstractBaseUser` model. We extend it, not replace it.

### 3.6 Dedup by Normalized Phone

**Dedup strategy:**
1. Normalize all phone numbers to `+91XXXXXXXXXX` (E.164 format).
2. Group by normalized phone.
3. For each group, create one `users_identity` record.

**Conflict resolution:**
- If phone matches across `reb_users` and `serviceRequest` → one identity, `is_requestor=True`.
- If phone matches across `players` and `reb_users` → one identity with both `player_profile` and `customer_profile`.
- If name matches but phone doesn't → flag for manual review (no automatic merge).

---

## 4. Target Architecture

### 4.1 Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    TENANT CONTEXT                               │
│  tenant_business_groups ──┐                                    │
│  tenant_divisions ────────┼──┐                                  │
│  tenant_branches ─────────┘  │                                  │
└──────────────────────────────┼─────────────────────────────────┘                              

┌─────────────────────────────────────────────────────────────────┐
│                    IDENTITY LAYER                               │
│                                                                 │
│  users_identity (core)                                          │
│  ├── bg_code → tenant_business_groups                          │
│  ├── div_code → tenant_divisions                               │
│  ├── branch_code → tenant_branches                             │
│  └── user → users_customuser (auth, nullable)                  │
│                                                                 │
│  users_employee (extension) ──1:1── users_identity             │
│  users_customer (extension) ──1:1── users_identity             │
│  users_player (extension) ──1:1── users_identity               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    ORGANIZATION LAYER                           │
│                                                                 │
│  users_organization (core)                                      │
│  ├── bg_code → tenant_business_groups                          │
│  ├── div_code → tenant_divisions                               │
│  users_vendor_profile (extension) ──1:1── users_organization   │
│  users_team_profile (extension) ──1:1── users_organization     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    AUTH LAYER (preserved)                       │
│                                                                 │
│  users_customuser ──1:1── users_identity.user (nullable)       │
│  rbac_user_roles ──userid→── users_customuser.userid           │
│  rbac_user_permissions ──userid→── users_customuser.userid     │
│  users_user_tenant_context ──userid→── users_customuser.userid │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    CAFE PLATFORM (aligned)                      │
│                                                                 │
│  caf_platform_wallets ──customer→── users_customuser.userid    │
│  caf_platform_walkins ──identity→── users_identity.identity_id │
│  caf_platform_users → REPLACED by users_identity               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    OPERATIONAL DATA (MongoDB, references ID)    │
│                                                                 │
│  orders_core ──customer_id→── users_identity.identity_id       │
│  employee_attendance ──identity_id→── users_identity           │
│  serviceRequest ──identity_id→── users_identity                │
│  players ──DEPRECATED (→ users_identity + users_player)        │
│  reb_users ──DEPRECATED (→ users_identity + users_customer)    │
│  vendors ──DEPRECATED (→ users_organization + users_vendor_profile)│
└─────────────────────────────────────────────────────────────────┘
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

### 4.3 Cross-Reference Queries

```sql
-- "This customer is also a player"
SELECT i.identity_id, i.phone, i.name,
       c.registered, c.order_count,
       p.player_id, p.rank
FROM users_identity i
JOIN users_customer c ON c.identity_id = i.identity_id
JOIN users_player p ON p.identity_id = i.identity_id
WHERE i.bg_code = 'KURO0001';

-- "All employees in a division"
SELECT i.identity_id, i.phone, i.name, e.userid, e.role, e.department
FROM users_identity i
JOIN users_employee e ON e.identity_id = i.identity_id
WHERE i.div_code = 'KURO0001_001';

-- "Customer order history with identity"
SELECT i.name, i.phone, c.order_count, c.total_spent,
       o.orderid, o.total_amount, o.created_at
FROM users_identity i
JOIN users_customer c ON c.identity_id = i.identity_id
JOIN orders_core o ON o.customer_id = i.identity_id
WHERE i.bg_code = 'KURO0001'
ORDER BY o.created_at DESC;
```

---

## 5. Schema Design

### 5.1 `users_identity` — Core Identity

```python
class Identity(models.Model):
    """Unified identity — one row per person, regardless of role.

    Replaces: CustomUser (auth identity), reb_users (customers),
              employee_attendance.userid (employees),
              players.userid (players), serviceRequest.phone (requestors),
              caf_platform_walkins (walk-ins), caf_platform_users (cafe users)

    Phone is the universal lookup key. All cross-domain lookups route
    through phone → identity_id → extension table.
    """

    # ── Primary Key ──────────────────────────────────────────────
    identity_id = models.CharField(
        max_length=20, primary_key=True,
        help_text="Stable ID: ID000001 (sequential, zero-padded, immutable)",
    )

    # ── Universal Lookup ─────────────────────────────────────────
    phone = PhoneNumberField(
        help_text="Normalized E.164: +91XXXXXXXXXX — primary lookup key",
    )
    # NOTE: alternate_phone removed — use IdentityPhoneAlias table instead

    # ── Core Identity Fields ─────────────────────────────────────
    name = models.CharField(
        max_length=200,
        help_text="Full name (display name). Legacy: reb_users.name, players.name, etc.",
    )
    email = models.EmailField(
        null=True, blank=True, unique=True,
        help_text="Email address (nullable — not all identities have email)",
    )

    # ── Tenant Context (codes, not labels) ───────────────────────
    bg_code = models.CharField(
        max_length=10,
        db_index=True,
        help_text="Business group code (e.g. KURO0001). FK to tenant_business_groups.bg_code.",
    )
    div_code = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Division code (e.g. KURO0001_001). FK to tenant_divisions.div_code.",
    )
    branch_code = models.CharField(
        max_length=30, null=True, blank=True,
        db_index=True,
        help_text="Branch code (e.g. KURO0001_001_001). FK to tenant_branches.branch_code.",
    )

    # ── Role Derivation (no identity_type column) ────────────────
    # Roles are derived from which extension tables have rows.
    # A person can be employee + customer + player simultaneously.
    # See @property roles() and primary_role() below.

    # ── Status & Lifecycle ───────────────────────────────────────
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        SUSPENDED = 'suspended', 'Suspended'
        INACTIVE = 'inactive', 'Inactive'

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    # ── Verification & ID Proof ──────────────────────────────────
    phone_verified = models.BooleanField(
        default=False,
        help_text="True after OTP verification. Legacy: KuroUser.phone_verified.",
    )
    idproof_type = models.CharField(
        max_length=50, null=True, blank=True,
        help_text="ID proof type: aadhaar, pan, passport, voter_id, etc. Legacy: KuroUser.idproof_type.",
    )
    idproof_number = models.CharField(
        max_length=50, null=True, blank=True,
        help_text="ID proof number. Legacy: KuroUser.idproof_number.",
    )

    # ── Auth Linkage ─────────────────────────────────────────────
    user = models.OneToOneField(
        'CustomUser',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='identity',
        help_text=(
            "FK to CustomUser for login-capable identities. "
            "NULL for phone-only identities (unregistered customers, walk-ins)."
        ),
    )

    # ── Timestamps ───────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_identity'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['bg_code', 'phone'], name='idx_identity_tenant_phone'),
            models.Index(fields=['bg_code', 'div_code'], name='idx_identity_tenant'),
            models.Index(fields=['email'], name='idx_identity_email'),
            models.Index(fields=['status'], name='idx_identity_status'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['bg_code', 'phone'],
                name='uq_identity_tenant_phone',
            ),
            models.CheckConstraint(
                check=Q(status__in=['active', 'suspended', 'inactive']),
                name='chk_identity_status',
            ),
        ]

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

    def __str__(self):
        return f"{self.identity_id} — {self.name} ({', '.join(self.roles) or 'none'})"
```

**Design decisions:**
- `identity_id` is the PK — not `phone` (phones change), not `CustomUser.userid` (format varies by type).
- `phone` is tenant-scoped unique (`bg_code` + `phone`) — same number can exist in different tenants.
- No `identity_type` column — roles derived from which extension tables have rows. A person can be employee + customer + player.
- `alternate_phone` removed — use `IdentityPhoneAlias` table for associated numbers (secondary, previous, shared, emergency).
- `user` FK is nullable — phone-only identities don't need auth records.
- Tenant fields are denormalized — query performance over normalization (consistent with tenant-first principle).

### 5.1.1 `identity_phone_aliases` — Associated Numbers

```python
class IdentityPhoneAlias(models.Model):
    """Associated phone numbers for an identity.
    
    Use cases:
    - Secondary number (personal vs work)
    - Previous number (portability history)
    - Shared family/business line
    - Emergency contact
    """
    identity = models.ForeignKey(
        Identity, on_delete=models.CASCADE,
        related_name='phone_aliases',
    )
    phone = PhoneNumberField(
        help_text="Normalized associated number (E.164)",
    )
    alias_type = models.CharField(
        max_length=20,
        choices=[
            ('secondary', 'Secondary number'),
            ('previous', 'Previous number (portability)'),
            ('shared', 'Shared family/business line'),
            ('emergency', 'Emergency contact'),
        ],
        default='secondary',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'identity_phone_aliases'
        constraints = [
            models.UniqueConstraint(
                fields=['identity', 'alias_type', 'phone'],
                name='uq_identity_alias_phone',
            ),
        ]
    
    def __str__(self):
        return f"{self.identity.identity_id} — {self.phone} ({self.alias_type})"
```

### 5.1.2 `team_memberships` — Team-to-Person Mapping

```python
class TeamMembership(models.Model):
    """Maps people to teams. Person may or may not have a registered identity.
    
    Supports:
    - Registered players (identity FK)
    - Unregistered members (phone + name only)
    - Role in team (captain, member, substitute)
    - Tenant scoping (bg_code)
    """
    team = models.ForeignKey(
        'TeamProfile', on_delete=models.CASCADE,
        related_name='memberships',
    )
    identity = models.ForeignKey(
        Identity, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='team_memberships',
    )
    phone = PhoneNumberField(
        null=True, blank=True,
        help_text="For unregistered members — phone-only reference",
    )
    name = models.CharField(
        max_length=200, null=True, blank=True,
        help_text="For unregistered members — display name",
    )
    role_in_team = models.CharField(
        max_length=20,
        choices=[('captain', 'Captain'), ('member', 'Member'), ('substitute', 'Substitute')],
        default='member',
    )
    bg_code = models.CharField(
        max_length=10, db_index=True,
        help_text="Tenant scoping — prevents cross-tenant team membership",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'team_memberships'
        constraints = [
            models.CheckConstraint(
                check=Q(identity__isnull=False) | Q(phone__isnull=False),
                name='chk_membership_has_reference',
            ),
            models.UniqueConstraint(
                fields=['team', 'identity'],
                condition=Q(identity__isnull=False),
                name='uq_team_identity',
            ),
            models.UniqueConstraint(
                fields=['team', 'phone'],
                condition=Q(phone__isnull=False),
                name='uq_team_phone',
            ),
        ]
    
    def __str__(self):
        ref = self.identity.identity_id if self.identity else self.phone
        return f"{self.team.team_id} — {ref} ({self.role_in_team})"
```

### 5.2 `users_employee` — Employee Extension

```python
class Employee(models.Model):
    """Employee-specific data. One row per employee identity.

    Replaces: KuroUser (employee fields), employee_attendance.userid (Mongo)
    """

    identity = models.OneToOneField(
        Identity,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='employee_profile',
    )

    # ── Employee ID ──────────────────────────────────────────────
    userid = models.CharField(
        max_length=20, unique=True,
        help_text="Employee ID (e.g. KCTM006, KCAD001)",
    )

    # ── Employee-Specific Fields ─────────────────────────────────
    class Role(models.TextChoices):
        TECH = 'tech', 'Tech'
        ADMIN = 'admin', 'Admin'
        STAFF = 'staff', 'Staff'
        MANAGER = 'manager', 'Manager'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        help_text="Employee role (NOT Django is_staff/is_superuser — those are auth flags)",
    )
    department = models.CharField(
        max_length=100, null=True, blank=True,
    )
    joining_date = models.DateField()

    # ── Compensation (from KuroUser) ────────────────────────────
    salary = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )

    # ── Bank Details (from KuroUser) ────────────────────────────
    bank_name = models.CharField(max_length=150, null=True, blank=True)
    bank_account_no = models.CharField(max_length=50, null=True, blank=True)
    bank_ifsc = models.CharField(max_length=20, null=True, blank=True)
    bank_branch = models.CharField(max_length=150, null=True, blank=True)

    # ── BFC (Business Facilitation Center) ──────────────────────
    bfc_code = models.CharField(max_length=200, null=True, blank=True)
    bfc_name = models.CharField(max_length=200, null=True, blank=True)
    bfc_account_no = models.CharField(max_length=200, null=True, blank=True)
    bfc_branch = models.CharField(max_length=200, null=True, blank=True)
    bfc_ifsc = models.CharField(max_length=200, null=True, blank=True)

    # ── Personal (from KuroUser) ────────────────────────────────
    gender = models.CharField(max_length=20, null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    pan = models.CharField(max_length=10, null=True, blank=True)

    # ── Address (from KuroUser) ─────────────────────────────────
    perm_address_line1 = models.CharField(max_length=150, null=True, blank=True)
    perm_address_line2 = models.CharField(max_length=150, null=True, blank=True)
    perm_address_city = models.CharField(max_length=150, null=True, blank=True)
    perm_address_state = models.CharField(max_length=150, null=True, blank=True)
    perm_address_pincode = models.CharField(max_length=10, null=True, blank=True)
    pres_address_line1 = models.CharField(max_length=150, null=True, blank=True)
    pres_address_line2 = models.CharField(max_length=150, null=True, blank=True)
    pres_address_city = models.CharField(max_length=150, null=True, blank=True)
    pres_address_state = models.CharField(max_length=150, null=True, blank=True)
    pres_address_pincode = models.CharField(max_length=10, null=True, blank=True)

    # ── Emergency Contact (from KuroUser) ───────────────────────
    emerg_name = models.CharField(max_length=150, null=True, blank=True)
    emerg_phone = PhoneNumberField(null=True, blank=True)

    # ── Leave Tracking (from KuroUser) ──────────────────────────
    paid_offs = models.IntegerField(default=0)
    available_offs = models.IntegerField(default=0)
    festival_offs = models.IntegerField(default=0)

    # ── Approval Workflow (from KuroUser) ───────────────────────
    created_by = models.CharField(max_length=150, null=True, blank=True)
    approved_by = models.CharField(max_length=150, null=True, blank=True)
    approved_date = models.DateTimeField(null=True, blank=True)

    # ── Timestamps ───────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_employee'
        ordering = ['userid']
        indexes = [
            models.Index(fields=['userid'], name='idx_employee_userid'),
            models.Index(fields=['role'], name='idx_employee_role'),
            models.Index(fields=['department'], name='idx_employee_department'),
        ]

    def __str__(self):
        return f"{self.userid} — {self.identity.name} ({self.role})"
```

**Design decisions:**
- **39 of 42 `KuroUser` fields mapped** — no data loss.
- `userid` is the employee ID — migrated from `KuroUser`.
- `businessgroups` JSON field from `KuroUser` is **replaced** by `Identity.bg_code` (single BG, enforced by tenant context).
- `roles` JSON field from `KuroUser` is **replaced** by `rbac_user_roles` table.
- `phone_verified`, `idproof_type`, `idproof_number` moved to `users_identity` (identity-level, not employee-only).
- `edit` dropped — dead code (never read, only written as `False` on profile update).

### 5.3 `users_customer` — Customer Extension

```python
class Customer(models.Model):
    """Customer and service requestor data.

    Merges: reb_users (1,979), misc users (1,979 duplicate),
            orders.user.phone (727 unregistered),
            serviceRequest.phone (1,328 requestors)

    Dedup strategy: phone normalization (+91 prefix, strip spaces/dashes).
    If a requestor's phone matches a customer → same row, is_requestor=True.
    """

    identity = models.OneToOneField(
        Identity,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='customer_profile',
    )

    # ── Registration Status ──────────────────────────────────────
    registered = models.BooleanField(
        default=False,
        help_text=(
            "True = in reb_users (has login/auth record). "
            "False = phone-only from orders/service requests."
        ),
    )

    # ── Service Requestor Flag ───────────────────────────────────
    is_requestor = models.BooleanField(
        default=False,
        help_text=(
            "True = has filed service requests. "
            "Can be True alongside registered=True (customer who also files SRs)."
        ),
    )

    # ── Order Metrics (computed, updated via outbox events) ──────
    order_count = models.IntegerField(
        default=0,
        help_text="Denormalized count — updated via order.placed outbox event",
    )
    total_spent = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Denormalized sum — updated via order.paid outbox event",
    )
    last_order_date = models.DateField(null=True, blank=True)

    # ── Service Request Metrics ──────────────────────────────────
    service_count = models.IntegerField(
        default=0,
        help_text="Denormalized count — updated via service_request.created outbox event",
    )
    last_service_date = models.DateField(null=True, blank=True)

    # ── Timestamps ───────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_customer'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['registered'], name='idx_customer_registered'),
            models.Index(fields=['is_requestor'], name='idx_customer_requestor'),
            models.Index(fields=['order_count'], name='idx_customer_orders'),
            models.Index(fields=['total_spent'], name='idx_customer_spent'),
        ]

    def __str__(self):
        return f"{self.identity.identity_id} — {self.identity.name} (customer)"
```

**Design decisions:**
- `registered` + `is_requestor` replaces two separate collections (`reb_users` + `serviceRequest`).
- `order_count` and `total_spent` are denormalized — updated via outbox events, not raw writes.

### 5.4 `users_player` — Player Extension

```python
class Player(models.Model):
    """Player-specific data. One row per player identity.

    Replaces: players collection (MongoDB)
    """

    identity = models.OneToOneField(
        Identity,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='player_profile',
    )

    # ── Player-Specific Fields ───────────────────────────────────
    player_id = models.CharField(
        max_length=20, unique=True,
        help_text="Player ID (e.g. REPL000001)",
    )
    team = models.ForeignKey(
        'Organization', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='player_teams',
        help_text="FK to users_organization — player's primary team",
    )
    riot_id = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="Riot Games ID (for Valorant/LoL players)",
    )
    rank = models.CharField(
        max_length=50, null=True, blank=True,
        help_text="Current rank (e.g. Diamond, Immortal)",
    )

    # ── Timestamps ───────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_player'
        ordering = ['player_id']
        indexes = [
            models.Index(fields=['player_id'], name='idx_player_id'),
            models.Index(fields=['team_id'], name='idx_player_team'),
            models.Index(fields=['rank'], name='idx_player_rank'),
        ]

    def __str__(self):
        return f"{self.player_id} — {self.identity.name}"
```

### 5.5 `users_organization` — Organizations

```python
class Organization(models.Model):
    """Organizations: teams and vendors.

    Merges: teams (14), vendors (409)
    """

    org_id = models.CharField(
        max_length=20, primary_key=True,
        help_text="Stable org ID: ORG00001 (sequential, zero-padded)",
    )

    class OrgType(models.TextChoices):
        TEAM = 'team', 'Team'
        VENDOR = 'vendor', 'Vendor'

    org_type = models.CharField(
        max_length=20,
        choices=OrgType.choices,
        db_index=True,
    )

    # ── Common Fields ────────────────────────────────────────────
    name = models.CharField(max_length=200)

    # ── Tenant Context ───────────────────────────────────────────
    bg_code = models.CharField(max_length=10, db_index=True)
    div_code = models.CharField(max_length=20, db_index=True)

    # ── Timestamps ───────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_organization'
        ordering = ['name']
        indexes = [
            models.Index(fields=['bg_code', 'div_code'], name='idx_org_tenant'),
            models.Index(fields=['org_type'], name='idx_org_type'),
        ]

    def __str__(self):
        return f"{self.org_id} — {self.name} ({self.org_type})"


class VendorProfile(models.Model):
    """Vendor-specific data.

    Replaces: vendors collection (MongoDB)
    """

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='vendor_profile',
    )

    gstin = models.CharField(max_length=15, unique=True)
    pan = models.CharField(max_length=10, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    payment_type = models.CharField(max_length=50, null=True, blank=True)
    contact_phone = PhoneNumberField(null=True, blank=True)
    contact_email = models.EmailField(null=True, blank=True)

    class Meta:
        db_table = 'users_vendor_profile'

    def __str__(self):
        return f"{self.organization.name} (vendor)"


class TeamProfile(models.Model):
    """Team-specific data.

    Replaces: teams collection (MongoDB)
    """

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='team_profile',
    )

    team_id = models.CharField(max_length=20, unique=True)
    coach = models.CharField(max_length=150, null=True, blank=True)

    class Meta:
        db_table = 'users_team_profile'

    def __str__(self):
        return f"{self.team_id} — {self.organization.name}"
```

**Design decisions:**
- `Organization` is separate from `Identity` — teams/vendors are organizations, not people. Different query patterns, different growth rates, different schemas.
- `VendorProfile` and `TeamProfile` are extension tables on `Organization` — same pattern as identity extensions.
- `Player.team_id` → `users_organization.org_id` — players link to teams via the organization table.
- `gstin` is `unique=True` on `VendorProfile` — enforces GST-level dedup at the database level.

---

## 6. Domain Protocol Updates

### 6.1 Identity Lookup Protocol

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

### 6.2 Domain-Specific Protocol Changes

| Domain | Before | After |
|---|---|---|
| **Orders** | `orders.user.phone` (embedded string) | `orders.customer_id` → `users_identity.identity_id` |
| **Employee Attendance** | `employee_attendance.userid` (KCTM006) | `employee_attendance.identity_id` → `users_identity.identity_id` |
| **Service Requests** | `serviceRequest.phone` (embedded string) | `serviceRequest.identity_id` → `users_identity.identity_id` |
| **Players** | `players` collection (Mongo) | `users_player` (PG) + `users_identity` (PG) |
| **Customers** | `reb_users` + `misc` (Mongo) | `users_customer` (PG) + `users_identity` (PG) |
| **Vendors** | `vendors` collection (Mongo) | `users_vendor_profile` (PG) + `users_organization` (PG) |
| **Teams** | `teams` collection (Mongo) | `users_team_profile` (PG) + `users_organization` (PG) |
| **Cafe Walk-ins** | `caf_platform_walkins` (PG) | `CafeWalkin.identity` → `users_identity.identity_id` (FK, cafe-specific profile) |

### 6.3 Outbox Event Contract

Denormalized fields (`order_count`, `total_spent`, `service_count`) are updated via outbox events, not raw writes.

```python
# Example: order.placed event → update customer metrics
@outbox_handler(event_type='order.placed')
def update_customer_order_metrics(event: dict):
    identity_id = event['customer_id']
    identity = Identity.objects.get(identity_id=identity_id)
    if hasattr(identity, 'customer_profile'):
        customer = identity.customer_profile
        customer.order_count += 1
        customer.total_spent += event['total_amount']
        customer.last_order_date = event['order_date']
        customer.save(update_fields=['order_count', 'total_spent', 'last_order_date', 'updated_at'])
```

### 6.4 Phone Normalization Protocol

All phone numbers are normalized to E.164 format (`+91XXXXXXXXXX`) before storage or lookup.

```python
import phonenumbers
from phonenumbers import PhoneNumberFormat, NumberParseException

def normalize_phone(raw_phone: str, region: str = 'IN') -> str:
    """Normalize phone to E.164 format.
    
    Let phonenumbers library handle ALL edge cases:
    - Indian mobiles: 9876543210 → +919876543210
    - Indian landlines: 02223456789 → +912223456789 (strips leading 0)
    - International format: 00919876543210 → +919876543210
    - Already E.164: +919876543210 → +919876543210
    
    region is tenant-configurable for future international expansion.
    """
    # Strip only non-digit/non-plus characters
    cleaned = re.sub(r'[^\d+]', '', raw_phone)
    
    try:
        parsed = phonenumbers.parse(cleaned, region)
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError(f"Invalid number: {raw_phone}")
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except NumberParseException as e:
        raise ValueError(f"Can't parse {raw_phone}: {e}")

# Test cases
assert normalize_phone("9876543210") == "+919876543210"
assert normalize_phone("+919876543210") == "+919876543210"
assert normalize_phone("02223456789") == "+912223456789"  # landline
assert normalize_phone("00919876543210") == "+919876543210"  # intl format
```

---

## 7. Migration Strategy

### 7.1 Pre-Deployment: Data Import Script

Single Django management command reads all legacy sources, deduplicates, and writes to new tables.

```
python manage.py migrate_identity --source=<mongo_uri> --validate

Step 1: Read & normalize
  ├── reb_users (1,979) → normalize phone → dedup by phone
  ├── misc (1,979) → SKIP (100% duplicate of reb_users)
  ├── players (117 docs, 59 unique) → normalize phone → dedup by phone
  ├── employee_attendance.userid (31 unique) → cross-ref CustomUser.phone
  ├── KuroUser (31 employees) → merge into employee records
  ├── serviceRequest.phone (1,328 unique) → normalize phone → dedup by phone
  ├── orders.user.phone (727 unregistered) → normalize phone → dedup by phone
  ├── teams (14) → import as organizations
  └── vendors (409) → import as organizations

Step 2: Cross-reference & merge (with name matching)
  ├── Same phone + same name → auto-merge (confidence 99%)
  ├── Same phone + fuzzy name match (>85% similarity) → merge with warning
  ├── Same phone + different name (<85% similarity) → flag for manual review
  ├── serviceRequest.phone ↔ reb_users.phone (30 matches → is_requestor=True)
  ├── players.mobile ↔ reb_users.phone (12 matches → dual: player_profile + customer_profile)
  ├── orders.user.phone ↔ reb_users.phone (73% match → registered=False for 727 unregistered)
  └── employee_attendance.userid ↔ CustomUser.phone (31 matches → employee_profile)

Step 3: Flag for manual review (dedup_review table)
  ├── 15 players with matching names but no phone match
  ├── Invalid phone numbers (format can't be normalized)
  ├── Same phone + different name across collections (conflict resolution needed)
  └── Name similarity 85-98% (needs human confirmation before merge)

```python
from difflib import SequenceMatcher

def should_merge(records: list[dict]) -> tuple[bool, str]:
    """Determine if records with same phone should be merged.
    
    Returns: (should_merge, reason)
    """
    names = [r.get('name', '').strip().lower() for r in records]
    unique_names = set(names)
    
    if len(unique_names) == 1:
        return True, "exact_name_match"
    
    # Fuzzy match: >85% similarity = likely same person
    for i, name1 in enumerate(names):
        for name2 in names[i+1:]:
            similarity = SequenceMatcher(None, name1, name2).ratio()
            if similarity > 0.85:
                return True, f"fuzzy_match ({similarity:.1%})"
    
    # Different names = different people sharing phone
    return False, "name_mismatch"

Step 4: Write to new tables (single transaction per batch)
  ├── users_identity (core record for each unique phone)
  ├── users_employee (31 rows)
  ├── users_customer (~4,500 rows)
  ├── users_player (59 rows)
  ├── users_organization (423 rows)
  ├── users_vendor_profile (409 rows)
  ├── users_team_profile (14 rows)
  └── caf_platform_walkins (backfill identity FK, drop phone uniqueness)
      ├── UPDATE caf_platform_walkins SET identity_id = (
      │     SELECT i.identity_id FROM users_identity i WHERE i.phone = caf_platform_walkins.phone
      │   ) WHERE identity_id IS NULL
      ├── ALTER TABLE caf_platform_walkins DROP CONSTRAINT caf_platform_walkins_phone_key
      └── ALTER TABLE caf_platform_walkins ALTER COLUMN identity_id SET NOT NULL
```

### 7.2 Deployment Steps

```
Step 1: Apply Django migrations (create empty tables + indexes)
Step 2: Run migrate_identity management command (import + dedup)
Step 3: Run --validate flag (row count checks, phone normalization checks)
Step 4: Deploy application code (all views use new Identity models)
Step 5: Verify health checks + smoke tests
Step 6: Legacy MongoDB collections remain untouched (eventual cleanup, not blocking)
```

### 7.3 Executable Validation (`--validate` flag)

```
python manage.py migrate_identity --validate

Runs assertions after import. Blocks deployment if any fail.

✅ Row count reconciliation per source:
   reb_users: 1979 source → 1979 output (0 dropped)
   players: 117 source → 59 output (58 duplicates merged)
   employees: 31 source → 31 output (0 dropped)
   vendors: 409 source → 409 output (0 dropped)
   teams: 14 source → 14 output (0 dropped)

✅ Phone normalization: 0 invalid numbers
✅ Dedup review: 12 rows flagged (manual resolution required)
✅ Phone uniqueness per tenant: 0 duplicates
✅ FK integrity: 0 orphaned extension rows
✅ CafeWalkin.identity FK coverage: 0 NULLs (all walk-ins linked to identity)
✅ Tenant codes: 0 invalid bg_code/div_code
✅ Auth linkage: 0 phone-only identities with CustomUser
✅ Financial data loss check: total_spent sum matches legacy orders
✅ Index creation: all indexes built
✅ Constraint validation: all CHECK constraints pass

❌ If any check fails:
   Migration aborted. Fix flagged rows and re-run.
   Reconciliation report saved to /tmp/migration_report_{timestamp}.json
```

### 7.4 Legacy Collection Disposition

```
Legacy collections are NOT deleted as part of this deployment.
They remain in MongoDB as read-only archives until explicitly dropped.

  ├── reb_users, misc → archive (no new writes after deployment)
  ├── players → archive
  ├── vendors, teams → archive
  ├── KuroUser → archive (fields migrated to users_employee)
  └── serviceRequest → phone field replaced with identity_id in new writes

Drop decision is separate from this deployment — no timeline attached.
```

---

## 8. API Contract

### 8.1 Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/v2/identity/lookup/` | `GET` | Lookup identity by phone (normalized) |
| `/api/v2/identity/{identity_id}/` | `GET` | Get full identity + extension profile |
| `/api/v2/identity/{identity_id}/employee/` | `GET/PATCH` | Employee extension CRUD |
| `/api/v2/identity/{identity_id}/customer/` | `GET/PATCH` | Customer extension CRUD |
| `/api/v2/identity/{identity_id}/player/` | `GET/PATCH` | Player extension CRUD |
| `/api/v2/organization/` | `GET/POST` | Organization list/create |
| `/api/v2/organization/{org_id}/` | `GET/PATCH/DELETE` | Organization CRUD |
| `/api/v2/identity/dedup/` | `POST` | Trigger dedup analysis (admin only) |

All endpoints use the new Identity models. No v1 endpoints.

### 8.2 Response Format Changes

```
Before (per-domain, no unified identity):
{
  "userid": "KCTM006",
  "phone": "9876543210",
  "name": "John Doe",
  "role": "tech",
  "department": "Engineering"
}

After (unified identity + extension):
{
  "identity": {
    "identity_id": "ID000001",
    "phone": "+919876543210",
    "name": "John Doe",
    "email": "john@example.com",
    "roles": ["employee", "customer"],  # derived from extensions
    "status": "active",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001",
    "branch_code": "KURO0001_001_001"
  },
  "employee_profile": {
    "userid": "KCTM006",
    "role": "tech",
    "department": "Engineering",
    "joining_date": "2024-01-15",
    "bank_name": "HDFC Bank",
    "bank_account_no": "XXXXXXXX1234",
    "bank_ifsc": "HDFC0001234"
  }
}
```

---

## 9. Performance Characteristics

### 9.1 Query Performance

| Operation | Index Used | Complexity |
|---|---|---|
| Lookup by phone | `idx_identity_phone` (unique B-tree) | O(1) |
| All employees in BG | `idx_identity_tenant` + EXISTS(users_employee) | O(log n) |
| Customer order history | `users_customer.order_count` (denormalized) | O(1) |
| Player → Team | `users_player.team_id` → `users_organization.org_id` | O(log n) |
| Vendor by GSTIN | `users_vendor_profile.gstin` (unique B-tree) | O(1) |
| Cross-ref: customer who is also player | `users_identity.phone` join | O(log n) |
| All identities in tenant | `idx_identity_tenant` (composite bg+div) | O(log n) |
| All identities by type in tenant | `idx_identity_full` (bg+div+type) | O(log n) |

### 9.2 Expected Row Counts (Post-Migration)

| Table | Estimated Rows | Growth Rate |
|---|---|---|
| `users_identity` | ~5,000 | +500/month (customers dominate) |
| `users_employee` | ~31 | +1/month |
| `users_customer` | ~4,500 | +400/month |
| `users_player` | ~59 | +5/month |
| `users_organization` | ~423 | +10/month (vendors dominate) |
| `users_vendor_profile` | ~409 | +8/month |
| `users_team_profile` | ~14 | +1/quarter |

### 9.3 Index Strategy

```
users_identity:
  ├── idx_identity_phone (unique) — primary lookup
  ├── idx_identity_tenant (bg_code, div_code) — tenant filtering
  ├── idx_identity_tenant_phone (bg_code, phone) — primary lookup
  ├── idx_identity_tenant (bg_code, div_code) — tenant filtering
  ├── idx_identity_email — email lookup
  ├── idx_identity_alt_phone — alternate phone lookup
  └── idx_identity_status — status filtering

users_employee:
  ├── idx_employee_userid — employee ID lookup
  ├── idx_employee_role — role filtering
  └── idx_employee_department — department filtering

users_customer:
  ├── idx_customer_registered — registration filtering
  ├── idx_customer_requestor — requestor filtering
  ├── idx_customer_orders — order count sorting
  └── idx_customer_spent — spending sorting

users_player:
  ├── idx_player_id — player ID lookup
  ├── idx_player_team — team membership
  └── idx_player_rank — rank filtering

users_organization:
  ├── idx_org_tenant (bg_code, div_code) — tenant filtering
  └── idx_org_type — type filtering
```

---

## 10. Guardrail Compliance

### 10.1 Tenant-First Compliance

| Requirement | Status | Implementation |
|---|---|---|
| bg_code, div_code, branch_code on every identity | ✅ | Denormalized on `users_identity` |
| Codes for logic, no labels | ✅ | All tenant fields use codes (e.g., `KURO0001`) |
| Query-level tenant filtering | ✅ | Composite indexes on `(bg_code, div_code)` |
| No cross-tenant data leakage | ✅ | Tenant codes enforced at application layer |

### 10.2 PostgreSQL as Relational Backbone

| Requirement | Status | Implementation |
|---|---|---|
| Identity in PG, not Mongo | ✅ | All identity data in PostgreSQL |
| FK constraints enforced | ✅ | `users_employee.identity_id` → `users_identity.identity_id` |
| ACID transactions | ✅ | Identity creation + auth record creation in single transaction |
| No raw Mongo access for identity | ✅ | MongoDB stores operational data only |

### 10.3 Naming Conventions

| Requirement | Status | Implementation |
|---|---|---|
| snake_case table names | ✅ | `users_identity`, `users_employee`, etc. |
| `_code` suffix for tenant fields | ✅ | `bg_code`, `div_code`, `branch_code` |
| `_id` suffix for FKs | ✅ | `identity_id`, `org_id`, `player_id` |
| No label-based scoping | ✅ | All scoping by code, not name |

### 10.4 Architecture Alignment

| Requirement | Status | Implementation |
|---|---|---|
| Repository → Service → View pattern | ✅ | New Django models enable proper layering |
| Outbox pattern for denormalized fields | ✅ | `order_count`, `total_spent` updated via events |
| RBAC compatibility | ✅ | `user` FK to `CustomUser` preserves role assignment chain |
| No label-based tenant filtering | ✅ | All tenant filtering by `bg_code`, `div_code` |

---

## 11. Risk Register

### 11.1 Identified Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Phone normalization fails for edge cases (landlines, extension numbers) | Medium | Medium | Manual review queue for unnormalizable numbers; allow raw storage with flag |
| R2 | 117 vs 59 player doc discrepancy — duplicates or multi-tenant records | High | High | Pre-migration audit of players collection; flag all duplicates for review |
| R3 | KuroUser has 42 fields — incomplete mapping risks data loss | Medium | Resolved | Field mapping complete: 31→employee, 3→identity, 4→replaced, 3→dropped. Migration script validates row counts. |
| R4 | 727 unregistered customers have no auth record — identity creation without CustomUser | Low | Low | Explicitly supported by nullable `user` FK; phone-only identities are designed for this |
| R5 | Cafe walk-in merge creates conflicts with `CustomUser.phone` uniqueness | Medium | Medium | `CafeWalkin.identity` FK → `users_identity`; drop `CafeWalkin.phone` unique constraint; wallet stays on `CustomUser` |
| R6 | Service request phone ↔ customer phone overlap (2.3%) causes silent merge errors | Low | Low | Dedup script with manual review for conflicts; `is_requestor` flag preserves both identities |
| R7 | Player ↔ customer overlap (20% by phone, 25% by name) causes identity confusion | Medium | Medium | One identity with both `player_profile` and `customer_profile`; name-only matches flagged for review |
| R8 | Data import script runs too long for deployment window | Low | Medium | Batch processing with progress tracking; estimated < 5 min for ~5K rows |

### 11.2 Risk Mitigation Timeline

```
Pre-Deployment:
  ├── R2: Audit players collection for duplicates
  ├── R3: Complete KuroUser field mapping
  └── R7: Pre-compute player ↔ customer overlap matrix

Deployment:
  ├── R1: Phone normalization with fallback
  ├── R6: Dedup script with manual review queue
  └── R8: Batch import with progress tracking

Post-Deployment:
  ├── R4: Validate phone-only identities
  └── R5: Backfill `CafeWalkin.identity` FK, drop phone uniqueness
```

---

## 12. Deployment & Rollback

### 12.1 Deployment Checklist

```
[ ] Django migrations applied (tables + indexes + constraints created)
[ ] migrate_identity command run with --validate flag
[ ] Row count validation passes (see Section 7.3)
[ ] FK integrity verified (all extension rows have valid identity_id)
[ ] Health checks pass
[ ] Smoke tests pass (identity lookup, employee query, customer query, player query)
[ ] Legacy MongoDB collections untouched (read-only archive)
```

### 12.2 Rollback Triggers

| Condition | Action |
|---|---|
| Data import fails (row count mismatch > 1%) | TRUNCATE new tables, fix script, re-run |
| Phone normalization failure rate > 5% | Fix normalization logic, re-run import |
| FK integrity violations detected | TRUNCATE new tables, fix mapping, re-run |
| Critical bug in application code | Rollback application code; new tables remain (empty or partial) |

### 12.3 Rollback Procedure

```
Scenario A: Schema migration fails
  └── Action: Django migrate --fake-zero + DROP tables
      Risk: None (no data written)

Scenario B: Data import produces incorrect results
  └── Action: TRUNCATE new tables + re-run import with fixed logic
      Risk: Low (legacy MongoDB data untouched)

Scenario C: Application code has critical bug
  └── Action: Rollback application deployment (previous version still uses legacy Mongo)
      Risk: Low (legacy MongoDB collections still available)

Scenario D: Full rollback
  └── Action:
      1. Rollback application code to previous version
      2. TRUNCATE new tables
      3. DROP new tables (optional, preserve for re-attempt)
      4. Root cause analysis + fix
      5. Re-attempt deployment
```

### 12.4 Key Property

```
Legacy MongoDB collections are NEVER deleted as part of this deployment.
This means:
  ├── Rollback is always data-loss-free.
  ├── Legacy data is always available for comparison/validation.
  └── Full rollback = revert application code + drop new tables.
```

---

## Appendix A: What This Doesn't Solve (Yet)

### A1. Player Document Discrepancy (117 vs 59)

The `players` collection has 117 documents but only 59 unique identities. Before migration, verify:
- Are the 58 extra documents duplicates (same player, multiple records)?
- Are they multi-tenant records (same player in multiple BGs)?
- Are they historical records (retired players, inactive accounts)?

**Action:** Pre-migration audit script to classify all 117 documents.

### A2. KuroUser Field Mapping — Complete

All 42 KuroUser fields accounted for:
- **31 → `users_employee`**: salary, bank, BFC, addresses, leave, emergency, approval workflow, personal
- **3 → `users_identity`**: `phone_verified`, `idproof_type`, `idproof_number`
- **4 → replaced**: `businessgroups`/`primary_bg` → `Identity.bg_code`; `roles`/`access` → RBAC tables
- **1 → dropped**: `edit` (dead code, never read, only written as `False` on profile update)

**Status:** ✅ Field mapping complete. Migration script must validate row counts.

### A3. Cafe Platform Walk-ins — Profile Transition

`CafeWalkin` becomes a cafe-specific profile linked to `users_identity` via FK.

**Migration path (big-bang, single deployment):**

1. Add `identity` FK to `CafeWalkin` (non-nullable):
   ```python
   identity = models.ForeignKey(
       'users.Identity', on_delete=models.CASCADE,
       related_name='cafe_walkin_profile',
   )
   ```

2. Backfill: match `CafeWalkin.phone` → `users_identity.phone`:
   ```sql
   UPDATE caf_platform_walkins w
   SET identity_id = (
       SELECT i.identity_id
       FROM users_identity i
       WHERE i.phone = w.phone
   )
   WHERE identity_id IS NULL;
   ```

3. Drop `unique=True` from `CafeWalkin.phone` (phone lives in `users_identity` only).

4. Update `customer_register` view: set `walkin.identity` FK instead of phone-based `update_or_create`.

**What doesn't change:**
- `CafeWallet.customer` stays on `CustomUser` (auth-bound, not identity-bound).
- `CafeUser` thin projection stays as-is (Phase 9 cleanup).
- Legacy MongoDB `kgorders` stays in MongoDB (council-locked).

**Action:** Include in identity migration script; validate `CafeWalkin.identity` FK coverage after import.

### A4. CustomUser.userid → identity_id Migration

Current `userid` format (`KCTM006`) is used throughout the codebase. After deployment, all new code references `identity_id` (`ID000001`). `userid` lives in `users_employee` as the employee's ID.

Full replacement of `userid` references with `identity_id` across the codebase is part of this deployment — no backward-compat layer.

---

## Appendix B: Cross-Reference Query Examples

### B1. "This Customer Is Also a Player"

```sql
SELECT i.identity_id, i.phone, i.name,
       c.registered, c.order_count, c.total_spent,
       p.player_id, p.rank, p.team_id
FROM users_identity i
JOIN users_customer c ON c.identity_id = i.identity_id
JOIN users_player p ON p.identity_id = i.identity_id
WHERE i.bg_code = 'KURO0001';
```

### B2. "All Employees in a Division"

```sql
SELECT i.identity_id, i.phone, i.name, e.userid, e.role, e.department
FROM users_identity i
JOIN users_employee e ON e.identity_id = i.identity_id
WHERE i.div_code = 'KURO0001_001';
```

### B3. "Customer Order History with Identity"

```sql
SELECT i.name, i.phone, c.order_count, c.total_spent,
       o.orderid, o.total_amount, o.created_at
FROM users_identity i
JOIN users_customer c ON c.identity_id = i.identity_id
JOIN orders_core o ON o.customer_id = i.identity_id
WHERE i.bg_code = 'KURO0001'
ORDER BY o.created_at DESC;
```

### B4. "Vendor by GSTIN with Organization"

```sql
SELECT o.org_id, o.name, o.org_type,
       vp.gstin, vp.pan, vp.contact_phone, vp.contact_email
FROM users_organization o
JOIN users_vendor_profile vp ON vp.organization_id = o.org_id
WHERE vp.gstin = '29AABCU9603R1ZM';
```

### B5. "Player Team Membership"

```sql
SELECT i.name, i.phone,
       p.player_id, p.rank,
       o.name AS team_name, o.org_id
FROM users_identity i
JOIN users_player p ON p.identity_id = i.identity_id
LEFT JOIN users_organization o ON o.org_id = p.team_id
WHERE i.bg_code = 'KURO0001';
```