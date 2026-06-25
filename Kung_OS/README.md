# Project Overview: Kung OS Backend Alignment

## 🎯 Executive Summary
Kung OS is undergoing a systemic architectural alignment to resolve legacy technical debt and implement a scalable, multi-tenant foundation. The project focuses on transitioning from a fragmented, domain-siloed user model to a **Unified Identity & Tenancy Framework**.

### Core Architectural Invariants
- **Unified Identity:** A singular `identity_id` represents a person globally. Domain-specific data (Employee, Customer, Player) is stored in **extension tables**, preventing "person silos."
- **Two-Layer Tenancy:** Clear separation between **Authorization Scope** (what a user *can* access: `div_codes[]`, `branch_codes[]`) and **Active Tenant Context** (what a user *is* accessing: `bg_code`, `active_div_code`, `active_branch_code`).
- **RBAC over Accesslevels:** Replacement of legacy flat "access level" blobs with a formal Role-Based Access Control (RBAC) system.
- **Domain-First Modularity:** Business capabilities are partitioned into bounded-context namespaces (e.g., `eshop/`, `tournaments/`, `cafe/`) consuming shared platform primitives.

---

## 📚 Specification Index
All authoritative blueprints are located in `/home/chief/llm-wiki/Kung_OS`.

### 🏗️ Architecture (The "Why" and "How")
*High-level design principles and systemic blueprints.*
- `architecture/identity_layer.md`: Person modeling and extension table strategy.
- `architecture/multi_tenancy.md`: Tenant hierarchy, active-vs-accessible context, and middleware semantics.
- `architecture/rbac_system.md`: Role and permission resolution logic.
- `architecture/platform_primitives.md`: Shared core utilities and platform-agnostic helpers.
- `architecture/alignment_audit.md`: Analysis of drift between current implementation and target state.

### 📜 Specifications (The "What")
*Concrete contracts and physical schemas.*

#### 🌐 Endpoint Contracts
- `specs/endpoint_contract_spec.md`: **The sole authority for wire contracts.** Defines response envelopes, routing namespaces, and API versioning.

#### 📂 Domain Specifications
*Bounded-context definitions for specific business modules.*
- `specs/domain_specs/identity_spec.md`: Identity lifecycle and normalization.
- `specs/domain_specs/ecommerce_spec.md`: Product catalog, cart, and order flow.
- `specs/domain_specs/tournaments_spec.md`: Tournament management and player tracking.
- `specs/domain_specs/cafe_spec.md`: Arcade sessions and F&B operations.

#### 🗄️ Database Schemas
*Physical storage definitions.*
- `specs/database_schemas/postgresql_schema.md`: Relational tables, constraints, and indexes.
- `specs/database_schemas/mongodb_schema.md`: Document structures for legacy/flexible data.
- `specs/database_schemas/migration_spec.md`: Ordered rollout plan and data backfill strategy.

### ⚙️ Operations & Reviews
*Audit trails and implementation history.*
- `chief-review/`: Executive audit findings.
- `operations/`: Migration logs and technical debt tracking.

---

## 🛠️ Project State
**Current Focus:** `Auth API Target Alignment`
Executing a unified refactor to align implementation with the above invariants, removing legacy paths, and scaffolding the M1 Identity layer.
