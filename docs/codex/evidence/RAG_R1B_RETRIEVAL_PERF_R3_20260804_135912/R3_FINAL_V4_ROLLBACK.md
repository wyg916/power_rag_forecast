# RAG-R1B Retrieval Performance R3 Rollback

- Starting point: `63fc9fc67172681665e97dbf71e54cf1d617a9a4`.
- Revert the independent R3 commit with a normal `git revert <R3_COMMIT>` if the controller rejects it.
- No database rollback is required: database writes were zero.
- No Qdrant rollback is required: collection writes were zero and collection identity remained unchanged.
- No alias, snapshot, release, or publication rollback is required because none of those actions occurred.
- Runtime embedding caches and raw matrices are ignored evidence artifacts and are not part of the commit.
- Do not merge, cherry-pick, rebase, publish, or switch alias from this branch.
