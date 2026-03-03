# undef-terminal: Handoff

## Current State
662 tests passing (99% coverage — 2373 stmts, 16 missed). All quality tools clean (ruff, mypy, bandit).

---

## Completed This Session — Hypothesis Property-Based / Fuzz / Concurrency Tests

### New file: `tests/test_hypothesis_hub.py` (10 tests)

**Category 1: Stateful Testing** — `TermHubStateMachine` (RuleBasedStateMachine)
- Models TermHub as a state machine with 8 rules: add_worker, add_browser, remove_browser, set_input_mode, acquire/release WS/REST hijack, disconnect_worker
- 7 invariants checked after every step: valid input_mode, hijack_owner type, open-mode send permissions, hijack-mode exclusive send, mode-switch rejection during hijack, monotonic event seqs, idle worker pruning

**Category 2: REST Fuzzing** (5 tests, ~100 examples each)
- Fuzz acquire (owner + lease), send (keys 0-10K), input_mode (random strings), worker_id paths, heartbeat lease values
- All via TestClient with real FastAPI routing + pydantic validation

**Category 3: Concurrent Stress** (4 async tests)
- Race acquire/release, concurrent mode switch, disconnect-during-hijack, event seq monotonicity under concurrency

### Dependencies added
- `hypothesis==6.151.9` + `sortedcontainers==2.4.0` installed in project venv

---

## Previous Session — Shared Input Mode + Subpackage Restructure

### Step 0: Restructured hijack into subpackages
- `hijack/hub.py` → `hijack/hub/__init__.py` (413 LOC) + `hijack/hub/ownership.py` (200 LOC)
- `hijack/routes.py` → `hijack/routes/__init__.py` (re-exports)
- `hijack/routes_ws.py` → `hijack/routes/websockets.py`
- `hijack/routes_rest.py` → `hijack/routes/rest.py`
- All import paths preserved (`from undef.terminal.hijack.hub import TermHub` etc.)
- Old files removed (would conflict with package directories)

### Step 1-2: input_mode field + core logic
- `WorkerTermState.input_mode: str = "hijack"` — `"hijack"` (default) or `"open"`
- `InputModeRequest` pydantic model with pattern validation
- `TermHub._set_input_mode()` — under lock, rejects if active hijack when → open
- `TermHub._disconnect_worker()` — programmatic worker WS disconnect
- `TermHub._can_send_input()` — open mode = any browser; hijack mode = owner only
- `_broadcast_hijack_state` and `_hijack_state_msg_for` now include `input_mode`

### Step 3: WS routes — worker_hello + open-mode input
- Worker handler: `worker_hello` message type in main loop sets `input_mode`
- Browser hello: now includes `input_mode` field
- Browser input: uses `_can_send_input()` — any browser in open mode, owner only in hijack
- `hijack_request`: rejected with error in open mode

### Step 4: REST endpoints
- `POST /worker/{id}/input_mode` — switch mode (404 no worker, 409 active hijack)
- `POST /worker/{id}/disconnect_worker` — force-disconnect worker WS (404 no worker)

### Step 5: hijack.js — open-mode UI
- Tracks `_inputMode` from hello, hijack_state, input_mode_changed messages
- Sends input in open mode (keyboard, text field, mobile keys)
- Hides Hijack/Step/Release buttons in open mode
- Shows "Connected (shared)" status

### Step 6: Tests (15 new)
- `tests/test_hijack_shared.py` — worker_hello, open-mode input, hijack rejection, REST endpoints, broadcasts
- Also fixed `_safe_int` import in `test_coverage_hub_routes.py` for new path

---

## Backward Compatibility
- Default `input_mode` is `"hijack"` — all existing behavior unchanged
- `worker_hello` is optional — omitting it gets hijack mode
- `hello` message gains additive `input_mode` field
- All 637 original tests still pass

---

## Architecture Notes
- `worker_hello` is handled in the main message loop (not peeked) to avoid blocking
- Open mode: no pause/resume control messages sent to worker
- `_can_send_input` is checked under lock atomically with lease extension
- `_disconnect_worker` closes WS outside lock, clears hijack state atomically

---

## Next Steps
- [ ] uwarp integration: use TermHub open mode instead of custom TeeWriter/MergedReader
- [ ] Consider: per-browser input filtering in open mode (e.g., role-based)
- [ ] Coverage: remaining misses are reconnect-stale (ws:58-61,65-66), WS send fail (ws:286,323,386), TOCTOU (rest:312,368), task cancel (bridge:178)
