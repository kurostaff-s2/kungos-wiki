a production-style execution plan for the next unification phase after v2.1, written in the same milestone/checklist format as the earlier task plans. It assumes v2.1 is already implemented and shifts the system toward true unification by prioritizing the highest-ROI shared entities first.
Phase 0: Unification lock
Deliverables

    Final ownership matrix for Council Core vs AppFlowy-owned data.

    Final list of shared entities in unification scope: work items, prompt templates, knowledge cards, reviews, and findings.

    Explicit decision on which fields are editable from AppFlowy for each shared entity.

    Updated migration order and dependency graph for the unification rollout.

Acceptance criteria

    Every shared entity has exactly one canonical owner.

    Every editable field has an explicit source of truth and revision rule.

    There is a single approved plan for the next production rollout wave.

Dependencies

    v2.1 schemas, core API, outbox, inbound sync, and hardening already exist.

Phase 1: Work items
Deliverables

    Finalized council_core.work_items schema aligned to the revised base contract.

    AppFlowy mapping for work items with approved editable fields and read-only fields.

    Revision-aware round-trip flows for create, edit, conflict, and retry.

    Production UI/database coverage for work-item board/list/calendar surfaces.

Acceptance criteria

    Work items can be created and updated from either Council or AppFlowy through the same canonical mutation path.

    Stale AppFlowy edits return 409 rather than silently overwriting Council state.

    Read-only work-item fields cannot be mutated from AppFlowy.

    All work-item tests pass end-to-end against the real or gated real-instance flow.

Dependencies

    Council Core API, outbox, inbound sync, binding lifecycle, and restart safety.

Phase 2: Prompt templates
Deliverables

    Final council_core.prompt_templates schema and resource endpoints.

    AppFlowy prompt-template editing surface for approved fields only.

    Outbound projection and inbound normalization for prompt-template updates.

    Field-policy tests that prove AppFlowy permissions match Council policy.

Acceptance criteria

    Prompt templates remain Council-owned canonical data.

    AppFlowy can edit only approved prompt fields.

    AppFlowy template changes round-trip cleanly through Council Core.

    Forbidden prompt fields are rejected and logged.

Dependencies

    Work-item unification is stable and the field-level editability contract is proven.

Phase 3: Knowledge cards
Deliverables

    Final council_core.knowledge_cards schema and mapping contract.

    AppFlowy knowledge-card editor and projection rules.

    FIELD_ALLOWLIST and field mapping aligned with the policy tables.

    E2E tests for allowed edits, forbidden edits, and conflict handling.

Acceptance criteria

    Knowledge cards are editable in AppFlowy only on approved human-facing fields.

    Provenance, confidence, and other canonical metadata remain Council-owned.

    Field policy, allowlist, and UI behavior are consistent.

    Round-trip sync works without duplicate or lost updates.

Dependencies

    Prompt-template unification and the canonical edit contract are already stable.

Phase 4: Reviews and findings
Deliverables

    Final council_core.reviews and council_core.review_findings contract.

    AppFlowy triage/edit surfaces for only the approved review and finding fields.

    Inbound rejection logging for forbidden review/finding edits.

    Testing for review notes, triage states, verdict protection, and severity protection.

Acceptance criteria

    AppFlowy supports review/finding workflow without owning verdict or severity authority.

    Council remains the source of truth for outcomes, evidence, and machine-generated review semantics.

    Review/finding edits are revision-safe and conflict-aware.

    The UI and API layers agree on allowed versus forbidden fields.

Dependencies

    Work items, prompt templates, and knowledge cards are already unified successfully.

Phase 5: Memory and rollups
Deliverables

    Final council_core.memory_entries and council_core.memory_rollups schemas.

    Migration of session diary / consolidation semantics to Council canonical storage.

    Optional AppFlowy read-model surfaces for summaries and operational views.

    Restart-safe processing and persistence tests for rollups and snapshots.

Acceptance criteria

    Memory-related canonical data lives in Council, not in scattered legacy stores.

    AppFlowy is a projection/editor surface only where explicitly allowed.

    Rollups and diary entries survive worker restarts without duplication or loss.

    No production path depends on the legacy SQLite model.

Dependencies

    All human-facing shared entities are already stable.

Phase 6: Read-model hardening
Deliverables

    Reduce custom sync behavior to a thin, documented adapter layer.

    Confirm all shared mutations go through Council Core API only.

    AppFlowy upgrade smoke tests for documented REST endpoints and UI surfaces.

    Dead-letter, orphan, and restart-safety operations remain visible and usable.

Acceptance criteria

    AppFlowy can be upgraded independently without schema surgery.

    No integration path depends on undocumented AppFlowy internals.

    Production metrics and recovery paths remain intact.

    The system behaves like one unified product to users, while remaining one-owned-per-dataset internally.

Dependencies

    Core shared entities are already unified and stable in production.

Phase 7: Optional polish
Deliverables

    Board/calendar/gallery refinements where needed.

    Notification, search, file/attachment, and dashboard improvements.

    AppFlowy operational views for sync health and exception tracking.

    UX cleanups that improve the “single system” feel.

Acceptance criteria

    Remaining gaps are mostly convenience or UX, not ownership or correctness gaps.

    Users can work in AppFlowy without noticing the underlying split ownership.

    Production monitoring remains transparent and actionable.

Dependencies

    The unified model is already stable and low-risk.

Phase 8: Arc Summarizer in AppFlowy AI
Deliverables

    Arc Summarizer exposed as AppFlowy LAI (Local AI) plugin.

    Consolidation pipeline triggerable from AppFlowy UI (session summaries, knowledge extraction).

    Tier 1 knowledge card injection into AppFlowy system context.

    Health monitoring for Arc server from AppFlowy AI status panel.

Acceptance criteria

    AppFlowy can invoke Arc consolidation without leaving the workspace.

    Session summaries appear as structured entries in AppFlowy databases.

    Knowledge extraction produces editable knowledge cards.

    Arc server health is visible in AppFlowy (latency, model status, fallback state).

Dependencies

    All human-facing shared entities are already stable.

    AppFlowy LAI plugin system supports custom OpenAI-compatible endpoints.

Integration Architecture

    AppFlowy LAI plugin → OpenAI-compatible API → Arc server (:18095) → Granite-4.1-3B

    Uses existing ArcClient HTTP interface with retry + fallback logic.

    No model swapping needed — Arc is dedicated to consolidation/summarization roles.

Rollout order

    Unification lock.

    Work items.

    Prompt templates.

    Knowledge cards.

    Reviews and findings.

    Memory and rollups.

    Read-model hardening.

    Arc Summarizer in AppFlowy AI.

    Optional polish.

Gating rule

Each phase is complete only when it has:

    Schema or contract alignment.

    AppFlowy mapping / UI exposure where relevant.

    API and sync tests.

    Restart or recovery validation where relevant.
