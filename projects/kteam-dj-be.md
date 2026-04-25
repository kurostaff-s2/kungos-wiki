---
tags: [django, backend, api, rest]
created: 2026-04-20
updated: 2026-04-20
sources: [kteam-dj-be/README.md, kteam-dj-be/src/]
related: [[knox-auth]], [[kteam-fe-react]], [[kteam-system-architecture]], [[postgres]], [[mongodb]], [[meilisearch]]
status: stable
---

# kteam-dj-be

## Summary

Django backend API server for the Kuro Gaming ecosystem. Serves both kteam-fe-react (staff portal) and other frontend clients. Uses PostgreSQL + MongoDB, Meilisearch for search, REST Framework with Knox auth.

## Tech Stack

- **Framework:** Django + Django REST Framework
- **Database:** PostgreSQL (relational), MongoDB (document)
- **Search:** Meilisearch
- **Authentication:** Knox auth
- **Task Scheduling:** Django crontab (DB backups daily at 19:30 SQL, 22:30 MongoDB)
- **Deployment:** Gunicorn + Nginx + SSL (Certbot)
- **API Port:** 8000

## Django Modules

- `users` — User management
- `careers` — Career/application handling
- `kurostaff` — Staff portal backend
- `kuroadmin` — Admin panel backend

## Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /auth/staff | Staff authentication |
| GET | /kuroadmin/home | Dashboard data |
| GET | /kuroadmin/employees | Employee list |
| GET | /kuroadmin/products | Product catalog |
| POST | /bgSwitch | Switch business group |
| GET | /bggroup | Business group info |
| GET | /kuro/user | User profile |
| GET | /products/kurodata | License/token data |

## Dev Server

```bash
./run_dev.sh start      # Start dev server
./run_dev.sh stop       # Stop dev server
./run_dev.sh restart    # Restart dev server
./run_dev.sh status     # Check status
```

Manual setup:
```bash
cd kteam-dj-be
python3 -m venv kc-backend-venv
source kc-backend-venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Production Deployment

Gunicorn + Nginx configuration with SSL via Certbot.
- Gunicorn socket at `/run/gunicorn.sock`
- Nginx proxies to `api.kurocadence.com`
- 5 workers configured

## References

- [[knox-auth]] — Authentication system
- [[kteam-fe-react]] — Frontend that consumes this API
- [[kteam-system-architecture]] — Full system architecture map
- [[postgres]] — PostgreSQL database
- [[mongodb]] — MongoDB document store
