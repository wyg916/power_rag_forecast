# Unresolved / Integration dependencies

No C code or real-provider blocker remains.

1. Final Integration runs B frontend typecheck/lint/test/build and attachment UI E2E on the merged SHA.
2. Final Integration resolves ownership of existing 8000/5173 processes; C did not terminate them.
3. Database-dependent failures use the restricted Day3 isolated-schema runner; T002 model-contract errors wait for A-owned admitted model assets.
