# undef-terminal: Handoff

## Current State

- **Main package (`undef-terminal`)**: 1082+ tests passing. `undef.terminal.server` at **99% coverage**. Pre-commit hooks active (ruff, mypy, ty, bandit).
- **CF package (`undef-terminal-cloudflare`)**: **208 unit tests passing** + E2E tests (`-m e2e`). Package at **79% total coverage**. Key module coverage: `bridge/hijack.py` 100%, `state/registry.py` 100%, `api/http_routes.py` 99%, `do/session_runtime.py` 82%, `entry.py` 89%.

---

## Completed in Most Recent Sessions

### Main Package — Server Coverage Push (98% → 99%)

Added 5 new test files covering `undef.terminal.server`:

| File | What it covers | Coverage gain |
|---|---|---|
| `tests/test_server_auth.py` | `auth.py`: JWT decode, bearer extraction, cookie handling, JWKS cache | 77% → 99% |
| `tests/test_server_runtime.py` | `runtime.py`: `_bridge_session` branches, `_run` error paths, backoff | 86% → 99% |
| `tests/test_server_authorization.py` | `authorization.py`: capability checks, visibility rules, browser role | 90% → 99% |
| `tests/test_server_registry.py` | `registry.py`: `_require_session`, `list_sessions`, recording entries | 88% → 99% |
| `tests/test_server_coverage2.py` | `routes/api.py`: 403/404/409/422 paths; `app.py`: CORS, 5xx metric | 88% → 99% |

Remaining 20 lines (1%) are legitimate integration-only paths:
- `runtime.py`: WS reconnect backoff reset requires a live WS connection
- `auth.py`: JWKS cache edge case (triggered only at cache capacity + concurrent access)
- `registry.py`: Recording file blank-line branches (covered in tail/offset modes)
- `routes/api.py`: Race-condition KeyError paths on PATCH and quick-connect

### CF Package — Coverage Improvements

New file `tests/test_coverage2.py`:
- `bridge/hijack.py`: **93% → 100%** (heartbeat/release edge cases, `can_send_input` when none)
- `state/registry.py`: **78% → 100%** (KV delete/put/list/get failure paths, empty key_name skip)
- `auth/jwt.py`: **60% → 78%** (empty sub, string roles, non-iterable roles, JWKS no-match)
- `state/store.py`: **67% → 74%** (`clear_lease`, `save_input_mode`, `min_event_seq`)

Remaining gaps in `do/session_runtime.py` (23%) and `entry.py` (38%) require the actual Cloudflare runtime — covered by E2E tests only.

### CF Package — Full-Stack E2E Tests (`test_e2e_full_stack.py`)

Tests `HostedSessionRuntime` (Python) → CF DO (WS) → Browser WS proxy chain:

| Test | Markers | What it verifies |
|---|---|---|
| `test_hosted_runtime_connects_and_appears_in_sessions` | `@e2e` | Runtime connects, status().connected == True, appears in /api/sessions |
| `test_hosted_runtime_snapshot_reaches_browser` | `@e2e` | Browser WS receives snapshot from shell connector |
| `test_hosted_runtime_hijack_cycle` | `@e2e` | Acquire hijack, GET snapshot, release while runtime live |
| `test_two_browsers_receive_same_snapshot` | `@e2e @real_cf` | Two browsers both receive worker snapshot broadcast |
| `test_state_persists_after_do_hibernation` | `@real_cf @slow` | SQLite snapshot survives ~40s DO hibernation cycle |

Run:
```bash
E2E=1 uv run pytest tests/test_e2e_full_stack.py -v
REAL_CF=1 REAL_CF_URL=https://undef-terminal-cloudflare.neurotic.workers.dev uv run pytest tests/test_e2e_full_stack.py -v
```

### Shell Connector + Quick-Connect (earlier sessions)
- `demo` → `shell` rename: `ShellSessionConnector` in `connectors/shell.py`
- Quick-connect: `GET /connect` page + `POST /api/connect` for ephemeral sessions
- `SessionDefinition.ephemeral` field; auto-deleted on last browser disconnect

### CF Package — All Items Complete (earlier sessions)
- Item 1 (Fleet KV), Item 2 (E2E), Item 3 (CF Access JWT), Item 4 (Alarm expiry), Item 5 (Snapshot endpoint)
- All hibernation bugs fixed in `do/session_runtime.py`

---

## Test Commands

```bash
# Main package (all non-playwright)
uv run pytest tests/ --ignore=tests/test_zzz_playwright_hijack.py -q

# Main package coverage
uv run pytest tests/ --ignore=tests/test_zzz_playwright_hijack.py --cov=undef.terminal.server --cov-report=term-missing -q

# CF package unit tests
cd packages/undef-terminal-cloudflare
uv run pytest tests/ --ignore=tests/test_e2e_*.py --ignore=tests/test_e2e_playwright_proxy.py -q

# CF E2E (pywrangler dev, ~90s startup)
E2E=1 uv run pytest tests/ -m e2e -v

# CF E2E (real CF deployment)
REAL_CF=1 REAL_CF_URL=https://undef-terminal-cloudflare.neurotic.workers.dev uv run pytest tests/ -m e2e -v

# CF hibernation test (slow, real CF only)
REAL_CF=1 SLOW=1 REAL_CF_URL=https://... uv run pytest tests/test_e2e_full_stack.py::test_state_persists_after_do_hibernation -v -s
```

---

## Next Steps

### 1. Release Prep
- **CHANGELOG.md**: Update test count (1082 main + 82 CF = 1164+ total) and coverage (99% server)
- **README.md**: Update feature list to include quick-connect, shell connector, CF Access JWT
- **Version bump**: Set `pyproject.toml` version to `0.1.0` and publish to PyPI

### 2. CF Package — Remaining Coverage
- `do/session_runtime.py` (82%) — remaining 18% = CF-runtime-only paths (WebSocketPair import, JS fetch, fallback imports). No unit test path.
- `entry.py` (89%) — remaining 11% = CF-runtime-only fallback imports (lines 12-17).
- `state/store.py` (74%) — remaining gaps are SQLite-level error branches (connection errors, malformed rows).
- `api/http_routes.py` (**99%**) — fully covered by unit tests.

### 3. Quick-Connect UX Polish
The `GET /connect` page is minimal (inline JS form). Could be enhanced with:
- Session type selection (shell / telnet / SSH)
- Display name / tag input
- Auto-redirect to new session URL on creation

### 4. CF Access JWT — Groups-Based Role Mapping
`JWT_DEFAULT_ROLE` gives all CF Access users the same role. For fine-grained access:
1. Configure SCIM / CF Access identity groups in Zero Trust dashboard
2. Add a custom claim (e.g. `"groups"`) to the CF Access application
3. Set `JWT_ROLES_CLAIM=groups` so the worker reads roles from that claim

### 5. Main Package `ty` Backlog
`ty check src/undef/` passes clean. If new type errors appear, they are CI-blocking for release.
