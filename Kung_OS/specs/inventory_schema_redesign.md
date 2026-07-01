# Inventory Schema Redesign — First Principles

**Status:** Proposed  
**Date:** 2026-07-01  
**Trigger:** Outward collection analysis revealed stock↔asset lifecycle gap  
**Scope:** Complete redesign of `inventory_` domain tables

---

## 1. Problem Essence

**Core problem:** Track every physical unit from purchase → stock → (sold OR installed as asset) → lifecycle events → end of life, with full audit trail and warranty tracking.

**So what? chain:**
- "We need serial tracking" → so we know which physical unit went where
- So what? → so we can handle warranty claims and replacements
- So what? → so we know the cost and history of every unit
- So what? → so we can make informed decisions about stock, assets, and replacements
- ← **GROUND TRUTH:** Every physical unit has a lifecycle that crosses domain boundaries (stock, asset, sold, returned) and must be traceable end-to-end.

**Success criteria:**
1. Query "where is serial X now?" → O(1) lookup
2. Query "full lifecycle of serial X" → ordered movement trail
3. Stock → Asset conversion → recorded with audit trail
4. Asset → Stock conversion → recorded with audit trail
5. Warranty expiry alerts → queryable per serial
6. Component-level tracking within PC builds → individual serials trackable even when part of a build
7. No data duplication across domains

---

## 2. Assumptions Challenged

| Assumption | Category | Challenge | Verdict |
|------------|----------|-----------|---------|
| Assets and stock are separate domains | Historical | A GPU can be stock today, asset tomorrow, stock again | **Discard** — unified serial registry needed |
| `sr_nos JSONB` on movements is sufficient for serial tracking | Technical | No referential integrity; can't query "current status of serial X" | **Discard** — needs FK-backed registry |
| `InventoryAsset.serial_number` as unique string is fine | Technical | Serial can exist in multiple contexts (stock, asset, sold); uniqueness should be per-item, not global | **Discard** — unique(item_id, serial_number) |
| Movement tables should be separate (stock vs asset) | Technical | Conversions between domains need cross-references | **Keep** — separate tables are cleaner, but add conversion types and unified serial FK |
| `InventoryItem.category='asset'` makes sense | Design | An item can be both sellable stock AND equipment (e.g., RTX 4080) | **Discard** — category describes the item type, not its current role |
| Depreciation belongs on InventoryAsset directly | Design | Not all assets are depreciated; some are sold items with warranty | **Keep** as separate table, but decouple from asset-only |
| `assets.py` service layer is correct | Code | References fields not in Django model (bg_code, div_code, asset_name, vendor, purchase_price) | **Fix** — service layer is stale/wrong |

---

## 3. Ground Truths

1. **A serial number identifies one physical unit** — it has one location and one status at any point in time
2. **A physical unit can change roles** — stock → sold → returned → stock → asset → decommissioned → stock
3. **An item type can fill multiple roles** — "RTX 4080" is a product that can be sold, kept as stock, or installed in a gaming station
4. **Movements are immutable events** — once recorded, they never change (append-only audit trail)
5. **Current state is derived from movements** — but for performance, denormalize current state on the serial record
6. **Warranty is per-serial, not per-item** — each physical unit has its own warranty period
7. **PC builds are compositions** — a build is a collection of individual serialized components, each independently trackable
8. **Stock quantity and serial tracking coexist** — some items are tracked by count (F&B), some by serial (PC components), some by both
9. **Multi-tenancy applies** — every record is scoped to a branch (and transitively to div/bg)
10. **Product catalog lives in MongoDB** — PostgreSQL tracks inventory state only (item_code, quantities, serials, movements)

---

## 4. Reasoning Chain

### 4.1 The Three Layers

```
Layer 1: WHAT (Item Catalog)
  └─ InventoryItem — "What kind of thing is this?"
     └─ item_code, category, is_serialized, is_consumable, unit_type

Layer 2: WHICH (Physical Unit Registry)
  └─ SerialRecord — "Which specific physical unit?"
     └─ serial_number, current_location, current_status, current_branch
     └─ warranty_expiry, purchase_cost, purchase_date

Layer 3: WHAT HAPPENED (Movement Trail)
  └─ InventoryMovement (stock events) + InventoryAssetMovement (asset events)
     └─ immutable, append-only, references SerialRecord
```

### 4.2 Why Not Merge Stock and Asset?

**Question:** Can't we just have one table for everything?

**Answer:** No — stock and asset have fundamentally different concerns:

| Concern | Stock | Asset |
|---------|-------|-------|
| Primary unit | Quantity (count) | Individual unit (serial) |
| Financial | Cost of goods sold | Depreciation / book value |
| Status | In stock, reserved, sold | Active, maintenance, retired |
| Location | Branch shelf | Physical location within branch |
| Lifecycle events | Purchase, sale, adjustment | Transfer, maintenance, repair, decommission |
| Pricing | avg/min/max price | purchase_cost, book_value |
| Reporting | Stock levels, turnover | Asset register, depreciation schedule |

**They share the serial registry (Layer 2), but diverge at Layer 3 (movements) and financial tracking.**

### 4.3 Why Not Use InventoryAsset for Sold Items?

**Question:** Can't we treat sold items as "assets" with status='sold'?

**Answer:** No — semantic mismatch:
- `InventoryAsset` tracks **company-owned equipment** (gaming stations, PCs in the cafe)
- Outward serials track **products sold to customers** (components shipped with orders)
- Mixing them conflates "our equipment" with "customer's property"
- Depreciation applies to company assets, not to items sold to customers
- Warranty tracking is different: asset warranty = manufacturer warranty on equipment; sold item warranty = warranty we owe the customer

### 4.4 The Conversion Bridge

**Question:** How do we track stock → asset and asset → stock?

**Answer:** Two movement types + state change on SerialRecord, linked by `conversion_id`:

```
Stock → Asset (single atomic transaction):
  1. Generate UUID conversion_id
  2. InventoryMovement(movement_type='to_asset', serial=X, conversion_id=uuid)
  3. SerialRecord.current_location = 'in_asset', asset_id = Y
  4. InventoryAssetMovement(movement_type='from_stock', asset=Y, conversion_id=uuid)

Asset → Stock (single atomic transaction):
  1. Generate UUID conversion_id
  2. InventoryAssetMovement(movement_type='to_stock', asset=Y, conversion_id=uuid)
  3. SerialRecord.current_location = 'in_stock', asset_id = NULL
  4. InventoryMovement(movement_type='from_asset', serial=X, conversion_id=uuid)
```

**Transactional integrity:** All steps in a conversion must execute within a single `transaction.atomic()` block. If any step fails, all steps roll back. The `conversion_id` (UUID) links the paired movements across both tables, enabling audit queries like "show all conversions in the last 30 days."

Both movements are recorded (one in each domain table) for complete audit trail.

### 4.5 Current State Invariant

**Invariant:** `SerialRecord.current_location` must always be consistent with the movement trail.

```
current_location = last_movement.movement_type → location mapping
  'purchase' → 'in_stock'
  'serial_sold' → 'sold'
  'serial_return' → 'returned'
  'to_asset' → 'in_asset'
  'from_asset' → 'in_stock'
  'adjustment' → 'in_stock' (quantity correction)
```

Application logic enforces this on every movement creation.

---

## 5. Target Schema

### 5.1 New Model: `SerialRecord`

```python
class SerialRecord(models.Model):
    """Unified serial registry — one row per physical serial number.
    
    Bridges stock and asset domains. Tracks current location, status,
    warranty, and financial data for every individually trackable unit.
    
    A serial number can transition through multiple roles:
      stock → sold → returned → stock → asset → decommissioned → stock
    """
    
    LOCATION_CHOICES = [
        ('in_stock', 'In Stock'),
        ('sold', 'Sold to Customer'),
        ('returned', 'Returned (warranty/RMA)'),
        ('in_asset', 'Installed as Asset'),
        ('in_transit', 'In Transit'),
        ('under_repair', 'Under Repair'),
        ('disposed', 'Disposed/Lost'),
    ]
    
    item = models.ForeignKey(
        'InventoryItem', on_delete=models.CASCADE,
        related_name='serial_records',
        help_text="The item type (catalog entry) this serial belongs to"
    )
    serial_number = models.CharField(
        max_length=100,
        help_text="Manufacturer or internal serial number"
    )
    
    # Tenant scoping
    bg_code = models.CharField(
        max_length=20, db_index=True,
        help_text="Business group this serial belongs to"
    )
    div_code = models.CharField(
        max_length=50, blank=True, default='', db_index=True,
        help_text="Division code (derived from branch hierarchy)"
    )
    
    # Current state (denormalized for O(1) lookup)
    current_location = models.CharField(
        max_length=20, choices=LOCATION_CHOICES, default='in_stock', db_index=True
    )
    current_branch = models.CharField(
        max_length=50, blank=True, default='', db_index=True,
        help_text="Branch where this unit currently resides"
    )
    
    # Stock context (populated when sold)
    sold_to_order = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Order ID this unit was sold with"
    )
    sold_to_customer = models.ForeignKey(
        'users.Identity',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sold_serials',
        help_text="Customer identity who purchased this unit"
    )
    sold_date = models.DateField(null=True, blank=True)
    
    # Financial (from purchase)
    purchase_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Unit cost from purchase order"
    )
    purchase_date = models.DateField(
        null=True, blank=True,
        help_text="Date this unit was purchased (from PO)"
    )
    
    WARRANTY_SOURCE_CHOICES = [
        ('manufacturer', 'Manufacturer'),
        ('estimated', 'Estimated'),
        ('custom', 'Custom'),
    ]
    
    # Warranty
    warranty_expiry = models.DateField(
        null=True, blank=True, db_index=True,
        help_text="Warranty expiration date (per-serial)"
    )
    warranty_source = models.CharField(
        max_length=20, blank=True, default='',
        choices=WARRANTY_SOURCE_CHOICES,
        help_text="Source of warranty date: manufacturer, estimated, or custom"
    )
    
    # Asset context (populated when converted to asset)
    asset = models.OneToOneField(
        'InventoryAsset', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='serial_record',
        help_text="Asset record if this unit is currently installed as equipment"
    )
    
    # Drift detection — movement count must match actual movement trail
    movement_count = models.PositiveIntegerField(
        default=0, db_index=True,
        help_text="Must match SELECT count(*) FROM inventory_movement WHERE serial_record_id = X"
    )
    
    # Tenant sync tracking — when bg_code/div_code were last propagated from branch
    tenant_synced_at = models.DateTimeField(null=True, blank=True)
    
    # Source system (promoted from metadata for queryability)
    source_system = models.CharField(
        max_length=50, blank=True, default='', db_index=True,
        help_text="Origin system: outward_products, outward_builds, purchase_order, manual"
    )
    migration_batch = models.CharField(
        max_length=50, blank=True, default='',
        help_text="Migration batch ID for traceability (e.g., 'outward_20260701')"
    )
    
    # Metadata (flexible extension for non-queryable data)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Audit
    created_by = models.BigIntegerField(null=True, blank=True, help_text="identity_id of creator")
    updated_by = models.BigIntegerField(null=True, blank=True, help_text="identity_id of last updater")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'inventory_serial_record'
        ordering = ['item__item_code', 'serial_number']
        unique_together = ('item', 'serial_number')
        indexes = [
            models.Index(fields=['current_location']),
            models.Index(fields=['serial_number']),
            models.Index(fields=['warranty_expiry']),
            models.Index(fields=['current_branch', 'current_location']),
            models.Index(fields=['movement_count']),
            models.Index(fields=['source_system']),
        ]
    
    def __str__(self):
        return f"{self.item.item_code}/{self.serial_number} ({self.current_location})"
```

### 5.2 Modified: `InventoryItem`

**Changes:**
- Remove `category='asset'` — an item is not inherently an asset; it becomes one through conversion
- Keep `is_serialized` flag — determines whether SerialRecord entries are created
- Add explicit `requires_serial` and `supports_serial` distinction

```python
CATEGORY_CHOICES = [
    ('product', 'Product (sellable)'),
    ('fnb', 'Food & Beverage'),
    ('arcade_package', 'Arcade Package'),
    ('component', 'PC Component'),
    ('accessory', 'Accessory'),
]

# New boolean flags for serial tracking policy
requires_serial = models.BooleanField(
    default=False, db_index=True,
    help_text="Serial tracking REQUIRED for this item type (e.g., high-value PC components). "
              "System will reject non-serialized stock entries."
)
supports_serial = models.BooleanField(
    default=False, db_index=True,
    help_text="Serial tracking OPTIONAL for this item type (e.g., monitors, peripherals). "
              "Serial records may be created but are not mandatory."
)

# Business rule:
# - requires_serial=True → SerialRecord entries MANDATORY for all stock movements
# - requires_serial=False, supports_serial=True → SerialRecord entries OPTIONAL
# - requires_serial=False, supports_serial=False → count-only tracking (F&B, consumables)

### 5.3 Modified: `InventoryMovement`

**Changes:**
- Add `to_asset` / `from_asset` movement types
- Remove `sr_nos JSONB` — serials referenced via junction table `InventoryMovementSerial`
- Add `conversion_id` (UUID) to link paired stock↔asset movements

```python
MOVEMENT_TYPE_CHOICES = [
    ('purchase', 'Purchase'),
    ('sale', 'Sale'),
    ('adjustment', 'Adjustment'),
    ('transfer_in', 'Transfer In'),
    ('transfer_out', 'Transfer Out'),
    ('waste', 'Waste'),
    ('return', 'Return'),
    ('count_correction', 'Count Correction'),
    ('serial_sold', 'Serial Sold'),
    ('serial_return', 'Serial Return'),
    ('to_asset', 'Converted to Asset'),      # NEW
    ('from_asset', 'Returned from Asset'),   # NEW
]
```

**Serial reference via junction table:**

```python
class InventoryMovementSerial(models.Model):
    """Junction table: InventoryMovement ↔ SerialRecord (many-to-many).
    
    Replaces sr_nos JSONB with FK-backed referential integrity.
    Bulk movements become multiple rows in this table (one per serial).
    """
    movement = models.ForeignKey(
        'InventoryMovement', on_delete=models.CASCADE,
        related_name='serial_records'
    )
    serial_record = models.ForeignKey(
        'SerialRecord', on_delete=models.PROTECT,
        related_name='movements'
    )
    
    class Meta:
        db_table = 'inventory_movement_serial'
        indexes = [
            models.Index(fields=['serial_record']),
            models.Index(fields=['movement']),
        ]
```

**Bulk movement performance:** A single bulk sale of 10 units creates 1 `InventoryMovement` row + 10 `InventoryMovementSerial` rows. Querying by serial uses `SELECT * FROM inventory_movement_serial WHERE serial_record_id = X` — indexed, O(log n).

**Updated InventoryMovement model (key fields):**

```python
class InventoryMovement(models.Model):
    # ... existing fields (item, branch_code, movement_type, quantity, ...)
    # REMOVED: sr_nos = models.JSONField(default=list, blank=True)
    
    # NEW: Conversion bridge link (UUID)
    conversion_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="Links paired stock↔asset movements (e.g., to_asset + from_stock). "
                  "NULL for non-conversion movements."
    )
    
    # ... existing fields (notes, created_by, created_at)
```

**Updated InventoryAssetMovement model (key fields):**

```python
class InventoryAssetMovement(models.Model):
    # ... existing fields (asset, movement_type, from_branch, to_branch, ...)
    
    # NEW: Conversion bridge link (UUID)
    conversion_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="Links paired stock↔asset movements (e.g., from_stock + to_asset). "
                  "NULL for non-conversion movements."
    )
    
    # ... existing fields (cost, notes, created_by, created_at)
```

### 5.4 Modified: `InventoryAsset`

**Changes:**
- Replace `serial_number` string with FK to `SerialRecord`
- Remove global unique constraint on serial (now unique per item in SerialRecord)
- Asset becomes a "role" that a serialized item takes on

**Financial field ownership:**

| Field | SerialRecord | InventoryAsset | Rule |
|-------|-------------|----------------|------|
| `purchase_cost` | Per-unit cost from PO | Aggregate build cost | SerialRecord is immutable once set from PO; InventoryAsset can change as components are swapped |
| `purchase_date` | Date unit was purchased | Date asset was registered | SerialRecord is immutable; InventoryAsset can be updated |
| `warranty_expiry` | Per-serial warranty from manufacturer | Asset-level warranty (composite) | SerialRecord is source of truth for individual component warranty; InventoryAsset tracks overall asset warranty |

**Example:** A PC build (InventoryAsset) has 5 components (SerialRecords). Each component has its own `purchase_cost` and `warranty_expiry`. The asset's `purchase_cost` is the sum of all components (can change if a component is swapped).

```python
class InventoryAsset(models.Model):
    """Equipment asset tracking — gaming stations, PCs, controllers, high-value items.
    
    An asset represents a unit of company equipment. It may be:
    - A single serialized component (e.g., a monitor)
    - A composite of multiple serialized components (e.g., a PC build)
    - A non-serialized item (e.g., furniture)
    
    The primary physical unit (if serialized) is linked via serial_record.
    Additional components are tracked via AssetInstallation.
    """
    
    ASSET_TYPE_CHOICES = [
        ('gaming_station', 'Gaming Station'),
        ('vr_station', 'VR Station'),
        ('pc_build', 'PC Build'),
        ('console', 'Console (PS5, etc.)'),
        ('controller', 'Controller'),
        ('monitor', 'Monitor'),
        ('peripheral', 'Peripheral'),
        ('furniture', 'Furniture'),
        ('other', 'Other Equipment'),
    ]
    
    ASSET_STATUS_CHOICES = [
        ('active', 'Active'),
        ('maintenance', 'Under Maintenance'),
        ('retired', 'Retired'),
        ('decommissioned', 'Decommissioned'),
        ('in_transit', 'In Transit'),
    ]
    
    asset_code = models.CharField(max_length=50, unique=True, db_index=True)
    item = models.ForeignKey(
        'InventoryItem', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assets',
        help_text="Item type (optional for composite assets like PC builds)"
    )
    asset_type = models.CharField(max_length=30, choices=ASSET_TYPE_CHOICES)
    
    # Primary serialized unit (if applicable)
    serial_record = models.OneToOneField(
        'SerialRecord', on_delete=models.PROTECT,
        null=True, blank=True, related_name='current_asset',
        help_text="The physical unit this asset represents (NULL for non-serialized assets)"
    )
    
    status = models.CharField(max_length=20, choices=ASSET_STATUS_CHOICES, default='active')
    branch_code = models.CharField(max_length=50, db_index=True)
    location = models.CharField(max_length=100, blank=True, default='')
    
    # Financial
    purchase_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    
    # Composite assets (PC builds) — specifications hold component list
    specifications = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'inventory_asset'  # renamed from inventory_inventoryasset
        ordering = ['branch_code', 'asset_type', 'asset_code']
        indexes = [
            models.Index(fields=['branch_code', 'status']),
            models.Index(fields=['asset_type', 'status']),
        ]
```

### 5.5 New Model: `AssetInstallation`

For composite assets (PC builds) where multiple serialized items form one asset.
Tracks which physical units are installed in which asset, enabling component-level
replacement tracking.

```python
class AssetInstallation(models.Model):
    """Installation record for a serialized unit within a composite asset.
    
    Tracks when a physical unit (SerialRecord) was installed into an asset,
    when it was removed, and why. Enables component-level replacement tracking
    for composite assets like PC builds.
    """
    
    asset = models.ForeignKey(
        'InventoryAsset', on_delete=models.CASCADE,
        related_name='installations'
    )
    bg_code = models.CharField(
        max_length=20, db_index=True,
        help_text="Business group (denormalized from asset for tenant-scoped queries)"
    )
    serial_record = models.ForeignKey(
        'SerialRecord', on_delete=models.PROTECT,
        related_name='installations'
    )
    component_role = models.CharField(
        max_length=50, blank=True, default='',
        help_text="Role in the asset: CPU, GPU, RAM, SSD, etc."
    )
    installed_date = models.DateField(null=True, blank=True)
    removed_date = models.DateField(null=True, blank=True)
    removal_reason = models.CharField(max_length=100, blank=True, default='')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'inventory_asset_installation'
        ordering = ['asset', 'component_role']
        indexes = [
            models.Index(fields=['asset', 'is_active']),
            models.Index(fields=['serial_record']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['asset', 'serial_record'],
                condition=models.Q(is_active=True),
                name='uq_active_asset_installation',
            ),
        ]
```

### 5.6 Modified: `InventoryAssetMovement`

**Changes:**
- Add `to_stock` / `from_stock` movement types for conversion bridge

```python
MOVEMENT_TYPE_CHOICES = [
    ('purchase', 'Purchase'),
    ('transfer_in', 'Transfer In'),
    ('transfer_out', 'Transfer Out'),
    ('maintenance', 'Maintenance'),
    ('repair', 'Repair'),
    ('retirement', 'Retirement'),
    ('decommission', 'Decommission'),
    ('status_change', 'Status Change'),
    ('inventory_count', 'Inventory Count'),
    ('to_stock', 'Returned to Stock'),        # NEW — asset → stock conversion
    ('from_stock', 'Converted from Stock'),   # NEW — stock → asset conversion
    ('component_swap', 'Component Replacement'),  # NEW — sub-component change
]
```

### 5.7 Unchanged Models

The following models require no changes:

| Model | Reason |
|-------|--------|
| `InventoryItem` | Minor changes only (see §5.2: category deprecation) |
| `InventoryStock` | Branch-level quantity tracking — unchanged |
| `StockAudit` / `StockAuditItem` | Physical count reconciliation — unchanged |
| `Indent` / `IndentItem` | Purchase requisitions — unchanged |
| `Vendor` | Supplier registry — unchanged |
| `AssetDepreciation` | Financial depreciation — unchanged (still one-to-one with asset) |
| `InventoryItemEshopLink` | MongoDB bridge — unchanged |

---

## 6. Data Flow: Outward Migration

### 6.1 Per Outward Record

```
For each outward record (781 total):
  1. Parse products[] and builds[].serials[]
  2. For each serial in products[].sr_no[]:
     a. Find or create InventoryItem (via productid)
     b. Find or create SerialRecord(serial_number)
        - bg_code, div_code = resolve from outward.entity/branch
        - current_location = 'sold'
        - sold_to_order = outward.orderid
        - sold_date = outward.created_date
        - warranty_expiry = outward_date + 1 year (estimated)
        - metadata.source = 'outward_products'
     c. Create InventoryMovement:
        - movement_type = 'serial_sold'
        - quantity = -1
        - reference_type = 'order'
        - reference_id = outward.orderid
     d. Create InventoryMovementSerial:
        - movement_id = (from step c)
        - serial_record_id = (from step b)
  3. For each build in builds[]:
     a. For each serial in build.serials[]:
        - Same as step 2, but:
        - metadata.source = 'outward_builds'
        - metadata.build_id = build.buildid (if available)
        - metadata.component_role = build.component (if available)
        - If build maps to a gaming station asset: create AssetInstallation
  4. Update stock_register.sold[] in MongoDB (mirror)
```

### 6.2 Warranty Rotation Detection

```
For serials appearing in multiple outward records (164 detected):
  0. Pre-filter: exclude known duplicate outward records (§6.3 cases)
  1. Order outward records by date
  2. First occurrence: movement_type = 'serial_sold'
  3. Subsequent occurrences:
     a. Compute gap = date_diff(first, subsequent)
     b. If gap < 7 days: flag as metadata.rotation_type = 'data_duplicate'
        (likely same shipment recorded twice — skip, don't create movements)
     c. If gap >= 7 days AND gap < 30 days:
        - Create InventoryMovement(movement_type = 'serial_return') — implicit return
        - Create InventoryMovement(movement_type = 'serial_sold') — re-shipment
        - metadata.rotation_type = 'warranty_return'
        - Update SerialRecord to latest state
     d. If gap >= 30 days:
        - Flag as metadata.rotation_type = 'manual_review_required'
        (long gap suggests possible data error or unusual return pattern)
  4. Post-migration: review all 'data_duplicate' and 'manual_review_required' flags manually
```

### 6.3 Duplicate Outward Records

```
For orders with duplicate outward records (TP23000027, TP23000030):
  1. Compare serial lists — if identical, skip duplicate
  2. If different, treat as partial shipment (both valid)
```

### 6.4 Orphaned Outward Records

```
For outward records without matching order (KG23000031, KG23000081):
  1. Create SerialRecord records as normal
  2. Set sold_to_order = outward.orderid (preserves reference)
  3. Set metadata.orphaned = true
  4. Also store in KungOS_Mongo_One.outward_archived (audit trail)
```

---

## 7. Migration Plan

### Phase A: Schema Changes (Django Migration)

1. Create `SerialRecord` model (with movement_count, source_system, migration_batch, tenant_synced_at)
2. Create `AssetInstallation` model
3. Create `InventoryMovementSerial` junction table (replaces sr_nos JSONB)
4. Add `conversion_id` (UUID) to `InventoryMovement` and `InventoryAssetMovement`
5. Add `requires_serial` and `supports_serial` boolean flags to `InventoryItem`
6. Add conversion movement types to `InventoryMovement` and `InventoryAssetMovement`
7. Alter `InventoryAsset`: replace `serial_number` with `serial_record` FK
8. Rename `inventory_inventoryasset` → `inventory_asset` via `AlterModelTable`
9. Remove `category='asset'` from `InventoryItem.CATEGORY_CHOICES`

### Phase B: Data Migration (Outward → SerialRecord)

1. Read `kc_inspect.outward` (781 records)
2. Create `SerialRecord` records (3,802 unique serials)
3. Create `InventoryMovement` records (serial_sold, serial_return)
4. Handle warranty rotations (164 duplicate serials)
5. Handle orphaned records (2)
6. Handle malformed record (1)
7. Deduplicate outward records (2 orders)

### Phase C: Enrichment

1. Populate `stock_register.sold[]` from outward data
2. Link `SerialRecord` to `InventoryItem` via productid
3. Infer warranty dates (outward_date + 1 year, source='estimated')
4. Populate `purchase_cost` from PO data (where available)

### Phase D: Service Layer Fix

1. Rewrite `assets.py` to use correct model fields
2. Add `convert_stock_to_asset()` and `convert_asset_to_stock()` functions
3. Add `create_serial_movement()` helper

---

## 8. Entity Relationship Diagram

```
InventoryItem (catalog)
    │
    ├─ is_serialized? ──yes──► SerialRecord (3,802+ rows)
    │                              │
    │                              ├─ current_location: stock/sold/returned/asset
    │                              ├─ current_branch
    │                              ├─ sold_to_order, sold_to_customer, sold_date
    │                              ├─ purchase_cost, purchase_date
    │                              ├─ warranty_expiry, warranty_source
    │                              ├─ movement_count (drift detection)
    │                              ├─ source_system, migration_batch
    │                              │
    │                              ├─ current_asset ──one─► InventoryAsset (equipment)
    │                              │                            │
    │                              │                            └─ installations ──► AssetInstallation (PC build parts)
    │                              │                                                   │
    │                              │                                                   └─ serial_record (back-ref)
    │                              │
    │                              └─ movements ──many─► InventoryMovementSerial ──► InventoryMovement
    │
    ├─ stock_entries ──► InventoryStock (branch quantities)
    ├─ movements ──► InventoryMovement (stock events)
    ├─ assets ──► InventoryAsset (when item is equipment type)
    └─ eshop_links ──► InventoryItemEshopLink (MongoDB bridge)

InventoryMovement (stock events)
    ├─ movement_type: purchase/sale/serial_sold/serial_return/to_asset/from_asset/...
    └─ conversion_id: UUID (links paired stock↔asset movements)

InventoryAssetMovement (asset events)
    ├─ movement_type: transfer/maintenance/repair/to_stock/from_stock/component_swap/...
    └─ conversion_id: UUID (links paired stock↔asset movements)

AssetDepreciation (financial)
    └─ one-to-one with InventoryAsset

InventoryMovementSerial (junction: movement ↔ serial)
    └─ FK to InventoryMovement + FK to SerialRecord
```

---

## 9. Key Queries (Post-Redesign)

### "Where is serial X now?"
```sql
SELECT serial_number, current_location, current_branch, sold_to_order, asset_id
FROM inventory_serial_record
WHERE serial_number = 'SN21253G024238';
```

### "Full lifecycle of serial X"
```sql
SELECT m.movement_type, m.branch_code, m.reference_type, m.reference_id, m.created_at
FROM inventory_movement_serial ims
JOIN inventory_movement m ON ims.movement_id = m.id
JOIN inventory_serial_record sr ON ims.serial_record_id = sr.id
WHERE sr.serial_number = 'SN21253G024238'
ORDER BY m.created_at;
```

### "All items under warranty expiring this month"
```sql
SELECT serial_number, item__item_code,
       current_location, warranty_expiry, sold_to_order
FROM inventory_serial_record
WHERE warranty_expiry BETWEEN NOW() AND NOW() + INTERVAL '30 days'
  AND current_location IN ('sold', 'in_asset');
```

### "Stock → Asset conversions this month"
```sql
SELECT sr.serial_number, sr.item__item_code,
       m.created_at, m.reference_id
FROM inventory_movement m
JOIN inventory_movement_serial ims ON m.id = ims.movement_id
JOIN inventory_serial_record sr ON ims.serial_record_id = sr.id
WHERE m.movement_type = 'to_asset'
  AND m.created_at >= NOW() - INTERVAL '30 days';
```

### "Drift detection: SerialRecords with mismatched movement count"
```sql
SELECT sr.id, sr.serial_number, sr.movement_count,
       (SELECT count(*) FROM inventory_movement_serial ims WHERE ims.serial_record_id = sr.id) AS actual_count
FROM inventory_serial_record sr
WHERE sr.movement_count != (
    SELECT count(*) FROM inventory_movement_serial ims WHERE ims.serial_record_id = sr.id
);
```

### "Assets with expired warranty"
```sql
SELECT a.asset_code, sr.serial_number, a.asset_type,
       a.warranty_expiry, a.status
FROM inventory_asset a
LEFT JOIN inventory_serial_record sr ON a.serial_record_id = sr.id
WHERE a.warranty_expiry < NOW()
  AND a.status = 'active';
```

### "Component replacement history for Station #7"
```sql
SELECT ai.component_role, sr.serial_number,
       ai.installed_date, ai.removed_date, ai.removal_reason
FROM inventory_asset_installation ai
JOIN inventory_serial_record sr ON ai.serial_record_id = sr.id
WHERE ai.asset_id = (SELECT id FROM inventory_asset WHERE asset_code = 'STATION-007')
ORDER BY ai.component_role, ai.installed_date;
```

---

## 10. Migration Notes (Greenfield)

**All inventory tables are empty** — this is a clean-slate migration. No backward compatibility shims needed.

### Model Changes (applied fresh, no data migration needed)
1. `InventoryAsset.serial_number` (CharField) → `serial_record` (OneToOneFK to SerialRecord)
   - No `@property` shim needed — no existing code references the old field
   - Table renamed: `inventory_inventoryasset` → `inventory_asset` via `AlterModelTable`

2. `InventoryItem.category='asset'` removed from choices
   - No existing data to convert — simply omit from CATEGORY_CHOICES

3. `assets.py` service layer references non-existent fields
   - Already broken — rewrite to use correct model fields (Phase D)

### New Tables (created empty, populated by migration scripts)
1. `inventory_serial_record` — populated from outward collection (3,802 serials)
2. `inventory_asset_installation` — populated from outward builds (429 records)
3. `inventory_movement_serial` — junction table, populated alongside InventoryMovement records
4. New movement types — added to choices, no existing data affected
5. `conversion_id` (UUID) on InventoryMovement and InventoryAssetMovement — NULL for non-conversion movements

---

## 11. Stress Test

1. **If a serial is sold, returned, resold 10 times:** SerialRecord.current_location always reflects latest state. Movement trail has 20 entries (10 sold + 10 return). Query performance: O(1) for current state, O(n) for history (indexed by serial_number).

2. **If a PC build has 15 components swapped over 3 years:** AssetInstallation has ~30 entries (15 original + 15 replacements). Active components filtered by `is_active=True`. Original components have `removed_date` set.

3. **If stock count and serial count diverge:** InventoryStock tracks quantity (count). SerialRecord tracks individual units. Reconciliation via stock audit: `StockAuditItem` compares `system_quantity` (from stock table) vs `counted_quantity` (physical count). Discrepancy triggers `count_correction` movement.

4. **If an asset is decommissioned and components returned to stock:** 
   - InventoryAssetMovement(movement_type='decommission') 
   - AssetInstallation entries marked `is_active=False`, `removed_date`=today
   - SerialRecord.current_location = 'in_stock' for each component
   - InventoryMovement(movement_type='from_asset') for each component

---

## 12. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v1.0 | 2026-07-01 | Initial | First principles redesign proposal |
| v1.1 | 2026-07-01 | Naming | Renamed InventorySerializedItem → SerialRecord, AssetComponent → AssetInstallation |
| v1.2 | 2026-07-01 | Review | Fixed 3 HIGH: §5.3 FK contradiction, §4.5 invariant values, §5.1 sold_to_customer type. Fixed 5 MODERATE: tenant scoping, SQL syntax, audit fields, warranty rotation logic. Fixed 4 LOW: category conversion, warranty_source choices, db_table migration, builds handling. |
| v1.3 | 2026-07-01 | Greenfield | Simplified for clean-slate migration: removed backward compat shims (§10), removed @property serial_number, removed deprecated category='asset', simplified Phase A. |
| v1.4 | 2026-07-02 | Production | Replaced sr_nos JSONB with InventoryMovementSerial junction table (FK-backed). Added conversion_id (UUID) to movement tables for transactional integrity. Added movement_count for drift detection. Fixed sold_to_customer to proper FK. Defined requires_serial/supports_serial. Clarified financial field ownership. Tightened warranty rotation threshold (7-30 days vs >30 days manual review). Added source_system/migration_batch columns. |
