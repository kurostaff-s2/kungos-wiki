# Data Propagation & Frontend Hydration Testing

| Field | Value |
|-------|-------|
| Project ID | kung-os |
| Primary entity ID | d075f8 |
| Entity type | work_item |
| Short description | End-to-end testing of data propagation from MongoDB → Backend FilterParserMixin → Frontend hydration across all migrated ViewSets |
| Status | draft |
| Source references | `29-06-2026_filter-parser-mixin-and-frontend-migration_7bd873.md`, `endpoint_contract_spec_revised.md` §9.2 |
| Generated | 29-06-2026 |
| Next action / owner | Testing agent — execute Phases 1-4 |

---

## Context

The FilterParserMixin migration is complete. 32 backend view files now use `apply_filter_params(request)` for business filters. 23 frontend files send `?filter[field]=value` format. This task verifies:

1. **Data propagation:** MongoDB → Backend → Frontend flow works correctly
2. **Filter parsing:** `FilterParserMixin` correctly parses all operator types
3. **Frontend hydration:** Data renders accurately on the frontend
4. **Edge cases:** Empty data, errors, pagination, filtering combinations

---

## Project Context

**Backend project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Frontend project root:** `/home/chief/Coding-Projects/kteam-fe-chief`
**Reference docs:**
- `/home/chief/llm-wiki/00-prompt-handoff/29-06-2026_filter-parser-mixin-and-frontend-migration_7bd873.md`
- `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec_revised.md`
- `/home/chief/llm-wiki/Kung_OS/specs/frontend_alignment_handoff.md`

**Key backend files:**
- `plat/django/filters.py` — FilterParserMixin implementation
- `plat/tests/test_filter_parser.py` — Existing unit tests (20 tests)
- `domains/accounts/viewsets.py` — Example DRF ViewSet with mixin
- `domains/inventory/views.py` — Example function-based view with mixin

**Key frontend files:**
- `src/hooks/useTenantQuery.jsx` — Centralized query hook
- `src/pages/Accounts/Analytics.jsx` — Already uses canonical format
- `src/pages/Inventory/Stock.jsx` — Migrated to filter format

---

## Execution Order

```
Phase 1 (Backend Unit Tests)
    ↓
Phase 2 (Backend Integration Tests)
    ↓
Phase 3 (Frontend Component Tests)
    ↓
Phase 4 (End-to-End Smoke Tests)
```

**Parallelism:** Phases 1-2 can run sequentially (Phase 2 depends on Phase 1). Phases 3-4 must run after 1-2 complete.

---

## Phase 1: Backend Unit Tests — FilterParserMixin

**What:** Extend existing 20 tests to cover all operator types and edge cases.

**Files:**
- `plat/tests/test_filter_parser.py` — Modify (add tests)

**Steps:**

1. Run existing tests to establish baseline:
   ```bash
   cd /home/chief/Coding-Projects/kteam-dj-chief
   python3 -m pytest plat/tests/test_filter_parser.py -v
   ```

2. Add tests for each operator type:

   | Test | Query Params | Expected Output |
   |------|-------------|-----------------|
   | Exact match | `?filter=status=active` | `{'status': 'active'}` |
   | Greater than | `?filter[age__gt]=18` | `{'age': {'$gt': 18}}` |
   | Less than | `?filter[age__lt]=65` | `{'age': {'$lt': 65}}` |
   | Greater than or equal | `?filter[price__gte]=100` | `{'price': {'$gte': 100}}` |
   | Less than or equal | `?filter[price__lte]=1000` | `{'price': {'$lte': 1000}}` |
   | In list | `?filter[status__in]=active,pending` | `{'status': {'$in': ['active', 'pending']}}` |
   | Contains | `?filter[name__contains]=john` | `{'name': {'$regex': 'john', '$options': 'i'}}` |
   | Startswith | `?filter[code__startswith]=INV-` | `{'code': {'$regex': '^INV-', '$options': 'i'}}` |
   | Endswith | `?filter[email__endswith]=@example.com` | `{'email': {'$regex': '@example\.com$', '$options': 'i'}}` |
   | Regex | `?filter[code__regex]=^INV-\d{4}$` | `{'code': {'$regex': '^INV-\\d{4}$'}}` |
   | Is null | `?filter[deleted_at__isnull]=true` | `{'deleted_at': None}` |
   | Case-insensitive exact | `?filter[name__iexact]=john` | `{'name': {'$regex': '^john$', '$options': 'i'}}` |
   | Multiple operators same field | `?filter[age__gt]=18&filter[age__lt]=65` | `{'age': {'$gt': 18, '$lt': 65}}` |
   | Type coercion (int) | `?filter[limit]=10` | `{'limit': 10}` (int, not str) |
   | Type coercion (bool) | `?filter[active]=true` | `{'active': True}` (bool, not str) |
   | Empty filter | `?filter[]=` | `{}` (empty dict) |
   | Invalid operator | `?filter[name__invalid]=test` | Skip field, log warning |
   | Tenant fields excluded | `?filter[div_code]=DIV001` | NOT in output (tenant scoping) |
   | Search param excluded | `?search=test` | NOT in output (handled separately) |
   | Sort param excluded | `?sort=-name` | NOT in output (handled separately) |

3. Add tests for MongoDB vs ORM mode:
   - Test with `db_type='mongo'` — should use MongoDB operators (`$gt`, `$regex`, etc.)
   - Test with `db_type='orm'` — should use ORM lookups (`gt`, `icontains`, etc.)

4. Run tests and verify all pass:
   ```bash
   python3 -m pytest plat/tests/test_filter_parser.py -v
   ```

**Tests:**
- [ ] All 20 existing tests still pass
- [ ] All 21 new tests pass
- [ ] Total: 41 tests passing

**Dependencies:** None

---

## Phase 2: Backend Integration Tests — ViewSet Endpoints

**What:** Test that ViewSets correctly use the FilterParserMixin and return expected data.

**Files:**
- `plat/tests/test_viewset_integration.py` — Create (new test file)

**Steps:**

1. Create test file with mock MongoDB collection:

   ```python
   from django.test import TestCase, RequestFactory
   from django.http import QueryDict
   from domains.accounts.viewsets import InwardInvoiceViewSet
   from plat.django.filters import FilterParserMixin

   class InwardInvoiceViewSetTest(TestCase):
       def setUp(self):
           self.factory = RequestFactory()
           self.viewset = InwardInvoiceViewSet()
           self.filter_parser = FilterParserMixin()

       def test_apply_filter_params_basic(self):
           # Create mock request with filter params
           query_dict = QueryDict('filter=status&filter=active')
           request = self.factory.get('/?filter=status&filter=active', query_dict)
           
           # Apply filter params
           filters = self.viewset.apply_filter_params(request)
           
           # Assert correct parsing
           self.assertEqual(filters, {'status': 'active'})

       def test_apply_filter_params_operators(self):
           query_dict = QueryDict('filter[price__gte]=100&filter[price__lte]=1000')
           request = self.factory.get('/?filter[price__gte]=100', query_dict)
           
           filters = self.viewset.apply_filter_params(request)
           
           self.assertEqual(filters, {'price': {'$gte': 100, '$lte': 1000}})

       def test_tenant_fields_excluded(self):
           query_dict = QueryDict('filter[div_code]=DIV001&filter[status]=active')
           request = self.factory.get('/?filter[div_code]=DIV001', query_dict)
           
           filters = self.viewset.apply_filter_params(request)
           
           # div_code should NOT be in filters (tenant scoping)
           self.assertNotIn('div_code', filters)
           self.assertIn('status', filters)
   ```

2. Add tests for each operator type (reuse Phase 1 patterns):
   - Test `__gt`, `__lt`, `__gte`, `__lte`, `__in`, `__contains`, `__startswith`, `__endswith`, `__regex`, `__iexact`, `__isnull`

3. Add tests for edge cases:
   - Empty filter params
   - Invalid operator
   - Multiple operators on same field
   - Type coercion

4. Run tests:
   ```bash
   python3 -m pytest plat/tests/test_viewset_integration.py -v
   ```

**Tests:**
- [ ] All 10 integration tests pass
- [ ] ViewSet correctly applies filters to MongoDB queries
- [ ] Tenant fields are excluded from business filters
- [ ] Edge cases handled gracefully

**Dependencies:** Phase 1 (FilterParserMixin unit tests must pass)

---

## Phase 3: Frontend Component Tests

**What:** Test that frontend components correctly send filter params and hydrate data.

**Files:**
- `src/components/__tests__/FilterParams.test.jsx` — Create (new test file)
- `src/hooks/__tests__/useTenantQuery.test.jsx` — Modify (add tests)

**Steps:**

1. Create test for FilterParams component:

   ```jsx
   import { renderHook, waitFor } from '@testing-library/react';
   import { useTenantQuery } from '../../hooks/useTenantQuery';
   
   describe('useTenantQuery', () => {
     it('sends filter[div_code] instead of division', async () => {
       const { result } = renderHook(() => 
         useTenantQuery({
           endpoint: '/api/v1/accounts/inward-invoices',
           params: { div_code: 'DIV001' }
         })
       );
       
       await waitFor(() => expect(result.current.data).toBeDefined());
       
       // Verify the request was made with correct params
       expect(global.fetch).toHaveBeenCalledWith(
         expect.stringContaining('?filter[div_code]=DIV001'),
         expect.any(Object)
       );
     });

     it('sends filter[status] for status filter', async () => {
       const { result } = renderHook(() => 
         useTenantQuery({
           endpoint: '/api/v1/accounts/inward-invoices',
           params: { status: 'active' }
         })
       );
       
       await waitFor(() => expect(result.current.data).toBeDefined());
       
       expect(global.fetch).toHaveBeenCalledWith(
         expect.stringContaining('?filter[status]=active'),
         expect.any(Object)
       );
     });

     it('handles multiple filter params', async () => {
       const { result } = renderHook(() => 
         useTenantQuery({
           endpoint: '/api/v1/accounts/inward-invoices',
           params: { 
             div_code: 'DIV001',
             status: 'active',
             branch_code: 'BR001'
           }
         })
       );
       
       await waitFor(() => expect(result.current.data).toBeDefined());
       
       expect(global.fetch).toHaveBeenCalledWith(
         expect.stringContaining('?filter[div_code]=DIV001&filter[status]=active&filter[branch_code]=BR001'),
         expect.any(Object)
       );
     });
   });
   ```

2. Add tests for edge cases:
   - Empty params
   - Invalid params (should not send)
   - Pagination params (limit, offset, page)
   - Search and sort params (should not be in filter[])

3. Run tests:
   ```bash
   cd /home/chief/Coding-Projects/kteam-fe-chief
   npm run test -- --testPathPattern=FilterParams
   ```

**Tests:**
- [ ] All 8 frontend tests pass
- [ ] Components send `?filter[field]=value` format
- [ ] Legacy `division=`/`branch=` params NOT sent
- [ ] Data hydrates correctly from API response

**Dependencies:** Phase 2 (Backend must return correct data format)

---

## Phase 4: End-to-End Smoke Tests

**What:** Manual smoke tests to verify full data flow: MongoDB → Backend → Frontend.

**Files:**
- `tests/smoke_tests.md` — Create (test plan document)

**Steps:**

1. **Setup test data in MongoDB:**
   ```bash
   # Connect to MongoDB
   mongo kuroadmin
   
   # Insert test inward invoices
   db.inwardinvoices.insertMany([
     {
       invoice_no: "INV-TEST-001",
       invoice_date: new Date(),
       vendor: ObjectId("..."),
       total_amount: 1000,
       status: "active",
       div_code: "DIV001",
       branch_code: "BR001",
       delete_flag: false
     },
     {
       invoice_no: "INV-TEST-002",
       invoice_date: new Date(),
       vendor: ObjectId("..."),
       total_amount: 2000,
       status: "pending",
       div_code: "DIV001",
       branch_code: "BR002",
       delete_flag: false
     }
   ])
   ```

2. **Test Backend API directly:**
   ```bash
   # Test with filter[status]
   curl -X GET "http://localhost:8000/api/v1/accounts/inward-invoices?filter[status]=active" \
     -H "Authorization: Bearer <token>"
   
   # Expected: Returns only active invoices
   # Verify: response.data contains INV-TEST-001, not INV-TEST-002

   # Test with filter[div_code]
   curl -X GET "http://localhost:8000/api/v1/accounts/inward-invoices?filter[div_code]=DIV001" \
     -H "Authorization: Bearer <token>"
   
   # Expected: Returns invoices for DIV001
   # Verify: response.data contains both test invoices

   # Test with multiple filters
   curl -X GET "http://localhost:8000/api/v1/accounts/inward-invoices?filter[status]=active&filter[div_code]=DIV001" \
     -H "Authorization: Bearer <token>"
   
   # Expected: Returns active invoices for DIV001
   # Verify: response.data contains only INV-TEST-001
   ```

3. **Test Frontend UI:**
   - Navigate to Accounts → Inward Invoices
   - Apply filter: Status = Active
   - Verify: Only active invoices displayed
   - Apply filter: Division = DIV001
   - Verify: Only DIV001 invoices displayed
   - Apply multiple filters
   - Verify: Intersection of all filters applied

4. **Test edge cases:**
   - Empty result set (no matching invoices)
   - Invalid filter value (should show empty or error)
   - Pagination (limit, offset, page)
   - Search and sort (should work alongside filters)

5. **Document results in `tests/smoke_tests.md`:**

   | Test Case | Expected | Actual | Status |
   |-----------|----------|--------|--------|
   | filter[status]=active | Only active invoices | ... | ✅/❌ |
   | filter[div_code]=DIV001 | Only DIV001 invoices | ... | ✅/❌ |
   | Multiple filters | Intersection | ... | ✅/❌ |
   | Empty result | Empty list | ... | ✅/❌ |
   | Pagination | Correct page | ... | ✅/❌ |

**Tests:**
- [ ] All 5 smoke tests pass
- [ ] Backend returns correct filtered data
- [ ] Frontend displays correct data
- [ ] Edge cases handled gracefully

**Dependencies:** Phase 3 (Frontend tests must pass)

---

## Success Criteria

- [ ] Phase 1: 41/41 backend unit tests pass
- [ ] Phase 2: 10/10 backend integration tests pass
- [ ] Phase 3: 8/8 frontend component tests pass
- [ ] Phase 4: 5/5 end-to-end smoke tests pass
- [ ] No regression in existing tests
- [ ] All commits pushed to `origin/develop`

---

## Constraints

- **Do NOT modify** `src/pages/Accounts/Analytics.jsx`, `src/pages/Home.jsx`, or `src/hooks/useTenantParams.jsx`
- **FilterParserMixin must NOT parse tenant fields** (`div_code`, `branch_code`, `bg_code`) — only business filters
- **No legacy alias support** in the mixin — `division=` is ignored, not mapped
- **All `query_params.get('division')` → `query_params.get('div_code')`** and `query_params.get('branch')` → `query_params.get('branch_code')`
- **Variable renaming:** `query_division` → `query_div_code`, `division_param` → `div_code_param`, `division_filter` → `div_code_filter`
- **All tests must run against the migrated codebase** (commit `41b3756` or later)

---

## Caveats & Uncertainty

1. **MongoDB test data:** Test data must be inserted into the correct database (`kuroadmin` or tenant DB). Verify DB name before inserting.

2. **Authentication:** Backend tests require valid JWT tokens. Use test user credentials or mock authentication.

3. **Frontend dev server:** Must be running on `http://localhost:5173` for smoke tests. Start with `npm run dev`.

4. **Backend dev server:** Must be running on `http://localhost:8000` for smoke tests. Start with `python3 manage.py runserver`.

5. **Test isolation:** Use unique test data (e.g., `INV-TEST-*`) to avoid conflicts with existing data.

6. **FilterParserMixin limitations:** Commas in `__in` values must be URL-encoded by client. Document this limitation.

---

## Next Steps

1. Execute Phase 1 (Backend Unit Tests)
2. Execute Phase 2 (Backend Integration Tests)
3. Execute Phase 3 (Frontend Component Tests)
4. Execute Phase 4 (End-to-End Smoke Tests)
5. Commit all test files to `origin/develop`
6. Update this handoff with results
