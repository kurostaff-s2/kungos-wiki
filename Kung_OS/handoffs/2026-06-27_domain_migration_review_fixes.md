# Domain Migration Review Fixes: Handoff

**Date:** 2026-06-27  
**Status:** Ready for Execution  
**Priority:** High (Security & Architecture)  
**Total Estimated Time:** 6-8 hours

---

## Executive Summary

Review identified **10 issues** across migrated domain modules. This handoff covers all 7 actionable items, organized by priority and phase.

| Priority | Issue | Phase | Time | Risk |
|----------|-------|-------|------|------|
| **High** | Missing authentication | Immediate | 1 hr | Security |
| **High** | Hardcoded bg_code | Immediate | 30 min | Tenant isolation |
| **High** | Business logic in viewsets | Phase 2 | 3-4 hrs | Architecture |
| **High** | Naming conventions | Phase 2 | 1 hr | Consistency |
| **Medium** | Missing event emissions | Phase 3 | 1 hr | Cross-cutting |
| **Medium** | Code duplication | Phase 3 | 30 min | Maintainability |
| **Medium** | Missing tests | Ongoing | 2 hrs | Coverage |

---

## Phase 0: Immediate Fixes (Security & Tenant Isolation)

**Duration:** 1.5 hours  
**Risk:** High (if not fixed)  
**Dependencies:** None

### Issue 1: Missing Authentication (Security Risk)

**Severity:** Critical  
**Files Affected:**
- `domains/inventory/stock_register.py`
- `domains/inventory/stock_audit.py`
- `domains/inventory/purchase_orders.py`
- `domains/inventory/indents.py`
- `domains/orders/estimates/viewsets.py`

**Current State (INSECURE):**
```python
@api_view(['GET', 'POST'])
@authentication_classes([])
@permission_classes([])
def stock(request):
    # No authentication!
```

**Required Fix:**
```python
from users.cookie_auth import CookieJWTAuthentication
from rest_framework.permissions import IsAuthenticated

@api_view(['GET', 'POST'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def stock(request):
    # Secure
```

**Implementation Steps:**
1. Add imports to each file
2. Replace empty authentication/permission classes
3. Verify all endpoints require authentication
4. Run tests to ensure no breaking changes

**Acceptance Criteria:**
- [ ] All 5 files have proper authentication decorators
- [ ] No anonymous access to any endpoint
- [ ] Tests pass (148/148)
- [ ] No breaking changes to existing functionality

---

### Issue 2: Hardcoded bg_code (Tenant Isolation Violation)

**Severity:** Critical  
**Files Affected:**
- `domains/inventory/stock_register.py`

**Current State (BROKEN):**
```python
# domains/inventory/stock_register.py:35
stock_coll, _ = get_collection('stock_register', bg_code='BG0001')

# domains/inventory/stock_register.py:52
stock_audit_coll, _ = get_collection('stock_audit', bg_code='BG0001')
```

**Required Fix:**
```python
from backend.auth_utils import resolve_access

def stock(request):
    # Resolve tenant context from request
    result = resolve_access(request)
    bg = result['bg']
    
    # Use dynamic bg_code
    stock_coll, _ = get_collection('stock_register', bg_code=bg.bg_code)
    stock_audit_coll, _ = get_collection('stock_audit', bg_code=bg.bg_code)
```

**Implementation Steps:**
1. Read `domains/inventory/stock_register.py` completely
2. Add `resolve_access` import
3. Replace hardcoded `bg_code='BG0001'` with dynamic resolution
4. Verify all collection accesses use tenant context
5. Run tests

**Acceptance Criteria:**
- [ ] No hardcoded `bg_code='BG0001'` in any file
- [ ] All collection accesses use `bg.bg_code` from resolved context
- [ ] Tenant isolation works correctly
- [ ] Tests pass (148/148)

---

## Phase 1: Architecture & Consistency (Phase 2)

**Duration:** 4-5 hours  
**Risk:** Medium (architecture compliance)  
**Dependencies:** Phase 0 complete

### Issue 3: Business Logic in Viewsets (Architecture Violation)

**Severity:** High  
**Files Affected:**
- `domains/accounts/sales/viewsets.py` (~300 lines of business logic)
- `domains/accounts/expenditure/debit_notes.py`
- `domains/accounts/expenditure/payments.py`
- `domains/accounts/expenditure/purchase_orders.py`
- `domains/accounts/tax/itc.py`
- `domains/accounts/financials/viewsets.py` (~100 lines)
- `domains/orders/estimates/viewsets.py` (~200 lines)
- `domains/inventory/stock_register.py`
- `domains/inventory/stock_audit.py`
- `domains/inventory/purchase_orders.py`
- `domains/inventory/indents.py`

**Current State (VIOLATION):**
```python
# domains/accounts/sales/viewsets.py:35-180
def outwardinvoices(request):
    """API endpoint for outward invoices."""
    # 150+ lines of business logic:
    # - PDF generation
    # - Data transformation
    # - Database queries
    # - Permission checks
    # - Error handling
```

**Required Fix:**
Extract business logic into service functions:

```python
# viewsets.py - Only handle HTTP
def outwardinvoices(request):
    """API endpoint for outward invoices."""
    result = resolve_access(request)
    if not check_permission(result['permissions'], 'accounts.sales.view'):
        return Response({"error": "Unauthorized"}, status=401)
    
    # Parse request params
    filters = {}
    limit = request.query_params.get('limit')
    
    # Delegate to service
    data = get_outward_invoices(filters, limit, bg_code)
    return Response(data)

# services.py - Business logic
def get_outward_invoices(filters, limit, bg_code):
    """Query outward invoices with filters."""
    collection_obj, tenant_filter = get_collection('outward', bg_code=bg_code)
    if limit:
        return decode_result(collection_obj.find({**tenant_filter, **filters}).limit(limit))
    return decode_result(collection_obj.find({**tenant_filter, **filters}))
```

**Implementation Steps:**
1. Identify business logic in each viewset
2. Extract into service functions in corresponding `services.py`
3. Update viewsets to call services
4. Maintain backward compatibility
5. Run tests

**Acceptance Criteria:**
- [ ] Viewsets contain only HTTP handling logic (<50 lines)
- [ ] Business logic in service functions
- [ ] All tests pass (148/148)
- [ ] No breaking changes

---

### Issue 4: Naming Convention Violations

**Severity:** High  
**Files Affected:**
- `domains/accounts/sales/services.py`: `getOutwardInvoices`, `format_outwardinvoice`
- `domains/accounts/sales/credit_notes.py`: `getOutwardCreditNotes`, `format_creditnote`
- `domains/accounts/expenditure/debit_notes.py`: `getOutwardDebitNotes`
- `domains/accounts/expenditure/services.py`: `getpurchaseorders`

**Current State (INCONSISTENT):**
```python
# camelCase (PEP 8 violation)
def getOutwardInvoices(...)
def format_outwardinvoice(...)
def getOutwardCreditNotes(...)
def getOutwardDebitNotes(...)
```

**Required Fix (PEP 8):**
```python
# snake_case (PEP 8 compliant)
def get_outward_invoices(...)
def format_outward_invoice(...)
def get_outward_credit_notes(...)
def get_outward_debit_notes(...)
```

**Implementation Steps:**
1. Rename all camelCase functions to snake_case
2. Update all imports across domain modules
3. Update test references
4. Update any external references
5. Run tests

**Acceptance Criteria:**
- [ ] All functions use snake_case
- [ ] All imports updated
- [ ] All tests pass (148/148)
- [ ] No breaking changes to external API

---

## Phase 2: Cross-Cutting Concerns (Phase 3)

**Duration:** 1.5 hours  
**Risk:** Low (enhancement)  
**Dependencies:** Phase 1 complete

### Issue 5: Missing Event Emissions

**Severity:** Medium  
**Files Affected:**
- All domain modules (no current event emissions)

**Current State (MISSING):**
```python
# No event emissions anywhere
# Expected: from plat.events.bus import emit
# Usage: emit("invoice.created", payload, bg_code=bg.bg_code)
```

**Required Fix:**
Add event emissions for key domain operations:

```python
# domains/accounts/sales/services.py
from plat.events.bus import emit

def create_outward_invoice(data, bg_code):
    """Create outward invoice and emit event."""
    # ... create invoice logic ...
    emit("invoice.created", {
        'invoice_no': data['invoice_no'],
        'div_code': data['div_code'],
        'totalprice': data['totalprice']
    }, bg_code=bg_code)
```

**Key Events to Emit:**
- `invoice.created` — Outward invoice creation
- `invoice.updated` — Outward invoice update
- `credit_note.created` — Credit note creation
- `payment.processed` — Payment voucher creation
- `purchase_order.created` — Purchase order creation
- `stock.updated` — Stock movement
- `indent.created` — Indent request

**Implementation Steps:**
1. Identify key operations that should emit events
2. Add `from plat.events.bus import emit` to relevant files
3. Add `emit()` calls after successful operations
4. Document event payloads
5. Run tests

**Acceptance Criteria:**
- [ ] All key operations emit events
- [ ] Event payloads documented
- [ ] Tests pass (148/148)
- [ ] No performance degradation

---

### Issue 6: Code Duplication

**Severity:** Medium  
**Files Affected:**
- `domains/accounts/financials/services.py`
- `domains/accounts/financials/reports.py`

**Current State (DUPLICATE):**
```python
# Both files contain identical functions
# domains/accounts/financials/services.py:35-95
def payment_financials():
    # ... identical implementation ...

# domains/accounts/financials/reports.py:35-95
def payment_financials():
    # ... identical implementation ...
```

**Required Fix:**
Remove duplicates and import from services:

```python
# domains/accounts/financials/reports.py
from domains.accounts.financials.services import payment_financials, past_present_fin_totals

# Now reports.py can just re-export or use the service functions
```

**Implementation Steps:**
1. Identify all duplicate functions
2. Keep one canonical implementation (prefer services.py)
3. Import from services in reports.py
4. Run tests

**Acceptance Criteria:**
- [ ] No duplicate function definitions
- [ ] Single source of truth for each function
- [ ] Tests pass (148/148)

---

## Phase 3: Test Coverage (Ongoing)

**Duration:** 2 hours  
**Risk:** Low (enhancement)  
**Dependencies:** None

### Issue 7: Missing Tests

**Severity:** Medium  
**Files Affected:**
- `domains/accounts/expenditure/services.py`
- `domains/accounts/tax/services.py`
- `domains/accounts/financials/services.py`
- `domains/inventory/stock_register.py`
- `domains/inventory/stock_audit.py`
- `domains/inventory/purchase_orders.py`
- `domains/inventory/indents.py`

**Current State (GAPS):**
```python
# Missing tests for:
# - getpurchaseorders (expenditure/services.py)
# - format_inwarddebitnote (expenditure/services.py)
# - itc_calculate (tax/services.py)
# - gst_return (tax/services.py)
# - financial_totals (financials/services.py)
# - stock endpoint (inventory/stock_register.py)
# - stockaudit endpoint (inventory/stock_audit.py)
# - getpurchaseorders endpoint (inventory/purchase_orders.py)
# - creating_indent endpoint (inventory/indents.py)
```

**Required Fix:**
Add tests for all public functions and endpoints:

```python
# tests/test_inventory_stock.py
class TestStockRegister:
    def test_stock_endpoint_authentication(self):
        """Test stock endpoint requires authentication"""
        
    def test_stock_query_with_filters(self):
        """Test stock query with various filters"""
        
    def test_stock_movement_creation(self):
        """Test stock movement creation"""
```

**Implementation Steps:**
1. Identify all untested public functions
2. Write tests for each function
3. Test happy path and error cases
4. Run full test suite
5. Verify 100% coverage

**Acceptance Criteria:**
- [ ] All public functions have tests
- [ ] All endpoints have tests
- [ ] 148+ tests passing
- [ ] Test coverage >80%

---

## Implementation Order

### Recommended Execution Sequence

1. **Phase 0: Immediate Fixes** (1.5 hrs)
   - Fix missing authentication (security)
   - Fix hardcoded bg_code (tenant isolation)
   - **Verify:** 148/148 tests pass

2. **Phase 1: Architecture & Consistency** (4-5 hrs)
   - Extract business logic from viewsets
   - Rename camelCase functions
   - **Verify:** 148/148 tests pass

3. **Phase 2: Cross-Cutting Concerns** (1.5 hrs)
   - Add event emissions
   - Fix code duplication
   - **Verify:** 148/148 tests pass

4. **Phase 3: Test Coverage** (2 hrs, ongoing)
   - Add missing tests
   - **Verify:** 155+ tests passing

---

## Validation

### Pre-Flight Checks

```bash
cd /home/chief/Coding-Projects/kteam-dj-chief

# Verify current test count
python3 manage.py test tests/ -v 1 --no-input

# Check for hardcoded bg_code
grep -r "bg_code='BG0001'" domains/

# Check for missing authentication
grep -r "@authentication_classes(\[\])" domains/

# Check for camelCase functions
grep -r "def [a-z]*[A-Z]" domains/ --include="*.py"
```

### Post-Flight Checks

```bash
# Run full test suite
python3 manage.py test tests/ -v 2 --no-input

# Verify no hardcoded bg_code
grep -r "bg_code='BG0001'" domains/ && echo "FAIL" || echo "PASS"

# Verify no empty authentication
grep -r "@authentication_classes(\[\])" domains/ && echo "FAIL" || echo "PASS"

# Verify snake_case naming
grep -r "def [a-z]*[A-Z]" domains/ --include="*.py" && echo "FAIL" || echo "PASS"
```

---

## Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Authentication | 100% secured | 60% (5 files missing) |
| Tenant isolation | 100% dynamic | 90% (1 file hardcoded) |
| Viewset complexity | <50 lines | 100-300 lines |
| Naming consistency | 100% snake_case | 70% camelCase |
| Event emissions | 7 key events | 0 events |
| Code duplication | 0 duplicates | 2 functions |
| Test coverage | >80% | ~60% |

---

## Rollback Plan

If any phase fails:

1. **Git revert:** `git revert HEAD`
2. **Restore from backup:** Commit before fixes is `02f4de6`
3. **Verify:** `python3 manage.py test tests/ -v 1 --no-input`

---

## Documentation Updates

After completion, update:
- `architecture/domain_architecture.md` — Reflect new event model
- `handoffs/2026-06-27_domain_migration_phase_plan.md` — Mark fixes complete
- `architecture/platform_primitives.md` — Document event usage

---

**Next Step:** Begin Phase 0 (Immediate Fixes) with chair gate validation.

