# Service SLOs

These SLO targets are the release baseline for hosted terminal control-plane deployments.

## User-facing latency SLOs

- Snapshot delivery latency (worker event -> browser receive):
  - p95: <= 350 ms
  - p99: <= 900 ms
- Command round-trip latency (browser input -> worker ack/event):
  - p95: <= 250 ms
  - p99: <= 700 ms
- Reconnect recovery time (browser WS reconnect -> first `hello`):
  - p95: <= 2.5 s
  - p99: <= 6.0 s

## Availability SLOs

- Browser WS successful connect rate: >= 99.9%
- Auth success rate for valid credentials: >= 99.99%

## Measurement

- Run load/churn with `scripts/load_profile.py`.
- Record results per release candidate in `artifacts/rc-baseline/`.
- Do not promote RCs that miss p95 or p99 targets without a written exception.
