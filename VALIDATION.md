# Validation record

The current release candidate passed:

- **46 backend/model integration tests**, including backup/idempotent initialization, ranking without the original dataset file, malformed/duplicate/UTF-16 input rejection, nullable fields, gzip files, atomic rollback, cross-job ranking invalidation, authentication, restart-status recovery, CLI submission format, job-specific ranking and small-corpus similarity.
- **Six Chromium browser tests against the built production container with authentication enabled**: recruiter workflow, JSONL upload → persisted profiles → ranking, actual feature rendering, invalid-upload consistency, persistent API errors, and mobile/direct routes.
- **Container build and fresh startup**, including a deliberately root-owned mounted volume and verification that PID 1 runs as UID 10001.
- **Production-image smoke checks** for authentication, two-candidate ranking, consistent SQLite backup with integrity check, and identical ranking results after a container restart.
- `run.sh` dependency installation, frontend build, fresh database initialization, demo ranking and server startup.
- Docker Compose configuration validation and source whitespace checks.

The image-level checks are reproducible with `scripts/verify_container.py`; the CI configuration includes backend/browser and container jobs. Those jobs have been prepared locally; a remote GitHub Actions run has not been claimed.

These checks use fictional/sample data and a local Docker host. They do not establish ranking quality or resource requirements for the missing full 100K-candidate dataset, a production SLA, or a published hosting deployment. The included Render Starter plan is a small-demo starting point. Load-test representative data and size memory/storage before a large deployment.

The earlier automatic approval-service usage error no longer blocks validation; the previously pending checks have now executed successfully.
