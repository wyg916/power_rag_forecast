# C AI Runtime release plan

Task: `PROJECT1_V2_12_C_AI_RUNTIME_ATTACHMENTS_STARTUP_QUALITY`

1. Preserve the existing JWT/RBAC -> intent -> AnalysisPlan/tool/RAG/attachment -> deterministic data access -> grounded answer -> trace/citation chain.
2. Centralize five logical model aliases and enforce explicit Premium consent with at most one non-Premium fallback.
3. Add session-scoped attachment validation, parsing, ownership/tenant checks, prompt-injection treatment, citations, TTL, and deletion without enterprise-KB publication.
4. Complete route/usage/error trace fields and capability/page-context guards.
5. Add one-console runtime control and a minimum offline CI quality gate.
6. Run focused contract/security/startup tests, then current backend regression that is proportionate to the branch.

No frontend, prediction engine, model ops, model activation, RAG production alias, database migration, or production key change is in scope.
