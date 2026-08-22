# Redacted real-provider summary

- MiMo general: PASS, HTTP 200, non-empty content and usage.
- MiMo Vision: PASS, `mimo-v2.5`, PNG data URL, HTTP 200, non-empty content, visible red/blue evidence found.
- DeepSeek: final 6/6 AnalysisPlan scenarios PASS; every raw structure was a valid JSON object without fence/envelope/alias drift; no repair or fallback.
- Kimi: explicit Premium PASS; the unconfirmed Premium request was denied locally and caused no remote call.

Structured evidence is in `provider_remediation_smoke.json` and `deepseek_analysis_plan_final.json`. They contain request/response structure, request IDs, model, MIME, finish reason, tokens, latency and safe errors only. API keys, Prompt bodies, answer bodies and image bytes are absent.

The initial file intentionally preserves the two DeepSeek semantic misses found during diagnosis. The DeepSeek-only final file is the authoritative post-fix result; already-passing MiMo/Kimi calls were not repeated.
