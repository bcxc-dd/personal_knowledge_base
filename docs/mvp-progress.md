# MVP execution ledger

Plan: docs/superpowers/plans/2026-09-19-rag-mvp.md

- User authorized implementation of v0.2. Native execution in current empty workspace.
- No repository exists; no worktree or automatic commit needed.
- Interface preflight: parser -> ingestion -> Chroma -> chat references all use stable document ID / chunk ID / location; frontend uses the API DTOs.
- User selected DeepSeek. Default local BGE embeddings avoid requiring a second key. DeepSeek key configured by user in the local UI during implementation; no secrets printed.
- Task 1: complete. Parser RED→GREEN for Chinese boundaries, empty input, DOCX tables, corrupt PDF; SQLite and ingestion tested.
- Task 2: complete. Real Chroma indexing, scope filtering, deletion, model fingerprint mismatch, missing config, answer citations and persisted history tested using controlled HTTP providers.
- Task 3: complete. Four responsive React pages, typed API and SSE client; build and front-end event tests passed. Browser uploaded sample.md and real local model generated 512-dimensional vectors.
- Review: independent read-only reviewer found cancellation stall, silent mixed-PDF page loss, and missing replacement history. Added regressions and fixed cancellation using async HTTP streaming; PDF empty extraction now reports pages and fails explicitly.
- Ruling: full document versions remain outside this MVP. Same-name changed content is rejected with explicit guidance to delete old version or rename; prevents accidental mixing of revisions. Cost: no seamless replacement or history restoration.
- Ruling: character chunking reduced to 400 with 60 overlap for BGE input headroom; embedding fingerprint bumped so prior indexes require rebuild. Existing documents are preserved and reindexed locally.
- Windows integration fix: registry mapped .js to text/plain, preventing module execution. Explicit JS/CSS MIME overrides added with a regression test.
- Ruling: single in-process worker instead of a separate process keeps Chroma ownership simple. Cost: one server process only, no multi-worker scaling.
- Ruling: local server-bound static assets and sample document download replace the need for two user-facing development servers; front-end routes are lazy-loaded.
- User's uploaded files and existing DeepSeek settings preserved during service update. Real backend network-disconnect regression passed.
- Task 4: complete. Setup/start scripts and README delivered. 19 backend tests + 2 frontend tests pass; production build passes with route splitting. Two test-dependency deprecation warnings remain (httpx TestClient / anyio alias), no functional failures.
- Real local BGE embedding + Chroma query verified in a separate process; stopped-process data copied and restored in a second process, retrieval correct. Evidence command: `.venv/Scripts/python scripts/verify_local.py`.
- Browser real-provider acceptance: sample.md uploaded, answered prototype review time and owner correctly with citation [2]; selecting reference reveals exact source paragraph. Follow-up about budget explicitly states insufficient information with citation [3]. DeepSeek key and user's existing PDFs untouched.
- Desktop and narrow-browser layouts inspected; temporary viewport override reset. Original paper PDFs successfully reindexed with smaller chunks; no original file deleted.
- Final scope: no account/auth, OCR, document version history, full export UI, or pgvector yet. Manual stopped-process backup is documented and verified. Missing extraction pages fail visibly; updates use delete/reupload rather than silent revision mixing.
