# RBAC System

**Status:** Constitution (stable, long-lived)
**Last updated:** 2026-05-16

---

## Principle

Permissions are normalized, tenant-scoped, and resolved through a cascading engine. Roles are additive. Direct overrides take priority over roles.

---

## Permission Model

### Permission Registry

`rbac_permissions` — source of truth for all permission codes.

```
perm_code  — unique identifier, format: {domain}.{module}.{resource}.{action}
domain     — bounded context: accounts, orders, inventory, vendors, teams, etc.
module     — sub-domain: sales, expenditure, tax, financials, stock, etc.
resource   — business entity: invoices, payments, purchase_orders, etc.
action     — verb: view, edit, approve, export, etc.

description — human-readable label
is_active  — False = deprecated (kept for audit)
```

**Examples:**
- `accounts.sales.view` — View sales invoices
- `accounts.expenditure.payments.edit` — Edit payment vouchers
- `inventory.stock.edit` — Edit stock register
- `orders.estimates.view` — View estimates
- `vendors.manage` — Manage vendors

### Permission Levels

| Level | Name | Meaning |
|-------|------|---------|
| 0 | None | Explicitly revoked |
| 1 | View | Read-only access |
| 2 | Edit | Create, update, delete |
| 3 | Supervisor | Full access including permission management |

---

## Role Model

### Roles

`rbac_roles` — user-created roles with optional single-level inheritance.

```
role_code   — unique identifier (e.g. store_manager, cashier, viewer)
role_name   — display name
parent_role — FK to self (nullable). Child inherits all parent permissions.
is_system   — reserved for future use (currently all roles are user-created)
```

**Inheritance rule:** Single-level only. No chains. A child role inherits all parent permissions; if the child defines the same `perm_code`, the child's level wins.

### Role Permissions

`rbac_role_permissions` — which permissions each role has and at what level.

```
(role_code, perm_code) — composite unique constraint
level                  — 0-3 (see Permission Levels)
```

---

## Assignment Model

### User Roles

`rbac_user_roles` — which roles each user has, scoped by tenant.

```
userid   — the user
role     — FK to rbac_roles.role_code
bg_code  — empty = global (all BGs), value = scoped to this BG
division — empty = all divisions within the BG, value = scoped to this division
```

### User Role Branches

`rbac_user_role_branches` — branch-level scoping for user roles.

```
(user_role_id, branch_code) — composite unique constraint
```

Empty = access to all branches of the division.

### User Permission Overrides

`rbac_user_permissions` — direct per-user permission overrides.

```
(userid, perm_code, bg_code, division) — composite unique constraint
level     — 0-3 (0 = explicit revocation)
reason    — required justification (audit compliance)
expires_at — optional TTL for temporary grants
granted_by — who granted this override
```

---

## Resolution Engine

`users/permissions.py` — `resolve_permission()` cascades through three layers:

1. **Direct override** (`rbac_user_permissions`) — checked first. `level=0` = explicit revocation.
2. **Role permissions** (`rbac_user_roles` → `rbac_role_permissions`) — cascades: exact division → BG-wide → global. Max-level wins.
3. **No access** — default if nothing matches.

**Key rules:**
- Roles are always additive — a user gets the union of all assigned roles' permissions.
- Direct overrides always win over role assignments.
- **Scope priority:** Branch > Division > BG > Global. A more specific scope always takes precedence over a broader scope, regardless of permission level.
- At the same scope level, the highest permission level wins.
- Expired overrides (`expires_at < now`) are ignored.

---

## Legacy Accesslevel Model

`users_accesslevel` — 55 columns, flat permission fields.

This model stores one permission field per resource (e.g., `inward_invoices`, `orders`, `inventory`) as integer levels. It has no role concept, no inheritance, no branch scoping, and no audit trail.

All permissions use normalized RBAC. `Accesslevel` is deprecated.

---

## Architecture Decisions

### Why Normalized Tables, Not Flat Permission Fields?

The legacy `Accesslevel` model has 40+ varchar permission fields. Adding a new permission requires a schema migration. Normalized tables add a row, not a column.

### Why Single-Level Inheritance, Not Chains?

Role chains (A → B → C → D) create debugging nightmares. Single-level inheritance gives you the benefit of templates (parent) with explicit overrides (child), without recursive resolution.

### Why Required Reason on Overrides?

Every direct permission override requires a `reason` field. This creates an audit trail for compliance — you can answer "who gave user X access to Y, when, and why?"

### Why Tenant-Scoped Roles?

A "store_manager" role at `KURO0001_001` should not grant access to `DUNE0003_001`. Roles are scoped by `bg_code` and optionally `division`. Empty = global.

---

> **Implementation state:** Normalized RBAC tables are implemented. Legacy `Accesslevel` deprecation and resolution engine enforcement are tracked in `operations/`.
