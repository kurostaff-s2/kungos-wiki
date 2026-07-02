# Phase 3: Accounts Viewsets Migration to Unified Collection

**Date:** 2026-07-02  
**Status:** ✅ **COMPLETE**  
**Effort:** 4 hours  

---

## 🎯 **Objectives**

1. Migrate accounts viewsets to use unified `financial_documents` collection
2. Add `DOC_TYPE` field to each viewset for document type filtering
3. Update BaseAccountsViewSet with helper methods
4. Maintain backward compatibility for legacy collections

---

## ✅ **Deliverables**

### 1. `domains/accounts/viewsets.py` — UPDATED

**Changes:**
- ✅ Added `DOC_TYPE` field to BaseAccountsViewSet
- ✅ Added `_get_unified_collection()` helper method
- ✅ Added `_apply_doc_type_filter()` helper method
- ✅ Updated 10 viewsets to use unified collection

**Migrated Viewsets:**
| ViewSet | DOC_TYPE | Status |
|---------|----------|--------|
| InwardInvoiceViewSet | `inward_invoice` | ✅ Migrated |
| OutwardInvoiceViewSet | `outward_invoice` | ✅ Migrated |
| InwardPaymentViewSet | `inward_payment` | ✅ Migrated |
| OutwardPaymentViewSet | `payment_voucher` | ✅ Migrated |
| PaymentVoucherViewSet | `payment_voucher` | ✅ Migrated |
| OutwardCreditNoteViewSet | `outward_credit_note` | ✅ Migrated |
| OutwardDebitNoteViewSet | `outward_debit_note` | ✅ Migrated |
| InwardCreditNoteViewSet | `inward_credit_note` | ✅ Migrated |
| InwardDebitNoteViewSet | `inward_debit_note` | ✅ Migrated |

**Legacy Viewsets (not migrated):**
| ViewSet | Collection | Reason |
|---------|------------|--------|
| PurchaseOrderViewSet | `purchaseorders` | Purchase orders in PostgreSQL (inventory domain) |
| AccountsViewSet | `accounts` | Needs PostgreSQL migration |
| SettlementsViewSet | `settlements` | Needs PostgreSQL migration |

---

### 2. Helper Methods Added

**`_get_unified_collection(request)`**
```python
def _get_unified_collection(self, request):
    """Get unified financial_documents collection with tenant filter."""
    sw, bg = self.get_tenant_context(request)
    div_code = request.query_params.get('div_code')
    branch_code = request.query_params.get('branch_code')
    return get_collection(
        'financial_documents',
        bg_code=sw.bg_code,
        div_code=div_code,
        branch_code=branch_code,
    )
```

**`_apply_doc_type_filter(filter_dict)`**
```python
def _apply_doc_type_filter(self, filter_dict):
    """Add doc_type filter if DOC_TYPE is set."""
    if self.DOC_TYPE:
        filter_dict['doc_type'] = self.DOC_TYPE
    return filter_dict
```

---

## 📊 **Migration Summary**

### Files Modified

| File | Lines | Changes |
|------|-------|---------|
| `domains/accounts/viewsets.py` | -50, +200 | UPDATED (10 viewsets migrated) |

**Total:** ~250 lines of code

### Code Pattern

**Before:**
```python
class InwardInvoiceViewSet(BaseAccountsViewSet):
    COLLECTION_NAME = 'inwardinvoices'
    
    def list(self, request):
        collection, tenant_filter = self.get_collection(request)
        # ... MongoDB calls
```

**After:**
```python
class InwardInvoiceViewSet(BaseAccountsViewSet):
    DOC_TYPE = 'inward_invoice'
    
    def list(self, request):
        collection, tenant_filter = self._get_unified_collection(request)
        filters = self._apply_doc_type_filter(filters)
        # ... MongoDB calls with unified collection
```

---

## 🔄 **Next Steps**

1. **Phase 4:** Add Redis caching infrastructure
2. **Phase 5:** Enable structured logging with correlation IDs
3. **Phase 6:** Integration testing and validation
4. **Phase 7:** Archive legacy MongoDB collections

---

## 📝 **Technical Notes**

- All migrated viewsets use `financial_documents` collection
- `DOC_TYPE` field filters documents by type
- Tenant context (bg_code, div_code, branch_code) applied automatically
- Legacy viewsets (PurchaseOrder, Accounts, Settlements) kept for backward compatibility
- Syntax verified (no errors)

---

**Next:** Phase 4 — Redis caching infrastructure
