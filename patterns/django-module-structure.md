---
tags: [django, backend, module-structure, kuro-cadence]
created: 2026-04-20
updated: 2026-04-20
sources: [kteam-dj-be/]
related: [[kteam-dj-be]], [[knox-auth]]
status: stable
---

# Django Module Structure

## Summary

Django module organization pattern used in kteam-dj-be (Kuro Gaming backend API).

## Module Layout

```
kteam-dj-be/
├── users/          # User management, auth, profiles
├── careers/        # Job listings, applications
├── kurostaff/      # Staff portal endpoints
├── kuroadmin/      # Admin panel customizations
├── kc_backend/     # Project settings, URL routing
└── manage.py
```

## Key Patterns

- Each module is a Django app with its own models, views, serializers, urls
- REST endpoints organized by module (e.g., /api/users/, /api/careers/)
- Knox auth middleware applied at the API level
- Django REST Framework for all API endpoints
- Separate management commands for maintenance tasks
- Django crontab for scheduled jobs (DB backups at 22:30)

## API Conventions

- Versioned endpoints under `/api/v1/`
- Token-based auth via Knox
- Pagination enabled for list endpoints
- Consistent error response format
