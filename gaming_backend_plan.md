# Gaming Backend — Migration Plan

## Status

| Area | Status |
|---|---|
| Per-BG routing removal in `backend/utils.py` | ✅ Complete |
| `get_db()` function removed | ✅ Complete |
| `get_collection()` simplified (no legacy `$or`, no configurable `db_name`) | ✅ Complete |
| `teams/millie.py` updated to use `get_mongo_client()['KungOS_Mongo_One']` | ✅ Complete |
| `bgData` compound index `(bgcode, entity)` | ✅ Created |
| Gaming Django apps | 🔴 Not started |
| Gaming PostgreSQL models | 🔴 Not started |
| Gaming data migration (MongoDB → PG) | 🔴 Not started |

---

## 1. Collection Inventory

### Gaming Collections Missing from KungOS_Mongo_One (9 collections)

These exist in the legacy dump at `/home/chief/Coding-Projects/db/mongo-ip-172-31-33-158-2026-04-27-040005.dump` but were **never migrated**:

| # | Collection | Description | Estimated Docs |
|---|---|---|---|
| 1 | `prods` | Gaming products catalog | TBD |
| 2 | `builds` | Custom PC builds (gaming-specific) | TBD |
| 3 | `kgbuilds` | KuroGaming custom builds | TBD |
| 4 | `components` | PC components (CPU, GPU, RAM, PSU, SSD, etc.) | TBD |
| 5 | `accessories` | Gaming accessories (keyboard, mouse, headset, etc.) | TBD |
| 6 | `monitors` | Gaming monitors | TBD |
| 7 | `networking` | Networking gear (routers, switches, cables) | TBD |
| 8 | `external` | External peripherals & storage | TBD |
| 9 | `tempproducts` | Temporary/test products | TBD |

### Gaming Collections Already in KungOS_Mongo_One (7 collections)

These were migrated during the `restore_kuropurchase` run and already have tenant fields:

| Collection | Docs | Description |
|---|---|---|
| `players` | 117 | Gaming player profiles (riotid, rank, mobile) |
| `teams` | 14 | Gaming teams (coach, teamid) |
| `tournaments` | 3 | Tournament events |
| `tourneyregister` | 56 | Tournament registrations |
| `kgorders` | 9,162 | KuroGaming orders (contains embedded builds + components) |
| `tporders` | 229 | TP orders |
| `tpbuilds` | 123 | TP builds |

**Total gaming-related collections: 16** (9 missing + 7 existing)

---

## 2. Proposed Django Apps Structure

```
kungos_gaming/          # Main gaming app
├── models/
│   ├── __init__.py
│   ├── product.py      # Product, Build, Component, Accessory, Monitor, Networking, External
│   ├── tournament.py   # Tournament, Team, Player, TournamentRegistration
│   └── order.py        # GamingOrder (extends existing order patterns)
├── serializers.py
├── views.py
├── urls.py
├── migrations/
└── management/
    └── commands/
        └── seed_gaming_data.py   # Migration command

gaming_products/        # Product catalog sub-app (if needed for separation)
gaming_tournaments/     # Tournament management sub-app (if needed)
```

**Recommended: Single app `kungos_gaming`** with modular models. Split only if the codebase grows beyond ~500 lines per model file.

---

## 3. PostgreSQL Models

### 3.1 Product Domain (5 models)

```python
# kungos_gaming/models/product.py

from django.db import models
from users.models import CustomUser


class Product(models.Model):
    """Gaming product catalog — unified across all sub-categories."""
    CATEGORY_CHOICES = [
        ('cpu', 'CPU'),
        ('gpu', 'GPU'),
        ('ram', 'RAM'),
        ('mob', 'Motherboard'),
        ('ssd', 'SSD/NVMe'),
        ('hdd', 'HDD'),
        ('psu', 'Power Supply'),
        ('tower', 'Cabinet/Tower'),
        ('cooler', 'CPU Cooler'),
        ('monitor', 'Monitor'),
        ('keyboard', 'Keyboard'),
        ('mouse', 'Mouse'),
        ('headset', 'Headset'),
        ('networking', 'Networking'),
        ('accessory', 'Accessory'),
        ('other', 'Other'),
    ]

    productid = models.CharField(max_length=50, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, db_index=True)
    maker = models.CharField(max_length=100, blank=True)
    collection = models.CharField(max_length=50, blank=True)  # e.g., 'components', 'monitors'
    type = models.CharField(max_length=50, blank=True)        # e.g., 'cpu', 'gpu'
    mrp = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    emp_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    taxrate = models.SmallIntegerField(default=18)
    hsn_code = models.CharField(max_length=20, blank=True)
    units = models.CharField(max_length=20, default='num')
    images = models.JSONField(default=list)
    specs = models.JSONField(default=dict)
    summary = models.JSONField(default=list)
    overview = models.JSONField(default=dict)
    status = models.CharField(max_length=50, blank=True)
    priority = models.SmallIntegerField(default=10)
    quantity = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    delete_flag = models.BooleanField(default=False)
    bgcode = models.CharField(max_length=20, db_index=True)
    entity = models.CharField(max_length=50, db_index=True)
    branch = models.CharField(max_length=100, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    updated_date = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='products_created')

    class Meta:
        db_table = 'gaming_products'
        indexes = [
            models.Index(fields=['bgcode', 'entity']),
            models.Index(fields=['category']),
            models.Index(fields=['productid']),
        ]


class Build(models.Model):
    """Custom PC build — composition of Components."""
    buildid = models.CharField(max_length=50, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    bgcode = models.CharField(max_length=20, db_index=True)
    entity = models.CharField(max_length=50, db_index=True)
    branch = models.CharField(max_length=100, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'gaming_builds'
        indexes = [
            models.Index(fields=['bgcode', 'entity']),
        ]


class BuildComponent(models.Model):
    """Many-to-many through: which Components are in a Build."""
    build = models.ForeignKey(Build, on_delete=models.CASCADE, related_name='components')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='build_components')
    quantity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = 'gaming_build_components'
        unique_together = ['build', 'product']
```

### 3.2 Tournament Domain (4 models)

```python
# kungos_gaming/models/tournament.py

from django.db import models
from users.models import CustomUser


class Team(models.Model):
    teamid = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    coach = models.CharField(max_length=255, blank=True)
    bgcode = models.CharField(max_length=20, db_index=True)
    entity = models.CharField(max_length=50, db_index=True)
    branch = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
    delete_flag = models.BooleanField(default=False)

    class Meta:
        db_table = 'gaming_teams'


class Player(models.Model):
    playerid = models.CharField(max_length=50, unique=True, db_index=True)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='players')
    userid = models.CharField(max_length=50, blank=True)  # links to CustomUser
    name = models.CharField(max_length=255)
    riotid = models.CharField(max_length=255, blank=True)  # Valorant-specific
    rank = models.CharField(max_length=50, blank=True)
    mobile = models.CharField(max_length=15, blank=True)
    bgcode = models.CharField(max_length=20, db_index=True)
    entity = models.CharField(max_length=50, db_index=True)
    branch = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
    delete_flag = models.BooleanField(default=False)

    class Meta:
        db_table = 'gaming_players'


class Tournament(models.Model):
    tournamentid = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    venue = models.CharField(max_length=255, blank=True)
    game = models.CharField(max_length=100)  # e.g., 'Valorant', 'BGMI'
    tour_date = models.DateField()
    reg_start = models.DateField()
    reg_end = models.DateField(null=True, blank=True)
    reg_fees = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    prize = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rankings = models.JSONField(default=list)
    active = models.BooleanField(default=False)
    delete_flag = models.BooleanField(default=False)
    bgcode = models.CharField(max_length=20, db_index=True)
    entity = models.CharField(max_length=50, db_index=True)
    branch = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'gaming_tournaments'


class TournamentRegistration(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='registrations')
    player = models.ForeignKey(Player, on_delete=models.PROTECT, related_name='registrations')
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gaming_tournament_registrations'
        unique_together = ['tournament', 'player']
```

### 3.3 Order Domain (1 model)

```python
# kungos_gaming/models/order.py

from django.db import models
from users.models import CustomUser


class GamingOrder(models.Model):
    """Extends the order pattern used by kgorders/tporders."""
    orderid = models.CharField(max_length=50, unique=True, db_index=True)
    estimate_no = models.CharField(max_length=50, blank=True)
    po_ref = models.CharField(max_length=50, blank=True)
    invoice_no = models.CharField(max_length=50, blank=True)
    order_status = models.CharField(max_length=50, default='Pending')
    totalprice = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    totalpricebgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxes = models.JSONField(default=dict)  # {'5': 0, '12': 0, '18': 27388.98, '28': 0}
    roundoff = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    fin_year = models.CharField(max_length=10, blank=True)
    order_date = models.DateTimeField(null=True, blank=True)
    dispatchby_date = models.DateTimeField(null=True, blank=True)

    # Customer info (denormalized from MongoDB pattern)
    customer_name = models.CharField(max_length=255, blank=True)
    customer_phone = models.CharField(max_length=15, blank=True)
    customer_company = models.CharField(max_length=255, blank=True)
    billing_address = models.JSONField(default=dict)  # addressline1, city, pincode, state, gstin, pan

    bgcode = models.CharField(max_length=20, db_index=True)
    entity = models.CharField(max_length=50, db_index=True)
    branch = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
    delete_flag = models.BooleanField(default=False)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'gaming_orders'
        indexes = [
            models.Index(fields=['bgcode', 'entity']),
            models.Index(fields=['orderid']),
            models.Index(fields=['order_status']),
        ]
```

---

## 4. Migration Framework

### 4.1 Architecture

```
Legacy MongoDB Dump (50MB)
        │
        ▼
┌─────────────────────────┐
│  mongorestore --dryRun   │  ← Restore to temp DB for inspection
│  /tmp/gaming_temp_db     │     (requires sudo install — see §4.3)
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│  seed_gaming_data.py     │  ← Django management command
│  backend/management/     │
│  commands/               │
├─────────────────────────┤
│  Step 1: Extract schema  │  Parse game collection structures
│  Step 2: Transform       │  Convert MongoDB docs → PG model instances
│  Step 3: Upsert          │  Bulk insert with conflict handling
│  Step 4: Verify          │  Count comparison, checksum validation
│  Step 5: Inject tenant   │  bgcode, entity, branch from Switchgroupmodel
└─────────────────────────┘
        │
        ▼
PostgreSQL (kuro-cadence DB)
```

### 4.2 Migration Command Design

```python
# backend/management/commands/seed_gaming_data.py

"""
Migrate gaming collections from MongoDB dump to PostgreSQL.

Usage:
    python manage.py seed_gaming_data --help
    python manage.py seed_gaming_data --dry-run
    python manage.py seed_gaming_data --verify
    python manage.py seed_gaming_data --output report.json
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import json


class Command(BaseCommand):
    help = 'Migrate gaming collections from MongoDB dump to PostgreSQL'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                          help='Show what would be migrated without writing')
        parser.add_argument('--verify', action='store_true',
                          help='Verify migration counts match source')
        parser.add_argument('--output', type=str, default=None,
                          help='Write report to JSON file')
        parser.add_argument('--collection', type=str, default=None,
                          help='Migrate only this collection (default: all)')

    def handle(self, *args, **options):
        # Collections to migrate: prods, builds, kgbuilds, components,
        # accessories, monitors, networking, external, tempproducts
        pass
```

### 4.3 Installing mongorestore (Prerequisite)

The MongoDB 8.0+ concurrent dump format cannot be read by pymongo or standard BSON parsers. It requires `mongorestore` from MongoDB Database Tools.

**Installation options:**

1. **apt (preferred)** — Requires adding MongoDB repo:
   ```bash
   echo 'deb [signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg] http://repo.mongodb.org/apt/ubuntu noble/mongodb-org/8.0 multiverse' | sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list
   sudo apt-get update && sudo apt-get install -y mongodb-database-tools
   ```
   ⚠️ This requires the MongoDB repo to be accessible. The `fastdl.mongodb.org` direct download returns "Access Denied" from this environment.

2. **Alternative: Restore dump to temp DB** — If mongorestore is installed:
   ```bash
   mongorestore --db gaming_temp /home/chief/Coding-Projects/db/mongo-ip-172-31-33-158-2026-04-27-040005.dump
   # Then query gaming_temp.prods, gaming_temp.builds, etc.
   mongorestore --nsRemove="gaming_temp." --drop --db KungOS_Mongo_One /home/chief/Coding-Projects/db/mongo-ip-172-31-33-158-2026-04-27-040005.dump --nsInclude="gaming_temp.prods:gaming_temp.builds:..."
   ```

3. **Alternative: Python BSON parser** — The dump file header is `m\xE2\x99\x81g` (MongoDB 8.0+ concurrent format). A custom parser would be needed since pymongo doesn't support this format.

---

## 5. Data Migration Mapping

### MongoDB → PostgreSQL Field Mapping

| MongoDB Collection | PG Table | Key Fields |
|---|---|---|
| `prods` | `gaming_products` | productid, title, category, maker, price, mrp, specs (JSON), bgcode, entity, branch |
| `builds` | `gaming_builds` | buildid, title, price, bgcode, entity, branch |
| `kgbuilds` | `gaming_builds` | Same schema as builds (merge with builds table) |
| `components` | `gaming_products` | productid, title, category='cpu'/'gpu'/'ram'/etc., maker, price, specs (JSON), bgcode, entity, branch |
| `accessories` | `gaming_products` | productid, title, category='accessory', maker, price, specs (JSON), bgcode, entity, branch |
| `monitors` | `gaming_products` | productid, title, category='monitor', maker, price, specs (JSON), bgcode, entity, branch |
| `networking` | `gaming_products` | productid, title, category='networking', maker, price, specs (JSON), bgcode, entity, branch |
| `external` | `gaming_products` | productid, title, category='other', maker, price, specs (JSON), bgcode, entity, branch |
| `tempproducts` | `gaming_products` | Same as products, flagged as temporary |

**Key insight:** The 9 missing collections map to just **3 PG tables**:
- `gaming_products` (7 collections: prods, components, accessories, monitors, networking, external, tempproducts)
- `gaming_builds` (2 collections: builds, kgbuilds)
- Plus existing tables for tournaments/orders

### Tenant Field Injection

All migrated documents must include:
```python
{
    'bgcode': switchgroup.bg_code,      # e.g., 'BG0001'
    'entity': entity_name,               # e.g., 'kurogaming' or 'rebellion'
    'branch': branch_name,               # e.g., 'Madhapur'
}
```

This matches the pattern established by `restore_kuropurchase.py`.

---

## 6. INSTALLED_APPS Update

Add to `backend/settings.py`:

```python
INSTALLED_APPS = [
    # ... existing apps ...
    'kungos_gaming',   # Gaming backend: products, tournaments, orders
]
```

---

## 7. Summary

| Metric | Value |
|---|---|
| Gaming collections to migrate | **9** (prods, builds, kgbuilds, components, accessories, monitors, networking, external, tempproducts) |
| PG tables to create | **3** (gaming_products, gaming_builds, gaming_build_components) |
| Existing gaming PG tables | **0** (PostgreSQL dump has no gaming tables) |
| Existing gaming Mongo collections | **7** (players, teams, tournaments, tourneyregister, kgorders, tporders, tpbuilds) |
| Total gaming collections (live + missing) | **16** |
| Django apps to create | **1** (kungos_gaming) |
| Migration command needed | **1** (seed_gaming_data) |
| Prerequisite | Install `mongodb-database-tools` (mongorestore) via apt with sudo |
