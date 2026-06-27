# Phase 3A: Standard Response Envelope

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 3A of 5 (parallel with 3B, 3C)
**Dependencies:** None (can run in parallel with Phase 2)
**Estimated effort:** ~20 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p3a` |
| Entity type | `handoff` |
| Short description | Create middleware for standard response envelope: `{status, data, meta}` wrapping all API responses. |
| Status | `draft` |
| Source references | `endpoint_contract_spec.md` §3.1 |
| Generated | `26-06-2026` |
| Next action / owner | Execute response envelope middleware — create middleware, add to settings, verify |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `backend/middleware/response_envelope.py` (new file)
- `backend/settings.py` (add middleware)
- `tests/test_response_envelope.py` (new tests)
**Related codebases:** None

## What This Phase Delivers

All JSON API responses wrapped in standard envelope: `{status: "success", data: ..., meta: {request_id, timestamp}}`. Non-JSON responses (files, redirects) excluded. `request_id` is unique UUID. `timestamp` is ISO 8601.

## Implementation Steps

### Step 1: Create Middleware

Create `backend/middleware/response_envelope.py`:

```python
import uuid
from datetime import datetime, timezone
from django.utils.deprecation import MiddlewareMixin
import json

class ResponseEnvelopeMiddleware(MiddlewareMixin):
    """Wrap all JSON API responses in standard envelope."""
    
    def process_response(self, request, response):
        # Skip non-JSON responses
        content_type = response.get('Content-Type', '')
        if 'application/json' not in content_type:
            return response
        
        # Skip non-2xx responses (errors handled separately)
        if response.status_code < 200 or response.status_code >= 300:
            return response
        
        # Skip empty responses
        if not response.content:
            return response
        
        try:
            data = json.loads(response.content)
        except (json.JSONDecodeError, ValueError):
            return response
        
        # Ensure meta is present (add if missing, even if already wrapped)
        if not isinstance(data, dict):
            return response
        
        # If response already has meta, leave as-is
        if 'meta' in data:
            return response
        
        # Add meta to already-wrapped responses (Phase 2B, etc.)
        if 'status' in data and 'data' in data:
            data['meta'] = {
                'request_id': str(uuid.uuid4()),
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            response.content = json.dumps(data)
            return response
        
        # Wrap in envelope
        envelope = {
            'status': 'success',
            'data': data,
            'meta': {
                'request_id': str(uuid.uuid4()),
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
        }
        
        response.content = json.dumps(envelope)
        response['Content-Length'] = str(len(response.content))
        return response
```

### Step 2: Add to Settings

Add to `backend/settings.py`:

```python
MIDDLEWARE = [
    # ... existing middleware
    'backend.middleware.response_envelope.ResponseEnvelopeMiddleware',
]
```

### Step 3: Exclude Third-Party Endpoints

Add exclusion list for third-party endpoints that shouldn't be wrapped:

```python
# In settings.py
RESPONSE_ENVELOPE_EXCLUDE_PATHS = [
    '/api/v1/health/',
    '/api/v1/ping/',
    '/api/v1/schema/',
]
```

Update middleware to check exclusion list:

```python
from django.conf import settings

class ResponseEnvelopeMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # Check exclusion list
        exclude_paths = getattr(settings, 'RESPONSE_ENVELOPE_EXCLUDE_PATHS', [])
        if any(request.path.startswith(path) for path in exclude_paths):
            return response
        
        # ... rest of middleware
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `backend/middleware/response_envelope.py` | Response envelope middleware |
| Create | `backend/middleware/__init__.py` | Package init |
| Modify | `backend/settings.py` | Add middleware + exclusion list |
| Create | `tests/test_response_envelope.py` | Verify envelope wrapping |

## Phase-Specific Tests

Create `tests/test_response_envelope.py`:

1. **Test JSON response wrapped:**
   ```python
   def test_json_response_wrapped():
       response = client.get('/api/v1/users/me/')
       assert 'status' in response.data
       assert response.data['status'] == 'success'
       assert 'data' in response.data
       assert 'meta' in response.data
   ```

2. **Test request_id present:**
   ```python
   def test_request_id_present():
       response = client.get('/api/v1/users/me/')
       assert 'request_id' in response.data['meta']
   ```

3. **Test timestamp ISO 8601:**
   ```python
   def test_timestamp_iso8601():
       response = client.get('/api/v1/users/me/')
       from datetime import datetime
       datetime.fromisoformat(response.data['meta']['timestamp'])
   ```

4. **Test non-JSON response not wrapped:**
   ```python
   def test_non_json_not_wrapped():
       response = client.get('/api/v1/docs/swagger/')
       assert 'status' not in response.content.decode()
   ```

5. **Test excluded paths not wrapped:**
   ```python
   def test_excluded_paths_not_wrapped():
       response = client.get('/api/v1/health/')
       # Health check should not be wrapped
   ```

## Completion Gate

- [ ] Middleware created and active
- [ ] All JSON responses wrapped in envelope
- [ ] `request_id` present and unique
- [ ] `timestamp` ISO 8601 format
- [ ] Non-JSON responses excluded
- [ ] Excluded paths not wrapped
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed

## Consistency Rules

**This phase defers to:**
- Wire shapes: `endpoint_contract_spec.md`
- Migration ordering: `migration_spec.md`
- Canonical naming: `CANONICAL_NAMING.md`

**This phase does NOT redefine:**
- Response shapes beyond what the spec allows
- Migration steps beyond what the spec defines
- Wire field names (use canonical names)

## Spec Contradictions

_None documented._

