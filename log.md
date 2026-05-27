# Central Wiki Operation Log

## [2026-05-17] audit | architectural constitution alignment audit completed
- Performed alignment audit between Architectural Constitution (stable) and Integration/Identity Plans.
- Identified three key gaps: Wallet binding, MongoDB naming skew, and F&B direct dual-write concurrency.
- Created [[alignment_audit.md]] to document findings and foolproof guidelines.
- Created local ADR-006 at `kteam-dj-chief/wiki/decisions/ADR-006-alignment-audit.md` to resolve issues.
- Updated local wiki index and log.
- Sources: users/models.py, domains/cafe_arcade/views.py, ~/llm-wiki/Kung_OS/architecture/

## [2026-05-17] ingest | legacy e-commerce codebase audit completed
- Conducted deep code audit of the legacy Kuro Gaming backend (`kuro-gaming-dj-backend`) for e-commerce.
- Isolated business logic including: Cart/Wishlist models, Immutable Address pattern, Custom PC presets copying in MongoDB, and local QR code generation.
- Exposed critical cross-store order-to-procurement webhook conversion logic and payment validation gaps.
- Created [[eshop_legacy_review.md]] to document findings.
- Created local ADR-007 at `kteam-dj-chief/wiki/decisions/ADR-007-eshop-reconciliations.md` to resolve issues.
- Updated local wiki index and log.
- Sources: kuro-gaming-dj-backend:accounts/, orders/, payment/, products/

## [2026-05-18] plan | subagent llm council and memsearch integration plan completed
- Formulated the strategic architecture for running a multi-model LLM Council and MemSearch pipeline on a single RTX 3090 GPU (Ryzen 7 7700, 96GB RAM).
- Defined isolated subagent role configurations (Scout, Planner, Builder, Reviewers, Security, UAT) to resolve token bloat and context pollution.
- Documented TDD-gated development, checkpoint resuming, and sequential slot persistence swapping in [[subagent_council_integration.md]].
- Registered hardware benchmarks, compression mode compile speeds, and asymmetric KV cache tunings (q8_0/turbo4).
- Sources: ~/llm-wiki/Local-Hardware.md, ~/llm-wiki/council-architecture.md, ~/llm-wiki/SuperMemory.md

