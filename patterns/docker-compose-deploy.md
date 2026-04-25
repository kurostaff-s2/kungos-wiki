---
tags: [docker, deployment, infrastructure]
created: 2026-04-20
updated: 2026-04-20
sources: [~/llm-wiki/]
related: [[local-ai-stack]]
status: stable
---

# Docker Compose Deploy

## Summary

Docker Compose deployment patterns used for local and production infrastructure.

## Common Patterns

- **Multi-service**: Docker Compose for orchestrating multiple services (DB, Redis, app, etc.)
- **Environment variables**: .env files for configuration, never hardcoded
- **Volumes**: Named volumes for persistent data (databases, caches)
- **Healthchecks**: Service health checks for dependency readiness
- **Networking**: Custom bridge networks for inter-service communication

## Typical Service Stack

- PostgreSQL — relational database
- MongoDB — document database (daily backups at 22:30)
- Redis — caching/session store
- MinIO — object storage (for RAGFlow)
- Elasticsearch — search engine (for RAGFlow)
- Meilisearch — search engine (for kteam-dj-be)

## Anti-Patterns

- No secrets in docker-compose.yml — use .env files
- No host network mode — use custom bridge networks
- No data on overlay filesystems — always use named volumes
