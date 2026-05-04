# Access Level Design — RBAC + Permission Matrix

Single source of truth for access control architecture, migration plan, and implementation decisions.

---

## 1. Current System — How It Works Today

### Data Model
```
Accesslevel (40+ columns):
  userid       → FK to CustomUser
  bg_code      → Business Group scope
  division     → Division scope (div_code like "KURO0001_002")
  branches     → JSON array of allowed branches
  inward_invoices    INTEGER (0=none, 1=view, 2=edit, 3=admin)
  outward_invoices   INTEGER
  purchase_orders    INTEGER
  ... (40+ permission columns total)
  is_active    BOOLEAN
  created_by / updated_by / timestamps
```

### Permission Flow
```
Admin assigns permissions → Accesslevel row created (one per division)
User logs in → kuro/user returns all Accesslevel rows → Frontend stores in Redux
Page loads → useNavAccess(key) resolves sidebar key → backend field name → checks value > 0
BG switch → bgSwitch POST returns only current BG's access levels → Redux updates
```

### Key Functions
| Function | What it does | Problem |
|---|---|---|
| `business_accesslevel()` | Clones permissions from template JSON file to new user | Static `accesslevels.json` must be manually updated for every new permission |
| `division_accesslevel()` | Bulk-creates zero-permission rows for all employees when a division is added | Creates N×M rows (employees × divisions) — bloats DB |
| `bgSwitch` POST | Returns access levels for switched BG | Only returns current BG's levels → frontend loses other BG permissions |
| `useNavAccess()` | Frontend permission checker with KEY_ALIAS mapping | Fragile manual mapping between sidebar keys and backend field names |

---

## 2. Why the Current Design Is Not Optimal

### 1. Horizontal Bloat (40+ columns)
Every new feature requires:
- New column migration on Accesslevel model
- Update to `accesslevels.json` template
- Add entry to frontend `KEY_ALIAS` mapping
- Update `division_accesslevel()` hardcoded dict
- Update serializers, forms, admin panels

**Cost:** 5+ touchpoints per new permission. High chance of missing one.

### 2. No Role System
Every user gets individual permissions. To give 10 new employees the same "Store Manager" permissions:
- Admin manually checks/unchecks 40+ boxes per employee
- Or uses `business_accesslevel()` to clone from another user (error-prone)

**Impact:** Doesn't scale beyond ~50 users. No standard roles ("Staff", "Manager", "Admin").

### 3. Row Duplication
User with access to 3 divisions = 3 Accesslevel rows, each with all 40 columns duplicated.
100 users × 3 divisions = 300 rows × 40 columns = **12,000 permission cells** in the DB.

### 4. Mixed Storage Patterns
- Permissions: Flat integer columns
- Branches: JSON array
- Division scope: Single varchar column (one division per row, stores div_code)
- Business groups: Derived from bg_code column

No consistent pattern. Hard to query "what does user X have access to?" across all dimensions.

### 5. No Audit Trail
`updated_by` / `updated_date` show WHO changed permissions but not WHAT changed.
Can't answer: "Who gave User X access to invoices and when?"

### 6. Frontend Coupling
`KEY_ALIAS` mapping in `useNavAccess.jsx` must stay in sync with backend field names.
If backend renames `inward_payments` → `incoming_payments`, frontend breaks silently.

---

## 3. Proposed Design — RBAC + Permission Matrix

### ER Diagram
```
┌──────────────┐       ┌─────────────────┐       ┌──────────────────┐
│ Permission   │ 1──N  │ RolePermission  │ N──1  │ Role             │
│ (registry)   │──────▶│                 │──────▶│                  │
│ perm_code    │       │ role_code       │       │ role_code        │
│ module       │       │ perm_code       │       │ role_name        │
│ description  │       │ level           │       │ parent_role_code │ ← inheritance
└──────────────┘       └─────────────────┘       │ is_system        │
                          ▲                        └──────────────────┘
                          │ 1──N                       │ 1──N
                     ┌────┴──────┐                    │
                     │ UserRole  │◀───────────────────┘
                     │ userid    │
                     │ role_code │
                     │ bg_code   │ (nullable — NULL = global)
                     │ division  │ (nullable — NULL = all divisions)
                     │ assigned_by│
                     │ assigned_at│
                     └────┬──────┘
                          │ 1──N
                   ┌──────┴───────────┐
                   │UserRoleBranch    │  ← normalized branch scoping
                   │ user_role_id     │
                   │ branch_code      │
                   └──────────────────┘

              ┌──────────────────┐
              │ UserPermission   │  ← direct per-user overrides
              │ userid           │
              │ perm_code        │
              │ level            │
              │ bg_code (nullable)│
              │ division (nullable)│
              │ reason           │  ← required justification
              │ granted_by       │
              │ granted_at       │
              │ expires_at       │  ← optional TTL for temporary grants
              └──────────────────┘
```

---

## 4. Permission Codes — Naming Convention

**Format:** `{module}.{resource}`

The `level` field (0–3) handles view/edit/admin — no action suffix needed.

| Code | Description | Example at level 2 |
|---|---|---|
| `invoices.inward` | Inward invoice management | Can edit inward invoices |
| `invoices.outward` | Outward invoice management | Can edit outward invoices |
| `orders.offline` | Offline order management | Can edit offline orders |
| `orders.online` | Online order management | Can edit online orders |
| `products.catalog` | Product catalog access | Can edit products |
| `inventory.stock` | Stock tracking | Can edit stock |
| `payments.inward` | Inward payment access | Can edit inward payments |
| `analytics.dashboard` | Analytics dashboard | Can view analytics |

**Level values (0–3):**

| Level | Label | Meaning |
|---|---|---|
| 0 | None | No access — hidden from nav, API returns 403 |
| 1 | View-Only | Read access — visible in nav, read-only pages |
| 2 | Edit | Create/modify records — **no delete, no approve** |
| 3 | Supervisor | Verify/approve actions taken by others **+ delete access** |

> **Admin functions are separate permissions**, not a level.
> Binary permissions (level 1 = granted): `admin.user_list`, `admin.bg_group`,
> `hr.access_level`, `products.replace_preset`, `admin.portal_editor`.

> **Hybrid UI labels:** The admin UI adapts per permission type:
> - CRUD modules → radio buttons "None / View-Only / Edit / Supervisor"
> - Binary actions → checkbox "Grant access" (maps to level 0 or 1)
> - Outliers get info bubbles explaining the convention.

> **Migration mapping from legacy 0–5 scale:**
> Legacy values were cumulative (higher = more access): 0=none, 1=minimal, 2=edit,
> 3=read+edit, 4=near-full, 5=super-admin. Frontend mostly checked `val !== 0` (binary).
> New mapping: `0→0, 1→1, 2→2, 3→2, 4→3, 5→3`.

---

## 5. Table Specifications

### 5.1 Permission (registry)
```
perm_code      VARCHAR(50) PK   — "invoices.outward", "orders.offline"
module         VARCHAR(30)      — "invoices", "orders", "analytics", "hr"
description    VARCHAR(200)     — "Access to outward invoice management"
is_active      BOOLEAN          — True = usable, False = deprecated
```

### 5.2 Role
```
role_code        VARCHAR(30) PK  — "store_manager", "cashier", "viewer" etc.
role_name        VARCHAR(100)    — "Store Manager"
description      TEXT            — Role purpose and scope
parent_role_code VARCHAR(30)     — NULL = no parent; FK → roles.role_code (inheritance)
is_system        BOOLEAN         — Reserved (currently all roles are user-created)
```

> **No System-Defined Roles:** All roles are user-created via the admin UI. There are no hardcoded "super_admin", "admin", or other system roles. Each BG creates their own roles with whatever names and permission sets they need. The `is_system` flag is reserved for future use.

> **Role Inheritance:** A role with `parent_role_code` inherits all parent permissions at their defined levels. Child entries override parent entries for the same `perm_code`. Single-level inheritance only (no deep chains) to keep resolution predictable.

### 5.3 RolePermission
```
role_code      FK → roles.role_code
perm_code      FK → permissions.perm_code
level          INTEGER           — 0=none, 1=view, 2=edit, 3=admin
UNIQUE(role_code, perm_code)
```

### 5.4 UserRole
```
id             BIGINT PK (surrogate)
userid         FK → CustomUser.userid
role_code      FK → roles.role_code
bg_code        VARCHAR(10)       — NULL = global, value = scoped to this BG
division       VARCHAR(200)      — NULL = all divisions, value = scoped to this division (was `division`)
assigned_by    FK → CustomUser
assigned_at    TIMESTAMP
```

> **NULL Uniqueness:** Standard `UNIQUE(userid, role_code, bg_code, division)` does NOT prevent duplicates when `bg_code` or `division` is NULL (PostgreSQL/MySQL treat `NULL != NULL`). Use partial indexes:
> ```sql
> CREATE UNIQUE INDEX uq_user_roles_global ON user_roles (userid, role_code)
>   WHERE bg_code IS NULL AND division IS NULL;
> CREATE UNIQUE INDEX uq_user_roles_bg ON user_roles (userid, role_code, bg_code)
>   WHERE bg_code IS NOT NULL AND division IS NULL;
> CREATE UNIQUE INDEX uq_user_roles_division ON user_roles (userid, role_code, bg_code, division)
>   WHERE bg_code IS NOT NULL AND division IS NOT NULL;
> ```

### 5.5 UserRoleBranch — Normalized Branch Scoping
```
user_role_id   FK → user_roles.id
branch_code    FK → tenant_branches.branch_code
UNIQUE(user_role_id, branch_code)
```

Replaces the JSON `branches` array. Branch checks become a simple `EXISTS` subquery.

### 5.6 UserPermission — Direct Overrides
```
id             BIGINT PK
userid         FK → CustomUser.userid
perm_code      FK → permissions.perm_code
level          INTEGER           — 0=explicitly revoke, 1=view, 2=edit, 3=admin
bg_code        VARCHAR(10)       — NULL = global override
division       VARCHAR(200)      — NULL = all divisions
reason         TEXT NOT NULL     — Justification required (audit compliance)
granted_by     FK → CustomUser
granted_at     TIMESTAMP
expires_at     TIMESTAMP         — NULL = permanent; set for temporary grants
```

> **Partial indexes** (same NULL pattern as UserRole):
> ```sql
> CREATE UNIQUE INDEX uq_user_perms_global ON user_permissions (userid, perm_code)
>   WHERE bg_code IS NULL AND division IS NULL;
> CREATE UNIQUE INDEX uq_user_perms_bg ON user_permissions (userid, perm_code, bg_code)
>   WHERE bg_code IS NOT NULL AND division IS NULL;
> CREATE UNIQUE INDEX uq_user_perms_division ON user_permissions (userid, perm_code, bg_code, division)
>   WHERE bg_code IS NOT NULL AND division IS NOT NULL;
> ```

> Use `level = 0` to **explicitly revoke** a permission that a role would otherwise grant.
> Expired rows (`expires_at < NOW()`) are treated as non-existent — filtered at query time.

---

## 6. Permission Resolution Algorithm

### Core Rules

1. **Roles are always additive across scopes.** Max-level wins.
2. **`user_permissions` overrides are checked FIRST.** A level-0 override blocks access regardless of roles.
3. **Division-scoped roles ADD permissions, they don't restrict BG-wide ones.** To restrict: use `user_permissions` override with `level = 0`.

### Algorithm
```python
from django.utils import timezone

def resolve_permission(userid, perm_code, bg_code=None, division=None):
    """
    Returns {"level": int, "source": str} for a user+permission+scope.
    Checks user overrides first, then aggregates max level across all matching roles.
    """

    # --- Step 1: Check direct user_permissions override (checked FIRST) ---
    override = UserPermission.objects.filter(
        userid=userid, perm_code=perm_code, bg_code=bg_code, division=division,
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    ).first()

    if override is not None:
        # level=0 means explicitly revoked — honour it without falling through to roles
        return {"level": override.level, "source": "user_override"}

    # --- Step 2: Collect all applicable role assignments (scope cascade) ---
    scopes = [
        {"bg_code": bg_code, "division": division},   # Exact scope match
        {"bg_code": bg_code, "division": None},      # BG-wide
        {"bg_code": None,    "division": None},      # Global
    ]

    max_level = 0
    source_role = None

    for scope in scopes:
        user_roles = UserRole.objects.filter(userid=userid, **scope)

        for ur in user_roles:
            # Resolve effective role permissions including parent inheritance
            effective_perms = get_effective_role_perms(ur.role_code)
            perm_level = effective_perms.get(perm_code, 0)

            if perm_level > max_level:
                max_level = perm_level
                source_role = ur.role_code

    return {"level": max_level, "source": source_role}


def get_effective_role_perms(role_code):
    """
    Returns {perm_code: level} for a role, merging parent permissions.
    Child entries override parent entries for the same perm_code.
    Single-level inheritance only.
    """
    role = Role.objects.select_related("parent_role").get(role_code=role_code)
    perms = {}

    # Start with parent permissions (if any)
    if role.parent_role_code:
        parent_perms = RolePermission.objects.filter(role_code=role.parent_role_code)
        for p in parent_perms:
            perms[p.perm_code] = p.level

    # Child role overrides parent
    own_perms = RolePermission.objects.filter(role_code=role_code)
    for p in own_perms:
        perms[p.perm_code] = p.level

    return perms
```

### Why Max-Level, Not First-Match?
A user can hold multiple roles (e.g. `store_manager` at BG level and `super_admin` scoped to division "rebellion"). First-match returns an arbitrary result depending on query order. Max-level is deterministic and always grants the highest access the user is entitled to across all their roles.

---

## 7. Edge Cases — Conflict Resolution

### Scenario: Two Division-Scoped Roles Conflict
```
User: KCAD002
Scope: bg_code=KURO0001, division=KURO0001_002

Role 1: cashier        → invoices.outward = 0 (no access)
Role 2: store_manager  → invoices.outward = 2 (edit)

Resolution: max(0, 2) = 2  → user CAN edit invoices
```

| Admin's Intent | Does max-level match? |
|---|---|
| "Give them cashier duties AND manager privileges" | ✅ Yes — they should have both |
| "They're a cashier, but also let them manage invoices" | ✅ Yes |
| "They're a cashier, DON'T let them touch invoices" | ❌ No — `store_manager` grants it anyway |

### Prevention Strategies

#### 1. Incompatible Role Pairs (API Guard)
```python
INCOMPATIBLE_ROLES = {
    frozenset({'cashier', 'store_manager'}),
    frozenset({'viewer', 'super_admin'}),
}

def validate_role_assignment(userid, role_code, bg_code, division):
    existing = UserRole.objects.filter(
        userid=userid, bg_code=bg_code, division=division
    ).values_list('role_code', flat=True)

    for pair in INCOMPATIBLE_ROLES:
        if role_code in pair and any(r in pair for r in existing):
            conflicting = pair - {role_code}
            raise ValidationError(
                f"Cannot assign {role_code} — conflicts with existing role(s): {conflicting}"
            )
```

#### 2. Admin UI Warning
```
⚠️ Assigning "store_manager" will grant invoices.outward (level 2)
   This overrides the restriction from "cashier" (level 0) on same division.
   [Proceed anyway]  [Cancel]
```

#### 3. If You MUST Restrict — Use `user_permissions` Override
This is the ONLY mechanism that can restrict:
```
Wrong way (won't work):
  Assign cashier role on rebellion → max(0, 2) = 2 → still has access ❌

Right way (works):
  Keep store_manager on rebellion
  INSERT user_permissions:
    userid=KCAD002, perm_code=invoices.outward, division=rebellion, level=0,
    reason="Restricted from invoice editing per branch policy"
```

### Decision Matrix — What Mechanism For What Scenario

| Scenario | Mechanism | Result |
|---|---|---|
| User needs TWO jobs (cashier + manager) | Assign both roles | Max-level grants highest ✅ |
| Admin tries to assign conflicting roles | Incompatible roles guard | Error at assignment time ✅ |
| User has a role but needs ONE permission revoked | `user_permissions` override (level=0) | Override checked first, blocks access ✅ |
| Temporary restriction (1 week) | `user_permissions` with `expires_at` | Auto-expires, audit trail ✅ |

**Rule:** Roles are always additive. `user_permissions` is the only way to restrict. This keeps resolution simple and deterministic.

---

## 8. Permission Caching (Redis)

The resolution algorithm is DB-heavy (multiple JOINs per check). At login time, pre-compute the full `_permissions` flat object and cache it in Redis. Invalidate on any role/permission change for that user.

```python
CACHE_KEY = "user_perms:{userid}:{bg_code}"
CACHE_TTL  = 60 * 15  # 15 minutes

def get_cached_permissions(userid, bg_code):
    key = CACHE_KEY.format(userid=userid, bg_code=bg_code)
    cached = redis_client.get(key)
    if cached:
        return json.loads(cached)

    perms = build_permissions_object(userid, bg_code)  # runs full resolution
    redis_client.setex(key, CACHE_TTL, json.dumps(perms))
    return perms

def invalidate_user_permissions(userid):
    """Call whenever user_roles or user_permissions change for a user."""
    pattern = CACHE_KEY.format(userid=userid, bg_code="*")
    for key in redis_client.scan_iter(pattern):
        redis_client.delete(key)
```

**When to invalidate:**
- Admin assigns/removes a role → invalidate affected user
- Admin edits `role_permissions` → invalidate **all users** with that role
- `user_permissions` override added/removed → invalidate affected user
- `expires_at` TTL hit → background job invalidates on expiry

---

## 9. Frontend Integration

### Sidebar Config — Permission Codes Directly
```jsx
// No KEY_ALIAS needed — sidebar uses permission codes directly
const sidebarConfig = [
  {
    key: 'invoices',
    perm: 'invoices.outward',
    children: [...]
  },
  {
    key: 'orders',
    perm: 'orders.offline',
    children: [...]
  },
]
```

### Permission Hooks
```jsx
// Simple flat lookup from cached _permissions object
function hasAccess(permCode) {
  const userPerms = useSelector(state => state.user?.userDetails?._permissions);
  return (userPerms?.[permCode]?.level ?? 0) > 0;
}

// Level-aware check (e.g. show Edit button only for level >= 2)
function hasLevel(permCode, minLevel) {
  const userPerms = useSelector(state => state.user?.userDetails?._permissions);
  return (userPerms?.[permCode]?.level ?? 0) >= minLevel;
}
```

---

## 10. API Response — kuro/user Endpoint

```json
{
  "_permissions": {
    "invoices.outward": {"level": 2, "source": "store_manager"},
    "orders.offline":   {"level": 3, "source": "user_override"},
    "analytics.view":   {"level": 1, "source": "store_manager"}
  },
  "_roles": [
    {"role_code": "store_manager", "bg_code": "KURO0001", "division": null},
    {"role_code": "super_admin",   "bg_code": "KURO0001", "division": "KURO0001_002"}
  ],
  "_overrides": [
    {
      "perm_code": "orders.offline",
      "level": 3,
      "reason": "Temporary access for inventory audit",
      "expires_at": "2026-05-15T00:00:00Z"
    }
  ],
  "_divisions": {
    "KURO0001_001": ["Madhapur"],
    "KURO0001_002":  ["Madhapur", "LB Nagar"]
  }
}
```

> **Full object sent at login.** ~5KB, cached in Redis. No lazy loading needed — frontend needs it immediately for sidebar rendering.

---

## 11. Role Explosion Risk

As BGs and divisions grow, avoid creating one role per business unit variant (e.g. `store_manager_kuro`, `store_manager_rebellion`). Use **scoped role assignments** instead — the same `store_manager` role assigned with different `bg_code`/`division` values. Only create new roles when the **permission set itself** genuinely differs.

> **Guideline:** No system roles exist. Admins create roles freely via `/tenant/roles` UI. Typical pattern: create a "Store Manager" role with permissions for orders, inventory, invoices, etc., then assign it to users at BG or division scope.

## 11a. Cascade Code Naming Convention

All tenant identifiers use **cascade codes** derived from the legal name:

| Model | Code Format | Example |
|---|---|---|
| BusinessGroup | First 4 letters of legal name + 4-digit seq | `KURO0001`, `DUNE0003` |
| Division | `bg_code` + `_` + 3-digit seq | `KURO0001_001`, `KURO0001_002` |
| Branch | `div_code` + `_` + 3-digit seq | `KURO0001_001_001`, `KURO0001_002_001` |
| BankAccount | `bg_code` + `_BK_` + 3-digit seq | `KURO0001_BK_001` |

**Current BGs:**
- `KURO0001` — KURO CADENCE LLP (active, 3 divisions)
- `DUNE0003` — DUNE LABS LLP (active, 1 division)
- `NAZA0002` — NAZARICK LABS LLP (**removed**, no longer active)

**Division mapping (KURO0001):**
- `KURO0001_001` — Kuro Gaming
- `KURO0001_002` — Rebellion
- `KURO0001_003` — RenderEdge

**Division mapping (DUNE0003):**
- `DUNE0003_001` — Rebellion

---

## 12. Migration Strategy

### Phase 1: Parallel Run — ✅ COMPLETE
- ~~Create new tables~~ → **Done**: `rbac_permissions`, `rbac_roles`, `rbac_role_permissions`, `rbac_user_roles`, `rbac_user_role_branches`, `rbac_user_permissions`
- **No system roles** — all roles user-created (original plan had 6 system roles, removed)
- ~~Seed with data derived from Accesslevel rows~~ → **Done**: 35 permissions seeded
- **System roles expanded to direct UserPermissions**: 5 UserRole entries → 175 UserPermission rows (no roles exist)
- **Do NOT delete Accesslevel rows.** Migration is additive only.
- ~~Add `_permissions`, `_roles`, `_overrides` to kuro/user response~~ → **Done**
- ~~Set up Redis cache layer~~ → **Done** (no-op if Redis not available)

### Phase 2: Frontend Migration — ✅ COMPLETE
- ~~Update `useNavAccess` to use new `_permissions` flat object~~ → **Done** (dual-mode: RBAC first, legacy fallback)
- ~~Remove `KEY_ALIAS` mapping~~ → **Done** (PERM_MAP: sidebar key → RBAC perm_code)
- ~~Expose `hasLevel(permCode, minLevel)` helper~~ → **Done**
- ~~Admin panel shows role-based assignment UI~~ → **Done** (`/tenant/roles`, `/tenant/user-access`)

### Phase 3: Cutover — IN PROGRESS
- ~~Prerequisite: Signed-off mismatch report showing <1% discrepancies~~
- ~~Switch all backend permission checks to new resolution algorithm~~
- ~~Deprecate Accesslevel model (keep as read-only audit table)~~
- ~~Remove old endpoints (`business_accesslevel()` rewritten for Division model, `division_accesslevel()` param renamed to `division`)
- ~~Enable Redis cache invalidation hooks on role/permission writes~~

### Phase 4: Cleanup — PENDING
- Archive Accesslevel table (move to `accesslevel_archive`)
- Remove `accesslevels.json` template file
- Clean up dead code (`KEY_ALIAS`, legacy serializers)

### Migration Script — Safety Nets

| Safety Net | What it does |
|---|---|
| **No delete** | Accesslevel rows are never deleted during migration. Kept as read-only audit data. |
| **Parallel run (2 weeks)** | Both old `accesslevel` and new `_permissions` returned in API response. Admin compares side-by-side. |
| **Mismatch report** | Script generates CSV: `userid \| perm_code \| old_value \| new_value \| match?`. Anything marked `NO` gets manual review before cutover. |

---

## 13. Effort Estimate

| Task | Effort | Risk |
|---|---|---|
| New tables + partial indexes + seed data | 3 days | Low |
| Permission resolution API + caching layer | 3 days | Medium |
| Frontend permission hook rewrite | 2 days | Medium |
| Admin role assignment UI + override management | 3 days | High (UX complexity) |
| Migration script (Accesslevel → new) + mismatch report | 4 days | High (data integrity) |
| Testing + rollback plan | 2 days | — |
| **Total** | **~3 weeks** | |

---

## 14. Decision Matrix — Current vs RBAC

| Factor | Current (40+ columns) | New (RBAC) |
|---|---|---|
| New permission cost | 5 touchpoints, manual | 1 INSERT into permissions table |
| Onboarding 10 users | 400 checkbox clicks | Assign 1 role to each |
| User exception handling | Impossible without cloning | `user_permissions` override with TTL |
| "What can User X do?" | Query 3 rows × 40 cols | JOIN user_roles → role_permissions |
| Audit "who changed what" | Impossible | Trivial (log role + override assignments) |
| Multi-division scaling | N rows per user | 1 row with division=NULL |
| Permission check speed | Fast (single row fetch) | Needs Redis cache for equivalent perf |
| Refactor risk | None | ~3 weeks, needs testing |
| **Verdict** | ❌ Doesn't scale | ✅ Worth the investment |
