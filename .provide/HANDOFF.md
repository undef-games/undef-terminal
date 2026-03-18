# undef-terminal: Handoff

## Current State

- **Main package (`undef-terminal`)**: **~2060 tests passing** (excl. Playwright). **100% branch coverage** (5121 stmts, 1394 branches, 0 missing). Pre-commit hooks active.
- **CF package (`undef-terminal-cloudflare`)**: **469 unit tests passing**. **100% branch coverage** (1536 stmts, 524 branches, 0 missing).
- **Playwright**: **39 tests passing** (4 resume + 4 auto-reconnect + existing hijack/server/example tests).
- **CF E2E**: 14/14 passing against live worker (incl. 4 resume tests).
- **Mutation score**: 67.3% (5972 killed, 2777 survived across 8877 mutants).
- **Both packages at version 0.3.0** — bump to **0.4.0** before release (WS session resumption is a new public API).
- **Dependency**: `undef-telemetry>=0.3` (structured logging via structlog)
- **Branch**: `feat/ws-session-resumption` — not yet merged or pushed to origin.
- **Note**: A separate LLM session is refactoring telnet/SSH proxying code; expect churn in `tests/cli/` and gateway-related tests.

---

## Completed in This Session

### WS Session Resumption

Full implementation of browser WS session resumption across both backends.
When a browser WS drops (CF idle timeout, network blip, mobile backgrounded),
the reconnecting browser can prove it was the same session and reclaim its
role and hijack ownership within a configurable TTL.

**New files:**
- `src/undef/terminal/hijack/hub/resume.py` — `ResumeSession` dataclass, `ResumeTokenStore` Protocol, `InMemoryResumeStore`
- `tests/hijack/test_resume.py` — 18 unit tests for store
- `tests/hijack/test_ws_resume.py` — 19 WS integration tests
- `tests/playwright/test_resume.py` — 4 Playwright E2E tests
- `packages/undef-terminal-cloudflare/tests/test_cf_resume.py` — 20 CF unit tests
- `docs/cf-do-architecture.md` — full DO architecture reference (344 lines)
- `docs/proposal-ws-session-resumption.md` — design rationale

**Modified files:**
- `src/undef/terminal/hijack/hub/core.py` — `resume_store`, `resume_ttl_s`, `on_resume` constructor params
- `src/undef/terminal/hijack/hub/connections.py` — token creation in `register_browser()`, ownership marking in `cleanup_browser_disconnect()`
- `src/undef/terminal/hijack/hub/__init__.py` — exports `InMemoryResumeStore`, `ResumeSession`, `ResumeTokenStore`, `ResumeCallback`
- `src/undef/terminal/hijack/routes/websockets.py` — resume dispatch in message loop
- `src/undef/terminal/hijack/routes/browser_handlers.py` — `_handle_resume()` function
- `packages/undef-terminal-frontend/src/hijack.js` — sessionStorage token persistence, auto-send on reconnect
- `src/undef/terminal/frontend/hijack.js` — compiled output
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/state/store.py` — `resume_tokens` SQLite table + CRUD
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/do/session_runtime.py` — token issuance in browser hello
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/ws_routes.py` — `_handle_resume()` dispatch
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/contracts.py` — `"resume"` frame type in `parse_frame()`
- `packages/undef-terminal-cloudflare/tests/test_e2e_ws.py` — 4 new E2E resume tests

**Deployed to production**: `https://undef-terminal-cloudflare.neurotic.workers.dev`
All 4 CF E2E resume tests pass against live worker.

---

## Documentation Updated

- `docs/cf-do-architecture.md` — new; full DO architecture with Mermaid diagrams
- `docs/protocol-matrix.md` — added session resumption section
- `docs/production-readiness-pass2.md` — version updated to 0.3.0/0.4.0, Gate 2 notes resumption parity
- `README.md` — highlights updated (resumption, 2000+ tests)
- `packages/undef-terminal-cloudflare/README.md` — WS session resumption in key features

---

## Test Commands

```bash
# Main package (100% coverage)
uv run pytest tests/ --ignore=tests/playwright -q

# CF package (100% coverage)
cd packages/undef-terminal-cloudflare && uv run pytest tests/ --no-cov -q

# Playwright (all, incl. resume tests)
uv run pytest tests/playwright/ -v --headed --no-cov -p no:randomly

# CF E2E (production)
REAL_CF=1 REAL_CF_URL=https://undef-terminal-cloudflare.neurotic.workers.dev \
  uv run pytest packages/undef-terminal-cloudflare/tests/test_e2e_wrangler.py \
  packages/undef-terminal-cloudflare/tests/test_e2e_ws.py -v -p no:randomly -p no:xdist --no-cov

# CF E2E (local pywrangler dev — no JWT required)
cd packages/undef-terminal-cloudflare && \
  uv run pywrangler dev --port 8787 &
  E2E=1 uv run pytest tests/test_e2e_ws.py -v -p no:randomly -p no:xdist --no-cov
```

---

## Remaining for Release

- [ ] Version bump: `0.3.0` → `0.4.0` in both `pyproject.toml` files and `VERSION` files
- [ ] `git push` (branch ahead of origin)
- [ ] PR: `feat/ws-session-resumption` → `main`
- [ ] Merge telnet/SSH refactor (separate LLM session in progress — watch `tests/cli/` failures)
- [ ] CHANGELOG.md (optional — all context is in commit messages and proposal doc)
- [ ] CF Access Application in Zero Trust dashboard (browser login redirect for production)
- [ ] Mutation score improvement (67.3% → target TBD; survivors in connectors, CLI, UI, bridge)
- [ ] PyPI publish (`uv build && uv publish`)
