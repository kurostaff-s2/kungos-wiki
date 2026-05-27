# Executive Summary: The Super-Council Architecture

## 1. System Vision & Purpose
The **Super-Council** is a multi-agent orchestration layer designed to coordinate specialized LLM subagents through a structured, test-driven development (TDD) workflow. Rather than relying on a single, general-purpose coder agent, the Super-Council divides engineering labor between distinct personas:
*   **The Chair (Main Agent):** Coordinates the overall task state, handles execution flow, and dispatches subagents.
*   **Subagents (Builders):** Write actual code inside temporary, isolated Git worktrees.
*   **Reviewers (Logic, Architecture, Diversity):** Evaluate design plans, specifications, and code modifications to ensure they align with project requirements and prevent regressions.

---

## 2. Core Architectural Pillars
The architecture proposed by the council consensus consists of four main pillars:

### A. Pipeline Orchestrator (State-Machine)
*   **Workflow:** Operates as a 6-phase state machine rather than a rigid linear chain:
    $$\text{SCOUT} \longrightarrow \text{PLAN} \longrightarrow \text{BUILD} \longrightarrow \text{AGENT\_VALIDATE} \longrightarrow \text{HUMAN\_GATE} \longrightarrow \text{INDEX} \longrightarrow \text{DONE}$$
*   **Adaptive Recovery:** If a subagent fails at any phase, the state machine triggers a **Scout** phase to analyze the workspace, identify errors, and update the plan instead of looping blindly.
*   **Idempotency & Versioning:** Every task is assigned a `pipeline_id` (UUID). State is saved in JSON/SQLite, using locking mechanism (`fcntl.flock`) to prevent concurrent write collisions.

### B. Persona Multiplexing
*   **Review Gates:** Auto-dispatches spec and plan reviews to specialized agents (`reviewer-arch`, `reviewer-logic`, etc.) to enforce quality and catch omissions before writing code.
*   **GPU Cooldown/Concurrency Control:** A Typescript/Python GPU semaphore serializes delegations to co-resident llama-server instances to prevent out-of-memory (VRAM) errors.

### C. Risk-Adaptive Verification
*   **Risk Scoring:** Evaluates the risk of changes (e.g. database schema changes or critical core libraries vs. simple comment/doc tweaks).
*   **Verification scaling:** The validation rigor and test-execution timeouts scale adaptively depending on the risk score of the modified files.

### D. Spec-Driven Backbone
*   **Triple Artifact Strategy:** Uses Spec, Implementation Plan, and Walkthrough artifacts as immutable boundaries that require explicit validation and gates to progress.

---

## 3. Gap Analysis & Resolution Status
Based on the Super-Council working report, several architectural gaps were identified and are being addressed:
1.  **Recall & Index Endpoints (Resolved):** Added `/v1/council/recall` (for active, phase-aware memory search) and `/v1/council/index` (for fire-and-forget vector indexing) to `super-council.py`.
2.  **GPU Semaphore Serialization (Resolved):** Serialized delegation calls inside `council-tools/index.ts` to avoid `409 Conflict` errors.
3.  **Project-wise Tracking & Recall (Current Focus):** Previously, memories were indexed in a flat vector space without project contexts, making cross-project search noisy.

---

## 4. Proposed Solution: Hybrid Project-Wise Tracking
To close the remaining gap, the proposed implementation plan introduces:
1.  **Project Metadata Tags (Memsearch/Milvus):** Leverage Milvus dynamic schema fields to tag chunks with a `project_id` at index time. Update search methods to allow filtering recall queries by project.
2.  **SQLite Tracking Table (Supervisor):** Implement a persistent SQLite tracking database (`~/.council-memory/migration.db`) managing:
    *   `pipelines` table to track execution status, attempts, and phase transitions.
    *   `translations` table to maintain backwards-compatibility between legacy `task_id`s and new `pipeline_id`s.
3.  **HTTP/CLI Interfaces:** Expose `/v1/council/pipelines` and CLI flags to allow querying pipelines and search filters easily.
