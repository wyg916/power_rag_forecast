# DAY6 ChatBI Semantic Analysis MVP

## Baseline

- Branch: `codex/day6-chatbi-semantic-analysis-mvp`
- Starting SHA: `0380f4cbc8e2685dd89572dfa0b678cf7b533a05`
- Starting Alembic head: `0021_memory_lifecycle_v1`
- Five packages execute serially on the same branch; each requires its own checkpoint, tests, evidence, commit, and clean Git state.

## Package chain

1. Catalog, AnalysisPlan, Validator, and the only planned migration.
2. Query Compiler plus Group/Time, Comparison, Ranking, Contribution, Drill Down, and whitelist Join.
3. Result Dataset, ChartSpec, Narrative, API, and complete identity/security propagation.
4. Reuse Enterprise Memory for multi-turn context and connect the existing Assistant page.
5. Freeze and run Golden 50, execute the unified regression matrix, close documentation, and perform RC convergence.

## Non-negotiable boundaries

- Formal execution is `LLM -> AnalysisPlan -> Validator -> Query Compiler -> PostgreSQL`.
- LLM SQL, arbitrary SQL, frontend SQL, unregistered metrics/dimensions/joins, and frontend business-data fallback are forbidden.
- Current question facts override remembered context; no second memory subsystem may be created.
- Chart, table, and narrative must share the same AnalysisPlan and Result Dataset hash.
- Cross-user and cross-tenant leakage must remain zero.
- Package failure stops the chain; no failure may be deferred into a later package.
- No remote push, production deployment, model activation, or RAG production alias change is authorized.

## Package 1 contract

- Freeze executable semantic catalogs against real Dataset Registry fields.
- Reject unknown fields and extra payload keys fail-closed.
- Add `0022_chatbi_semantic_v1` only for catalog snapshots and tenant-scoped AnalysisPlan audit records.
- Verify upgrade, downgrade, re-upgrade, unique head, protected row counts, and no unexplained writes.
