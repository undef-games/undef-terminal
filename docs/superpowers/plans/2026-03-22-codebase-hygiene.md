# Codebase Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two CI-failing LOC violations, add connector self-registration, remove compiled frontend from git, add undef.shell vendoring guard, and add session-state unification to the backlog.

**Architecture:** Six independent tasks that can be committed separately; each produces working, tested, passing-CI code on its own. Work in priority order (Tasks 1-2 fix active CI failures).

**Tech Stack:** Python 3.11+, pytest, GitHub Actions CI, npm (Node 20), uv

---

## File Map

### Created
- `packages/undef-terminal/src/undef/terminal/detection/input_type.py` — standalone `auto_detect_input_type()` function
- `packages/undef-terminal/src/undef/terminal/server/connectors/registry.py` — `_registry` dict, `register_connector()`, `build_connector()`, `registered_types()`
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes/__init__.py` — exports `route_http` only
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes/_shared.py` — constants, imports, shared helpers
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes/_hijack.py` — hijack route handlers
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes/_session.py` — session route handlers
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes/_dispatch.py` — `route_http` dispatcher
- `packages/undef-terminal-cloudflare/tests/test_ushell_vendor_guard.py` — vendoring import test

### Modified
- `packages/undef-terminal/src/undef/terminal/detection/detector.py` — remove `auto_detect_input_type` method
- `packages/undef-terminal/src/undef/terminal/detection/__init__.py` — add `auto_detect_input_type` export
- `packages/undef-terminal/tests/detection/test_detector.py` — update 34 call sites
- `packages/undef-terminal/src/undef/terminal/server/connectors/__init__.py` — switch to registry-backed `KNOWN_CONNECTOR_TYPES`
- `packages/undef-terminal/src/undef/terminal/server/connectors/telnet.py` — add `register_connector("telnet", ...)`
- `packages/undef-terminal/src/undef/terminal/server/connectors/shell.py` — add `register_connector("shell", ...)`
- `packages/undef-terminal/src/undef/terminal/server/connectors/ssh.py` — add `register_connector("ssh", ...)`
- `packages/undef-terminal/src/undef/terminal/server/connectors/websocket.py` — add `register_connector("websocket", ...)`
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/__init__.py` — update import if needed
- `.gitignore` — add `packages/undef-terminal/src/undef/terminal/frontend/`
- `.github/workflows/ci.yml` — add Node setup + `npm run build:frontend` steps; add ushell vendor check step
- `.provide/HANDOFF.md` — add session-state backlog note

### Deleted
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes.py` — replaced by module dir

---

## Task 1: Fix LOC — Split `detection/detector.py`

**Why first:** Active CI failure (`detector.py` is 501 lines; limit is 500).

**Files:**
- Create: `packages/undef-terminal/src/undef/terminal/detection/input_type.py`
- Modify: `packages/undef-terminal/src/undef/terminal/detection/detector.py` (lines 412–501)
- Modify: `packages/undef-terminal/src/undef/terminal/detection/__init__.py`
- Modify: `packages/undef-terminal/tests/detection/test_detector.py`

- [ ] **Step 1: Verify the current failure**

```bash
cd /path/to/undef-terminal
uv run python scripts/check_max_loc.py --max-lines 500 --baseline .ci/max-loc-baseline.json
```

Expected: FAIL — `detection/detector.py` reported as 501 lines.

- [ ] **Step 2: Create `detection/input_type.py`**

```python
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Heuristic input-type detection from terminal screen text."""

from __future__ import annotations


def auto_detect_input_type(screen: str) -> str:
    """Heuristically detect input type from prompt text.

    Args:
        screen: Screen text to analyze

    Returns:
        "any_key", "single_key", or "multi_key"
    """
    screen_lower = screen.lower()

    if any(
        phrase in screen_lower
        for phrase in [
            "press any key",
            "press a key",
            "hit any key",
            "strike any key",
            "<more>",
            "[more]",
            "-- more --",
        ]
    ):
        return "any_key"

    if any(
        phrase in screen_lower
        for phrase in [
            "(y/n)",
            "(yes/no)",
            "continue?",
            "quit?",
            "abort?",
            "retry?",
            "[y/n]",
            "(q)uit",
            "(a)bort",
        ]
    ):
        return "single_key"

    if any(
        phrase in screen_lower
        for phrase in [
            "enter",
            "type",
            "input",
            "name:",
            "password:",
            "username:",
            "choose:",
            "select:",
            "command:",
            "search:",
        ]
    ):
        return "multi_key"

    return "multi_key"
```

- [ ] **Step 3: Remove `auto_detect_input_type` from `detector.py`**

Delete lines 412–501 (the `auto_detect_input_type` and `add_pattern`/`reload_patterns` methods remain — only `auto_detect_input_type` is removed). The file should end at the `reload_patterns` method.

Verify line count after:

```bash
wc -l packages/undef-terminal/src/undef/terminal/detection/detector.py
```

Expected: ~438 lines.

- [ ] **Step 4: Update `detection/__init__.py`**

Add to the imports and `__all__`:

```python
from undef.terminal.detection.input_type import auto_detect_input_type
```

And add `"auto_detect_input_type"` to `__all__`.

- [ ] **Step 5: Update test call sites in `test_detector.py`**

`auto_detect_input_type` was an instance method — it takes no instance state, so it becomes a standalone function. All 34 call sites change from:

```python
d = PromptDetector(patterns=[])
result = d.auto_detect_input_type("Press any key")
```

to:

```python
from undef.terminal.detection.input_type import auto_detect_input_type
result = auto_detect_input_type("Press any key")
```

Tests that created a `PromptDetector` instance solely to call `auto_detect_input_type` can drop the fixture entirely. Add the import at the top of the test file and remove `d.auto_detect_input_type` everywhere.

- [ ] **Step 6: Run tests to verify**

```bash
uv run pytest packages/undef-terminal/tests/detection/ -q
```

Expected: all pass.

- [ ] **Step 7: Verify LOC check passes**

```bash
uv run python scripts/check_max_loc.py --max-lines 500 --baseline .ci/max-loc-baseline.json
```

Expected: PASS (no offenders, or only `http_routes.py` which is Task 2).

- [ ] **Step 8: Commit**

```bash
git add packages/undef-terminal/src/undef/terminal/detection/input_type.py \
        packages/undef-terminal/src/undef/terminal/detection/detector.py \
        packages/undef-terminal/src/undef/terminal/detection/__init__.py \
        packages/undef-terminal/tests/detection/test_detector.py
git commit -m "refactor(detection): extract auto_detect_input_type to input_type module"
```

---

## Task 2: Fix LOC — Split CF `api/http_routes.py`

**Why second:** Active CI failure (`http_routes.py` is 504 lines).

**Files:**
- Create: `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes/` (module dir)
- Delete: `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes.py`

The split:
- `_shared.py` — all imports, constants (`_HIJACK_ID_RE`, `_MIN_LEASE_S`, etc.), and helpers (`_safe_int`, `_extract_hijack_id`, `_parse_lease_s`, `_wait_for_prompt`, `_wait_for_analysis`, `_session_status_item`) — roughly lines 1–151
- `_hijack.py` — all `/hijack/` route branches + `_handle_hijack_send` — roughly lines 164–396
- `_session.py` — `_handle_session_route` — roughly lines 399–504
- `_dispatch.py` — `route_http` dispatcher (the top-level if/elif chain that calls into `_hijack` and `_session`) — roughly lines 153–335 minus the handler bodies
- `__init__.py` — `from ._dispatch import route_http` only

Every new file needs the SPDX header:
```python
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
```

- [ ] **Step 1: Create the module directory**

```bash
mkdir packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes
```

- [ ] **Step 2: Create `_shared.py`**

Move all imports, constants, and private helpers from the top of `http_routes.py` (lines 1–151). Keep the same logic — no changes to behavior. Helpers to include: `_safe_int`, `_extract_hijack_id`, `_parse_lease_s`, `_wait_for_prompt`, `_wait_for_analysis`, `_session_status_item`.

- [ ] **Step 3: Create `_hijack.py`**

Move the hijack route handler branches and `_handle_hijack_send`. This file imports from `._shared`. The route logic for `/hijack/acquire`, `/heartbeat`, `/release`, `/step`, `/send`, `/snapshot`, `/events`, `/input_mode`, `/disconnect_worker` plus the `_handle_hijack_send` helper (lines 338–396).

Extract into a single function `route_hijack(runtime, request, path, url, method) -> object | None` that returns a response if it matches a hijack route, or `None` if not. Also define `handle_hijack_send` (renamed from `_handle_hijack_send`) here.

- [ ] **Step 4: Create `_session.py`**

Move `_handle_session_route` from lines 399–504. Import from `._shared`. Rename to `route_session` for consistency.

- [ ] **Step 5: Create `_dispatch.py`**

The `route_http` function that calls `route_hijack` and `route_session`. Import from `._shared`, `._hijack`, `._session`.

```python
async def route_http(runtime: RuntimeProtocol, request: object) -> object:
    url = str(getattr(request, "url", ""))
    path = urlparse(url).path
    method = str(getattr(request, "method", "GET")).upper()

    if path == "/api/health":
        return json_response({"ok": True, "service": "undef-terminal-cloudflare"})

    if path == "/api/sessions":
        return json_response([_session_status_item(runtime)], headers={"X-Sessions-Scope": "local"})

    hijack_result = await route_hijack(runtime, request, path, url, method)
    if hijack_result is not None:
        return hijack_result

    session_match = _SESSION_ROUTE_RE.match(path)
    if session_match:
        return await route_session(runtime, request, path, url, method, session_match)

    return json_response({"error": "not_found", "path": path}, status=404)
```

- [ ] **Step 6: Create `__init__.py`**

```python
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

from undef_terminal_cloudflare.api.http_routes._dispatch import route_http

__all__ = ["route_http"]
```

- [ ] **Step 7: Delete the old `http_routes.py`**

```bash
git rm packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes.py
```

- [ ] **Step 8: Verify LOC check passes**

```bash
uv run python scripts/check_max_loc.py --max-lines 500 --baseline .ci/max-loc-baseline.json
```

Expected: PASS with no offenders.

- [ ] **Step 9: Run the CF test suite**

```bash
uv run pytest packages/undef-terminal-cloudflare/tests/ -q
```

Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes/
git rm packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes.py
git commit -m "refactor(cf/api): split http_routes into module dir (_shared, _hijack, _session, _dispatch)"
```

---

## Task 3: Connector Self-Registration

**Goal:** Replace the hardcoded `KNOWN_CONNECTOR_TYPES` frozenset + `if/elif` factory with a registry so new connectors self-register without editing `__init__.py`.

**Files:**
- Create: `packages/undef-terminal/src/undef/terminal/server/connectors/registry.py`
- Modify: `packages/undef-terminal/src/undef/terminal/server/connectors/__init__.py`
- Modify: `packages/undef-terminal/src/undef/terminal/server/connectors/telnet.py`
- Modify: `packages/undef-terminal/src/undef/terminal/server/connectors/shell.py`
- Modify: `packages/undef-terminal/src/undef/terminal/server/connectors/ssh.py`
- Modify: `packages/undef-terminal/src/undef/terminal/server/connectors/websocket.py`

- [ ] **Step 1: Write a failing test for registry**

In `packages/undef-terminal/tests/server/test_connectors.py` (check if this file exists first; if not, create it), add:

```python
def test_registry_known_types_derived_from_registry() -> None:
    from undef.terminal.server.connectors import KNOWN_CONNECTOR_TYPES
    from undef.terminal.server.connectors.registry import registered_types
    assert KNOWN_CONNECTOR_TYPES == registered_types()


def test_registry_build_connector_unknown_raises() -> None:
    from undef.terminal.server.connectors.registry import build_connector
    with pytest.raises(ValueError, match="unsupported connector_type"):
        build_connector("sid", "name", "nonexistent", {})


def test_registry_register_and_build() -> None:
    from undef.terminal.server.connectors.base import SessionConnector
    from undef.terminal.server.connectors.registry import build_connector, register_connector
    class _Fake(SessionConnector):
        def __init__(self, sid, name, cfg): ...
        async def start(self): ...
        async def stop(self): ...
        async def send_input(self, data): ...
    register_connector("_test_fake", _Fake)
    inst = build_connector("s", "n", "_test_fake", {})
    assert isinstance(inst, _Fake)
```

Run:
```bash
uv run pytest packages/undef-terminal/tests/server/test_connectors.py::test_registry_known_types_derived_from_registry -v
```

Expected: FAIL — `registered_types` does not exist yet.

- [ ] **Step 2: Create `connectors/registry.py`**

```python
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Connector self-registration registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from undef.terminal.server.connectors.base import SessionConnector

_registry: dict[str, type[SessionConnector]] = {}


def register_connector(name: str, cls: type[SessionConnector]) -> None:
    """Register a connector class under a type name."""
    _registry[name] = cls


def build_connector(
    session_id: str,
    display_name: str,
    connector_type: str,
    config: dict[str, Any],
) -> SessionConnector:
    """Instantiate a connector by type name. Raises ValueError for unknown types."""
    cls = _registry.get(connector_type)
    if cls is None:
        raise ValueError(f"unsupported connector_type: {connector_type!r}")
    return cls(session_id, display_name, config)


def registered_types() -> frozenset[str]:
    """Return the set of currently registered connector type names."""
    return frozenset(_registry)
```

- [ ] **Step 3: Add self-registration calls to each connector module**

At the bottom of each file (after the class definition), add:

**`telnet.py`** (always available, no optional dep):
```python
from undef.terminal.server.connectors.registry import register_connector
register_connector("telnet", TelnetSessionConnector)
```

**`shell.py`** (requires subprocess support):
```python
from undef.terminal.server.connectors.registry import register_connector
register_connector("shell", ShellSessionConnector)
```

**`ssh.py`** (requires asyncssh):
```python
from undef.terminal.server.connectors.registry import register_connector
register_connector("ssh", SshSessionConnector)
```

**`websocket.py`** (requires websockets):
```python
from undef.terminal.server.connectors.registry import register_connector
register_connector("websocket", WebSocketSessionConnector)
```

- [ ] **Step 4: Update `connectors/__init__.py`**

Replace the hardcoded `KNOWN_CONNECTOR_TYPES` frozenset and `build_connector` with the registry-backed versions:

```python
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Connector exports for the hosted server app."""

from __future__ import annotations

import contextlib

from undef.terminal.server.connectors.base import SessionConnector
from undef.terminal.server.connectors.registry import build_connector, register_connector, registered_types
from undef.terminal.server.connectors.telnet import TelnetSessionConnector  # registers "telnet"

__all__ = [
    "KNOWN_CONNECTOR_TYPES",
    "SessionConnector",
    "ShellSessionConnector",
    "SshSessionConnector",
    "TelnetSessionConnector",
    "UshellConnector",
    "WebSocketSessionConnector",
    "build_connector",
]

with contextlib.suppress(ImportError):
    from undef.terminal.server.connectors.shell import ShellSessionConnector  # registers "shell"
with contextlib.suppress(ImportError):
    from undef.terminal.server.connectors.ssh import SshSessionConnector  # registers "ssh"
with contextlib.suppress(ImportError):
    from undef.terminal.server.connectors.websocket import WebSocketSessionConnector  # registers "websocket"
with contextlib.suppress(ImportError):
    # register_connector is always available (from our own registry.py);
    # only the UshellConnector import is optional — it requires undef-shell installed.
    from undef.shell.terminal._connector import UshellConnector
    register_connector("ushell", UshellConnector)

# Derived from the registry — reflects whatever connectors are available in this env.
KNOWN_CONNECTOR_TYPES: frozenset[str] = registered_types()
```

Note: `models.py` and `registry.py` import `KNOWN_CONNECTOR_TYPES` from here — no changes needed to those files.

- [ ] **Step 5: Run the new tests**

```bash
uv run pytest packages/undef-terminal/tests/server/test_connectors.py -v
```

Expected: all pass.

- [ ] **Step 6: Run the full server test suite**

```bash
uv run pytest packages/undef-terminal/tests/server/ -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add packages/undef-terminal/src/undef/terminal/server/connectors/
git add packages/undef-terminal/tests/server/test_connectors.py
git commit -m "refactor(connectors): replace hardcoded frozenset+factory with self-registration registry"
```

---

## Task 4: Remove Compiled Frontend from Git

**Goal:** Frontend JS/CSS is a build artifact; remove it from the repo and generate it in CI.

**Files:**
- Modify: `.gitignore`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Verify the pin (no code change)**

```bash
grep "undef-telemetry" packages/undef-terminal/pyproject.toml
```

Expected: `undef-telemetry>=0.3` — already correct, nothing to change.

- [ ] **Step 2: Add frontend to `.gitignore`**

Append to `.gitignore`:

```
# Compiled frontend (build artifact — generated by npm run build:frontend in CI)
packages/undef-terminal/src/undef/terminal/frontend/
```

- [ ] **Step 3: Untrack the compiled files**

First verify the directory exists and has tracked files:

```bash
git ls-files packages/undef-terminal/src/undef/terminal/frontend/ | head -10
```

Expected: a list of tracked files (terminal.html, hijack.html, *.js, etc.). If empty, the files were never tracked — skip this step.

Then untrack:

```bash
git rm -r --cached packages/undef-terminal/src/undef/terminal/frontend/
```

Expected: a list of `rm '...'` lines for each removed file.

- [ ] **Step 4: Add Node.js setup and frontend build to `ci.yml`**

In the `quality` job, add after the `actions/setup-python` step and before the first `run:` step:

```yaml
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - run: npm run build:frontend
```

Also add these same three steps to the `release-readiness` job, before the `uv build` step.

- [ ] **Step 5: Verify locally that build still works**

```bash
npm run build:frontend
uv run python scripts/verify_package_artifacts.py
```

Expected: `artifact verification passed (N frontend files)`

- [ ] **Step 6: Commit**

```bash
git add .gitignore .github/workflows/ci.yml
# Do NOT stage the removed frontend files — git rm --cached already staged them
git commit -m "build: remove compiled frontend from git; generate in CI via npm run build:frontend"
```

---

## Task 5: undef.shell Vendoring Guard

**Goal:** Prevent silent CF deploys where `undef.shell` is absent from the vendor tree.

**Files:**
- Create: `packages/undef-terminal-cloudflare/tests/test_ushell_vendor_guard.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the vendoring test**

Create `packages/undef-terminal-cloudflare/tests/test_ushell_vendor_guard.py`:

```python
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Guard: verify undef.shell is present in the CF python_modules vendor tree.

If this test fails, run:
  uv pip install --python .venv-workers/pyodide-venv/bin/python --reinstall /path/to/undef-shell
  pywrangler sync --force
from packages/undef-terminal-cloudflare/.
"""

from pathlib import Path


def test_ushell_vendor_tree_exists() -> None:
    """undef/shell must be present in python_modules — absent means a missing vendor sync."""
    vendor_root = Path(__file__).resolve().parents[1] / "python_modules"
    ushell_path = vendor_root / "undef" / "shell"
    assert vendor_root.exists(), (
        "python_modules/ directory not found — run pywrangler sync from packages/undef-terminal-cloudflare/"
    )
    assert ushell_path.exists() and ushell_path.is_dir(), (
        f"undef/shell missing from vendor tree at {ushell_path}. "
        "Run: uv pip install --python .venv-workers/pyodide-venv/bin/python "
        "--reinstall /path/to/undef-shell && pywrangler sync --force"
    )
    py_files = list(ushell_path.rglob("*.py"))
    assert py_files, f"undef/shell vendor tree at {ushell_path} is empty"
```

- [ ] **Step 2: Run the test to confirm it passes locally**

```bash
uv run pytest packages/undef-terminal-cloudflare/tests/test_ushell_vendor_guard.py -v
```

Expected: PASS (vendor tree exists locally). If it fails, run the vendor sync first.

- [ ] **Step 3: Add CI vendor check step to `ci.yml`**

In the `quality` job, add a step before `uv run pytest -q packages/undef-terminal-cloudflare/tests`:

```yaml
      - name: Check undef.shell vendor tree
        run: |
          if [ ! -d "packages/undef-terminal-cloudflare/python_modules/undef/shell" ]; then
            echo "ERROR: undef.shell missing from CF vendor tree"
            exit 1
          fi
          if [ -z "$(find packages/undef-terminal-cloudflare/python_modules/undef/shell -name '*.py' -print -quit)" ]; then
            echo "ERROR: undef.shell vendor tree is empty"
            exit 1
          fi
```

- [ ] **Step 4: Commit**

```bash
git add packages/undef-terminal-cloudflare/tests/test_ushell_vendor_guard.py
git add .github/workflows/ci.yml
git commit -m "test(cf): add undef.shell vendor tree guard test and CI check"
```

---

## Task 6: Session State Backlog Note

**Goal:** Document the in-memory vs. KV session state divergence so it's not forgotten.

**Files:**
- Modify: `.provide/HANDOFF.md`

- [ ] **Step 1: Add backlog note to HANDOFF.md**

Append the following section to `.provide/HANDOFF.md`:

```markdown
## Backlog: Session State Unification

**Problem:** The hosted server (`TermHub`, `SessionRegistry`) manages session state in-memory, while the CF package (`state/registry.py`, `state/store.py`) manages the same logical state in Cloudflare KV. These are parallel implementations with no shared abstraction, different consistency guarantees, and divergent APIs.

**Impact:** Features added to one stack (e.g. new session fields, visibility rules) must be duplicated manually in the other. The `contracts.py` TypedDicts partially bridge this, but the storage and lifecycle logic is entirely duplicated.

**Proposed direction:** Define a `SessionStore` protocol in `undef-terminal` (main package) that both backends implement. Hosted server uses an in-memory `MemorySessionStore`; CF uses a `KvSessionStore`. Session lifecycle logic (auto-start, ephemeral cleanup, ownership) moves to protocol-agnostic code.

**Effort estimate:** Large — multi-session, requires parallel changes to both stacks and E2E validation.
```

- [ ] **Step 2: Commit**

```bash
git add .provide/HANDOFF.md
git commit -m "docs: add session state unification to backlog"
```

---

## Verification Checklist

After all tasks:

```bash
# LOC gate
uv run python scripts/check_max_loc.py --max-lines 500 --baseline .ci/max-loc-baseline.json

# Full test suites
uv run python scripts/run_pytest_gate.py -q
uv run pytest packages/undef-terminal-cloudflare/tests/ -q

# Type checks
uv run mypy packages/undef-terminal/src/
uv run ruff check packages/undef-terminal/src/ packages/undef-terminal-cloudflare/src/
```

Expected: all pass.
