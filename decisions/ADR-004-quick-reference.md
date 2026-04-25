# ADR-004 Quick Reference — LLM Integration for K-Team

## At-a-Glance

| Use Case | Recommended Model | VRAM | Key Action |
|----------|------------------|------|------------|
| Chat bot | Qwen3.6-35B-A3B (existing) | 12GB | Create kteam_ai Django app |
| Invoice OCR | Qwen2.5-VL-7B-Instruct | 14GB | Download GGUF, serve on port 11436 |
| Product classification | Qwen2.5-7B-Instruct | 5GB | Fast JSON output |
| Financial analysis | DeepSeek-R1-Distill-Qwen-32B (existing) | 18GB | Use port 11435 |
| Report generation | Qwen3.6-35B-A3B (existing) | 12GB | Long-form text gen |
| RAG embeddings | Qwen3-Embedding-0.6B (existing) | <1GB | TEI on port 6006 |

## VRAM Budget (RTX 3090, 24GB)

| Scenario | VRAM Used | Feasible |
|----------|-----------|----------|
| Qwen3.6-35B-A3B + DeepSeek-R1-32B | ~30GB | NO - must run on separate ports/instances |
| Qwen3.6-35B-A3B only | ~12GB | YES - leaves 12GB headroom |
| Qwen3.6-35B-A3B + Qwen2.5-VL-3B | ~18GB | YES - VL model on separate port |
| Qwen3.6-35B-A3B + Qwen2.5-VL-7B | ~26GB | NO - VL model needs separate GPU or CPU offload |

## Implementation Phases

### Phase 1 (Weeks 1-2): Chat Bot
- Create `kteam_ai` Django app
- Chat API + conversation history
- React chat component in staff portal
- ~22 hours effort

### Phase 2 (Weeks 3-6): Invoice Scanning
- Download Qwen2.5-VL-7B-Instruct GGUF
- Set up VL serving (port 11436)
- Invoice extraction API + review UI
- ~45 hours effort

### Phase 3 (Weeks 7-12): Automations
- RAG integration, classification, reports
- Anomaly detection, bulk validation, SMS gen
- ~60 hours effort

## Key Files Created

- `/home/chief/llm-wiki/decisions/ADR-004-llm-integration-assessment.md` — Full assessment
- `/home/chief/llm-wiki/decisions/ADR-004-quick-reference.md` — This file
- `/home/chief/llm-wiki/index.md` — Updated with ADR-004 link

## Critical Integration Points

1. **Django app**: `kteam_ai/` with views, services, tools, models, middleware
2. **llama.cpp ports**: 11434 (fast), 11435 (reasoning), 11436 (vision)
3. **Existing databases**: PostgreSQL (chat history), MongoDB (product/invoice data)
4. **Existing search**: MeiliSearch (frontend), RAGFlow/Elasticsearch (RAG)
5. **Existing auth**: Knox token authentication protects all LLM endpoints
