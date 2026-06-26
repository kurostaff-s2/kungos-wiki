# Phase 3B: Standard Error Handling

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 3B of 5 (parallel with 3A, 3C)
**Dependencies:** Phase 3A (needs envelope middleware)
**Estimated effort:** ~20 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p3b` |
| Entity type | `handoff` |
| Short description | Implement standard error codes (`VALIDATION_ERROR`, `PERMISSION_DENIED`, `TENANT_ISOLATION`) in `{status, error, meta}` envelope. |
| Status | `draft` |
| Source references | `endpoint_contract_spec.md` §8.1 |
| Generated | `26-06-2026` |
| Next action / owner | Execute error handling — define error codes, create exceptions, wire DRF handler |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `backend/exceptions.py` (new file)
- `backend/exception_handlers.py` (new file)
- `backend/settings.py` (REST_FRAMEWORK exception handler)
- `tests/test_error_handling.py` (new tests)
**Related codebases:** None

## What This Phase Delivers

All API errors wrapped in standard envelope: `{status: "error", error: {code, message, details}, meta: {request_id, timestamp}}`. Standard error codes defined: `VALIDATION_ERROR`, `PERMISSION_DENIED`, `TENANT_ISOLATION`, `NOT_FOUND`, `INTERNAL_ERROR`. DRF exception handler maps HTTP status codes to error codes.

## Implementation Steps

### Step 1: Define Error Codes

Create `backend/exceptions.py`:

```python
from enum import Enum
from rest_framework.exceptions import APIException
from rest_framework import status

class ErrorCode(Enum):
    VALIDATION_ERROR = 'VALIDATION_ERROR'
    PERMISSION_DENIED = 'PERMISSION_DENIED'
    TENANT_ISOLATION = 'TENANT_ISOLATION'
    NOT_FOUND = 'NOT_FOUND'
    INTERNAL_ERROR = 'INTERNAL_ERROR'
    AUTHENTICATION_REQUIRED = 'AUTHENTICATION_REQUIRED'
    RATE_LIMITED = 'RATE_LIMITED'
    CONFLICT = 'CONFLICT'

class StandardError(APIException):
    """Base class for standard errors."""
    default_code = 'INTERNAL_ERROR'
    default_detail = 'An internal error occurred'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    
    def __init__(self, code=None, detail=None, status_code=None):
        super().__init__(detail or self.default_detail, code or self.default_code)
        if status_code:
            self.status_code = status_code

class ValidationError(StandardError):
    default_code = 'VALIDATION_ERROR'
    default_detail = 'Validation failed'
    status_code = status.HTTP_400_BAD_REQUEST

class PermissionDeniedError(StandardError):
    default_code = 'PERMISSION_DENIED'
    default_detail = 'Permission denied'
    status_code = status.HTTP_403_FORBIDDEN

class TenantIsolationError(StandardError):
    default_code = 'TENANT_ISOLATION'
    default_detail = 'Tenant isolation violation'
    status_code = status.HTTP_403_FORBIDDEN

class NotFoundError(StandardError):
    default_code = 'NOT_FOUND'
    default_detail = 'Resource not found'
    status_code = status.HTTP_404_NOT_FOUND

class AuthenticationRequiredError(StandardError):
    default_code = 'AUTHENTICATION_REQUIRED'
    default_detail = 'Authentication required'
    status_code = status.HTTP_401_UNAUTHORIZED
```

### Step 2: Create Exception Handler

Create `backend/exception_handlers.py`:

```python
import uuid
from datetime import datetime, timezone
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.views import exception_handler
from backend.exceptions import StandardError, ErrorCode

def standard_exception_handler(exc, context):
    """DRF exception handler that returns standard error envelope."""
    # Let DRF handle the exception first
    response = exception_handler(exc, context)
    
    # Build standard error response
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    
    if response is not None:
        # DRF handled it — wrap in standard format
        error_code = getattr(exc, 'default_code', ErrorCode.INTERNAL_ERROR.value)
        error_detail = response.data if isinstance(response.data, dict) else {'message': str(response.data)}
        
        return response.__class__(
            {
                'status': 'error',
                'error': {
                    'code': error_code,
                    'message': str(exc),
                    'details': error_detail,
                },
                'meta': {
                    'request_id': request_id,
                    'timestamp': timestamp,
                }
            },
            status=response.status_code,
        )
    
    # DRF didn't handle it — wrap unexpected error
    return response.__class__(
        {
            'status': 'error',
            'error': {
                'code': ErrorCode.INTERNAL_ERROR.value,
                'message': 'An unexpected error occurred',
                'details': {},
            },
            'meta': {
                'request_id': request_id,
                'timestamp': timestamp,
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
```

### Step 3: Add to Settings

Update `backend/settings.py`:

```python
REST_FRAMEWORK = {
    # ... existing settings
    'EXCEPTION_HANDLER': 'backend.exception_handlers.standard_exception_handler',
}
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `backend/exceptions.py` | Standard error codes + exception classes |
| Create | `backend/exception_handlers.py` | DRF exception handler |
| Modify | `backend/settings.py` | Add exception handler |
| Create | `tests/test_error_handling.py` | Verify error handling |

## Phase-Specific Tests

Create `tests/test_error_handling.py`:

1. **Test validation error format:**
   ```python
   def test_validation_error_format():
       response = client.post('/api/v1/users/', data={})  # Invalid data
       assert response.data['status'] == 'error'
       assert response.data['error']['code'] == 'VALIDATION_ERROR'
   ```

2. **Test permission denied format:**
   ```python
   def test_permission_denied_format():
       response = client.get('/api/v1/admin/')  # No auth
       assert response.data['status'] == 'error'
       assert response.data['error']['code'] in ['PERMISSION_DENIED', 'AUTHENTICATION_REQUIRED']
   ```

3. **Test not found format:**
   ```python
   def test_not_found_format():
       response = client.get('/api/v1/users/nonexistent/')
       assert response.data['status'] == 'error'
       assert response.data['error']['code'] == 'NOT_FOUND'
   ```

4. **Test error envelope has meta:**
   ```python
   def test_error_has_meta():
       response = client.get('/api/v1/users/nonexistent/')
       assert 'request_id' in response.data['meta']
       assert 'timestamp' in response.data['meta']
   ```

## Completion Gate

- [ ] Standard error codes defined
- [ ] Exception handler active
- [ ] All errors wrapped in standard envelope
- [ ] Error codes match spec
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed
