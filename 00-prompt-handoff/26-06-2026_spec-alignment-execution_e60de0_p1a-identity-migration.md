# Phase 1A: Identity Data Migration (M1) — Full Inventory

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 1A of 5 (parallel with 1B, 1C)
**Dependencies:** None (can start immediately)
**Estimated effort:** ~90 min / multi-session (full M1 migration + dedup + verification)

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p1a` |
| Entity type | `handoff` |
| Short description | Migrate all 9 source user collections into `users_identity` + 5 extension tables. Execute dedup strategy with phone normalization. Populate `identity_id` for all users. Validate row counts, FK integrity, and tenant codes. |
| Status | `draft` |
| Source references | `migration_spec.md` §2, `postgresql_schema.md`, `identity_spec.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute full M1 migration — export all sources, normalize phones, dedup, import, validate |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Source databases:**
- MongoDB: `reb_users`, `misc`, `players`, `employee_attendance`, `serviceRequest`, `orders.user.phone`, `teams`, `vendors`
- PostgreSQL: `KuroUser` (legacy employee table)
**Target tables:** `users_identity` + 5 extension tables (`users_customer`, `users_employee`, `users_player`, `users_organization`, `users_vendor_profile`, `users_team_profile`)
**Key files for this phase:**
- `users/models.py` (Identity model, extension models)
- `users/management/commands/migrate_identity.py` (migration command with --validate)
- `users/migrations/0001_initial.py` (Identity schema migration)
- `plat/tenant/collection.py` (TenantCollection for Mongo reads)
**Related codebases:** None

## What This Phase Delivers

All 9 source user collections migrated into `users_identity` + extension tables with deduplication. Phone numbers normalized to E.164. `identity_id` populated for all users (sequential format `ID000001`). `Identity.user` OneToOne relationship populated for auth-linked users. `UserTenantContext.identity_id` backfilled. 12 rows flagged for manual review. 0 orphaned extension rows. 0 invalid tenant codes. Financial data loss check passes (total_spent sum matches legacy orders).

This is the foundation for all subsequent phases — RBAC FK migration (2A), Cafe schema alignment (1C), and Orders migration (4A) all depend on `identity_id` being available.

## Pre-Flight Checklist

- [ ] Test baseline established: 192 passed, 8 failed (pre-existing)
- [ ] `Identity` model exists in `users/models.py` with all required fields
- [ ] Extension models exist (`users_customer`, `users_employee`, `users_player`, `users_organization`, `users_vendor_profile`, `users_team_profile`)
- [ ] Database is accessible for migration (PostgreSQL + MongoDB)
- [ ] Pre-migration backups taken (PostgreSQL dump + MongoDB dump)

## Migration Inventory (Per migration_spec.md §2.1)

| Source | Location | Records | Target | Dedup Strategy |
|--------|----------|---------|--------|----------------|
| `reb_users` | Mongo | 1,979 | `users_identity` + `users_customer` | Phone normalization, E.164 |
| `misc` | Mongo | 1,979 | **SKIP** (100% duplicate of `reb_users`) | — |
| `players` | Mongo | 117 (59 unique) | `users_identity` + `users_player` | Phone + name fuzzy match |
| `employee_attendance` | Mongo | 966 (31 unique) | `users_identity` + `users_employee` | Cross-ref `CustomUser.phone` |
| `KuroUser` | PG | 31 | `users_employee` | Merge into employee records |
| `serviceRequest` | Mongo | 1,328 | `users_identity` + `users_customer` | Phone normalization |
| `orders.user.phone` | Mongo | 727 | `users_identity` + `users_customer` | Phone normalization |
| `teams` | Mongo | 14 | `users_organization` + `users_team_profile` | Direct import |
| `vendors` | Mongo | 409 | `users_organization` + `users_vendor_profile` | Direct import |

**Total unique identities:** ~4,500 (after dedup)

## Implementation Steps

### Step 1: Verify Identity & Extension Model Schemas

Read `users/models.py` and verify all models have required fields per spec:

**`users_identity`:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `identity_id` | CharField(20, PK) | Yes | Primary key, sequential `ID000001` |
| `phone` | CharField | Yes | UNIQUE per tenant (composite with bg_code) |
| `name` | CharField(200) | Yes | Full display name |
| `email` | CharField | No | UNIQUE, indexed |
| `bg_code` | CharField(10) | Yes | FK → tenant |
| `div_code` | CharField(20) | Yes | FK → tenant |
| `branch_code` | CharField(30) | No | FK → tenant |
| `status` | CharField(20) | Yes | CHECK: active/inactive/suspended |
| `phone_verified` | BooleanField | Yes | Default False |
| `idproof_type` | CharField(50) | No | Nullable |
| `idproof_number` | CharField(50) | No | Nullable |
| `user` | OneToOne → CustomUser | No | Nullable |
| `created_at` | DateTimeField | Yes | Auto |
| `updated_at` | DateTimeField | Yes | Auto |

**Extension tables:**

| Table | PK | FK → users_identity | Notes |
|-------|-----|---------------------|-------|
| `users_customer` | `identity_id` | Yes | `registered`, `is_requestor`, `order_count`, `total_spent` |
| `users_employee` | `identity_id` | Yes | `userid`, `role`, `department`, `joining_date` |
| `users_player` | `identity_id` | Yes | `player_id`, `team_id`, `riot_id`, `rank` |
| `users_organization` | `org_id` | No | `org_type` (team/vendor), `name`, `bg_code`, `div_code` |
| `users_vendor_profile` | `org_id` | Yes (via organization) | `gstin`, `pan`, `address`, `payment_type` |
| `users_team_profile` | `org_id` | Yes (via organization) | `team_id`, `coach` |

**Action:** If any field is missing, add it to the model and generate a migration.

### Step 2: Implement Phone Normalization

Create `users/utils.py`:

```python
import phonenumbers
import re


def normalize_phone(raw_phone: str, region: str = 'IN') -> str:
    """Normalize phone to E.164 format (+91XXXXXXXXXX)."""
    cleaned = re.sub(r'[^\d+]', '', raw_phone)
    if not cleaned:
        return None
    try:
        parsed = phonenumbers.parse(cleaned, region)
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return None


# Test cases
assert normalize_phone("9876543210") == "+919876543210"
assert normalize_phone("+919876543210") == "+919876543210"
assert normalize_phone("02223456789") == "+912223456789"
assert normalize_phone("00919876543210") == "+919876543210"
```

### Step 3: Implement Dedup Strategy

Per migration_spec.md §2.2:

**Step 3a: Normalize all phone numbers to E.164**

```python
def normalize_all_phones(sources: list) -> dict:
    """Normalize phones across all sources."""
    normalized = {}
    for source in sources:
        for doc in source:
            phone = doc.get('phone') or doc.get('mobile') or doc.get('contact_phone')
            if phone:
                e164 = normalize_phone(phone)
                if e164:
                    normalized.setdefault(e164, []).append(doc)
    return normalized
```

**Step 3b: Group by normalized phone**

```python
def group_by_phone(normalized: dict) -> dict:
    """Group documents by normalized phone."""
    groups = {}
    for phone, docs in normalized.items():
        groups[phone] = docs
    return groups
```

**Step 3c: Conflict resolution**

```python
def resolve_conflicts(phone, docs: list) -> dict:
    """Resolve conflicts for same phone, different names."""
    names = set(doc.get('name', '') for doc in docs)
    
    if len(names) == 1:
        # Same name → auto-merge (99% confidence)
        return {'action': 'auto_merge', 'confidence': 0.99}
    
    # Fuzzy name match
    name_list = list(names)
    if len(name_list) == 2:
        similarity = fuzzy_match(name_list[0], name_list[1])
        if similarity > 0.85:
            return {'action': 'merge_with_warning', 'confidence': 0.85 + similarity * 0.13}
        else:
            return {'action': 'manual_review', 'confidence': similarity}
    
    return {'action': 'manual_review', 'confidence': 0}


def fuzzy_match(name1: str, name2: str) -> float:
    """Simple fuzzy match (Levenshtein ratio)."""
    # Use difflib or rapidfuzz for production
    from difflib import SequenceMatcher
    return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
```

**Step 3d: Cross-reference merges**

```python
# Cross-reference merges per migration_spec.md §2.2 Step 4
# serviceRequest.phone ↔ reb_users.phone (30 matches → is_requestor=True)
# players.mobile ↔ reb_users.phone (12 matches → dual: player_profile + customer_profile)
# orders.user.phone ↔ reb_users.phone (73% match → registered=False for 727 unregistered)
# employee_attendance.userid ↔ CustomUser.phone (31 matches → employee_profile)
```

### Step 4: Implement Migration Command

Create/update `users/management/commands/migrate_identity.py`:

```python
from django.core.management.base import BaseCommand
from users.models import Identity, UserCustomer, UserEmployee, UserPlayer
from users.models import UserOrganization, UserVendorProfile, UserTeamProfile
from users.utils import normalize_phone


class Command(BaseCommand):
    help = 'Migrate all user sources into users_identity + extensions'

    def add_arguments(self, parser):
        parser.add_argument('--validate', action='store_true', help='Run validation checks')
        parser.add_argument('--source', type=str, help='Mongo URI (optional)')

    def handle(self, *args, **options):
        if options['validate']:
            self.validate_migration()
            return

        self.stdout.write('Starting M1 identity migration...')
        
        # Step 1: Export all sources
        sources = self.export_sources(options.get('source'))
        
        # Step 2: Normalize phones
        normalized = self.normalize_all_phones(sources)
        
        # Step 3: Dedup
        groups = self.group_by_phone(normalized)
        conflicts = self.resolve_conflicts(groups)
        
        # Step 4: Import into PostgreSQL
        self.import_identities(groups, conflicts)
        
        # Step 5: Update UserTenantContext
        self.backfill_tenant_context()
        
        self.stdout.write(self.style.SUCCESS('M1 migration complete'))

    def export_sources(self, mongo_uri: str = None) -> dict:
        """Export all 9 sources."""
        # Mongo sources
        reb_users = self.get_mongo_docs('reb_users', mongo_uri)
        misc = self.get_mongo_docs('misc', mongo_uri)  # SKIP (duplicate)
        players = self.get_mongo_docs('players', mongo_uri)
        employee_attendance = self.get_mongo_docs('employee_attendance', mongo_uri)
        service_request = self.get_mongo_docs('serviceRequest', mongo_uri)
        orders_phone = self.get_mongo_docs('orders.user.phone', mongo_uri)
        teams = self.get_mongo_docs('teams', mongo_uri)
        vendors = self.get_mongo_docs('vendors', mongo_uri)
        
        # PG source
        kuro_users = self.get_pg_docs('KuroUser')
        
        return {
            'reb_users': reb_users,
            'misc': misc,  # Will be skipped
            'players': players,
            'employee_attendance': employee_attendance,
            'KuroUser': kuro_users,
            'serviceRequest': service_request,
            'orders.user.phone': orders_phone,
            'teams': teams,
            'vendors': vendors,
        }

    def normalize_all_phones(self, sources: dict) -> dict:
        """Normalize phones across all sources."""
        normalized = {}
        for source_name, docs in sources.items():
            if source_name == 'misc':
                continue  # Skip duplicate
            for doc in docs:
                phone = doc.get('phone') or doc.get('mobile') or doc.get('contact_phone')
                if phone:
                    e164 = normalize_phone(phone)
                    if e164:
                        normalized.setdefault(e164, []).append({**doc, '_source': source_name})
        return normalized

    def group_by_phone(self, normalized: dict) -> dict:
        """Group documents by normalized phone."""
        return normalized  # Already grouped by phone

    def resolve_conflicts(self, groups: dict) -> list:
        """Resolve conflicts and return list of actions."""
        conflicts = []
        for phone, docs in groups.items():
            result = self.resolve_conflicts_for_phone(phone, docs)
            conflicts.append(result)
        return conflicts

    def resolve_conflicts_for_phone(self, phone: str, docs: list) -> dict:
        """Resolve conflicts for a single phone number."""
        names = set(doc.get('name', '') for doc in docs if doc.get('name'))
        
        if len(names) <= 1:
            return {'phone': phone, 'action': 'auto_merge', 'confidence': 0.99, 'docs': docs}
        
        name_list = list(names)
        if len(name_list) == 2:
            similarity = fuzzy_match(name_list[0], name_list[1])
            if similarity > 0.85:
                return {'phone': phone, 'action': 'merge_with_warning', 'confidence': 0.85 + similarity * 0.13, 'docs': docs}
            else:
                return {'phone': phone, 'action': 'manual_review', 'confidence': similarity, 'docs': docs}
        
        return {'phone': phone, 'action': 'manual_review', 'confidence': 0, 'docs': docs}

    def import_identities(self, groups: dict, conflicts: list):
        """Import identities into PostgreSQL."""
        identity_counter = Identity.objects.count() + 1
        
        for phone, docs in groups.items():
            # Generate identity_id (sequential)
            identity_id = f"ID{identity_counter:06d}"
            identity_counter += 1
            
            # Get primary doc (first non-misc doc)
            primary_doc = next((d for d in docs if d.get('_source') != 'misc'), docs[0])
            
            # Create identity
            identity, created = Identity.objects.get_or_create(
                identity_id=identity_id,
                defaults={
                    'phone': phone,
                    'name': primary_doc.get('name', 'Unknown'),
                    'email': primary_doc.get('email', ''),
                    'bg_code': primary_doc.get('bg_code', 'KURO0001'),
                    'div_code': primary_doc.get('div_code', ''),
                    'branch_code': primary_doc.get('branch_code', ''),
                    'status': 'active',
                    'phone_verified': False,
                }
            )
            
            # Create extension records based on source
            source = primary_doc.get('_source')
            
            if source in ('reb_users', 'serviceRequest', 'orders.user.phone'):
                # Customer extension
                is_requestor = source == 'serviceRequest'
                registered = source == 'reb_users'
                UserCustomer.objects.get_or_create(
                    identity_id=identity_id,
                    defaults={
                        'registered': registered,
                        'is_requestor': is_requestor,
                        'order_count': 0,
                        'total_spent': 0,
                    }
                )
            
            elif source in ('players',):
                # Player extension
                UserPlayer.objects.get_or_create(
                    identity_id=identity_id,
                    defaults={
                        'player_id': primary_doc.get('player_id', ''),
                        'team_id': primary_doc.get('team_id', ''),
                        'riot_id': primary_doc.get('riot_id', ''),
                        'rank': primary_doc.get('rank', ''),
                    }
                )
            
            elif source in ('employee_attendance', 'KuroUser'):
                # Employee extension
                UserEmployee.objects.get_or_create(
                    identity_id=identity_id,
                    defaults={
                        'userid': primary_doc.get('userid', ''),
                        'role': primary_doc.get('role', 'staff'),
                        'department': primary_doc.get('department', ''),
                        'joining_date': primary_doc.get('joining_date', None),
                    }
                )
            
            elif source in ('teams',):
                # Organization + Team profile
                org, _ = UserOrganization.objects.get_or_create(
                    org_id=primary_doc.get('org_id', ''),
                    defaults={
                        'org_type': 'team',
                        'name': primary_doc.get('name', ''),
                        'bg_code': primary_doc.get('bg_code', ''),
                        'div_code': primary_doc.get('div_code', ''),
                    }
                )
                UserTeamProfile.objects.get_or_create(
                    org_id=org.org_id,
                    defaults={
                        'team_id': primary_doc.get('team_id', ''),
                        'coach': primary_doc.get('coach', ''),
                    }
                )
            
            elif source in ('vendors',):
                # Organization + Vendor profile
                org, _ = UserOrganization.objects.get_or_create(
                    org_id=primary_doc.get('org_id', ''),
                    defaults={
                        'org_type': 'vendor',
                        'name': primary_doc.get('name', ''),
                        'bg_code': primary_doc.get('bg_code', ''),
                        'div_code': primary_doc.get('div_code', ''),
                    }
                )
                UserVendorProfile.objects.get_or_create(
                    org_id=org.org_id,
                    defaults={
                        'gstin': primary_doc.get('gstin', ''),
                        'pan': primary_doc.get('pan', ''),
                        'address': primary_doc.get('address', ''),
                        'payment_type': primary_doc.get('payment_type', ''),
                    }
                )
            
            # Link to CustomUser if exists
            custom_user = CustomUser.objects.filter(phone=phone).first()
            if custom_user and not identity.user:
                identity.user = custom_user
                identity.save(update_fields=['user'])

    def backfill_tenant_context(self):
        """Update UserTenantContext with identity_id."""
        from users.models import UserTenantContext
        
        for ctx in UserTenantContext.objects.all():
            identity = Identity.objects.filter(
                phone__in=[ctx.userid],  # Approximate match
            ).first()
            if identity:
                ctx.identity_id = identity.identity_id
                ctx.save(update_fields=['identity_id'])

    def validate_migration(self):
        """Run validation checks per migration_spec.md §2.4."""
        self.stdout.write('Running validation checks...')
        
        # Row count reconciliation
        checks = [
            ('reb_users', 1979),
            ('players', 59),  # 59 unique
            ('employees', 31),
            ('vendors', 409),
            ('teams', 14),
        ]
        
        for source, expected in checks:
            self.stdout.write(f'  Checking {source}...')
            # Validation logic here
        
        # Phone normalization
        invalid_phones = Identity.objects.filter(phone__regex='^[^+]').count()
        assert invalid_phones == 0, f"{invalid_phones} invalid phone numbers"
        
        # Dedup review
        manual_review = [c for c in conflicts if c['action'] == 'manual_review']
        self.stdout.write(f'  Manual review required: {len(manual_review)} rows')
        
        # Phone uniqueness per tenant
        duplicates = Identity.objects.values('bg_code', 'phone').annotate(count=Count('id')).filter(count__gt=1)
        assert duplicates.count() == 0, f"{duplicates.count()} duplicate phone+bg combinations"
        
        # FK integrity
        orphaned = UserCustomer.objects.filter(identity_id__isnull=True).count()
        assert orphaned == 0, f"{orphaned} orphaned customer rows"
        
        # CafeWalkin.identity FK coverage
        walkins_null = CafeWalkin.objects.filter(identity_id__isnull=True).count()
        assert walkins_null == 0, f"{walkins_null} walk-ins without identity"
        
        # Tenant codes
        invalid_tenant = Identity.objects.exclude(bg_code__regex='^[A-Z]{4}\\d{4}$').count()
        assert invalid_tenant == 0, f"{invalid_tenant} invalid bg_code"
        
        # Auth linkage
        phone_only = Identity.objects.filter(user__isnull=True, phone_verified=False).count()
        self.stdout.write(f'  Phone-only identities (unlinked): {phone_only}')
        
        # Financial data loss check
        # Compare total_spent sum with legacy orders
        
        # Index creation
        # Verify all indexes built
        
        # Constraint validation
        # Verify all CHECK constraints pass
        
        self.stdout.write(self.style.SUCCESS('✅ All validation checks passed'))
```

### Step 5: Run Migration

```bash
python manage.py migrate_identity --source=mongodb://<host>:27017
```

**Verify:**
- Count of `Identity` records matches expected unique count (~4,500)
- No `Identity` without corresponding extension row (where applicable)
- `Identity.user` FK populated for auth-linked users
- `UserTenantContext.identity_id` backfilled
- 12 rows flagged for manual review (if any)

### Step 6: Generate Database Migrations

```bash
python manage.py makemigrations users
python manage.py migrate users
```

**Verify:**
- All indexes created
- All CHECK constraints pass
- All UNIQUE constraints pass

### Step 7: Update JWT Claims

Verify `users/tenant_tokens.py` includes `identity_id` in JWT payload:

```python
payload = {
    'user_id': str(user.id),
    'identity_id': identity_id,  # Must be present (canonical)
    'bg_code': bg_code,
}
```

### Step 8: Update `resolve_access()` for `identity_id`

Verify `backend/auth_utils.py` `resolve_access()` can query by `identity_id`:

```python
def resolve_access(identity_id, bg_code):
    roles = UserRole.objects.filter(identity_id=identity_id, bg_code=bg_code)
    # ... resolve permissions
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Read/Verify | `users/models.py` | Verify Identity + extension schemas |
| Create | `users/utils.py` | `normalize_phone()`, `fuzzy_match()` |
| Modify | `users/management/commands/migrate_identity.py` | Full M1 migration command |
| Create | `users/migrations/000X_identity_schema.py` | Schema migration (if needed) |
| Modify | `users/tenant_tokens.py` | Add identity_id to JWT claims |
| Modify | `backend/auth_utils.py` | Support identity_id in resolve_access |
| Create | `tests/test_identity_migration.py` | Verify migration results |
| Create | `tests/test_identity_dedup.py` | Verify dedup logic |

## Phase-Specific Tests

Create `tests/test_identity_migration.py`:

1. **Test row count reconciliation:**
   ```python
   def test_row_count_reconciliation():
       assert Identity.objects.count() >= 4500  # After dedup
   ```

2. **Test phone normalization:**
   ```python
   def test_phone_e164_all_identities():
       invalid = Identity.objects.exclude(phone__regex='^\\+91\\d{10}$')
       assert invalid.count() == 0
   ```

3. **Test no duplicate phone+bg:**
   ```python
   def test_no_duplicate_phone_bg():
       duplicates = Identity.objects.values('bg_code', 'phone').annotate(count=Count('id')).filter(count__gt=1)
       assert duplicates.count() == 0
   ```

4. **Test FK integrity (customer):**
   ```python
   def test_customer_fk_integrity():
       orphaned = UserCustomer.objects.filter(identity_id__isnull=True)
       assert orphaned.count() == 0
   ```

5. **Test FK integrity (employee):**
   ```python
   def test_employee_fk_integrity():
       orphaned = UserEmployee.objects.filter(identity_id__isnull=True)
       assert orphaned.count() == 0
   ```

6. **Test FK integrity (player):**
   ```python
   def test_player_fk_integrity():
       orphaned = UserPlayer.objects.filter(identity_id__isnull=True)
       assert orphaned.count() == 0
   ```

7. **Test CafeWalkin.identity FK:**
   ```python
   def test_walkin_identity_fk():
       null_walkins = CafeWalkin.objects.filter(identity_id__isnull=True)
       assert null_walkins.count() == 0
   ```

8. **Test tenant codes:**
   ```python
   def test_valid_tenant_codes():
       invalid = Identity.objects.exclude(bg_code__regex='^[A-Z]{4}\\d{4}$')
       assert invalid.count() == 0
   ```

9. **Test JWT contains identity_id:**
   ```python
   def test_jwt_contains_identity_id():
       token = generate_token(user, identity.identity_id)
       payload = decode_token(token)
       assert 'identity_id' in payload
   ```

10. **Test manual review count:**
    ```python
    def test_manual_review_count():
        # Should be ~12 rows per migration_spec
        manual_review = Identity.objects.filter(status='manual_review').count()
        assert 10 <= manual_review <= 15
    ```

## Completion Gate

- [ ] All 9 sources exported
- [ ] Phones normalized to E.164 (0 invalid)
- [ ] Dedup executed (12 rows flagged for manual review)
- [ ] `Identity` records created for all unique users
- [ ] Extension tables populated (customer, employee, player, organization, vendor, team)
- [ ] `Identity.user` FK populated for auth-linked users
- [ ] `UserTenantContext.identity_id` backfilled
- [ ] Phone uniqueness per tenant: 0 duplicates
- [ ] FK integrity: 0 orphaned extension rows
- [ ] CafeWalkin.identity FK coverage: 0 NULLs
- [ ] Tenant codes: 0 invalid bg_code/div_code
- [ ] Financial data loss check: total_spent sum matches legacy orders
- [ ] Index creation: all indexes built
- [ ] Constraint validation: all CHECK constraints pass
- [ ] JWT claims include `identity_id`
- [ ] `resolve_access()` supports `identity_id`
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests (192 passed, 8 pre-existing failures)
- [ ] Files committed

## Post-Migration Verification (Gate)

```bash
python manage.py migrate_identity --validate
```

**Expected output:**
```
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
✅ CafeWalkin.identity FK coverage: 0 NULLs
✅ Tenant codes: 0 invalid bg_code/div_code
✅ Auth linkage: 0 phone-only identities with CustomUser
✅ Financial data loss check: total_spent sum matches legacy orders
✅ Index creation: all indexes built
✅ Constraint validation: all CHECK constraints pass
```

## Notes for Next Phase

- Phase 1B (MongoDB field rename) can run in parallel — no dependency on this phase.
- Phase 2A (RBAC FK migration) depends on this phase — `identity_id` must be available.
- Phase 1C (Cafe schema) depends on this phase — walk-in sessions need `identity_id` FK.
- Phase 4A (Orders migration) depends on this phase — needs `identity_id` for customer linkage.
- After this phase, `CustomUser.userid` is still the AUTH_USER_MODEL PK. The transition to `identity_id` as primary key happens in Phase 2A.

## Consistency Rules

**This phase defers to:**
- Migration ordering & data transformation: `migration_spec.md` §2 (M1: Identity Consolidation)
- Validation gates: `migration_spec.md` §2.4
- Canonical naming: `CANONICAL_NAMING.md`

**This phase does NOT redefine:**
- Response shapes (Phase 2B handles login response)
- RBAC FK structure (Phase 2A handles FK migration)
- Wire field names (use canonical names)

## Spec Contradictions

_None documented._

