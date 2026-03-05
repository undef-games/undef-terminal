#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from typing import TYPE_CHECKING

import httpx
import websockets

if TYPE_CHECKING:
    from collections.abc import Callable


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    idx = round((p / 100.0) * (len(values) - 1))
    return sorted(values)[idx]


def _summary(name: str, values: list[float]) -> str:
    if not values:
        return f"{name}: no samples"
    return (
        f"{name}: count={len(values)} mean={statistics.mean(values):.2f}ms "
        f"p95={_percentile(values, 95):.2f}ms p99={_percentile(values, 99):.2f}ms"
    )


async def _recv_json(ws: object, timeout_s: float) -> dict[str, object]:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)  # type: ignore[attr-defined]
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object frame")
    return value


async def _await_snapshot(ws: object, timeout_s: float) -> dict[str, object]:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        remaining = max(0.05, deadline - time.perf_counter())
        try:
            msg = await _recv_json(ws, timeout_s=remaining)
        except TimeoutError:
            continue
        if msg.get("type") == "snapshot":
            return msg
    raise TimeoutError("timed out waiting for snapshot frame")


async def _await_snapshot_matching(
    ws: object, timeout_s: float, predicate: Callable[[dict[str, object]], bool]
) -> dict[str, object]:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        snap = await _await_snapshot(ws, timeout_s=max(0.05, deadline - time.perf_counter()))
        if predicate(snap):
            return snap
    raise TimeoutError("timed out waiting for matching snapshot frame")


async def run(base_url: str, worker_id: str, rounds: int, timeout_s: float) -> int:
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout_s) as client:
        health = await client.get("/api/health")
        if health.status_code != 200:
            raise RuntimeError("health check failed")
        # Force a deterministic input path for the probe.
        await client.post(f"/api/sessions/{worker_id}/connect")
        await client.post(f"/api/sessions/{worker_id}/mode", json={"input_mode": "open"})

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws/browser/{worker_id}/term"
    snapshot_req_latencies: list[float] = []
    input_rtt_latencies: list[float] = []

    async with websockets.connect(ws_url, open_timeout=timeout_s, close_timeout=timeout_s) as ws:
        hello = await _recv_json(ws, timeout_s=timeout_s)
        if hello.get("type") != "hello":
            raise RuntimeError(f"expected hello frame, got {hello.get('type')!r}")
        worker_online = bool(hello.get("worker_online"))
        if not worker_online:
            deadline = time.perf_counter() + timeout_s
            while time.perf_counter() < deadline:
                msg = await _recv_json(ws, timeout_s=max(0.05, deadline - time.perf_counter()))
                if msg.get("type") == "worker_connected":
                    worker_online = True
                    break
        if not worker_online:
            raise TimeoutError("worker did not come online before latency probe started")

        # Prime a known-good snapshot path with an input token before timing.
        warmup_token = "latency-warmup-token"  # noqa: S105
        await ws.send(json.dumps({"type": "input", "data": warmup_token}))
        await _await_snapshot_matching(
            ws,
            timeout_s=max(timeout_s, 15.0),
            predicate=lambda snap: warmup_token in str(snap.get("screen") or ""),
        )

        for i in range(rounds):
            start_snapshot = time.perf_counter()
            await ws.send(json.dumps({"type": "snapshot_req"}))
            await _await_snapshot(ws, timeout_s=timeout_s)
            snapshot_req_latencies.append((time.perf_counter() - start_snapshot) * 1000.0)

            token = f"latency-probe-{i:04d}"
            start_input = time.perf_counter()
            await ws.send(json.dumps({"type": "input", "data": token}))
            await _await_snapshot_matching(
                ws,
                timeout_s=timeout_s,
                predicate=lambda snap, expected=token: expected in str(snap.get("screen") or ""),
            )
            input_rtt_latencies.append((time.perf_counter() - start_input) * 1000.0)

    print(_summary("snapshot_req_latency", snapshot_req_latencies))
    print(_summary("input_roundtrip_latency", input_rtt_latencies))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure snapshot and input round-trip latency over browser WS.")
    parser.add_argument("--base-url", required=True, help="Server base URL, e.g. http://127.0.0.1:8400")
    parser.add_argument("--worker-id", default="demo-session", help="Worker/session ID")
    parser.add_argument("--rounds", type=int, default=50, help="Probe rounds")
    parser.add_argument("--timeout-s", type=float, default=5.0, help="Per-step timeout")
    args = parser.parse_args()
    return asyncio.run(run(args.base_url, args.worker_id, args.rounds, args.timeout_s))


if __name__ == "__main__":
    raise SystemExit(main())
