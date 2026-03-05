# Local Soak Reports

- `local-load-profile-20260305-113438.txt`
  - probes: `400`
  - successful: `400`
  - failed: `0`
  - connect latency: `p95=21.55ms`, `p99=25.65ms`
  - hello latency: `p95=2.65ms`, `p99=3.68ms`

- `local-failure-injection-20260305-115436.txt`
  - rounds: `20`
  - reconnect latency: `mean=1.44ms`, `p95=2.18ms`, `p99=2.84ms`

Generated with:

```bash
uv run python scripts/load_profile.py \
  --base-url http://127.0.0.1:18765 \
  --worker-id demo-session \
  --concurrency 20 \
  --rounds 20 \
  --timeout-s 5.0
```

```bash
uv run python scripts/failure_injection.py \
  --base-url http://127.0.0.1:18766 \
  --session-id demo-session \
  --rounds 20 \
  --timeout-s 10.0
```
