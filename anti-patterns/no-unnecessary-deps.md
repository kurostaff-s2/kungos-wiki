---
tags: [anti-pattern, dependencies, maintenance]
created: 2026-04-20
updated: 2026-04-20
status: active
---

# No Unnecessary Dependencies

## What

Minimize npm/pip/package dependencies. Only add a dependency if it solves a real problem that can't be solved with stdlib or existing deps.

## Why

- Fewer attack surface (supply chain attacks)
- Smaller bundle sizes
- Fewer version conflicts
- Easier maintenance and upgrades
- Faster CI/CD builds

## Guidelines

- **Python**: Prefer stdlib first, then well-maintained single-purpose packages
- **JavaScript/Node**: Prefer Vite-native features, then minimal packages. Avoid heavy frameworks when not needed
- **Docker**: Use minimal base images, multi-stage builds
- **Review**: Question every dependency added to package.json or requirements.txt

## Examples

**Bad:**
- Adding lodash when you only need `Array.prototype.flat()` (native since ES2019)
- Adding a full UI framework when you only need one component

**Good:**
- Adding `class-variance-authority` for CVA pattern in shadcn-style components
- Adding `xlsx` for Excel export (no native JS solution)
