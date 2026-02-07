#!/usr/bin/env python3
"""
Load test: simulate ~1000 counts at irregular intervals over 6 hours.

POSTs to BASE_URL/api/check. Uses a pool of synthetic IPs (X-Real-IP) so the
per-user rate limit (10 per 10 min) does not cap the test; each request is
attributed to a random "user" to approximate many real users scanning over time.

Usage (run on remote machine, e.g. in tmux/screen):
  export API_BASE_URL=https://your-pruef-instance.example.com
  python load_test_6h.py

  # Override defaults
  python load_test_6h.py --duration 21600 --target-count 1000
  python load_test_6h.py --base-url http://localhost:5000 --dry-run

  # With server-side bypass (set LOAD_TEST_BYPASS_KEY on server, then):
  export LOAD_TEST_KEY=your-secret-key
  python load_test_6h.py

Options:
  --base-url URL     API base (default: API_BASE_URL env or https://pruef.st)
  --duration SECS    Total run duration in seconds (default: 21600 = 6h)
  --target-count N   Target number of successful counts (default: 1000)
  --ip-pool-size N   Number of synthetic IPs for rotation (default: 150)
  --load-test-key K  Bypass rate limit (server must set LOAD_TEST_BYPASS_KEY to same value)
  --dry-run          Print schedule only, do not send requests
  --verbose          Log every request; otherwise log summary every 5 min
"""

import argparse
import os
import random
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests", file=sys.stderr)
    sys.exit(1)

DEFAULT_BASE_URL = os.environ.get("API_BASE_URL", "https://pruef.st").rstrip("/")
DEFAULT_DURATION_SEC = 6 * 3600
DEFAULT_TARGET_COUNT = 1000
DEFAULT_IP_POOL_SIZE = 150
SUMMARY_INTERVAL_SEC = 300


def make_ip_pool(size: int) -> list[str]:
    """Generate a pool of synthetic IPv4 addresses for X-Real-IP rotation."""
    return [f"10.0.0.{1 + (i % 254)}" for i in range(size)]


def irregular_schedule(duration_sec: int, num_events: int) -> list[float]:
    """
    Return sorted offsets in [0, duration_sec) for num_events, with irregular gaps.
    Uses exponential-ish inter-arrival times so spacing feels natural.
    """
    if num_events <= 0:
        return []
    if num_events == 1:
        return [duration_sec / 2]
    # Target mean gap
    mean_gap = duration_sec / (num_events - 1)
    gaps = []
    for _ in range(num_events - 1):
        # Exponential with mean = mean_gap; clip so we don't get huge gaps
        g = random.expovariate(1.0 / mean_gap)
        g = max(1.0, min(g, mean_gap * 4))
        gaps.append(g)
    # Scale so total ≈ duration_sec
    total = sum(gaps)
    scale = (duration_sec - 1) / total if total > 0 else 1
    gaps = [g * scale for g in gaps]
    offsets = [0.0]
    t = 0.0
    for g in gaps:
        t += g
        if t < duration_sec:
            offsets.append(t)
    offsets.append(float(duration_sec - 0.5))
    offsets.sort()
    return offsets[:num_events]


def run(
    base_url: str,
    duration_sec: int,
    target_count: int,
    ip_pool_size: int,
    load_test_key: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    ip_pool = make_ip_pool(ip_pool_size)
    schedule = irregular_schedule(duration_sec, target_count)
    api_url = f"{base_url}/api/check"
    start = time.monotonic()
    start_wall = datetime.now(timezone.utc)
    next_summary = start + SUMMARY_INTERVAL_SEC
    ok = 0
    rate_limited = 0
    errors = 0

    if dry_run:
        print(f"Dry run: would send {len(schedule)} requests over {duration_sec}s")
        print(f"First 5 offsets (sec): {[round(schedule[i], 1) for i in range(min(5, len(schedule)))]}")
        print(f"Last 5 offsets (sec): {[round(schedule[i], 1) for i in range(max(0, len(schedule)-5), len(schedule))]}")
        return

    print(f"Starting load test: {len(schedule)} requests over {duration_sec}s ({duration_sec/3600:.1f}h)")
    print(f"Base URL: {base_url}")
    if load_test_key:
        print("Rate limit: bypass (X-Load-Test-Key)")
    print("---")

    for i, offset_sec in enumerate(schedule):
        # Sleep until this event time
        elapsed = time.monotonic() - start
        to_sleep = offset_sec - elapsed
        if to_sleep > 0:
            time.sleep(to_sleep)

        ip = random.choice(ip_pool)
        headers = {"X-Real-IP": ip}
        if load_test_key:
            headers["X-Load-Test-Key"] = load_test_key
        try:
            r = requests.post(api_url, headers=headers, timeout=15)
            if r.status_code == 200:
                ok += 1
                body = r.json()
                if verbose:
                    print(f"{datetime.now(timezone.utc).isoformat()} OK ip={ip} count={body.get('count')}")
            elif r.status_code == 429:
                rate_limited += 1
                if verbose:
                    print(f"{datetime.now(timezone.utc).isoformat()} 429 ip={ip} (rate limited)")
            else:
                errors += 1
                if verbose:
                    print(f"{datetime.now(timezone.utc).isoformat()} {r.status_code} ip={ip}")
        except Exception as e:
            errors += 1
            if verbose:
                print(f"{datetime.now(timezone.utc).isoformat()} error ip={ip} {e}", file=sys.stderr)

        # Summary every SUMMARY_INTERVAL_SEC
        now = time.monotonic()
        if now >= next_summary:
            elapsed_wall = (datetime.now(timezone.utc) - start_wall).total_seconds()
            print(f"[{elapsed_wall/60:.0f} min] ok={ok} 429={rate_limited} err={errors} (sent {i+1}/{len(schedule)})")
            next_summary = now + SUMMARY_INTERVAL_SEC

    elapsed_wall = (datetime.now(timezone.utc) - start_wall).total_seconds()
    print("---")
    print(f"Done. ok={ok} 429={rate_limited} err={errors} in {elapsed_wall/60:.1f} min")


def main() -> None:
    p = argparse.ArgumentParser(description="Simulate ~1000 counts over 6h at irregular intervals")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    p.add_argument("--duration", type=int, default=DEFAULT_DURATION_SEC, help="Run duration in seconds")
    p.add_argument("--target-count", type=int, default=DEFAULT_TARGET_COUNT, help="Target number of counts")
    p.add_argument("--ip-pool-size", type=int, default=DEFAULT_IP_POOL_SIZE, help="Synthetic IP pool size")
    p.add_argument("--load-test-key", default=os.environ.get("LOAD_TEST_KEY", ""), help="Bypass rate limit (match server LOAD_TEST_BYPASS_KEY)")
    p.add_argument("--dry-run", action="store_true", help="Print schedule only")
    p.add_argument("--verbose", action="store_true", help="Log every request")
    args = p.parse_args()

    base = (args.base_url or "").rstrip("/")
    if not base:
        print("Set API_BASE_URL or pass --base-url", file=sys.stderr)
        sys.exit(1)

    load_key = (args.load_test_key or "").strip() or None

    run(
        base_url=base,
        duration_sec=args.duration,
        target_count=args.target_count,
        ip_pool_size=args.ip_pool_size,
        load_test_key=load_key,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
