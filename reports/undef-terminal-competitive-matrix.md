# Undef Terminal Competitive Matrix

## Scope

This report compares Undef Terminal against adjacent tools, not only direct substitutes.

That means some rows compare:

- direct terminal peers
- browser SSH/telnet tools
- terminal sharing tools
- access governance platforms
- inspection/tunnel tools

The value of the comparison is not to force all of them into one product category. It is to show where Undef Terminal is stronger, where it is weaker, and which part of the market each comparison actually covers.

## Capability Snapshot

| Tool | Browser terminal | Multi-user sharing | Formal roles / takeover | Session API / programmability | Recording / replay | Tunnel / HTTP inspect |
|---|---|---|---|---|---|---|
| Undef Terminal | Yes | Yes | Yes | Strong | Yes | Yes |
| `ttyd` | Yes | Limited | No | Weak | Limited | No |
| `GoTTY` | Yes | Limited | No | Weak | Limited | No |
| `WeTTY` | Yes | Limited | No | Weak | Limited | No |
| `WebSSH2` | Yes | Limited | No | Weak | Limited | No |
| `Sshwifty` | Yes | Limited | No | Weak | Limited | No |
| `tmate` | Indirectly | Yes | Informal | Weak | Limited | No |
| Guacamole | Yes | Moderate | Yes | Moderate | Yes | No |
| Teleport | Yes | Moderate | Yes | Strong | Yes | No |
| ngrok | No | No | No | Moderate | Partial | Yes |
| mitmproxy | No | No | No | Strong | Strong for HTTP | Yes |

## Stronger / Weaker By Tool

## [`ttyd`](https://github.com/tsl0922/ttyd)

### Undef Terminal is stronger when:

- you need session identity, ownership, and visibility
- you need read-only viewers versus interactive operators
- you need takeover or shared/exclusive input semantics
- you need replay, recording, or server-managed pages
- you need backends beyond a simple browser-terminal relay

### Undef Terminal is weaker when:

- you want the smallest possible deployment for "share a terminal over the web"
- you want a simpler mental model with fewer moving parts
- you value minimalism over control-plane features

### Net

`ttyd` is the simpler browser-terminal utility. Undef Terminal is the richer terminal session system.

## [`GoTTY`](https://github.com/yudai/gotty)

### Undef Terminal is stronger when:

- terminal access needs governance rather than just exposure
- multiple users need different privileges on the same session
- you need connectors, session APIs, and session lifecycle management
- you need browser pages for operators, users, replay, or inspect flows

### Undef Terminal is weaker when:

- the problem is just "publish this process to a browser quickly"
- operational simplicity matters more than feature depth

### Net

`GoTTY` is closer to a terminal-publishing utility. Undef Terminal is closer to a hosted terminal application framework.

## [`WeTTY`](https://github.com/butlerx/wetty)

### Undef Terminal is stronger when:

- you need more than a browser SSH entry point
- you want role-aware observers and operators
- you want session recording, replay, or takeovers
- you want hosted session management rather than direct host login

### Undef Terminal is weaker when:

- the target job is just "web SSH access to a box"
- direct SSH login UX is the center of the product

### Net

`WeTTY` is a cleaner answer for web SSH alone. Undef Terminal is stronger once the terminal becomes a managed shared session instead of a direct login surface.

## [`WebSSH2`](https://github.com/billchurch/webssh2)

### Undef Terminal is stronger when:

- browser SSH should be one connector among several
- sessions should exist independently of one user's connection
- takeover, observation, and replay matter
- browser UI needs operator and end-user surfaces

### Undef Terminal is weaker when:

- you want a conventional web SSH client specifically
- you want fewer product concepts around the access path

### Net

`WebSSH2` is more obviously a web SSH client. Undef Terminal is more of a terminal session platform.

## [`Sshwifty`](https://github.com/nirui/sshwifty)

### Undef Terminal is stronger when:

- you need session lifecycle, not only session access
- you need multiple connectors, not just SSH/telnet access
- you need explicit collaboration semantics
- you need inspect, share, replay, or quick-connect behavior around the session

### Undef Terminal is weaker when:

- the main requirement is browser SSH/telnet with familiar connection forms
- the hosted access UI itself is the primary product

### Net

`Sshwifty` is better viewed as a browser client for remote shells. Undef Terminal is better viewed as a system that manages shells as objects.

## [`tmate`](https://tmate.io/)

### Undef Terminal is stronger when:

- users should not need tmux or SSH-based collaboration habits
- viewers and controllers need explicit separation
- browser-first sharing is required
- replay, hosted pages, and session APIs matter
- collaboration should be modeled and governed, not only shared

### Undef Terminal is weaker when:

- the audience already lives in tmux
- terminal-native workflows matter more than browser UX
- the simplest path to ad hoc shell sharing is the goal

### Net

`tmate` is the strongest conceptual analogue for the collaboration slice. Undef Terminal is broader, more browser-native, and more policy-oriented. `tmate` is often simpler and more natural for terminal-native operators.

## [Apache Guacamole](https://guacamole.apache.org/)

### Undef Terminal is stronger when:

- the product should be terminal-specific rather than general remote desktop
- developers want embeddable session abstractions in code
- terminal takeover and collaboration semantics need to be first-class
- HTTP inspection and tunnel workflows belong in the same system

### Undef Terminal is weaker when:

- broad remote access coverage is required across RDP, VNC, and SSH
- a mature clientless access gateway is the main requirement
- terminal-specific collaboration is less important than broad protocol coverage

### Net

Guacamole is broader. Undef Terminal is narrower and deeper on terminal session semantics.

## [Teleport](https://goteleport.com/docs/reference/architecture/session-recording/)

### Undef Terminal is stronger when:

- the team wants a developer-facing, embeddable terminal platform
- browser session takeover and collaboration are central
- the product needs custom connectors or custom terminal UX
- tunnel and inspect behavior should live beside terminal access

### Undef Terminal is weaker when:

- enterprise-grade access governance is the primary problem
- infrastructure identity, policy, enrollment, and compliance posture dominate the requirements
- broad operational ecosystem matters more than custom session UX

### Net

Teleport is the stronger security and access platform. Undef Terminal is the more programmable terminal-specific system.

## [ngrok](https://ngrok.com/docs/obs)

### Undef Terminal is stronger when:

- the tunnel is part of a shared terminal workflow
- browser session access, not just service exposure, matters
- HTTP inspection should be attached to a broader session-control plane

### Undef Terminal is weaker when:

- the primary need is polished service tunneling
- endpoint exposure and traffic observability are the whole product
- non-terminal developers just want quick tunnel ergonomics

### Net

ngrok is the better tunnel product. Undef Terminal is interesting where tunneling is part of a larger terminal and collaboration system.

## [mitmproxy](https://www.mitmproxy.org/)

### Undef Terminal is stronger when:

- HTTP inspection is only one subsystem of a larger terminal platform
- inspect flows need browser-hosted operator surfaces tied to live sessions
- terminal sharing and HTTP interception should coexist

### Undef Terminal is weaker when:

- deep HTTP manipulation and proxy tooling are the main task
- the user wants a purpose-built interception proxy rather than a session platform
- protocol analysis depth matters more than session integration

### Net

`mitmproxy` is the better interception tool. Undef Terminal is the more integrated cross-domain system.

## Summary By Buyer Mindset

If someone wants:

- "a small browser terminal" -> `ttyd`, `GoTTY`, `WeTTY`
- "browser SSH/telnet access" -> `WeTTY`, `WebSSH2`, `Sshwifty`
- "terminal sharing" -> `tmate`
- "remote access gateway" -> Guacamole
- "security and access governance" -> Teleport
- "service tunnel and traffic inspector" -> ngrok
- "deep interception proxy" -> mitmproxy

If someone wants:

> "a terminal-centered platform where sessions can be created, shared, observed, hijacked, replayed, tunneled, inspected, and controlled through browser and API surfaces"

then Undef Terminal is the more distinctive fit.

## Repo Anchors For Undef-Specific Capabilities

- Product summary: [`../README.md`](../README.md)
- Workspace composition: [`../pyproject.toml`](../pyproject.toml)
- Core server scripts and package entrypoints: [`../packages/undef-terminal/pyproject.toml`](../packages/undef-terminal/pyproject.toml)
- Term hub and role model: [`../packages/undef-terminal/src/undef/terminal/bridge/hub/core.py`](../packages/undef-terminal/src/undef/terminal/bridge/hub/core.py)
- Hosted runtime and connectors:
  - [`../packages/undef-terminal/src/undef/terminal/server/runtime.py`](../packages/undef-terminal/src/undef/terminal/server/runtime.py)
  - [`../packages/undef-terminal/src/undef/terminal/server/connectors/__init__.py`](../packages/undef-terminal/src/undef/terminal/server/connectors/__init__.py)
- Pages and app surfaces:
  - [`../packages/undef-terminal/src/undef/terminal/server/routes/pages.py`](../packages/undef-terminal/src/undef/terminal/server/routes/pages.py)
  - [`../packages/undef-terminal-app/src/components/session/SessionPage.tsx`](../packages/undef-terminal-app/src/components/session/SessionPage.tsx)
- Protocol and inspect features:
  - [`../docs/protocol-matrix.md`](../docs/protocol-matrix.md)
  - [`../docs/inspect.md`](../docs/inspect.md)
