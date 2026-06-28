# Unified Inventory Management System

**Status:** Spec — IMPLEMENTED (Phase 8 + Phase 9)  
**Date:** 2026-06-27  
**Source:** Legacy MongoDB analysis, cafe_spec.md, ecommerce_spec.md  
**Purpose:** Universal inventory system serving all domains (eshop, tp, instore, cafe fnb, cafe arcade)

---

## 1. Domain Overview

The unified inventory system manages all product types across Kuro Gaming's business domains:

| Domain | Inventory Type | Collections Migrated |
|---|---|---|
| **E-Commerce (eshop)** | Products, Builds, Components | builds, kgbuilds, custombuilds, components, accessories, monitors, networking, external |
| **In-Store (tp)** | Products, Builds | builds, kgbuilds, custombuilds |
| **Cafe F&B** | Food & Beverage | products (82 items) |
| **Cafe Arcade** | Arcade Packages | presets (31 packages) |

**Total Items:** 2,294 (2,212 migrated + 82 F&B)  
**Total Stock Entries:** 372 (branch-level)  
**Total Movements:** 178 (audit trail)

---

## 2. Architecture

### 2.1 PostgreSQL Tables

| Table | Purpose | Records |
|---|---|---|
| `inventory_items` | Universal item registry | 2,294 |
| `inventory_stock` | Branch-level stock | 372 |
| `inventory_movements` | Audit trail | 178 |

### 2.2 Model Relationships

```
InventoryItem
    ├── inventory_stock (1:N) — Branch-level stock
    └── inventory_movements (1:N) — Movement history

InventoryStock
    └── inventory_movements (1:N) — Stock movements

InventoryMovement
    └── inventory_items (N:1) — Item reference
```

---

## 3. Data Migration

### 3.1 Legacy Collections Migrated

| Collection | Count | Type | Notes |
|---|---|---|---|
| `builds` | 258 | prebuilt | Pre-built PC builds with preset references |
| `kgbuilds` | 516 | prebuilt | Kuro Gaming pre-built variants |
| `custombuilds` | 1,995 | custom | Custom PC builds (ordered) |
| `components` | 164 | component | PC components (CPU, GPU, RAM, etc.) |
| `accessories` | 23 | accessory | PC accessories (mouse, keyboard, etc.) |
| `monitors` | 12 | monitor | Monitor catalog |
| `networking` | 5 | networking | Networking equipment |
| `products` | 82 | fnb | F&B products (migrated in Phase 8) |

### 3.2 Stock Register Migration

Legacy `stock_register` contains 194 items with:
- Serial number tracking (`sr_nos` TEXT[])
- Invoice-based stock entries
- Price variance tracking (avg, min, max)
- Branch-level stock

**Migration:** Each stock_register item becomes:
1. `InventoryItem` (universal registry)
2. `InventoryStock` (branch-level)
3. `InventoryMovement` (initial stock-in)

### 3.3 Builds & Presets

Pre-built PCs reference presets (hardware components):

```json
{
  "presets": {
    "cpu": ["PRECPU0064"],
    "mob": ["PREMOB0005"],
    "gpu": ["PREGPU0033"],
    "ram": ["PRERAM0010"],
    "psu": ["PREPSU0015"],
    "ssd": ["PRESSD0003"],
    "cooler": ["PRECOO0012"],
    "tower": ["PRETOW0026"],
    "wifi": ["PREWIF0001"],
    "os": ["PREOS0001"]
  }
}
```

**Metadata stored in `InventoryItem.metadata`:**
- `presets`: JSON object mapping component type → preset IDs
- `summary`: List of specifications
- `images`: List of image URLs
- `warranty`: Warranty information
- `series`: Product series (e.g., "servers", "renderedge")

---

## 4. Inventory Flow

### 4.1 Order Creation → Stock Deduction

When an order is created (eshop, in-store, or F&B):

```python
# 1. Create order in orders_core
order = OrderCore.objects.create(...)

# 2. Deduct stock for each item
for item in order.products:
    stock = InventoryStock.objects.select_for_update().get(
        item=item,
        branch_code=order.branch_code
    )
    stock.stock_quantity -= item.quantity
    stock.save()
    
    # 3. Record movement
    InventoryMovement.objects.create(
        item=item,
        branch_code=order.branch_code,
        movement_type='sale',
        quantity=-item.quantity,
        reference_type='order',
        reference_id=order.order_id,
    )
```

### 4.2 Stock Reconciliation

```python
# Low stock alert
low_stock = InventoryStock.objects.filter(
    stock_quantity__lte=F('low_stock_threshold')
)

# Stock audit
def reconcile_stock(item, branch_code):
    physical_count = get_physical_count(item, branch_code)
    system_count = InventoryStock.objects.get(
        item=item, branch_code=branch_code
    ).stock_quantity
    
    if physical_count != system_count:
        InventoryMovement.objects.create(
            item=item,
            branch_code=branch_code,
            movement_type='count_correction',
            quantity=physical_count - system_count,
            notes=f'Stock correction: {system_count} → {physical_count}',
        )
```

---

## 5. API Endpoints

### 5.1 Inventory Items

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/inventory/items/` | List all items (filter by collection, type, category) |
| `GET` | `/api/v1/inventory/items/{id}/` | Item detail with stock |
| `POST` | `/api/v1/inventory/items/` | Create item (admin) |
| `PATCH` | `/api/v1/inventory/items/{id}/` | Update item |

### 5.2 Stock Management

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/inventory/stock/` | List stock (filter by branch, item, low_stock) |
| `GET` | `/api/v1/inventory/stock/{id}/` | Stock detail |
| `PATCH` | `/api/v1/inventory/stock/{id}/` | Update stock quantity |
| `POST` | `/api/v1/inventory/stock/reconcile/` | Stock reconciliation |

### 5.3 Movements & Audit

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/inventory/movements/` | List movements (filter by item, branch, type) |
| `GET` | `/api/v1/inventory/movements/{id}/` | Movement detail |
| `POST` | `/api/v1/inventory/movements/create/` | Create movement (adjustment, transfer, etc.) |

### 5.4 Reports

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/inventory/reports/stock-level/` | Current stock levels by branch |
| `GET` | `/api/v1/inventory/reports/movements/` | Movement history report |
| `GET` | `/api/v1/inventory/reports/low-stock/` | Low stock alert report |

---

## 6. Domain Integration

### 6.1 E-Commerce (eshop)

- **Products:** `inventory_items` with `collection='builds'`, `collection='components'`, etc.
- **Stock:** `inventory_stock` per branch
- **Orders:** `orders_core` + `eshop_detail`
- **Stock deduction:** On order confirmation

### 6.2 In-Store (tp)

- **Products:** Same `inventory_items` (shared catalog)
- **Stock:** `inventory_stock` per branch
- **Orders:** `orders_core` + `in_store_detail`
- **Stock deduction:** On order completion

### 6.3 Cafe F&B

- **Products:** `inventory_items` with `category='fnb'`
- **Stock:** `inventory_stock` per branch
- **Orders:** `orders_core` + `cafe_fnb_detail`
- **Stock deduction:** On order creation (implemented)

### 6.4 Cafe Arcade

- **Packages:** `inventory_items` with `type='arcade_package'`
- **Stock:** Not tracked (time-based, not quantity-based)
- **Orders:** `orders_core` + `cafe_arcade_detail`
- **Stock deduction:** N/A (session-based)

---

## 7. Migration Phases

| Phase | Status | Description |
|---|---|---|
| **Phase 8** | ✅ Done | F&B inventory + stock deduction |
| **Phase 8b** | ✅ Done | Unified inventory migration (2,212 items) |
| **Phase 9** | Planned | E-commerce + Asset inventory integration |
| **Phase 10** | Planned | Legacy MongoDB retirement |

---

## 8. Legacy Pattern Mapping

### 8.1 stock_register → inventory_items + inventory_stock

| Legacy Field | New Field | Notes |
|---|---|---|
| `productid` | `item_code` | Unique identifier |
| `product_name` | `name` | Display name |
| `collection` | `collection` | Legacy taxonomy (components, food, etc.) |
| `type` | `type` | Legacy type (cooler, psu, Water, etc.) |
| `quantity` | `stock_quantity` | Current stock |
| `avgprice` | `avg_price` | Average cost |
| `minprice` | `min_price` | Minimum cost |
| `maxprice` | `max_price` | Maximum cost |
| `stock[].sr_nos` | `inventory_movements.sr_nos` | Serial numbers |
| `stock[].invoiceid` | `inventory_movements.reference_id` | Invoice reference |

### 8.2 builds → inventory_items (with presets metadata)

| Legacy Field | New Field | Notes |
|---|---|---|
| `productid` | `item_code` | Unique identifier |
| `title` | `name` | Display name |
| `presets` | `metadata.presets` | JSON object |
| `summary` | `metadata.summary` | Specification list |
| `price` | `base_price` | Base price |

---

## 9. Future Enhancements

### 9.1 Assets Tracking

- `inventory_assets` table for equipment (stations, controllers, PCs)
- Asset lifecycle tracking (purchase → deployment → maintenance → retirement)
- Asset-to-branch assignment

### 9.2 Cross-Branch Transfers

- `inventory_transfers` table for inter-branch stock movement
- Transfer approval workflow
- Transfer status tracking (pending → approved → shipped → received)

### 9.3 Purchase Orders

- `inventory_purchase_orders` table
- PO approval workflow
- PO-to-stock reconciliation

### 9.4 Barcode/QR Integration

- Barcode generation for `inventory_items`
- QR code scanning for stock counts
- Mobile app integration

---

## 9. Phase 9 — Asset Depreciation & E-Commerce Integration (IMPLEMENTED)

### 9.1 Asset Tracking

| Table | Purpose | Records |
|---|---|---|
| `inventory_assets` | Equipment tracking (stations, controllers, PCs) | 32 |
| `inventory_asset_movements` | Asset lifecycle events | 33 |
| `asset_depreciation` | Depreciation schedules | 32 |

**Asset Types:**
- `gaming_station` (21 assets)
- `console` (6 assets)
- `controller` (4 assets)
- `vr_station` (1 asset)

**Asset Statuses:**
- `active` (31), `maintenance` (1), `retired`, `decommissioned`, `in_transit`

**Asset Movement Types:**
- `purchase`, `transfer_in`, `transfer_out`, `maintenance`, `repair`, `retirement`, `decommission`, `status_change`

### 9.2 Depreciation

**Methods:**
- `straight_line`: Fixed annual amount
- `reducing_balance`: Rate × current book value

**Depreciation Parameters by Asset Type:**

| Asset Type | Useful Life | Salvage Value | Method |
|---|---|---|---|
| `gaming_station` | 5 years | ₹10,000 | straight-line |
| `vr_station` | 4 years | ₹5,000 | straight-line |
| `console` | 4 years | ₹3,000 | straight-line |
| `controller` | 3 years | ₹500 | straight-line |
| `pc_build` | 5 years | ₹10,000 | straight-line |

**Depreciation Fields:**
- `useful_life_years`: Total useful life in years
- `salvage_value`: Expected value at end of life
- `annual_depreciation`: Fixed annual depreciation amount
- `depreciation_rate`: Rate for reducing-balance method
- `accumulated_depreciation`: Total depreciation to date
- `book_value`: Current book value (cost - accumulated depreciation)
- `started_at`: Depreciation start date
- `ends_at`: Depreciation end date
- `is_active`: Whether depreciation is still running

### 9.3 E-Commerce Integration

**Eshop Link Model:**
- `InventoryItemEshopLink` bridges PostgreSQL `inventory_items` to MongoDB eshop `productid`
- Fields: `item` (FK), `productid` (MongoDB product ID), `category`, `is_active`
- Unique constraint: `(item, productid)`

**Total Eshop Links:** 2,168 (82 F&B + 258 builds + 1,828 custombuilds)

**Eshop Order Creation Flow:**
1. User submits order with products from cart
2. System resolves products via `InventoryItemEshopLink`
3. System deducts stock from `inventory_stock`
4. System creates `OrderCore` + `EshopDetail` records
5. System records `InventoryMovement` for each item
6. System generates payment info (UPI URL, Cashfree PG, Bank Transfer)

**Eshop Order Statuses:**
- `payment_pending` → `confirmed` → `processing` → `shipped` → `delivered` → `completed`
- `cancelled`, `refunded`, `failed`

### 9.4 Asset Reports

**Report Endpoints:**

| Endpoint | Description |
|---|---|
| `GET /api/v1/inventory/reports/assets/{id}/maintenance` | Maintenance history for an asset |
| `GET /api/v1/inventory/reports/assets/{id}/lifecycle` | Lifecycle cost report (purchase cost + maintenance - depreciation) |
| `GET /api/v1/inventory/reports/branch/assets?branch_code=X` | Branch asset summary (by status, by type, financial totals) |
| `GET /api/v1/inventory/reports/depreciation` | Depreciation schedule for all assets |

**Lifecycle Cost Report Fields:**
- `financial`: purchase_cost, maintenance_cost, replacement_cost, lifecycle_cost, accumulated_depreciation, book_value
- `age`: purchase_date, age_days, age_years, useful_life_years, remaining_years, utilization_pct
- `usage`: maintenance_events, transfers, usage_hours, cost_per_hour
- `depreciation`: method, annual_depreciation, salvage_value, starts_at, ends_at

---

> **Implementation state:** Phase 8 + 8b + Phase 9 complete. 2,294 items migrated. Stock deduction working for F&B and eshop. Asset tracking with 32 assets and 33 movements. Depreciation schedules for all assets. Eshop order creation with stock deduction. Reports working. Phase 10 (legacy retirement) pending.
