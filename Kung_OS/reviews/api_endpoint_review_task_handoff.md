# KungOS DJ API Endpoint Review Task Handoff

**Date:** 2026-07-02  
**Reviewer:** Chief Architect  
**Status:** In Progress  
**Scope:** All API endpoints against migrated PostgreSQL data

---

## Executive Summary

**Objective:** Verify that all KungOS DJ API endpoints are correctly retrieving data from the migrated PostgreSQL database and returning the expected JSON schema.

**Current State:**
- ✅ Phase 0-10 data migrations completed
- ✅ 3,531 users with tenant context
- ✅ 412 serial records, 890 movements
- ✅ 8 banks, 2 partners, 1 loan
- ✅ All MongoDB collections migrated to PostgreSQL

**Review Approach:**
1. Systematic endpoint-by-endpoint verification
2. Schema validation against target spec
3. Data integrity checks
4. Business logic validation

---

## API Endpoint Inventory

### 1. Authentication (`/api/v1/auth/`)
- `POST /auth/login/` — Phone/password login
- `POST /auth/logout/` — Blacklist tokens
- `POST /auth/refresh/` — Rotate JWT
- `POST /auth/verify/` — Send OTP
- `POST /auth/pwdreset/` — Change password
- `GET /auth/health/` — Health check

### 2. Users (`/api/v1/users/`)
- `GET /users/me/` — Current user profile
- `GET /users/profile/` — Employee profile
- `POST /users/profile/` — Update profile
- `GET /users/employees/` — List employees
- `POST /users/emp_acc/` — Assign RBAC roles
- `GET /users/lookup?phone=...` — Lookup identity
- `POST /users/identity` — Create identity
- `PATCH /users/identity/{id}` — Update identity

### 3. Tenant (`/api/v1/tenant/`)
- `GET /tenant/current/` — Current tenant context
- `POST /tenant/switch/` — Switch tenant
- `GET /tenant/accessible/` — Accessible tenants

### 4. RBAC (`/api/v1/rbac/`)
- `GET /rbac/roles/` — List roles
- `GET /rbac/users/` — List user roles
- `POST /rbac/users/` — Assign role
- `GET /rbac/permissions/` — List permissions
- `POST /rbac/permissions/` — Assign permission

### 5. Finance (`/api/v1/accounts/`)
- `GET /accounts/invoices/` — List invoices
- `GET /accounts/payments/` — List payments
- `GET /accounts/financials/` — Financial statements
- `GET /accounts/tax/` — Tax records

### 6. Orders (`/api/v1/orders/`)
- `GET /orders/estimates/` — List estimates
- `GET /orders/tp/` — List TP orders
- `GET /orders/kg/` — List KG orders
- `GET /orders/service/` — List service requests

### 7. Products (`/api/v1/products/`)
- `GET /products/` — Product catalog
- `GET /products/assets/` — Assets
- `GET /products/custom-catalog/` — Custom catalog

### 8. Inventory (`/api/v1/inventory/`)
- `GET /inventory/stock/` — Stock levels
- `GET /inventory/audit/` — Audit trail
- `GET /inventory/assets/` — Asset register
- `GET /inventory/indents/` — Purchase orders
- `GET /inventory/serials/` — Serial records
- `GET /inventory/movements/` — Movement history

### 9. E-Commerce (`/api/v1/eshop/`)
- `GET /eshop/cart/` — Shopping cart
- `GET /eshop/wishlist/` — Wishlist
- `GET /eshop/addresses/` — Saved addresses

### 10. Vendors (`/api/v1/vendors/`)
- `GET /vendors/` — Vendor list
- `POST /vendors/` — Create vendor

### 11. Teams (`/api/v1/teams/`)
- `GET /teams/employees/` — Employee list
- `GET /teams/attendance/` — Attendance records
- `GET /teams/payroll/` — Payroll data

### 12. Cafe (`/api/v1/cafe/`)
- `GET /cafe/sessions/` — Arcade sessions
- `GET /cafe/stations/` — Station status
- `GET /cafe/wallet/` — Wallet balance

### 13. Cafe F&B (`/api/v1/cafe-fnb/`)
- `GET /cafe-fnb/menu/` — Menu items
- `GET /cafe-fnb/orders/` — F&B orders

### 14. Search (`/api/v1/search/`)
- `GET /search/query/` — MeiliSearch integration

### 15. Shared (`/api/v1/shared/`)
- `GET /shared/dashboard/` — Dashboard data
- `POST /shared/sms/` — Send SMS

### 16. Tournaments (`/api/v1/tournaments/`)
- `GET /tournaments/` — Tournament list
- `GET /tournaments/players/` — Player list
- `GET /tournaments/teams/` — Team list

### 17. Admin (`/api/v1/admin/`)
- `GET /admin/tenants/` — Tenant bootstrap
- `POST /admin/tenants/` — Create tenant

### 18. Careers (`/api/v1/careers/`)
- `GET /careers/applications/` — Job applications

---

## Review Methodology

### For Each Endpoint:
1. **Schema Validation:** Does the response match the target JSON schema?
2. **Data Integrity:** Are all fields populated correctly?
3. **Business Logic:** Does the endpoint enforce correct business rules?
4. **Edge Cases:** How does it handle missing data, errors, permissions?

### Verification Steps:
1. Start Django development server
2. Test each endpoint with sample data
3. Compare response against target schema
4. Document findings in review table
5. Flag issues for remediation

---

## Review Table Template

| Endpoint | Method | Status | Schema Match | Data Integrity | Business Logic | Notes |
|----------|--------|--------|--------------|----------------|----------------|-------|
| /auth/login/ | POST | ❌/✅ | ❌/✅ | ❌/✅ | ❌/✅ | ... |

---

## Expected JSON Schemas

### 1. Login Response (`POST /auth/login/`)
```json
{
  "status": "success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
      "identity_id": "ESH1234567890",
      "phone": "+911234567890",
      "name": "John Doe",
      "email": "john@example.com",
      "bg_code": "KURO0001",
      "div_codes": ["KURO0001_001"],
      "branch_codes": ["KURO0001_001_001"],
      "active_div_code": "KURO0001_001",
      "active_branch_code": "KURO0001_001_001",
      "scope": "full",
      "roles": ["branch_supervisor"],
      "permissions": {
        "invoices.view": 1,
        "invoices.create": 2
      },
      "is_admin": false
    }
  },
  "meta": {
    "request_id": "abc123",
    "timestamp": "2026-07-02T10:00:00Z"
  }
}
```

### 2. User Profile Response (`GET /users/me/`)
```json
{
  "status": "success",
  "data": {
    "identity_id": "ESH1234567890",
    "phone": "+911234567890",
    "name": "John Doe",
    "email": "john@example.com",
    "bg_code": "KURO0001",
    "active_div_code": "KURO0001_001",
    "active_branch_code": "KURO0001_001_001",
    "status": "active",
    "roles": ["branch_supervisor"],
    "permissions": {
      "invoices.view": 1
    },
    "is_admin": false,
    "employee_profile": {
      "userid": "KCTM001",
      "role": "staff",
      "department": "Sales",
      "joining_date": "2024-01-15"
    },
    "customer_profile": {
      "registered": true,
      "order_count": 5,
      "total_spent": 15000.00
    }
  },
  "meta": {
    "request_id": "abc123",
    "timestamp": "2026-07-02T10:00:00Z"
  }
}
```

### 3. Inventory Movement Response (`GET /inventory/movements/`)
```json
{
  "status": "success",
  "data": {
    "id": 1,
    "movement_code": "MOV001",
    "movement_type": "outward",
    "product_id": 123,
    "quantity": 5,
    "from_location": "WH001",
    "to_location": "STORE001",
    "movement_date": "2026-07-01",
    "status": "completed",
    "serial_records": [
      {
        "serial_number": "SN001",
        "purchase_date": "2024-07-11",
        "customer_id": 456
      }
    ],
    "conversion_id": null,
    "metadata": {}
  }
}
```

---

## Next Steps

1. **Start Django server:** `python manage.py runserver 0.0.0.0:8000`
2. **Test endpoints systematically** using the review table
3. **Document findings** with actual API responses
4. **Flag issues** for immediate remediation
5. **Update migration guide** with endpoint verification status

---

## Initial Findings (2026-07-02)

### 1. Authentication Endpoint (`POST /api/v1/auth/login/`)

**Status:** ❌ FAILING  
**Issue:** Phone number format mismatch between database and authentication logic

**Root Cause:**
- Database stores phone in national format: `9511220403`
- Django PhoneNumberField returns E.164 format: `+919511220403`
- Login viewset doesn't normalize phone before querying
- `USERNAME_FIELD = 'phone'` but `username` field is different (e.g., `sohamm_10`)

**Test Results:**
```bash
# Request with national format phone
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"9511220403","password":"9511220403"}'

# Response: {"status": "FAILURE", "msg": "Invalid Credentials"}
```

**Database Verification:**
```sql
SELECT userid, phone, user_status FROM users_customuser WHERE phone = '9511220403';
-- Returns: userid=5000111392, phone=9511220403, user_status=active
```

**Django Model Verification:**
```python
user = CustomUser.objects.get(userid='5000111392')
print(f'Phone: {user.phone}')  # +919511220403 (E.164)
print(user.check_password('9511220403'))  # False (password mismatch)
```

**Recommendation:**
1. Normalize phone in login viewset before querying
2. Verify password hashes are correct from migration
3. Consider using `userid` as alternative login field

### 2. User Data Migration

**Status:** ✅ COMPLETE  
**Records:** 3,531 users with `user_status = 'active'`

**Schema:**
- Table: `users_customuser`
- Fields: `userid` (PK), `username`, `email`, `name`, `phone`, `user_status`, `password`, etc.
- Phone format: National (stored), E.164 (read via PhoneNumberField)

### 3. Tenant Context

**Status:** ✅ COMPLETE  
**Records:** 3,531 UserTenantContext records

**Schema:**
- Table: `users_user_tenant_context`
- Fields: `userid`, `identity_id`, `bg_code`, `div_codes`, `branch_codes`, `scope`, `token_key`
- All users have: `bg_code='KURO0001'`, `scope='full'`

---

## Updated Review Table

| Endpoint | Method | Status | Schema Match | Data Integrity | Business Logic | Notes |
|----------|--------|--------|--------------|----------------|----------------|-------|
| /auth/login/ | POST | ❌ | - | ❌ | ❌ | Phone format mismatch, password verification failing |
| /users/me/ | GET | ❌ | - | - | - | Requires auth token (login not working) |
| /tenant/current/ | GET | ❌ | - | - | - | Requires auth token |
| /inventory/movements/ | GET | ❌ | - | - | - | Requires auth token |
| /users/employees/ | GET | ❌ | - | - | - | Requires auth token |

**Legend:** ❌ = Not tested (blocked by auth issue), ✅ = Tested and passing, - = N/A

---

## Files Referenced

- `/home/chief/Coding-Projects/KungOS-dj/backend/urls.py` — Root URL configuration
- `/home/chief/Coding-Projects/KungOS-dj/users/api/viewsets.py` — User/Auth viewsets
- `/home/chief/Coding-Projects/KungOS-dj/users/models.py` — User/Identity models
- `/home/chief/Coding-Projects/KungOS-dj/tenant/models.py` — Tenant models
- `/home/chief/Coding-Projects/KungOS-dj/domains/inventory/models.py` — Inventory models
- `/home/chief/Coding-Projects/KungOS-dj/domains/orders/models.py` — Orders models
- `/home/chief/Coding-Projects/KungOS-dj/users/management/commands/populate_tenant_context.py` — Tenant context population

---

## Contact

**Questions:** Chief Architect  
**Escalations:** Project Lead
