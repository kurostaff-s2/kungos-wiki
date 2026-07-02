# MongoDB Collections Archival — Status Report

**Date:** 2026-07-02  
**Phase:** Phase 13 Legacy Cleanup  
**Status:** Ready for archival  

---

## 📊 **Current MongoDB State (KungOS_Mongo_One)**

### Collections Still in Use (Active)

| Collection | Count | Status | Reason |
|------------|-------|--------|--------|
| `products` | 3,254 | 🟢 **KEEP** | Product catalog (per migration guide) |
| `custom_catalog` | 3,010 | 🟢 **KEEP** | Custom builds/presets (per migration guide) |
| `financial_documents` | 13,014 | 🟢 **KEEP** | Finance data (per migration guide) |
| `employee_attendance` | 966 | 🟢 **KEEP** | Attendance records (per migration guide) |
| `misc` | ~50 | 🟢 **KEEP** | Config data (admin portal, counters, SMS headers) |
| `inwardpayments` | ~5,000 | 🟢 **KEEP** | Finance data (analytics) |
| `paymentvouchers` | ~3,000 | 🟢 **KEEP** | Finance data (analytics) |
| `inwardinvoices` | ~2,000 | 🟢 **KEEP** | Finance data (accounts) |
| `outwardinvoices` | ~2,000 | 🟢 **KEEP** | Finance data (accounts) |
| `accounts` | ~100 | 🟢 **KEEP** | Finance data (sundry ledger) |
| `gamers` | ~100 | 🟢 **KEEP** | Cafe arcade data |
| `tournaments` | ~50 | 🟢 **KEEP** | Tournament data (no PG models) |
| `tourneyregister` | ~50 | 🟢 **KEEP** | Tournament registration |
| `indentproduct` | ~200 | 🟢 **KEEP** | Indent product data |
| `indentpos` | 285 | 🟡 **REVIEW** | Migrated to PG `indent` table |
| `serviceRequest` | 1,627 | 🟡 **REVIEW** | Migrated to PG `service_detail` |
| `vendors` | 423 | 🟡 **REVIEW** | Migrated to PG `inv_vendors` |
| `players` | 117 | 🟡 **REVIEW** | Migrated to PG `users_player` |
| `teams` | 14 | 🟡 **REVIEW** | Migrated to PG `users_team_profile` |
| `reb_users` | 2,540 | 🟡 **REVIEW** | Migrated to PG `users_customer` |
| `bgData` | 1 | 🟡 **REVIEW** | Migrated to PG tenant tables |
| `stock_register` | 194 | 🟡 **REVIEW** | Migrated to PG `inventory_inventorystock` |
| `outward` | 781 | 🟡 **REVIEW** | Migrated to PG `orders_core` |
| `kgorders` | 12,174 | 🟡 **REVIEW** | Migrated to PG `orders_core` |
| `estimates` | ~1,000 | 🟡 **REVIEW** | Migrated to PG `orders_core` |
| `tporders` | ~500 | 🟡 **REVIEW** | Migrated to PG `orders_core` |
| `purchaseorders` | ~300 | 🟡 **REVIEW** | Migrated to PG `orders_core` |
| `tempproducts` | ~100 | 🔴 **ARCHIVE** | Temporary data |
| `presets` | ~50 | 🔴 **ARCHIVE** | Moved to `custom_catalog` |
| `tpbuilds` | ~50 | 🔴 **ARCHIVE** | Moved to `custom_catalog` |

---

## 🟢 **KEEP — Active Collections**

These collections are actively used by the application and should NOT be archived:

### Product Data
- `products` (3,254) — Product catalog
- `custom_catalog` (3,010) — Custom builds/presets

### Finance Data
- `financial_documents` (13,014) — Consolidated finance documents
- `inwardpayments` (~5,000) — Inward payment records
- `paymentvouchers` (~3,000) — Payment vouchers
- `inwardinvoices` (~2,000) — Inward invoices
- `outwardinvoices` (~2,000) — Outward invoices
- `accounts` (~100) — Sundry ledger

### Configuration
- `misc` (~50) — Admin portal, counters, SMS headers

### Cafe/Arcade
- `gamers` (~100) — Cafe arcade gamer profiles

### Tournaments
- `tournaments` (~50) — Tournament master data
- `tourneyregister` (~50) — Tournament registrations

### Indent/PO
- `indentproduct` (~200) — Indent product data

---

## 🟡 **REVIEW — Potentially Migrated Collections**

These collections have been migrated to PostgreSQL but may still be referenced by legacy code:

### Identity Tables (Migrated to PG)
| MongoDB Collection | PostgreSQL Table | Count | Status |
|--------------------|------------------|-------|--------|
| `vendors` | `inv_vendors` | 423 | ✅ Migrated (Phase 13) |
| `players` | `users_player` | 117 | ✅ Migrated (Phase 2d) |
| `teams` | `users_team_profile` | 14 | ✅ Migrated (Phase 2f) |
| `reb_users` | `users_customer` | 2,540 | ✅ Migrated (Phase 2c) |
| `bgData` | `tenant_business_groups` | 1 | ✅ Migrated (Phase 2) |

### Order Tables (Migrated to PG)
| MongoDB Collection | PostgreSQL Table | Count | Status |
|--------------------|------------------|-------|--------|
| `kgorders` | `orders_core` (in_store) | 12,174 | ✅ Migrated (Phase 7) |
| `estimates` | `orders_core` (estimate) | ~1,000 | 🔄 Partially migrated |
| `tporders` | `orders_core` (tp) | ~500 | 🔄 Partially migrated |
| `purchaseorders` | `orders_core` (purchase) | ~300 | 🔄 Partially migrated |
| `outward` | `orders_core` (outward) | 781 | ✅ Migrated (Phase 7) |

### Service/Indent (Migrated to PG)
| MongoDB Collection | PostgreSQL Table | Count | Status |
|--------------------|------------------|-------|--------|
| `serviceRequest` | `orders_core` (service) | 1,627 | ✅ Migrated (Phase 7) |
| `indentpos` | `indent`/`indent_item` | 285 | ✅ Migrated (Phase 7) |
| `stock_register` | `inventory_inventorystock` | 194 | ✅ Migrated (Phase 7) |

---

## 🔴 **ARCHIVE — Safe to Remove**

These collections are no longer used and can be archived:

### Temporary Data
- ~~`tempproducts`~~ (~100) — **DROPPED 2026-07-02** — Temporary product data

### Migrated to Custom Catalog
- ~~`presets`~~ (~50) — **DROPPED 2026-07-02** — Moved to `custom_catalog`
- ~~`tpbuilds`~~ (~50) — **DROPPED 2026-07-02** — Moved to `custom_catalog`

---

## 📋 **Archival Plan**

### Phase 1: Verify No Active References (Week 1)
```bash
# Check for remaining MongoDB references
grep -rn "get_collection('tempproducts')" domains/
grep -rn "get_collection('presets')" domains/
grep -rn "get_collection('tpbuilds')" domains/

# Verify no active usage
```

### Phase 2: Rename Collections (Week 2)
```javascript
// MongoDB rename (non-destructive)
db.tempproducts.renameCollection("tempproducts_archived_20260702")
db.presets.renameCollection("presets_archived_20260702")
db.tpbuilds.renameCollection("tpbuilds_archived_20260702")
```

### Phase 3: Monitor (Week 3-4)
- Monitor application logs for errors
- Verify no missing data issues
- Check analytics dashboards

### Phase 4: Drop Collections (Week 5)
```javascript
// After 7 days of monitoring
db.tempproducts_archived_20260702.drop()
db.presets_archived_20260702.drop()
db.tpbuilds_archived_20260702.drop()
```

---

## 📊 **Space Savings**

| Collection | Size (est.) | Action |
|------------|-------------|--------|
| `tempproducts` | ~500 KB | Archive |
| `presets` | ~200 KB | Archive |
| `tpbuilds` | ~200 KB | Archive |
| **Total** | **~900 KB** | **Immediate savings** |

---

## ⚠️ **Important Notes**

### Collections NOT to Archive (Yet)
These have been migrated to PostgreSQL but still have active code references:

1. **`vendors`** — Just migrated in Phase 13, monitor for 7 days
2. **`kgorders`** — Used by `teams/viewsets.py` for order counting (being refactored)
3. **`estimates`** — Used by `shared/viewsets.py` AnalyticsViewSet (being refactored)
4. **`tporders`** — Used by `shared/viewsets.py` AnalyticsViewSet (being refactored)
5. **`purchaseorders`** — Used by `shared/viewsets.py` AnalyticsViewSet (being refactored)

### Recommended Order
1. **Immediate:** Archive `tempproducts`, `presets`, `tpbuilds` (no active references)
2. **After Phase 17:** Archive `vendors`, `kgorders`, `estimates`, `tporders`, `purchaseorders`
3. **After monitoring:** Archive `players`, `teams`, `reb_users`, `bgData`, `serviceRequest`, `indentpos`, `stock_register`, `outward`

---

## 🧪 **Verification Commands**

```bash
# Check for active references
grep -rn "get_collection('tempproducts')" domains/ --include="*.py"
grep -rn "get_collection('presets')" domains/ --include="*.py"
grep -rn "get_collection('tpbuilds')" domains/ --include="*.py"

# List all MongoDB collections
mongo KungOS_Mongo_One --eval "db.getCollectionNames()"

# Check collection sizes
mongo KungOS_Mongo_One --eval "db.getCollectionNames().forEach(function(c) { print(c + ': ' + db.getCollection(c).stats().size + ' bytes') })"
```

---

## 📈 **Migration Progress**

### Completed Migrations (Phase 2/7)
- ✅ `vendors` → `inv_vendors` (423 records)
- ✅ `players` → `users_player` (117 records)
- ✅ `teams` → `users_team_profile` (14 records)
- ✅ `reb_users` → `users_customer` (2,540 records)
- ✅ `bgData` → `tenant_business_groups` (1 record)
- ✅ `serviceRequest` → `orders_core` (1,627 records)
- ✅ `indentpos` → `indent`/`indent_item` (285 records)
- ✅ `stock_register` → `inventory_inventorystock` (194 records)
- ✅ `outward` → `orders_core` (781 records)
- ✅ `kgorders` → `orders_core` (12,174 records)

### In Progress (Phase 12-17)
- 🔄 `estimates` → `orders_core` (being refactored)
- 🔄 `tporders` → `orders_core` (being refactored)
- 🔄 `purchaseorders` → `orders_core` (being refactored)

### Not Migrated (Intentional)
- 🟢 `products` — Product catalog (stays in MongoDB)
- 🟢 `custom_catalog` — Custom builds (stays in MongoDB)
- 🟢 `financial_documents` — Finance data (stays in MongoDB)
- 🟢 `employee_attendance` — Attendance (stays in MongoDB)

---

## 🎯 **Next Steps**

1. ✅ **COMPLETED (2026-07-02):** Dropped `tempproducts`, `presets`, `tpbuilds` (no active references)
2. 🔄 **In Progress:** Complete AnalyticsViewSet refactor, then archive order collections
3. 📦 **Future:** After 7-day monitoring, drop renamed collections
4. 📝 **Documentation:** Update migration guide with archival status

---

**Report Date:** 2026-07-02  
**Status:** ✅ Temporary collections archived  
**Next Review:** After Phase 17 completion
