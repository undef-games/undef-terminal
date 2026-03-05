# Production Readiness Pass 2

This document tracks the ordered release hardening gates for the release candidate.

## Gate 0 (P0): Freeze and Reproducible Baseline

- Pin and capture:
  - Python version (`python --version`)
  - `uv` version (`uv --version`)
  - Playwright browser versions (`uv run playwright --version`)
  - OS image (`uname -a`)
- Generate immutable baseline artifacts with `scripts/capture_rc_baseline.sh`.
- Branch policy:
  - No direct deploy from `main`.
  - Release candidates are cut from `rc/*` and tagged (`vX.Y.Z-rcN`) before promotion.

Exit criteria:
- Clean checkout reproduces the saved pass/fail matrix.

## Gate 1 (P0): Auth and Session Security

Implemented:
- Cloudflare `AUTH_MODE` defaults to `jwt` and rejects `dev`/`none` in production.
- Query-string token auth is disabled by default in production.
- Cloudflare JWT requires `sub`, `exp`, `iat`, `nbf` and uses bounded clock skew.
- Page-route auth cookies now set explicit `HttpOnly`, `SameSite=Lax`, and `Secure` policy.
- Cloudflare hijack lease values are validated and clamped at HTTP entrypoints.

## Gate 2 (P0): Cross-Backend Protocol Parity

Decision:
- Public hijack control contract is capability-driven:
  - FastAPI: WS hijack control (`hijack_control=ws`)
  - Cloudflare: REST hijack control (`hijack_control=rest`)

Implemented:
- Both backends now advertise capabilities in WS `hello`.
- Cloudflare includes REST `step` route.
- Frontend hijack widget dynamically chooses WS or REST control by handshake.

## Gate 3 (P1): Packaging and Runtime Artifact Integrity

Implemented:
- Startup validation fails fast if required frontend assets are missing.
- `MANIFEST.in` includes required frontend assets and prunes transient runtime artifacts.
- `scripts/verify_package_artifacts.py` validates wheel/sdist required files.

## Gate 4 (P1): Performance, Scalability, Resilience

Required before release:
- Load profile for concurrent browser sockets, reconnect churn, and snapshot throughput.
  - Use `scripts/load_profile.py` for reproducible connect/hello latency measurement.
  - Latest local baseline: `artifacts/soak/local-load-profile-20260305-113438.txt`.
  - WS snapshot/input latency probe: `scripts/latency_probe.py` (run on staging candidate build).
  - Latest local latency probe: `artifacts/soak/local-latency-probe-20260305-122728.txt`.
- Failure-injection scenarios:
  - worker disconnect/restart
  - upstream WS flap
  - latency spikes
  - Restart churn harness: `scripts/failure_injection.py`.
  - Latest local restart-churn baseline: `artifacts/soak/local-failure-injection-20260305-115436.txt`.
- Publish SLOs:
  - snapshot latency p95/p99
  - command round-trip p95/p99
  - reconnect time p95/p99

## Gate 5 (P1): Observability and Incident Readiness

Required before release:
- Structured logs with correlation IDs: request/session/worker/hijack.
  - Implemented for HTTP via `x-request-id` middleware logging and `/api/metrics`.
- Metrics: auth failures, hijack conflicts, lease expiries, disconnect reasons, reconnect counters.
- Alert thresholds and on-call runbook with concrete triage queries.
  - See `docs/operations/runbook.md`.

## Gate 6 (P2): Supply Chain and Release Governance

Required before release:
- Dependency vulnerability policy gate (fail on high/critical).
- SBOM generation for release artifacts.
- Artifact signing and provenance metadata.
- Staging rollback drill with documented result.
  - Governance automation entrypoint: `scripts/release_governance_check.sh`.
