# AppFlowy Integration Analysis for Super-Council

> **Date:** 2026-06-01
> **Context:** Evaluating AppFlowy (open-source Notion alternative) as external task, review, and knowledge management layer for the super-council flow.
> **References:** [migration-plan-2026-06-01.md](../00-prompt-handoff/migration-plan-2026-06-01.md), [01-overview.md](01-overview.md), [05-pipeline-api.md](05-pipeline-api.md)

---

## Executive Summary

**Refactor RelationalStore + ContextRouter into council-domain services, backed by a single PostgreSQL instance that also hosts AppFlowy.** This eliminates the sync adapter, collapses two databases into one, and gives the data layer native understanding of council concepts (pipelines, phases, transitions, reviews, work items).

The migration plan's Phase 4 (review streamlining) and Phase 5 (unified work items) already require heavy rewrites of `store.py` and `router.py` — same window to do the SQLite → PostgreSQL + council-domain refactor.

---

## Current Architecture (Loose Coupling)

```
SlotSupervisor (super_council.py)
  ├── self.relational_store = memory_service.store    # generic SQLite CRUD
  ├── self.context_router = memory_service.router      # generic SQL queries
  ├── self.memory_layer = memory_service.layer         # artifact slicing
  ├── self.review_service = memory_service.review      # fake pipelines
  └── self.memory = CouncilMemory()                    # markdown file logging

MemoryService (memory_service/__init__.py)
  ├── RelationalStore    → sqlite3.connect(pipelines.db)  # generic CRUD
  ├── ContextRouter      → raw SQL queries over store.db  # generic queries
  ├── MemoryLayer        → artifact management
  └── ReviewService      → creates fake pipelines for reviews
```

**The gap:** RelationalStore knows about pipelines/phases/transitions but exposes them as generic CRUD (`upsert_pipeline`, `find_active_pipeline`, `_record_transition`). ContextRouter builds queries from raw SQL strings. Neither understands council *workflows* — they're data access layers bolted onto council logic.

The council (SlotSupervisor) has to orchestrate everything: create pipeline → ensure workflow run → record transition → log event → store artifact. Five separate calls across two modules for one logical operation.

---

## Proposed Architecture (Tight Integration)

```
SlotSupervisor (super_council.py)
  ├── self.council_db = CouncilDatabase()              # council-domain data layer
  │   ├── .pipelines.create(task, project)             # domain method
  │   ├── .pipelines.transition(run_id, to_phase)      # atomic transition
  │   ├── .reviews.start(reviewer, target)             # native reviews
  │   ├── .work_items.upsert(...)                      # unified work tracking
  │   └── .recall.context(run_id)                      # integrated recall
  │
  └── self.council_db.appflowy                         # visual sync (thin)
      ├── .push_work_item(work_id)                     # API call
      ├── .push_review(review_id)                      # API call
      └── .create_todo(...)                            # API call

CouncilDatabase (memory_service/council_db.py) — NEW
  ├── SQLAlchemy ORM (PostgreSQL backend)
  ├── Council-domain models (Pipeline, WorkflowRun, Review, WorkItem, Finding)
  ├── Integrated recall (run snapshots, events, artifacts — one query)
  ├── AppFlowy adapter (thin REST client, no sync logic)
  └── Migration path: RelationalStore + ContextRouter → unified layer

PostgreSQL (single instance)
  ├── council_schema
  │   ├── pipelines
  │   ├── workflow_runs
  │   ├── state_executions
  │   ├── work_items          (Phase 5)
  │   ├── reviews             (Phase 4)
  │   ├── review_findings     (Phase 4)
  │   ├── event_log
  │   ├── artifacts
  │   ├── working_memory      (Phase 2)
  │   ├── long_term_memory    (Phase 2)
  │   ├── raw_session_memories
  │   └── pgvector embeddings (MemIndex)
  ├── appflowy_public         (AppFlowy's tables, untouched)
  └── auth                    (GoTrue tables)
```

---

## The Refactor: RelationalStore + ContextRouter → CouncilDatabase

### What Changes

| Current | Proposed | Why |
|---------|----------|-----|
| `RelationalStore` (generic CRUD) | `CouncilDatabase.pipelines` (domain methods) | Pipeline creation, transition, archival — one call |
| `ContextRouter` (raw SQL queries) | `CouncilDatabase.recall` (integrated queries) | Run snapshots, events, artifacts — one query |
| `ReviewService` (fake pipelines) | `CouncilDatabase.reviews` (native tables) | No more fake pipelines |
| `sqlite3` (file-based) | `SQLAlchemy` (PostgreSQL) | Single DB, ACID, joins |
| Separate module loads | Single `CouncilDatabase` instance | One initialization, one config |
| CouncilMemory (markdown files) | `CouncilDatabase.events` (structured) | Structured event log, queryable |

### CouncilDatabase API

```python
"""CouncilDatabase: Council-domain data layer.

Replaces RelationalStore + ContextRouter + ReviewService + CouncilMemory.
Backed by PostgreSQL (SQLAlchemy ORM). Council concepts are first-class.
"""
from sqlalchemy import create_engine, Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from contextlib import contextmanager

Base = declarative_base()

# ── Council-Domain Models ──────────────────────────────────────────────

class Pipeline(Base):
    """Council pipeline — tracks task execution through phases."""
    __tablename__ = "pipelines"
    __table_args__ = {"schema": "council"}

    pipeline_id = Column(String, primary_key=True)
    task = Column(Text, nullable=False)
    task_hash = Column(String(32), nullable=False)
    project_id = Column(String, nullable=False)
    phase = Column(String, nullable=False)  # CHECK constraint
    status = Column(String, default="active")  # CHECK constraint
    global_attempts = Column(Integer, default=0)
    metadata = Column(Text)  # JSON
    work_id = Column(String, ForeignKey("council.work_items.work_id"))
    created_at = Column(DateTime, server_default="now()")
    updated_at = Column(DateTime, server_default="now(), onupdate=now()")
    completed_at = Column(DateTime)

    runs = relationship("WorkflowRun", back_populates="pipeline")


class WorkflowRun(Base):
    """Execution run within a pipeline."""
    __tablename__ = "workflow_runs"
    __table_args__ = {"schema": "council"}

    run_id = Column(String, primary_key=True)
    pipeline_id = Column(String, ForeignKey("council.pipelines.pipeline_id"))
    project_id = Column(String, nullable=False)
    phase = Column(String, nullable=False)
    status = Column(String, default="running")
    started_at = Column(DateTime, server_default="now()")
    finished_at = Column(DateTime)

    pipeline = relationship("Pipeline", back_populates="runs")
    executions = relationship("StateExecution", back_populates="run")


class StateExecution(Base):
    """Phase execution attempt."""
    __tablename__ = "state_executions"
    __table_args__ = {"schema": "council"}

    execution_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("council.workflow_runs.run_id"))
    phase = Column(String, nullable=False)
    attempt_number = Column(Integer, nullable=False)
    outcome = Column(String, nullable=False)  # CHECK: success/failure/retreat/...
    error = Column(Text)
    duration_ms = Column(Float)
    started_at = Column(DateTime, server_default="now()")
    finished_at = Column(DateTime)

    run = relationship("WorkflowRun", back_populates="executions")


class WorkItem(Base):
    """Unified work tracking — pipelines, reviews, delegations, ad-hoc."""
    __tablename__ = "work_items"
    __table_args__ = {"schema": "council"}

    work_id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False)
    work_type = Column(String, nullable=False)  # CHECK: pipeline/review/delegation/ad-hoc
    task = Column(Text, nullable=False)
    task_hash = Column(String(32), nullable=False)
    parent_work_id = Column(String, ForeignKey("council.work_items.work_id"))
    status = Column(String, default="active")  # CHECK: active/done/failed
    metadata = Column(Text)  # JSON: {phase, reviewer, target, model, ...}
    created_at = Column(DateTime, server_default="now()")
    finished_at = Column(DateTime)


class Review(Base):
    """Review lifecycle — replaces fake pipelines."""
    __tablename__ = "reviews"
    __table_args__ = {"schema": "council"}

    review_id = Column(String, primary_key=True)
    reviewer = Column(String, nullable=False)
    target = Column(Text, nullable=False)
    project_id = Column(String, nullable=False)
    work_id = Column(String, ForeignKey("council.work_items.work_id"))
    status = Column(String, default="active")  # CHECK: active/passed/failed/partial
    started_at = Column(DateTime, server_default="now()")
    finished_at = Column(DateTime)

    findings = relationship("ReviewFinding", back_populates="review")


class ReviewFinding(Base):
    """Review finding — stored once, not duplicated."""
    __tablename__ = "review_findings"
    __table_args__ = {"schema": "council"}

    finding_id = Column(String, primary_key=True)
    review_id = Column(String, ForeignKey("council.reviews.review_id"))
    severity = Column(String, nullable=False)  # CHECK: critical/high/moderate/low/info
    summary = Column(Text, nullable=False)
    fix = Column(Text)
    evidence = Column(Text)
    action = Column(Text)
    created_at = Column(DateTime, server_default="now()")

    review = relationship("Review", back_populates="findings")


class EventLog(Base):
    """Structured event log — replaces CouncilMemory markdown files."""
    __tablename__ = "event_log"
    __table_args__ = {"schema": "council"}

    event_id = Column(String, primary_key=True)
    run_id = Column(String)
    event_type = Column(String, nullable=False)  # CHECK constraint
    severity = Column(String, nullable=False)  # CHECK constraint
    message = Column(Text, nullable=False)
    metadata = Column(Text)  # JSON
    occurred_at = Column(DateTime, server_default="now()")


class Artifact(Base):
    """Content artifact linked to runs."""
    __tablename__ = "artifacts"
    __table_args__ = {"schema": "council"}

    artifact_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("council.workflow_runs.run_id"))
    phase = Column(String)
    key = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    content_type = Column(String, default="text/plain")
    created_at = Column(DateTime, server_default="now()")


# ── CouncilDatabase: Domain Service ────────────────────────────────────

class CouncilDatabase:
    """Council-domain data layer.

    Replaces RelationalStore + ContextRouter + ReviewService.
    All council operations are domain methods — no raw SQL exposure.
    """

    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # connection health check
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

        # Sub-services (lazy-loaded)
        self._pipelines = None
        self._reviews = None
        self._work = None
        self._recall = None
        self._appflowy = None

    @property
    def pipelines(self) -> "PipelineService":
        if self._pipelines is None:
            self._pipelines = PipelineService(self.Session)
        return self._pipelines

    @property
    def reviews(self) -> "ReviewDomain":
        if self._reviews is None:
            self._reviews = ReviewDomain(self.Session)
        return self._reviews

    @property
    def work(self) -> "WorkService":
        if self._work is None:
            self._work = WorkService(self.Session)
        return self._work

    @property
    def recall(self) -> "RecallService":
        if self._recall is None:
            self._recall = RecallService(self.Session)
        return self._recall

    @property
    def appflowy(self) -> "AppFlowySync":
        if self._appflowy is None:
            from .appflowy_adapter import AppFlowySync
            self._appflowy = AppFlowySync(self.Session)
        return self._appflowy

    @contextmanager
    def session(self):
        """Session context manager with auto-commit/rollback."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# ── Pipeline Service ───────────────────────────────────────────────────

class PipelineService:
    """Pipeline lifecycle — creation, transition, archival."""

    def __init__(self, Session):
        self._Session = Session

    def create(self, task: str, project_id: str, pipeline_id: str = None) -> Pipeline:
        """Create pipeline + workflow run + work item + seed event. One call."""
        import hashlib
        import uuid
        from datetime import datetime

        task_hash = hashlib.sha256(task.encode()).hexdigest()[:32]
        pid = pipeline_id or f"pipe-{uuid.uuid4().hex}"
        now = datetime.utcnow()

        with self._Session() as session:
            # 1. Pipeline
            pipeline = Pipeline(
                pipeline_id=pid, task=task, task_hash=task_hash,
                project_id=project_id, phase="SCOUT", status="active",
                created_at=now, updated_at=now,
            )
            session.add(pipeline)

            # 2. Workflow run
            run = WorkflowRun(
                run_id=pid, pipeline_id=pid, project_id=project_id,
                phase="SCOUT", status="running", started_at=now,
            )
            session.add(run)

            # 3. Work item
            work = WorkItem(
                work_id=pid, project_id=project_id, work_type="pipeline",
                task=task, task_hash=task_hash, status="active", created_at=now,
            )
            session.add(work)

            # 4. Seed event
            event = EventLog(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                run_id=pid, event_type="transition", severity="info",
                message=f"Pipeline created: {task[:80]}", occurred_at=now,
            )
            session.add(event)

            session.commit()
            return pipeline

    def transition(self, run_id: str, from_phase: str, to_phase: str,
                   outcome: str = "success", error: str = "",
                   duration_ms: float = 0.0,
                   artifact_key: str = None, artifact_content: str = None) -> dict:
        """Record phase transition atomically. One call replaces five."""
        import uuid
        from datetime import datetime

        with self._Session() as session:
            now = datetime.utcnow()
            run = session.query(WorkflowRun).filter_by(run_id=run_id).first()
            if not run:
                raise ValueError(f"Run {run_id} not found")

            execution_id = f"exe-{uuid.uuid4().hex[:8]}"
            event_id = f"evt-{uuid.uuid4().hex[:8]}"

            # 1. State execution
            execution = StateExecution(
                execution_id=execution_id, run_id=run_id, phase=to_phase,
                attempt_number=self._next_attempt(session, run_id, to_phase),
                outcome=outcome, error=error or None, duration_ms=duration_ms,
                started_at=now,
            )
            session.add(execution)

            # 2. Event log
            severity = "error" if outcome == "failure" else "info"
            event = EventLog(
                event_id=event_id, run_id=run_id, event_type="transition",
                severity=severity,
                message=f"Transition {from_phase} → {to_phase} (attempt {execution.attempt_number}, {outcome})",
                occurred_at=now,
            )
            session.add(event)

            # 3. Artifact (optional)
            artifact_id = None
            if artifact_key and artifact_content:
                artifact_id = f"art-{uuid.uuid4().hex[:8]}"
                artifact = Artifact(
                    artifact_id=artifact_id, run_id=run_id, phase=to_phase,
                    key=artifact_key, content=artifact_content, created_at=now,
                )
                session.add(artifact)

            # 4. Update workflow run
            terminal = to_phase in {"DONE", "FAILED"}
            run.phase = to_phase
            run.status = "done" if to_phase == "DONE" else ("failed" if to_phase == "FAILED" else "running")
            run.finished_at = now if terminal else None

            # 5. Update pipeline
            pipeline = session.query(Pipeline).filter_by(pipeline_id=run.pipeline_id).first()
            if pipeline:
                pipeline.phase = to_phase
                pipeline.status = run.status
                pipeline.updated_at = now
                pipeline.completed_at = now if terminal else None

            session.commit()

            return {
                "execution_id": execution_id,
                "event_id": event_id,
                "artifact_id": artifact_id,
                "run_id": run_id,
                "phase": to_phase,
            }

    def find_active(self, task: str, project_id: str) -> Pipeline | None:
        """Find active pipeline by task hash."""
        import hashlib
        task_hash = hashlib.sha256(task.encode()).hexdigest()[:32]
        with self._Session() as session:
            return session.query(Pipeline).filter_by(
                task_hash=task_hash, project_id=project_id,
            ).filter(Pipeline.status.notin_(["done", "failed"])).first()

    def _next_attempt(self, session, run_id: str, phase: str) -> int:
        max_attempt = session.query(StateExecution).filter_by(
            run_id=run_id, phase=phase,
        ).with_entities(StateExecution.attempt_number.max() or 0).scalar()
        return max_attempt + 1


# ── Review Domain ──────────────────────────────────────────────────────

class ReviewDomain:
    """Review lifecycle — native tables, no fake pipelines."""

    def __init__(self, Session):
        self._Session = Session

    def start(self, reviewer: str, target: str, project_id: str,
              work_id: str = None) -> Review:
        """Start review. One call — no fake pipeline needed."""
        import uuid
        from datetime import datetime

        review_id = f"rev-{uuid.uuid4().hex[:12]}"
        with self._Session() as session:
            review = Review(
                review_id=review_id, reviewer=reviewer.upper(),
                target=target, project_id=project_id, work_id=work_id,
                status="active", started_at=datetime.utcnow(),
            )
            session.add(review)

            # Seed event
            event = EventLog(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                run_id=review_id, event_type="review-finding", severity="info",
                message=f"Review started: {reviewer.upper()} → {target}",
                occurred_at=datetime.utcnow(),
            )
            session.add(event)
            session.commit()
            return review

    def log_finding(self, review_id: str, severity: str, summary: str,
                    fix: str = "", evidence: str = "", action: str = "") -> ReviewFinding:
        """Log finding. One call — no fake artifact needed."""
        import uuid
        from datetime import datetime

        with self._Session() as session:
            finding = ReviewFinding(
                finding_id=f"finding-{uuid.uuid4().hex[:8]}",
                review_id=review_id, severity=severity, summary=summary,
                fix=fix or None, evidence=evidence or None, action=action or None,
                created_at=datetime.utcnow(),
            )
            session.add(finding)

            # Event log
            event = EventLog(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                run_id=review_id, event_type="review-finding", severity=severity,
                message=f"[{fix}] {summary}", occurred_at=datetime.utcnow(),
            )
            session.add(event)
            session.commit()
            return finding

    def record_verdict(self, review_id: str, verdict: str, reason: str = "") -> Review:
        """Record verdict. One call — no fake workflow update needed."""
        from datetime import datetime

        status_map = {"PASS": "passed", "FAIL": "failed", "PARTIAL": "partial"}
        verdict = verdict.upper()
        with self._Session() as session:
            review = session.query(Review).filter_by(review_id=review_id).first()
            if not review:
                raise ValueError(f"Review {review_id} not found")
            review.status = status_map[verdict]
            review.finished_at = datetime.utcnow()

            # Event log
            severity = "info" if verdict == "PASS" else ("error" if verdict == "FAIL" else "warning")
            event = EventLog(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                run_id=review_id, event_type="review-verdict", severity=severity,
                message=f"Verdict: {verdict} — {reason}",
                occurred_at=datetime.utcnow(),
            )
            session.add(event)
            session.commit()
            return review


# ── Recall Service ─────────────────────────────────────────────────────

class RecallService:
    """Integrated recall — run snapshots, events, artifacts in one query."""

    def __init__(self, Session):
        self._Session = Session

    def run_snapshot(self, run_id: str) -> dict:
        """Full run snapshot: pipeline + executions + events + artifacts."""
        with self._Session() as session:
            run = session.query(WorkflowRun).filter_by(run_id=run_id).first()
            if not run:
                return None

            pipeline = session.query(Pipeline).filter_by(pipeline_id=run.pipeline_id).first()
            executions = session.query(StateExecution).filter_by(run_id=run_id).order_by(
                StateExecution.started_at
            ).all()
            events = session.query(EventLog).filter_by(run_id=run_id).order_by(
                EventLog.occurred_at.desc()
            ).all()
            artifacts = session.query(Artifact).filter_by(run_id=run_id).order_by(
                Artifact.created_at
            ).all()

            return {
                "run_id": run.run_id,
                "pipeline": {
                    "pipeline_id": pipeline.pipeline_id,
                    "task": pipeline.task,
                    "project_id": pipeline.project_id,
                    "phase": pipeline.phase,
                    "status": pipeline.status,
                } if pipeline else {},
                "phase": run.phase,
                "status": run.status,
                "started_at": str(run.started_at),
                "finished_at": str(run.finished_at) if run.finished_at else None,
                "executions": [
                    {
                        "execution_id": e.execution_id,
                        "phase": e.phase,
                        "attempt": e.attempt_number,
                        "outcome": e.outcome,
                        "error": e.error,
                        "duration_ms": e.duration_ms,
                    }
                    for e in executions
                ],
                "events": [
                    {
                        "event_id": e.event_id,
                        "type": e.event_type,
                        "severity": e.severity,
                        "message": e.message,
                        "occurred_at": str(e.occurred_at),
                    }
                    for e in events
                ],
                "artifacts": [
                    {
                        "artifact_id": a.artifact_id,
                        "phase": a.phase,
                        "key": a.key,
                        "content_type": a.content_type,
                        "created_at": str(a.created_at),
                    }
                    for a in artifacts
                ],
            }

    def recent_events(self, run_id: str = None, limit: int = 10) -> list:
        """Recent events, optionally scoped to a run."""
        with self._Session() as session:
            q = session.query(EventLog).order_by(EventLog.occurred_at.desc())
            if run_id:
                q = q.filter_by(run_id=run_id)
            return [
                {
                    "event_id": e.event_id,
                    "run_id": e.run_id,
                    "type": e.event_type,
                    "severity": e.severity,
                    "message": e.message,
                    "occurred_at": str(e.occurred_at),
                }
                for e in q.limit(limit).all()
            ]

    def review_findings(self, project_id: str = None, limit: int = 10) -> list:
        """Recent review findings with review context."""
        with self._Session() as session:
            q = session.query(ReviewFinding).join(Review)
            if project_id:
                q = q.filter(Review.project_id == project_id)
            q = q.order_by(ReviewFinding.created_at.desc()).limit(limit)
            return [
                {
                    "finding_id": f.finding_id,
                    "review_id": f.review_id,
                    "reviewer": f.review.reviewer,
                    "target": f.review.target,
                    "severity": f.severity,
                    "summary": f.summary,
                    "fix": f.fix,
                    "created_at": str(f.created_at),
                }
                for f in q.all()
            ]


# ── Work Service ───────────────────────────────────────────────────────

class WorkService:
    """Unified work tracking."""

    def __init__(self, Session):
        self._Session = Session

    def upsert(self, work_id: str, project_id: str, work_type: str,
               task: str, status: str = "active", metadata: str = None,
               parent_work_id: str = None) -> WorkItem:
        import hashlib
        import uuid
        from datetime import datetime

        task_hash = hashlib.sha256(task.encode()).hexdigest()[:32]
        with self._Session() as session:
            existing = session.query(WorkItem).filter_by(
                task_hash=task_hash, project_id=project_id, work_type=work_type,
            ).first()
            if existing:
                existing.status = status
                existing.metadata = metadata
                existing.updated_at = datetime.utcnow()
                session.commit()
                return existing

            item = WorkItem(
                work_id=work_id, project_id=project_id, work_type=work_type,
                task=task, task_hash=task_hash, status=status,
                metadata=metadata, parent_work_id=parent_work_id,
                created_at=datetime.utcnow(),
            )
            session.add(item)
            session.commit()
            return item
```

---

## Integration with SlotSupervisor

### Before (5 calls for one transition)

```python
# super_council.py — current
self.relational_store.upsert_pipeline(...)
self.relational_store.ensure_workflow_run(...)
self.relational_store._record_transition(...)
self.relational_store.log_event(...)
self.relational_store.store_artifact(...)
```

### After (1 call)

```python
# super_council.py — refactored
result = self.council_db.pipelines.transition(
    run_id=run_id,
    from_phase=from_phase,
    to_phase=to_phase,
    outcome="success",
    artifact_key="plan",
    artifact_content=plan_text,
)
```

### Before (fake pipeline for review)

```python
# review.py — current
pipeline_id = f"mcp-review-{uuid.uuid4().hex[:12]}"
self._rs.upsert_pipeline(pipeline_id=pipeline_id, project_id="mcp-review", ...)
self._rs.ensure_workflow_run(run_id=rid, pipeline_id=pipeline_id, ...)
self._rs.log_event(run_id=rid, event_type="info", ...)
```

### After (native review)

```python
# council_db.py — refactored
review = self.council_db.reviews.start(
    reviewer="nemotron", target="auth-refactor", project_id="7-council"
)
self.council_db.reviews.log_finding(
    review_id=review.review_id, severity="high",
    summary="Missing input validation", fix="Add z-schema"
)
self.council_db.reviews.record_verdict(
    review_id=review.review_id, verdict="FAIL", reason="Needs input validation"
)
```

---

## AppFlowy Sync (Thin Adapter)

The AppFlowy adapter becomes a thin REST client that pushes council data to AppFlowy databases. No sync logic, no polling, no conflict resolution — just "write this row."

```python
"""AppFlowy Sync Adapter — thin REST client.

Pushes council data to AppFlowy databases for visual management.
No sync logic. No polling. Just API calls on state changes.
"""
import httpx
from typing import Optional

class AppFlowySync:
    def __init__(self, council_db: "CouncilDatabase"):
        config = council_db.config  # from config-subsystem.json
        self._db = council_db
        self._client = httpx.Client(
            base_url=config.appflowy.base_url,
            headers={"Authorization": f"Bearer {config.appflowy.token}"},
            timeout=30,
        )
        self.workspace_id = config.appflowy.workspace_id
        self.databases = config.appflowy.databases  # {name: db_uuid}

    # Called from PipelineService.create()
    def push_work_item(self, work_item: "WorkItem") -> None:
        """Push work item to AppFlowy."""
        if not self._db.config.appflowy.enabled:
            return
        cells = {
            "work_id": work_item.work_id,
            "project_id": work_item.project_id,
            "work_type": work_item.work_type,
            "task": work_item.task,
            "status": work_item.status,
        }
        self._upsert_row(self.databases["work_items"], cells)

    # Called from ReviewDomain.start()
    def push_review(self, review: "Review") -> None:
        if not self._db.config.appflowy.enabled:
            return
        cells = {
            "review_id": review.review_id,
            "reviewer": review.reviewer,
            "target": review.target,
            "project_id": review.project_id,
            "status": review.status,
        }
        self._upsert_row(self.databases["reviews"], cells)

    # Called from ReviewDomain.log_finding()
    def push_finding(self, finding: "ReviewFinding") -> None:
        if not self._db.config.appflowy.enabled:
            return
        cells = {
            "finding_id": finding.finding_id,
            "review_id": finding.review_id,
            "severity": finding.severity,
            "summary": finding.summary,
            "fix": finding.fix or "",
        }
        self._upsert_row(self.databases["findings"], cells)

    # Called from event handlers (pipeline failure, critical finding)
    def create_todo(self, title: str, priority: str = "medium",
                    source: str = "manual", related_work_id: str = None) -> None:
        if not self._db.config.appflowy.enabled:
            return
        cells = {
            "title": title,
            "status": "Todo",
            "priority": priority,
            "source": source,
            "related_work_id": related_work_id or "",
        }
        self._create_row(self.databases["todos"], cells)

    def _upsert_row(self, database_id: str, cells: dict) -> dict:
        url = f"/api/workspace/{self.workspace_id}/database/{database_id}/row"
        resp = self._client.put(url, json={"rows": [{"cells": cells}]})
        resp.raise_for_status()
        return resp.json()

    def _create_row(self, database_id: str, cells: dict) -> dict:
        url = f"/api/workspace/{self.workspace_id}/database/{database_id}/row"
        resp = self._client.post(url, json={"rows": [{"cells": cells}]})
        resp.raise_for_status()
        return resp.json()
```

**Integration hooks** (added to domain methods, not scattered across the codebase):

```python
# PipelineService.create()
def create(self, task, project_id, pipeline_id=None):
    # ... create pipeline, run, work_item, event ...
    session.commit()

    # Push to AppFlowy (thin adapter, called from domain method)
    if self._db.config.appflowy.enabled:
        self._db.appflowy.push_work_item(work)
    return pipeline

# ReviewDomain.start()
def start(self, reviewer, target, project_id, work_id=None):
    # ... create review, event ...
    session.commit()

    if self._db.config.appflowy.enabled:
        self._db.appflowy.push_review(review)
    return review
```

---

## Migration Path

### Phase 1: SQLAlchemy Layer (Migration Phase 3 window)

- [ ] Add SQLAlchemy models (above) to `memory_service/council_db.py`
- [ ] Add `database_url` to `config-subsystem.json`
- [ ] Keep SQLite RelationalStore as fallback (dual-write during transition)
- [ ] Test: write to PostgreSQL, read from SQLAlchemy, verify data matches

### Phase 2: Domain Services (Migration Phase 4-5 window)

- [ ] Implement `PipelineService`, `ReviewDomain`, `WorkService`, `RecallService`
- [ ] Hook into SlotSupervisor: `self.council_db = CouncilDatabase(config.database_url)`
- [ ] Replace `self.relational_store.upsert_pipeline()` → `self.council_db.pipelines.create()`
- [ ] Replace `self.relational_store._record_transition()` → `self.council_db.pipelines.transition()`
- [ ] Replace ReviewService → `self.council_db.reviews.*`
- [ ] Test: full pipeline lifecycle through new API

### Phase 3: Drop SQLite (Migration Phase 7 window)

- [ ] Remove `sqlite3` dependency from `store.py`
- [ ] Remove `RelationalStore`, `ContextRouter` classes
- [ ] Update all references in `super_council.py`
- [ ] Update MCP server tools
- [ ] Test: full council operation on PostgreSQL only

### Phase 4: AppFlowy Sync (Post-migration)

- [ ] Deploy AppFlowy Cloud (docker-compose)
- [ ] Create workspace + databases
- [ ] Wire `AppFlowySync` to `CouncilDatabase`
- [ ] Test: pipeline creation → AppFlowy row appears

---

## What Stays Separate

| Component | Backend | Reason |
|-----------|---------|--------|
| `codegraph.db` | SQLite (FTS5) | FTS5 is SQLite-native; PostgreSQL FTS is different |
| `MemIndex` (Milvus) | Milvus-lite | Vector search, not relational |
| AppFlowy tables | PostgreSQL (appflowy_public schema) | Untouched, managed by AppFlowy |
| GoTrue auth | PostgreSQL (auth schema) | Untouched, managed by GoTrue |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| SQLAlchemy ORM overhead | Slight performance hit | Connection pooling, session management, benchmark |
| Migration complexity | Downture during switch | Dual-write Phase 1, gradual cutover |
| PostgreSQL downtime | All council ops halt | Connection health checks, retry logic, monitoring |
| AppFlowy API changes | Sync adapter breaks | Feature flag, graceful degradation |
| CodeGraph FTS5 mismatch | Cross-DB JOINs harder | CodeGraph stays SQLite; JOIN via Python, not SQL |

---

## Config Changes

```json
// config-subsystem.json
{
  "memory": {
    "database_url": "postgresql://council:council_pass@localhost:5432/council_db",
    "codegraph_db_path": "~/.council-memory/codegraph.db",
    "appflowy": {
      "enabled": false,
      "base_url": "http://appflowy.local:80",
      "workspace_id": "workspace-uuid",
      "token_file": "~/.appflowy/token",
      "databases": {
        "work_items": "db-uuid",
        "reviews": "db-uuid",
        "findings": "db-uuid",
        "todos": "db-uuid"
      }
    }
  }
}
```

---

## Summary

| Aspect | Current | Proposed |
|--------|---------|----------|
| **Data layer** | RelationalStore (SQLite CRUD) | CouncilDatabase (PostgreSQL, domain methods) |
| **Recall** | ContextRouter (raw SQL) | RecallService (SQLAlchemy queries) |
| **Reviews** | Fake pipelines | Native reviews table |
| **Work tracking** | Pipelines only | Unified work_items |
| **Transitions** | 5 separate calls | 1 domain method |
| **AppFlowy** | N/A | Thin adapter, pushed from domain methods |
| **Backends** | SQLite + (optionally) AppFlowy PostgreSQL | Single PostgreSQL + SQLite (codegraph only) |
| **Coupling** | Loose (bolted on) | Tight (council concepts are first-class) |

**Trade-off:** Tighter coupling means `CouncilDatabase` is council-specific (not reusable elsewhere). But it already is council-specific — the refactor just makes that explicit and eliminates the impedance mismatch between council logic and data access.

---

## Feature Inventory: Analysis Draft vs Available

### Features Proposed in Analysis Draft

| # | Feature | Status | Integration Point |
|---|---------|--------|-------------------|
| 1 | CouncilDatabase (SQLAlchemy ORM) | ✅ Proposed | Replaces RelationalStore + ContextRouter |
| 2 | Pipeline domain service | ✅ Proposed | `council_db.pipelines.create/transition` |
| 3 | Review domain service | ✅ Proposed | `council_db.reviews.start/log/verdict` |
| 4 | Work items service | ✅ Proposed | `council_db.work.upsert` |
| 5 | Recall service | ✅ Proposed | `council_db.recall.run_snapshot/events/findings` |
| 6 | AppFlowy sync adapter | ✅ Proposed | `council_db.appflowy.push_*` |
| 7 | Single PostgreSQL instance | ✅ Proposed | council_schema + appflowy_public + auth |
| 8 | SQLAlchemy models (7 tables) | ✅ Proposed | Pipeline, WorkflowRun, Review, WorkItem, Finding, EventLog, Artifact |
| 9 | Migration path (SQLite → PostgreSQL) | ✅ Proposed | Dual-write Phase 1, cutover Phase 3 |
| 10 | Config changes | ✅ Proposed | `database_url`, `appflowy` section |
| 11 | AppFlowy databases (4) | ✅ Proposed | Work Items, Reviews, Findings, To-Do |
| 12 | AppFlowy views (Board/Grid/Calendar) | ✅ Proposed | Visual management layer |

### Super-Council Features: Available but NOT in Analysis Draft

| # | Feature | Module | Description | Integration Potential |
|---|---------|--------|-------------|----------------------|
| 1 | **MicroModelEnricher** | `micro_model.py` | ONNX embeddings (pplx-embed-v1-0.6b), failure classification, artifact enrichment, TF-IDF fallback | ✅ High — could feed AppFlowy AI fields |
| 2 | **Voice Pipeline** | `voice_pipeline/` | ASR (Whisper CUDA) → LLM → TTS (Supertonic 3), conversation memory | ✅ High — voice-to-task creation |
| 3 | **Output Gate** | `output_gate.py` | Subagent validation, verdict extraction, escalation, 5-step Chair gate | ✅ Medium — review finding validation |
| 4 | **State Machine Linter** | `state_linter.py` | 8-check transition graph validation (unreachable states, dead ends, infinite loops, orphaned transitions, asymmetric transitions, retreat paths) | ✅ Medium — pipeline integrity checks |
| 5 | **Fanout Manager** | `fanout.py` | Parallel/sequential tiny council (nemotron-nano, qwen3-4b, granite-tiny), job management, port selection | ✅ Low — internal orchestration |
| 6 | **CodeGraph Store** | `code_graph/store.py` | FTS5 search, call graph traversal (callers/callees), impact analysis, path finding, children/incoming/outgoing edges | ✅ Medium — code review context |
| 7 | **Arc Summarizer** | `arc_summarizer/` | Tiered consolidation (daily/short/weekly/bimonthly), knowledge card injection, Granite-4.1-3B on Arc A380 | ✅ High — session summaries → AppFlowy documents |
| 8 | **MemIndex** | `memory_service/index.py` | Milvus-lite vector indexing, graceful degradation, search with project filtering | ✅ High — semantic search across council + AppFlowy |
| 9 | **Service Health Checker** | `memory_service/health.py` | Supervisor, memory service, arc summarizer, memsearch, SSE sessions, web search health checks | ✅ Medium — monitoring dashboard |
| 10 | **DbIndexPoller** | `memory_service/db_poller.py` | Channel A: polls SQLite for unindexed rows → Milvus | ✅ Medium — auto-index council data |
| 11 | **DocFileWatcher** | `memory_service/file_watcher.py` | Channel B: watches doc directories → Milvus on change | ✅ Medium — auto-index AppFlowy documents |
| 12 | **Consolidation Tiers** | `store.py` | Daily, short (3d), weekly (7d), bimonthly (15d) consolidation with TTL phases | ✅ Medium — AppFlowy calendar views |
| 13 | **Injection Blacklist** | `store.py` | Pattern-based content filtering for knowledge card injection | ✅ Low — internal safety |
| 14 | **Failure Classifications** | `micro_model.py` | Embedding-based + pattern-based failure classification with confidence scores | ✅ High — AppFlowy severity triage |
| 15 | **Event Window Summaries** | `store.py` | Temporal event aggregation with structured summaries | ✅ Medium — AppFlowy timeline views |
| 16 | **Artifact Summaries** | `store.py` | Enrichment data (summary, tags, keywords) LEFT JOINed with artifacts | ✅ Medium — AppFlowy row metadata |
| 17 | **Session Diary** | `store.py` | Structured memory with sections (decisions, open_items, work_completed) | ✅ High — AppFlowy document sync |
| 18 | **Raw Session Memories** | `store.py` | Mechanical upsert with provenance traceability (trace-*, sess-*, consol-* prefixes) | ✅ Medium — audit trail |
| 19 | **Translation Table** | `store.py` | task_id → pipeline_id mapping (replaced by work_items in migration) | ❌ Replaced by work_items |
| 20 | **Audit Events** | `store.py` | Structured audit trail (endpoint, method, status, write boundary, gate validity, bypass tracking) | ✅ High — AppFlowy audit database |
| 21 | **Binary Hash Tracker** | `super_council.py` | Slot invalidation on llama-server binary change | ❌ Internal only |
| 22 | **Slot Store** | `super_council.py` | Model binary management (write/read meta, cleanup duplicates, slot files) | ❌ Internal only |
| 23 | **Model Registry** | `super_council.py` | Alias resolution, config management, upstream grouping, swap target resolution | ❌ Internal only |
| 24 | **Upstream Process** | `super_council.py` | llama-server management (start/stop/health/restart/crash detection) | ❌ Internal only |
| 25 | **Slot Client** | `super_council.py` | HTTP client for upstream (save/restore slot, health, metrics) | ❌ Internal only |
| 26 | **CouncilMemory** | `super_council.py` | Daily markdown logging (chat, delegation, swap, compaction detection) | ✅ Medium — AppFlowy log database |
| 27 | **MCP Server** | `memory_service/mcp_server.py` | FastMCP tools + resources (stdio + SSE transport, 22 tools, 7 resources) | ✅ High — AppFlowy AI integration |
| 28 | **MCP Client** | `mcp_client.py` | Sync MCP client for Pi agent (background event-loop thread) | ❌ Internal only |
| 29 | **HTTP Endpoints** | `memory_service/http_endpoints.py` | REST API for council (health, status, metrics, chat, delegate, fanout, chain, pipeline, recall, index, summarize, restart) | ✅ High — AppFlowy webhook target |
| 30 | **Voice Pipeline Config** | `voice_pipeline/config.py` | ASR, TTS, LLM configuration | ✅ Medium — voice task creation |
| 31 | **Voice Memory Integration** | `voice_pipeline/memory_integration.py` | Conversation history integration with memory layer | ✅ Medium — voice session tracking |
| 32 | **Summarizer Server** | `summarizer/server.py` | External summarization endpoint | ✅ Medium — AppFlowy document summarization |
| 33 | **Idle Window Scheduler** | `arc_summarizer/scheduler.py` | Adaptive background consolidation (CPU-aware, health-gated, pyramid order) | ✅ Medium — AppFlowy auto-updates |
| 34 | **Log Parsers** | `memory_service/log_parsers.py` | Structured log parsing for unified recall | ✅ Low — internal |
| 35 | **Memory Config** | `memory_service/config.py` | Memsearch, MCP, validation, tier max chars, recency weighting | ✅ Medium — shared config |

### AppFlowy Features: Available but NOT in Analysis Draft

| # | Feature | Module | Description | Integration Potential |
|---|---------|--------|-------------|----------------------|
| 1 | **Field Type Options** | `flowy-database2/type_option_entities/` | Checkbox, Checklist, Date (format/time), Media (file types), Number (format), Relation (linked rows), Select (single/multi, colors), URL, Time, Translate, Rich Text | ✅ High — council field mapping |
| 2 | **Board Layout** | `flowy-database2/board_entities.rs` | Kanban board with groups, drag-drop, column settings | ✅ High — pipeline status board |
| 3 | **Grouping** | `flowy-database2/group_entities/` | Database row grouping by field value (configuration, changeset) | ✅ High — group by severity, reviewer, project |
| 4 | **Sorting** | `flowy-database2/sort_entities.rs` | Multi-field sorting with direction | ✅ Medium — sort by priority, date, status |
| 5 | **Notifications** | `flowy-notification/` | Event-driven notifications with debouncing, payload support, subject pattern | ✅ High — pipeline event notifications |
| 6 | **Document Management** | `flowy-document/` | Block-based editor, JSON parsing, external format import, document snapshots, sync state | ✅ High — session summaries, architectural decisions |
| 7 | **Full-Text Search** | `flowy-search/` | Tantivy-based FTS, local + cloud search handlers, search filters, result ranking | ✅ High — unified search across council + AppFlowy |
| 8 | **SQLite Vector** | `flowy-sqlite-vec/` | SQLite vector extension, embedded documents, fragments, pending index queue | ✅ High — semantic search alternative to Milvus |
| 9 | **Cloud Sync** | `flowy-server/af_cloud/` | Database, document, search, file storage, folder, user sync with AppFlowy Cloud | ✅ Medium — multi-device council access |
| 10 | **Local Server** | `flowy-server/local_server/` | Template management, workspace creation, local database operations | ✅ Medium — offline council operations |
| 11 | **AI Chat Chains** | `flowy-ai/chat/chains/` | ConversationalRetrieverChain (with memory, rephrasing, source documents), RelatedQuestionChain, ContextQuestionChain | ✅ High — council AI assistant |
| 12 | **AI Summary Memory** | `flowy-ai/chat/summary_memory.rs` | Conversation summary memory for context management | ✅ High — council session memory |
| 13 | **AI Multi-Source Retriever** | `flowy-ai/chat/retriever/` | Multi-source retrieval with SQLite vector backend | ✅ High — council recall enhancement |
| 14 | **AI Local Completion** | `flowy-ai/local_ai/completion/` | Local AI completion with chain, stream interpreter, writer | ✅ Medium — council inline completion |
| 15 | **Storage Abstraction** | `flowy-storage/` | Local + cloud storage abstraction, sync state management | ✅ Medium — council data persistence |
| 16 | **Folder Hierarchy** | `flowy-folder/` | Workspace → folder → view hierarchy, folder sync state | ✅ High — council project organization |
| 17 | **Date/Timezone** | `flowy-date/` | Timezone-aware date handling, format conversion | ✅ Medium — council timestamp handling |
| 18 | **Error Types** | `flowy-error/` | Domain-specific error types with flowy result pattern | ✅ Low — internal |
| 19 | **User Management** | `flowy-user/` | Authentication, profile, workspace membership, cloud service integration | ✅ Medium — council user roles |
| 20 | **Collaboration (Collab)** | `collab-integrate/` | Yjs-based real-time collaboration, collab state management | ✅ Medium — multi-user council |
| 21 | **Event Dispatch** | `lib-dispatch/` | Command pattern, event handling, message routing | ✅ Medium — council event system |
| 22 | **Build Tool** | `build-tool/` | Flutter + Rust compilation, FFI generation | ❌ Internal |
| 23 | **Calculation** | `flowy-database2/calculation/` | Database field calculations (sum, count, average, etc.) | ✅ Medium — council metrics |
| 24 | **Share Entities** | `flowy-database2/share_entities.rs` | Database sharing, access control, invite links | ✅ Medium — council collaboration |
| 25 | **File Entities** | `flowy-database2/file_entities.rs` | File attachment management, upload/download | ✅ Medium — council artifact storage |
| 26 | **Position Entities** | `flowy-database2/position_entities.rs` | Row/field positioning, move operations | ✅ Low — internal |
| 27 | **Setting Entities** | `flowy-database2/setting_entities.rs` | Database settings, layout configuration | ✅ Low — internal |
| 28 | **View Entities** | `flowy-database2/view_entities.rs` | Database view management (grid, board, calendar, gallery) | ✅ High — council view customization |
| 29 | **Database Sync State** | `flowy-database2/database_entities.rs` | Sync state tracking, snapshot management | ✅ Medium — council data sync |
| 30 | **Custom Prompts** | `flowy-database2/database_entities.rs` | Custom AI prompts for database operations | ✅ High — council AI customization |

### Integration Opportunities (Cross-System)

| # | Super-Council Feature | AppFlowy Feature | Integration Idea |
|---|----------------------|------------------|------------------|
| 1 | MemIndex (Milvus) | SQLite Vector | Unified vector search: Milvus for council, SQLite vec for AppFlowy, bridge via adapter |
| 2 | CouncilMemory (daily logs) | Notifications | Pipeline events → AppFlowy notifications with debouncing |
| 3 | Arc Summarizer | Document Management | Session summaries → AppFlowy documents with block-based editing |
| 4 | CodeGraph Store | Full-Text Search | Code search (FTS5) + document search (Tantivy) → unified search interface |
| 5 | MicroModelEnricher | AI Chat Chains | Embedding-based enrichment → AppFlowy AI chat with council context |
| 6 | Failure Classifications | Board Layout | Severity triage → AppFlowy Kanban board with auto-grouping |
| 7 | Session Diary | Folder Hierarchy | Structured memory → AppFlowy workspace with project folders |
| 8 | Audit Events | Share Entities | Audit trail → AppFlowy shared database with access control |
| 9 | Voice Pipeline | AI Summary Memory | Voice-to-task creation with conversation memory |
| 10 | State Machine Linter | Notifications | Pipeline integrity violations → AppFlowy notifications |
| 11 | Consolidation Tiers | Calculation | Tier metrics → AppFlowy database calculations |
| 12 | Event Window Summaries | View Entities | Timeline views → AppFlowy calendar/gallery views |
| 13 | MCP Server | Custom Prompts | MCP tools → AppFlowy AI with council-specific prompts |
| 14 | HTTP Endpoints | Cloud Sync | REST API → AppFlowy cloud sync for multi-device access |
| 15 | Idle Window Scheduler | Database Sync State | Background consolidation → AppFlowy sync state updates |

### Feature Coverage Summary

| Category | In Draft | Available | Gap |
|----------|----------|-----------|-----|
| **Council Core** | 10/35 | 25 not covered | 71% gap |
| **AppFlowy Core** | 4/30 | 26 not covered | 87% gap |
| **Cross-System** | 0/15 | 15 opportunities | 100% gap |

**Key gaps (high-priority integration opportunities):**
1. **AI integration** — AppFlowy's AI chat chains, summary memory, multi-source retriever not considered
2. **Vector search** — AppFlowy's SQLite vector vs council's Milvus — could be unified
3. **Notifications** — AppFlowy's event-driven system could replace council's polling
4. **Document management** — AppFlowy's block-based editor for session summaries
5. **Full-text search** — AppFlowy's Tantivy vs council's FTS5 — could complement
6. **Voice pipeline** — council's ASR→LLM→TTS not considered for task creation
7. **MicroModelEnricher** — ONNX embeddings for failure classification not mapped to AppFlowy
8. **Audit trail** — council's structured audit events not mapped to AppFlowy
9. **Cloud sync** — AppFlowy's sync for multi-device council access
10. **Folder hierarchy** — AppFlowy's workspace organization for council projects

---

## Options:
- **A.** Full refactor as described — SQLAlchemy models, domain services, PostgreSQL backend, migration in phases
- **B.** Lighter refactor — keep RelationalStore but add council-domain methods on top (less invasive, less clean)
- **C.** Defer — do the migration plan as-is (SQLite), add PostgreSQL later as separate effort
- **D.** Extended analysis — incorporate gap features (AI integration, vector search unification, notifications, voice pipeline, audit trail)

Which direction? I can draft the full SQLAlchemy models + domain services (option A), or expand the analysis to cover the gap features (option D), or refine whichever you prefer.
