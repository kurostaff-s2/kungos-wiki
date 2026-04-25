---
tags: [django, authentication, backend, kuro-cadence]
created: 2026-04-20
updated: 2026-04-20
sources: [kteam-dj-be/, kteam-fe-react/]
related: [[kteam-dj-be]], [[kteam-fe-react]], [[django-middleware]]
status: stable
---

# Knox Auth

## Summary

Authentication system used in kteam-dj-be (Django backend). Knox provides token-based authentication for the REST API endpoints consumed by kteam-fe-react and other clients.

## Key Details

- **Implementation:** Django Knox (token-based auth)
- **Used by:** kteam-dj-be backend, kteam-fe-react frontend
- **Staff auth endpoint:** POST /auth/staff
- **Token management:** Handled via Django Knox tokens

## Integration

The frontend (kteam-fe-react) sends Knox tokens with API requests to authenticate against the Django backend. Token lifecycle (issue, refresh, revoke) follows standard Knox patterns.

## References

- [[kteam-dj-be]] — Backend where Knox is configured
- [[kteam-fe-react]] — Frontend that consumes Knox-authenticated API
