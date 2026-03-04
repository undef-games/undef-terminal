# undef-terminal-cloudflare

Cloudflare Workers package for running the `undef-terminal` hosted control plane.

## Commands

- `undefterm-cf build`
- `undefterm-cf dev`
- `undefterm-cf deploy --env production`

## Runtime model

- One Durable Object per `worker_id` session.
- Durable Object SQLite stores hijack leases, snapshots, and event stream sequence.
- Browser and worker websocket traffic is arbitrated by the DO.
- Upstream runtime connector uses websocket backend for v1.
