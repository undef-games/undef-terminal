# undef-terminal-pty — Design Spec

**Date:** 2026-03-30  
**Package:** `undef-terminal-pty`  
**Diagram:** [`docs/diagrams/pty-architecture.svg`](../../diagrams/pty-architecture.svg)

---

## Context

undef-terminal currently has no way to spawn a real local PTY. All connectors are remote proxies (SSH, Telnet, WebSocket) or the sandboxed Python REPL (ushell). This means the server can only broker sessions to things it can already reach — it cannot authenticate a local OS user and give them a shell on the server machine, and it cannot wrap an arbitrary binary it doesn't own the code for.

Three capabilities are needed:

1. **PAM + PTY connector** — authenticate via PAM, spawn a real PTY shell as the authenticated OS user (like `login`/`sshd` do), supervised by the undef-terminal server.
2. **dyld / LD_PRELOAD capture** — intercept `read`/`write`/`connect` inside an arbitrary binary by preloading `libuterm_capture` before exec. Captures I/O from binaries that bypass the PTY or do direct network I/O.
3. **Daemon bridge** — a PAM session module (`pam_uterm.so`) dropped into `/etc/pam.d/` that fires a Unix socket notification to undef-terminal whenever `sshd`/`login`/`su` opens a session, automatically registering those sessions without replacing the daemon.

All three run on the Python server, independent of WebSocket state. CF DO hibernation does not affect PTY process lifetime — the `HostedSessionRuntime` already survives WS disconnects for SSH sessions; PTY sessions behave identically.

---

## Package

**New package:** `packages/undef-terminal-pty/`  
**Namespace:** `undef.terminal.pty`  
**Dependencies:** `pamela>=1.2` (ctypes wrapper for libpam, actively maintained by minrk; `python-pam` is stale/discontinued as of 2025); native C components built at install time  
**Extras:** `[terminal]` → `undef-terminal` (for `SessionConnector` base class)

---

## Components

### 1. PTYConnector  (`connector_type="pty"`)

**File:** `packages/undef-terminal-pty/src/undef/terminal/pty/connector.py`

Implements `SessionConnector` from `undef-terminal`. Session config:

```python
{
    "connector_type": "pty",
    "connector_config": {
        "command": "/bin/bash",          # binary to exec (required)
        "args": [],                       # argv[1..] (optional)
        "username": "alice",             # application user — used for PAM auth (optional)
        "password": "...",               # PAM credential (optional)
        "run_as": "www-data",            # OS user to exec as (optional — overrides uid_map)
        "run_as_uid": 33,                # explicit uid override (takes precedence over run_as)
        "run_as_gid": 33,                # explicit gid override
        "env": {},                        # extra env vars merged in
        "inject": False,                  # preload libuterm_capture (optional)
        "cols": 80,
        "rows": 24,
    }
}
```

**uid/gid resolution** (via `UidMap`, see component 2a):
1. If `run_as_uid` is set → use directly (no name lookup)
2. Else if `run_as` is set → `pwd.getpwnam(run_as)` → uid, gid
3. Else check server-level `[pty.uid_map]` config for a mapping entry keyed on `username` (supports name or numeric uid, and a `"*"` wildcard fallback)
4. Else → `pwd.getpwnam(username)` — authenticated user runs as themselves

After resolution: `os.setgid(gid)` → `os.initgroups(target_username, gid)` → `os.setuid(uid)`. Supplementary groups are always initialized via `initgroups` so the process has full group membership.

**Privilege requirement:** `setuid()` to a different user requires the server to run as root or hold `CAP_SETUID`/`CAP_SETGID`. The connector checks `os.geteuid() == 0` at start and raises `PermissionError` early if user-switching is requested without sufficient privilege.

**Lifecycle:**
1. If `username` is set: run the full PAM sequence via `PamSession`:
   - `pam_start(service="undef-terminal", username, conv)`
   - `pam_authenticate()` — verify credentials
   - `pam_acct_mgmt()` — check account validity, expiration, access restrictions (not skipped — sshd calls this)
   - `pam_setcred(PAM_ESTABLISH_CRED)` — establish credentials (Kerberos tickets, etc.)
   - `pam_open_session()` — triggers pam_systemd, pam_limits, home dir mounts, etc.
   - `pam_getenvlist()` — collect PAM-provided env vars (PATH, HOME, SHELL, etc.)
2. `openpty()` → (master_fd, slave_fd).
3. `os.fork()`:
   - **Child:** close master_fd, `setsid()`, set slave as controlling terminal, `setgid()`/`setuid()` to target user, merge PAM env + `connector_config.env`, optionally set `DYLD_INSERT_LIBRARIES`/`LD_PRELOAD` to `libuterm_capture` path, `os.execve(command, args, env)`.
   - **Parent:** close slave_fd, own master_fd, start async read loop, optionally start `CaptureSocket` Unix socket listener.
4. On `stop()`: send `SIGHUP` to process group, close master_fd, then `pam_close_session()` → `pam_setcred(PAM_DELETE_CRED)` → `pam_end()`.

**I/O:** `poll_messages()` reads from master_fd (non-blocking). `handle_input()` writes to master_fd. Terminal resize sends `TIOCSWINSZ` ioctl.

**Survival across WS disconnect:** The async read loop runs as a background task inside `HostedSessionRuntime`. No WS dependency. Scrollback is buffered in the existing snapshot mechanism.

---

### 2. UidMap  (`undef.terminal.pty.uid_map`)

**File:** `packages/undef-terminal-pty/src/undef/terminal/pty/uid_map.py`

Resolves an application-level username to a `(uid, gid, home, shell)` tuple using a priority chain. Loaded once at server startup from the `[pty.uid_map]` section of the server config TOML:

```toml
[pty.uid_map]
# application username → OS username, uid, or "uid:gid"
alice   = "www-data"
bob     = "1001"
ci      = "1001:1002"   # explicit uid:gid
"*"     = "nobody"      # wildcard fallback (optional)
```

```python
@dataclass
class ResolvedUser:
    uid: int
    gid: int
    home: str
    shell: str
    name: str           # resolved OS username (for initgroups)

class UidMap:
    def resolve(self, username: str, override: dict | None = None) -> ResolvedUser: ...
```

`override` carries per-session `run_as` / `run_as_uid` / `run_as_gid` from `connector_config`, which take precedence over the table. `pwd.getpwnam()` and `pwd.getpwuid()` are used for all name↔uid lookups.

---

### 3. PamSession  (`undef.terminal.pty.pam`)

**File:** `packages/undef-terminal-pty/src/undef/terminal/pty/pam.py`

Thin wrapper around `pamela` (minrk/pamela — the idiomatic choice; `python-pam` is stale). `pamela` uses ctypes internally and handles the Linux vs macOS/OpenPAM platform differences in call ordering (`pam_setcred` before vs after `pam_open_session`).

```python
class PamSession:
    def authenticate(self, username: str, password: str) -> None: ...
    def acct_mgmt(self) -> None: ...                              # check account validity
    def establish_cred(self) -> None: ...                         # PAM_ESTABLISH_CRED
    def open_session(self) -> None: ...
    def get_env(self) -> dict[str, str]: ...                      # pam_getenvlist → dict
    def close_session(self) -> None: ...                          # pam_close_session + PAM_DELETE_CRED + pam_end
```

Used as a context manager: `with PamSession(username, password) as pam_env: ...` — handles the full lifecycle in the correct order. Raises `PamError` (wraps pamela's `PAMError`) on any failure.

**Why PAM is still correct:** PAM is what sshd, login, tmux, and gnome-terminal all use for local OS user auth and PTY spawning in 2026. systemd-logind extends PAM (via `pam_systemd.so`) rather than replacing it. Direct shadow file access is dangerous and doesn't handle Kerberos/LDAP/2FA.

---

### 3. libuterm_capture  (C shared library)

**File:** `packages/undef-terminal-pty/native/capture/capture.c`  
**Output:** `libuterm_capture.so` (Linux) / `libuterm_capture.dylib` (macOS)

Intercepts via symbol interposition:
- `ssize_t write(int fd, const void *buf, size_t count)`
- `ssize_t read(int fd, void *buf, size_t count)`
- `int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen)`

On load (`__attribute__((constructor))`): reads `UTERM_CAPTURE_SOCKET` env var, connects to the Unix socket. Forwards intercepted data as length-prefixed frames: `[1B channel][4B len][N bytes]` where channel `0x01` = stdout, `0x02` = stdin, `0x03` = connect call (addr as string).

Only intercepts when `UTERM_CAPTURE_SOCKET` is set — inert otherwise.

macOS: uses `DYLD_INSERT_LIBRARIES` + `DYLD_FORCE_FLAT_NAMESPACE`.  
Linux: uses `LD_PRELOAD` + `dlsym(RTLD_NEXT, "write")` etc.

**macOS SIP caveat:** System Integrity Protection (macOS 10.15+) blocks `DYLD_INSERT_LIBRARIES` for system-signed binaries (e.g., `/usr/sbin/sshd`, `/bin/bash` in some contexts). Injection works for user-space binaries and non-SIP-protected targets. The daemon bridge mode (`pam_uterm.so`) is the correct path for bridging sshd sessions on macOS — it doesn't require injection into sshd.

**Build:** `setuptools` extension via `cffi` or a plain `Makefile` invoked from `setup.py`. Output path stored in package data so `PTYConnector` can locate it at runtime.

---

### 4. CaptureSocket  (`undef.terminal.pty.capture`)

**File:** `packages/undef-terminal-pty/src/undef/terminal/pty/capture.py`

Async Unix socket server (one connection per injected process). Reads length-prefixed frames from `libuterm_capture`, demuxes by channel, and feeds into the PTYConnector's message stream alongside PTY master output.

---

### 5. pam_uterm  (C PAM module — daemon bridge)

**File:** `packages/undef-terminal-pty/native/pam_uterm/pam_uterm.c`  
**Output:** `pam_uterm.so`

A standard PAM session module implementing `pam_sm_open_session` and `pam_sm_close_session`. When called by `sshd`/`login`/`su` (via `/etc/pam.d/` config), it:

1. Reads `UTERM_NOTIFY_SOCKET` from PAM environment (set in pam.d config via `setenv`).
2. Sends a JSON notification over that Unix socket:
   ```json
   {"event": "open", "username": "alice", "tty": "/dev/pts/3", "pid": 12345}
   ```
3. On `pam_sm_close_session`: sends `{"event": "close", "pid": 12345}`.

undef-terminal server listens on that socket and creates/destroys session entries pointing at the existing PTY fd (obtained via `/proc/<pid>/fd/` on Linux or `proc_pidinfo` on macOS).

Install: `sudo cp pam_uterm.so /usr/lib/security/` (Linux) or `/usr/lib/pam/` (macOS), then add to `/etc/pam.d/sshd`:
```
session optional pam_uterm.so
```

---

## Data Flow

```
Browser → CF DO (may hibernate) → undef-terminal server
                                        │
                              HostedSessionRuntime
                                        │
                                  PTYConnector
                                   ├── PamSession ──→ libpam (OS)
                                   ├── PtyProcess ──→ fork → setuid → execve
                                   │                         └── [libuterm_capture preloaded]
                                   │                               └── Unix socket → CaptureSocket
                                   └── master_fd ←→ target process PTY

Daemon bridge (optional):
  sshd → pam_uterm.so → Unix socket → undef-terminal → register session
```

---

## Error Handling

- PAM auth failure → `PamError` raised before fork → session creation fails with 401
- `UidMap.resolve()` failure (unknown username, bad config) → raises `ValueError` → session creation fails with 400
- User-switching requested but `os.geteuid() != 0` → `PermissionError` raised at connector start → session creation fails with 403
- `setuid`/`setgid` failure in child → child exits with code 126; parent detects EOF on master_fd, logs error, marks session stopped
- Process exits unexpectedly → `HostedSessionRuntime` receives EOF on master_fd, marks session stopped
- `libuterm_capture` socket unavailable → library is inert; PTY I/O still works normally
- `pam_uterm` socket unavailable → `pam_sm_open_session` returns `PAM_SUCCESS` (non-fatal optional module)

---

## Testing

- **Unit:** `UidMap.resolve()` — test name lookup, numeric uid, `uid:gid` pair, wildcard fallback, per-session override precedence; `PamSession` with a mock `pam_conv` conversation; `CaptureSocket` frame parsing
- **Integration:** spawn `/bin/echo hello` via `PTYConnector` (no PAM, no inject), assert output arrives through `poll_messages()`
- **Inject integration:** spawn a test binary with `inject=True`, assert `write()` calls are captured on the Unix socket
- **PAM integration:** requires a PAM service config (`/etc/pam.d/uterm-test`) — mark with `@pytest.mark.requires_pam`, skip in CI unless Linux runner with PAM available
- **Daemon bridge:** requires manual install of `pam_uterm.so` — documented separately, not in automated suite

---

## File Layout

```
packages/undef-terminal-pty/
  src/undef/terminal/pty/
    __init__.py
    connector.py      # PTYConnector
    uid_map.py        # UidMap — username → (uid, gid, home, shell) resolution
    pam.py            # PamSession (pamela)
    capture.py        # CaptureSocket
    _build.py         # locate native libs at runtime
  native/
    capture/
      capture.c       # libuterm_capture
      Makefile
    pam_uterm/
      pam_uterm.c     # PAM session module
      Makefile
  tests/
    test_connector.py
    test_uid_map.py
    test_pam.py
    test_capture.py
  pyproject.toml
  README.md
```
