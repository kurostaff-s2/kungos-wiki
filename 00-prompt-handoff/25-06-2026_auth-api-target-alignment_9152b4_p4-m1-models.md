# Phase 4: M1 Identity Model Preparation (Scaffolding Only)

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `9152b4-p4` |
| Entity type | `handoff` |
| Short description | Create 9 Django models for M1 identity layer, migration scaffolding, and migrate_identity management command. Do NOT execute migration. |
| Status | `draft` |
| Parent plan | `25-06-2026_auth-api-target-alignment_9152b4.md` |
| Phase | 4 of 5 |
| Source references | `llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md` §3, `llm-wiki/Kung_OS/specs/database_schemas/migration_spec.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute model scaffolding — owner: agent with code-edit access |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Key files for this phase:**
- `users/models/identity.py` — new
- `users/models/extensions.py` — new
- `users/models/organizations.py` — new
- `users/models/phone_aliases.py` — new
- `users/models/__init__.py` — modify (exports)
- `users/migrations/` — new migration file
- `users/management/commands/migrate_identity.py` — new

---

## What This Phase Delivers

9 Django models matching `postgresql_schema.md` §3 exactly, a migration that creates empty tables with constraints, and a `migrate_identity` management command. **No data migration executed** — tables are empty scaffolding.

---

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete (canonical naming in place)
- [ ] `postgresql_schema.md` §3 is readable
- [ ] Django project is in a clean state (no uncommitted migrations)

---

## Implementation Steps

### 4A. Create Identity Model

**File:** `users/models/identity.py`

```python
from django.db import models

class Identity(models.Model):
    """Core identity record — singular person model."""
    identity_id = models.CharField(primary_key=True, max_length=20, db_index=True)
    phone = models.CharField(max_length=20, db_index=True)  # E.164
    name = models.CharField(max_length=255, blank=True, default="")
    bg_code = models.CharField(max_length=20, db_index=True)
    div_code = models.CharField(max_length=50, blank=True, default="")
    user = models.ForeignKey(
        'users.CustomUser', on=models.SET_NULL, null=True, blank=True,
        related_name='identity'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_identity'
        constraints = [
            models.UniqueConstraint(
                fields=['bg_code', 'phone'],
                name='uq_identity_tenant_phone'
            ),
        ]

    def __str__(self):
        return f"Identity({self.identity_id})"
```

### 4B. Create Extension Models

**File:** `users/models/extensions.py`

```python
from django.db import models

class EmployeeProfile(models.Model):
    identity = models.OneToOneField(
        'users.Identity', on_delete=models.CASCADE,
        primary_key=True, related_name='employee_profile'
    )
    userid = models.CharField(max_length=50, db_index=True)
    role = models.CharField(max_length=50, blank=True, default="")
    department = models.CharField(max_length=100, blank=True, default="")
    # Add remaining fields from postgresql_schema.md §3.2

    class Meta:
        db_table = 'users_employee'


class CustomerProfile(models.Model):
    identity = models.OneToOneField(
        'users.Identity', on_delete=models.CASCADE,
        primary_key=True, related_name='customer_profile'
    )
    registered = models.BooleanField(default=False)
    order_count = models.IntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Add remaining fields from postgresql_schema.md §3.3

    class Meta:
        db_table = 'users_customer'


class PlayerProfile(models.Model):
    identity = models.OneToOneField(
        'users.Identity', on_delete=models.CASCADE,
        primary_key=True, related_name='player_profile'
    )
    player_id = models.CharField(max_length=50, blank=True, default="")
    team_id = models.CharField(max_length=50, blank=True, default="")
    rank = models.CharField(max_length=50, blank=True, default="")
    # Add remaining fields from postgresql_schema.md §3.4

    class Meta:
        db_table = 'users_player'
```

### 4C. Create Organization Models

**File:** `users/models/organizations.py`

```python
from django.db import models

class Organization(models.Model):
    org_id = models.CharField(primary_key=True, max_length=20, db_index=True)
    org_type = models.CharField(max_length=20, choices=[('team', 'Team'), ('vendor', 'Vendor')])
    name = models.CharField(max_length=255)
    bg_code = models.CharField(max_length=20, db_index=True)
    div_code = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_organization'


class VendorProfile(models.Model):
    organization = models.OneToOneField(
        'users.Organization', on_delete=models.CASCADE,
        primary_key=True, related_name='vendor_profile'
    )
    gstin = models.CharField(max_length=20, blank=True, default="")
    pan = models.CharField(max_length=20, blank=True, default="")
    address = models.TextField(blank=True, default="")
    # Add remaining fields from postgresql_schema.md §3.6

    class Meta:
        db_table = 'users_vendor_profile'


class TeamProfile(models.Model):
    organization = models.OneToOneField(
        'users.Organization', on_delete=models.CASCADE,
        primary_key=True, related_name='team_profile'
    )
    team_id = models.CharField(max_length=50, db_index=True)
    coach = models.CharField(max_length=255, blank=True, default="")
    # Add remaining fields from postgresql_schema.md §3.7

    class Meta:
        db_table = 'users_team_profile'


class TeamMembership(models.Model):
    id = models.BigAutoField(primary_key=True)
    team_id = models.CharField(max_length=50, db_index=True)
    identity = models.ForeignKey(
        'users.Identity', on_delete=models.CASCADE, null=True, blank=True,
        related_name='team_memberships'
    )
    phone = models.CharField(max_length=20, blank=True, default="")  # unregistered members
    role_in_team = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        db_table = 'team_memberships'
        # Composite CHECK: (identity_id IS NOT NULL) OR (phone IS NOT NULL)
        # Enforced via migration constraint
```

### 4D. Create PhoneAlias Model

**File:** `users/models/phone_aliases.py`

```python
from django.db import models

class PhoneAlias(models.Model):
    id = models.BigAutoField(primary_key=True)
    identity = models.ForeignKey(
        'users.Identity', on_delete=models.CASCADE,
        related_name='phone_aliases'
    )
    phone = models.CharField(max_length=20, db_index=True)  # E.164
    alias_type = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        db_table = 'identity_phone_aliases'
```

### 4E. Update Model Exports

**File:** `users/models/__init__.py`

Add exports:
```python
from .identity import Identity
from .extensions import EmployeeProfile, CustomerProfile, PlayerProfile
from .organizations import Organization, VendorProfile, TeamProfile, TeamMembership
from .phone_aliases import PhoneAlias
```

### 4F. Create Migration

**File:** `users/migrations/00XX_create_identity_tables.py`

1. Run `python manage.py makemigrations users` to generate the migration.
2. Verify migration creates all 9 tables with correct `db_table` names.
3. Verify constraints: `uq_identity_tenant_phone` unique index, FK cascade on extensions.
4. **Apply migration:** `python manage.py migrate users` (creates empty tables).

### 4G. Create Management Command

**File:** `users/management/commands/migrate_identity.py`

```python
from django.core.management.base import BaseCommand
from django.db import transaction

class Command(BaseCommand):
    help = 'Migrate identity data from legacy sources to users_identity tables'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
        parser.add_argument('--source', choices=['all', 'customuser', 'kurouser', 'accesslevel'],
                          default='all', help='Source to migrate from')

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            'M1 identity migration: creates Identity + extension records from legacy sources. '
            'Run --dry-run first to preview.'
        ))
        # Implementation per migration_spec.md Phase 4
        # 1. Deduplicate by phone (E.164 normalized)
        # 2. Create Identity records
        # 3. Create extension records (EmployeeProfile, CustomerProfile, PlayerProfile)
        # 4. Link to existing CustomUser via FK
        # 5. Verify referential integrity
        raise NotImplementedError("M1 migration execution is a separate handoff")
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `users/models/identity.py` | Identity model |
| Create | `users/models/extensions.py` | EmployeeProfile, CustomerProfile, PlayerProfile |
| Create | `users/models/organizations.py` | Organization, VendorProfile, TeamProfile, TeamMembership |
| Create | `users/models/phone_aliases.py` | PhoneAlias with Meta.db_table |
| Modify | `users/models/__init__.py` | Export all new models |
| Create | `users/migrations/00XX_create_identity_tables.py` | Empty tables + constraints |
| Create | `users/management/commands/migrate_identity.py` | Import + dedup command (stub) |

---

## Phase-Specific Tests

1. **Models load:** `python -c "from users.models import Identity, EmployeeProfile, CustomerProfile, PlayerProfile, Organization, VendorProfile, TeamProfile, TeamMembership, PhoneAlias"` — no errors.
2. **Migration applies:** `python manage.py migrate users` — creates 9 empty tables.
3. **Table names correct:** `SELECT tablename FROM pg_tables WHERE tablename LIKE 'users_%' OR tablename LIKE 'team_%' OR tablename LIKE 'identity_%'` — matches schema spec.
4. **Constraints exist:** `uq_identity_tenant_phone` unique index present. FK cascade on extension tables.
5. **Command exists:** `python manage.py migrate_identity --help` — shows help text.
6. **No data loss:** Legacy `CustomUser`, `KuroUser`, `Accesslevel` tables untouched.

---

## Completion Gate

- [ ] All 9 models defined with correct fields and `db_table` names
- [ ] `PhoneAlias` declares `Meta.db_table = 'identity_phone_aliases'`
- [ ] `TeamMembership` declares `Meta.db_table = 'team_memberships'`
- [ ] Migration creates empty tables with constraints
- [ ] `migrate_identity` management command exists (untested stub)
- [ ] No data loss — legacy tables untouched
- [ ] Existing tests still pass

---

## Notes for Next Phase

Phase 5 wires everything together and verifies end-to-end. The M1 models are empty scaffolding — actual data migration is a separate handoff per `migration_spec.md`.
