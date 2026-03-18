# Production Readiness

This document tracks the release hardening gates. **0.3.0 has shipped. 0.4.0 in progress (WS session resumption).** Gates 0–3 are implemented. Gates 4–6 define the ongoing release bar for future RCs.

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
- Cloudflare JWT requires `sub`, `exp`, `iat`, `nbf` and uses bounded clock skew. (**Note**: FastAPI reduced its required claims to `["sub", "exp"]` for IdP compatibility; CF still requires all four — a known parity gap, tracked for resolution.)
- Page-route auth cookies now set explicit `HttpOnly`, `SameSite=Lax`, and `Secure` policy.
- Cloudflare hijack lease values are validated and clamped at HTTP entrypoints.

Known gaps:
- FastAPI hosted page routes do not yet bridge bearer-auth JWTs into `token_cookie`.
  The initial HTML request can succeed in `jwt` mode while subsequent browser
  `/api/...` requests fail unless an auth proxy keeps injecting `Authorization`
  headers.

## Gate 2 (P0): Cross-Backend Protocol Parity

Decision:
- Public hijack control contract is capability-driven:
  - FastAPI: WS hijack control (`hijack_control=ws`)
  - Cloudflare: REST hijack control (`hijack_control=rest`)

Implemented:
- Both backends now advertise capabilities in WS `hello`.
- Cloudflare includes REST `step` route.
- Frontend hijack widget dynamically chooses WS or REST control by handshake.

Implemented (0.4.0 addition):
- WS session resumption parity: both backends issue resume tokens in `hello`,
  accept `{"type":"resume","token":"…"}` frames, rotate tokens on success, and
  restore role + hijack ownership. CF uses DO SQLite; FastAPI uses pluggable
  `ResumeTokenStore` (default: `InMemoryResumeStore`).
- Protocol matrix updated: see `docs/protocol-matrix.md`.

Known gaps:
- Cloudflare and FastAPI are not yet identical in every hijack REST edge case.
  Route names and capability negotiation match, but validation and security
  semantics still need periodic parity review.

## Gate 3 (P1): Packaging and Runtime Artifact Integrity

Implemented:
- Startup validation fails fast if required frontend assets are missing.
- `MANIFEST.in` includes required frontend assets and prunes transient runtime artifacts.
- `scripts/verify_package_artifacts.py` validates wheel/sdist required files.

## Gate 4 (P1): Performance, Scalability, Resilience

Required per RC before promotion:
- Load profile for concurrent browser sockets, reconnect churn, and snapshot throughput.
  - `scripts/load_profile.py` — connect/hello latency measurement.
  - `scripts/latency_probe.py` — snapshot fetch and command send latency.
  - Initial 0.1.0 baselines in `artifacts/soak/` (captured 2026-03-05).
- Failure-injection scenarios: worker disconnect/restart, upstream WS flap, latency spikes.
  - `scripts/failure_injection.py` — restart churn harness.
- SLO targets: see `docs/operations/slo.md`.

## Gate 5 (P1): Observability and Incident Readiness

Implemented:
- Structured logs with correlation IDs: request/session/worker/hijack.
  - HTTP via `x-request-id` middleware logging and `/api/metrics`.
- Metrics: auth failures, hijack conflicts, lease expiries, disconnect reasons, reconnect counters.
- Alert thresholds and on-call runbook: `docs/operations/runbook.md`.

## Gate 6 (P2): Supply Chain and Release Governance

Required per RC before promotion:
- Dependency vulnerability policy gate (fail on high/critical).
- SBOM generation for release artifacts.
- Artifact signing and provenance metadata.
- Staging rollback drill with documented result.
  - Governance automation: `scripts/release_governance_check.sh`.
