# M1 Identity Data Migration

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `1a1902` |
| Entity type | `handoff` |
| Short description | Implement `migrate_identity` management command to migrate data from legacy sources to M1 identity tables |
| Status | `draft` |
| Source references | `Kung_OS/specs/database_schemas/postgresql_schema.md` (§3 User Schema — TARGET), `users/migrations/0013_spec_alignment.py` |
| Generated | 26-06-2026 |
| Next action / owner | Execute Phase 1 (Identity creation), then Phase 2 (Employee), Phase 3 (Customer), Phase 4 (Player/Vendor/Team), Phase 5 (Phone aliases) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Reference docs:**
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md` (§3.1-3.9 TARGET schema)
- `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec.md` (§4.3 Auth Migration Notes)
**Related codebases:** `/home/chief/Coding-Projects/kteam-fe-chief` (frontend uses identity_id post-migration)
**Key files for this task:**
- `users/management/commands/migrate_identity.py` (stub → implementation)
- `users/models.py` (M1 Identity models)
- `users/migrations/0013_spec_alignment.py` (schema migration, must be applied first)

## Background

Migration 0013 created the M1 Identity schema (9 new/modified tables). The `migrate_identity` management command is a stub that raises `NotImplementedError`. This handoff implements the actual data migration from legacy sources:

- **CustomUser** (auth records, ~N users) → `Identity` + `EmployeeProfile`
- **KuroUser** (extended profiles, ~N employees) → `EmployeeProfile` (full column set)
- **Accesslevel** (55-col legacy permissions, ~N rows) → RBAC tables (via `seed_rbac_roles.py`)
- **reb_users** (customers, 1,979) → `CustomerProfile`
- **players** (MongoDB, 117 docs, 59 unique) → `PlayerProfile`
- **teams** (14) + **vendors** (409) → `Organization` + `TeamProfile`/`VendorProfile`
- **PhoneModel** (OTP records) → `PhoneAlias`

**Prerequisites:**
- Migration 0013 applied (`python manage.py migrate users`)
- Staging DB available for dry-run testing
- Backup of legacy tables before production run

---

## Phase 1: Identity Creation (CustomUser → Identity)

**What:** Create `Identity` records from `CustomUser` with E.164 phone normalization, sequential `identity_id`, and tenant scoping.

**Files:**
- Modify `users/management/commands/migrate_identity.py`

**Steps:**

1. Read current M1 Identity model from `users/models.py` to confirm column names and constraints.
2. Implement Phase 1 in `migrate_identity.py`:

```python
def migrate_identities(self, dry_run=False):
    """Create Identity records from CustomUser."""
    from users.models import Identity, CustomUser
    from users.utils import normalize_phone
    from tenant.models import BusinessGroup, Division

    count = 0
    errors = []

    for user in CustomUser.objects.filter(is_active=True).order_by('created_date'):
        try:
            # Resolve tenant context
            tenant_ctx = user.usertenantcontext_set.first()
            if not tenant_ctx:
                errors.append(f"{user.userid}: no tenant context, skipping")
                continue

            bg_code = tenant_ctx.bg_code
            div_codes = tenant_ctx.div_codes or []
            div_code = div_codes[0] if div_codes else ''

            # Generate identity_id (sequential)
            max_id = Identity.objects.aggregate(Max('identity_id'))['identity_id__max'] or 'ID000000'
            seq = int(max_id[2:]) + 1
            identity_id = f'ID{seq:06d}'

            # Normalize phone
            phone = normalize_phone(getattr(user, 'phone', ''))

            if not dry_run:
                Identity.objects.create(
                    identity_id=identity_id,
                    phone=phone,
                    name=getattr(user, 'name', ''),
                    email=getattr(user, 'email', ''),
                    bg_code=bg_code,
                    div_code=div_code,
                    branch_code=None,  # Will be set from tenant context if available
                    status='active',
                    phone_verified=False,  # Default, verify from PhoneModel
                    idproof_type=None,
                    idproof_number=None,
                    user=user.userid,  # OneToOne FK to CustomUser
                )
                count += 1
            else:
                count += 1

        except Exception as e:
            errors.append(f"{user.userid}: {str(e)}")

    self.stdout.write(f'Identities: {count} created ({len(errors)} errors)')
    return count, errors
```

3. Add `--dry-run` flag support (already in `add_arguments`).
4. Add `--source customuser` filter support.
5. Verify against staging DB with `--dry-run`.

**Tests:**
1. **Dry-run count:** Run `--dry-run --source customuser` and assert count matches `CustomUser.objects.filter(is_active=True).count()`.
2. **Identity format:** Assert `identity_id` matches `ID000001` format.
3. **Phone normalization:** Assert `phone` is E.164 format (`+91...`).
4. **Tenant scoping:** Assert `bg_code` and `div_code` populated from `UserTenantContext`.

**Dependencies:** Migration 0013 applied.

---

## Phase 2: Employee Profiles (KuroUser → EmployeeProfile)

**What:** Create `EmployeeProfile` records from `KuroUser` with full column mapping.

**Files:**
- Modify `users/management/commands/migrate_identity.py`

**Steps:**

1. Map `KuroUser` columns to `EmployeeProfile` columns (38 fields total):

| KuroUser Field | EmployeeProfile Field | Notes |
|---|---|---|
| `userid` | `identity_id` | Via Identity FK (lookup by user.userid) |
| `userid` | `userid` | Employee ID (e.g., KCTM006) |
| `role` | `role` | tech/admin/staff/manager |
| `department` | `department` | |
| `joining_date` | `joining_date` | |
| `salary` | `salary` | |
| `bank_name` | `bank_name` | |
| `bank_account_no` | `bank_account_no` | |
| `bank_ifsc` | `bank_ifsc` | |
| `bank_branch` | `bank_branch` | |
| `bfc_name` | `bfc_name` | 5 BFC fields |
| `bfc_relation` | `bfc_relation` | |
| `bfc_phone` | `bfc_phone` | |
| `bfc_email` | `bfc_email` | |
| `bfc_address` | `bfc_address` | |
| `gender` | `gender` | |
| `dob` | `dob` | |
| `pan` | `pan` | |
| `perm_address_line1` | `perm_address_line1` | 5 perm address fields |
| `perm_address_line2` | `perm_address_line2` | |
| `perm_city` | `perm_city` | |
| `perm_state` | `perm_state` | |
| `perm_pincode` | `perm_pincode` | |
| `pres_address_line1` | `pres_address_line1` | 5 present address fields |
| `pres_address_line2` | `pres_address_line2` | |
| `pres_city` | `pres_city` | |
| `pres_state` | `pres_state` | |
| `pres_pincode` | `pres_pincode` | |
| `emerg_name` | `emerg_name` | |
| `emerg_phone` | `emerg_phone` | |
| `paid_offs` | `paid_offs` | |
| `available_offs` | `available_offs` | |
| `festival_offs` | `festival_offs` | |
| `created_by` | `created_by` | |
| `approved_by` | `approved_by` | |
| `approved_date` | `approved_date` | |

2. Implement Phase 2:

```python
def migrate_employees(self, dry_run=False):
    """Create EmployeeProfile records from KuroUser."""
    from users.models import EmployeeProfile, KuroUser, Identity
    from datetime import datetime

    count = 0
    errors = []

    for kuser in KuroUser.objects.all():
        try:
            # Find corresponding Identity
            identity = Identity.objects.filter(user=kuser.userid).first()
            if not identity:
                errors.append(f"{kuser.userid}: no Identity found, skipping")
                continue

            # Map fields (use getattr for safety)
            emp_data = {
                'identity_id': identity.identity_id,
                'userid': kuser.userid,
                'role': getattr(kuser, 'role', 'staff'),
                'department': getattr(kuser, 'department', None),
                'joining_date': getattr(kuser, 'joining_date', datetime.now().date()),
                'salary': getattr(kuser, 'salary', None),
                # ... all 38 fields
            }

            if not dry_run:
                EmployeeProfile.objects.update_or_create(
                    identity_id=identity.identity_id,
                    defaults=emp_data
                )
                count += 1
            else:
                count += 1

        except Exception as e:
            errors.append(f"{kuser.userid}: {str(e)}")

    self.stdout.write(f'Employees: {count} created ({len(errors)} errors)')
    return count, errors
```

3. Verify field mapping against `users/models.py` EmployeeProfile definition.
4. Test with `--dry-run --source kurouser`.

**Tests:**
1. **Count match:** Assert employee count matches `KuroUser.objects.count()`.
2. **FK integrity:** Assert every `EmployeeProfile.identity_id` references an existing `Identity`.
3. **Field mapping:** Spot-check 3 random records for correct field values.

**Dependencies:** Phase 1 (Identity records must exist first).

---

## Phase 3: Customer Profiles (reb_users → CustomerProfile)

**What:** Create `CustomerProfile` records from `reb_users` (1,979 customers).

**Files:**
- Modify `users/management/commands/migrate_identity.py`

**Steps:**

1. Locate `reb_users` source (MongoDB collection or legacy table). Check `users/models.py` for `RebUser` model or MongoDB gateway.
2. For each customer:
   - Look up or create `Identity` by phone (E.164 normalized).
   - Create `CustomerProfile` with `registered=True` (if in reb_users with login), `is_requestor=False` (default).
   - Denormalized fields (`order_count`, `total_spent`, etc.) start at 0/NULL. Will be populated via outbox events post-migration.
3. Handle unregistered customers (phones in orders but not in reb_users) — create `Identity` with `registered=False`.

**Tests:**
1. **Count match:** Assert customer count matches `reb_users` count.
2. **Registered flag:** Assert `registered=True` for users with auth records.
3. **Phone dedup:** Assert no duplicate `(bg_code, phone)` in Identity.

**Dependencies:** Phase 1 (Identity creation).

---

## Phase 4: Player, Vendor, Team Profiles

**What:** Create `PlayerProfile`, `VendorProfile`, `TeamProfile`, `Organization`, `TeamMembership` from legacy sources.

**Files:**
- Modify `users/management/commands/migrate_identity.py`

**Steps:**

1. **Players (MongoDB, 117 docs, 59 unique):**
   - Read from MongoDB `players` collection.
   - For each player, look up `Identity` by phone/userid.
   - Create `PlayerProfile` with `player_id`, `team_id`, `riot_id`, `rank`.

2. **Vendors (409):**
   - Read from legacy vendor source (table or MongoDB).
   - Create `Organization` with `org_type='vendor'`.
   - Create `VendorProfile` with `gstin`, `pan`, `address`, `payment_type`, `contact_phone`, `contact_email`.

3. **Teams (14):**
   - Read from legacy teams source.
   - Create `Organization` with `org_type='team'`.
   - Create `TeamProfile` with `team_id`, `coach`.
   - Create `TeamMembership` records for team members.

**Tests:**
1. **Player count:** Assert 59 unique players migrated.
2. **Vendor count:** Assert 409 vendors migrated.
3. **Team count:** Assert 14 teams migrated.
4. **FK integrity:** Assert all extension records reference valid Identity/Organization.

**Dependencies:** Phase 1 (Identity records).

---

## Phase 5: Phone Aliases

**What:** Create `PhoneAlias` records for secondary/previous phone numbers.

**Files:**
- Modify `users/management/commands/migrate_identity.py`

**Steps:**

1. Scan `PhoneModel` (OTP records) for phones that differ from primary `Identity.phone`.
2. For each alternate phone, create `PhoneAlias` with `alias_type='secondary'`.
3. Handle shared phones (same number across tenants) with `alias_type='shared'`.

**Tests:**
1. **Uniqueness:** Assert no duplicate `(identity_id, alias_type, phone)`.
2. **FK integrity:** Assert all aliases reference valid Identity.

**Dependencies:** Phase 1 (Identity records).

---

## Phase 6: Verification & Integrity

**What:** Full referential integrity check and data validation.

**Files:**
- Modify `users/management/commands/migrate_identity.py` (add `--verify` flag)

**Steps:**

1. Implement `--verify` mode:
   - Check all `Identity` records have valid `bg_code`, `div_code`.
   - Check all extension records have valid FK to `Identity`/`Organization`.
   - Check no orphaned `CustomUser` records without `Identity`.
   - Check phone uniqueness constraint `(bg_code, phone)`.
   - Check `TeamMembership` CHECK constraint (identity_id OR phone NOT NULL).

2. Report summary:
   - Total Identities, Employees, Customers, Players, Vendors, Teams.
   - Error count and list.
   - Orphaned records count.

**Tests:**
1. **Zero orphans:** Assert all CustomUser records have corresponding Identity.
2. **Zero constraint violations:** Assert all CHECK/UNIQUE constraints satisfied.
3. **Phone uniqueness:** Assert no duplicate `(bg_code, phone)` pairs.

**Dependencies:** All Phases 1-5 complete.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `users/management/commands/migrate_identity.py` | Full migration implementation (6 phases) |

## Constraints

- **Idempotent:** Use `update_or_create` to allow re-runs without duplicates.
- **Atomic per record:** Each record creation is a separate transaction. Failures don't roll back entire batch.
- **Dry-run first:** Always run `--dry-run` before production execution.
- **Backup first:** Legacy tables must be backed up before production run.
- **No data loss:** Do not delete legacy records until verification passes.
- **Sequential identity_id:** Use `ID000001` format, sequential, no gaps.
- **E.164 normalization:** All phones normalized via `normalize_phone()` before DB writes.

## Success Criteria

- [ ] `--dry-run` produces correct counts for all sources
- [ ] Identity records created for all active CustomUsers
- [ ] EmployeeProfile records created for all KuroUsers
- [ ] CustomerProfile records created for all reb_users
- [ ] PlayerProfile records created for all MongoDB players
- [ ] VendorProfile + Organization created for all vendors
- [ ] TeamProfile + Organization + TeamMembership created for all teams
- [ ] PhoneAlias records created for secondary phones
- [ ] `--verify` passes with zero orphans and zero constraint violations
- [ ] All extension records have valid FK references
- [ ] No duplicate `(bg_code, phone)` pairs
- [ ] Legacy tables preserved (not deleted) post-migration

## Caveats & Uncertainty

1. **reb_users source format** — Need to confirm whether `reb_users` is a PostgreSQL table or MongoDB collection. If MongoDB, need gateway to read it.
2. **Player/team/vendor sources** — Same uncertainty. Need to locate actual data sources before implementation.
3. **Phone deduplication** — Same phone may exist across tenants. The spec says `(bg_code, phone)` is unique per tenant. Need to handle cross-tenant duplicates.
4. **CustomUser→Identity linkage** — The `user` FK on Identity is nullable. Some phones may not have CustomUser records (walk-ins, phone-only identities). Need to handle this case.
5. **MongoDB player data** — 117 docs but only 59 unique players. Need deduplication logic.

---

## Execution Order

```
Phase 1 (Identity) → Phase 2 (Employee) → Phase 3 (Customer) → Phase 4 (Player/Vendor/Team) → Phase 5 (Phone aliases) → Phase 6 (Verification)
```

All phases sequential. Each phase depends on the previous one's Identity records.

**Estimated effort:** Multi-session (4-6 hours total, including dry-run testing and verification).
