---
tags: [anti-pattern, security, credentials]
created: 2026-04-20
updated: 2026-04-20
status: active
---

# No Inline API Keys

## What

Never hardcode credentials, API keys, or secrets directly in source code.

## Why

- Exposed in version control (even private repos)
- Hard to rotate without code changes
- Risk of accidental commit to public repos
- Violates principle of least privilege

## Correct Approach

- Use environment variables (.env files)
- Use Django settings for backend config
- Use Vite env vars for frontend (REACT_APP_* prefix)
- Never commit .env files to version control

## Examples

**Bad:**
```python
API_KEY = "sk-1234567890abcdef"
```

**Good:**
```python
import os
API_KEY = os.environ.get("API_KEY")
```

**Bad (frontend):**
```javascript
const API_KEY = "abc123";
```

**Good (frontend):**
```javascript
const API_KEY = import.meta.env.VITE_API_KEY;
```
