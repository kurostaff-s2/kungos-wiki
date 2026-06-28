# Admin Test User Credentials

Created: 2026-06-27

## Admin User
- **userid**: `admin`
- **phone**: `2222222222`
- **password**: `admin`
- **identity_id**: `ID000001`
- **role**: `super_admin` (global scope, all BGs)
- **permissions**: All 74 permissions at level 3

## Setup
The `super_admin` role was created via `python manage.py seed_rbac_roles --force`.

## Login
```bash
curl -X POST http://127.0.0.1:9000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'
```

## Notes
- Admin's JWT token has `bg_code: ""`, `div_codes: []`, `identity_id: null` (no UserTenantContext)
- `HasRbacAdminAccess` fallback query handles empty bg_code via `UserRole` table
