"""SQLite DB, IP canonicalisation, HMAC user_id, rate limit, epoch, retention."""
import sqlite3
import hmac
import hashlib
import re
import zoneinfo
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from flask import request

from .config import (
    DATABASE_PATH,
    SERVER_SECRET,
    RATE_LIMIT_COUNT,
    RATE_LIMIT_WINDOW_SECONDS,
    BLOCK_DURATION_SECONDS,
    RETENTION_DAYS,
)


def get_client_ip():
    """Get client IP from request, respecting X-Forwarded-For (first entry) or X-Real-IP.
    Trust exactly one proxy (ProxyFix(1) should be applied in app).
    """
    if request.headers.get("X-Forwarded-For"):
        # First IP in list is client when using one proxy
        return request.headers.get("X-Forwarded-For").strip().split(",")[0].strip()
    if request.headers.get("X-Real-IP"):
        return request.headers.get("X-Real-IP").strip()
    return request.remote_addr or ""


def canonicalise_ip(ip: str) -> str:
    """Normalise IP for stable HMAC: IPv4-mapped IPv6 -> IPv4, IPv6 lowercase, strip whitespace."""
    if not ip:
        return ""
    ip = ip.strip()
    # IPv4-mapped IPv6: ::ffff:x.x.x.x -> x.x.x.x
    if ip.lower().startswith("::ffff:"):
        rest = ip[7:].strip()
        if rest and re.match(r"^[\d.]+\Z", rest):
            return rest
    # IPv6: lowercase
    if ":" in ip:
        return ip.lower()
    return ip


def user_id_from_ip(ip: str) -> str:
    """HMAC-SHA256(ip, SERVER_SECRET) as hex; store only this, never raw IP."""
    canonical = canonicalise_ip(ip)
    return hmac.new(SERVER_SECRET, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables if not exist."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id TEXT NOT NULL,
                epoch_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                delta INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
            ("current_epoch", "1"),
        )
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_epoch ON events(epoch_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_user_ts ON events(user_id, timestamp)
        """)


def get_current_epoch(conn) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", ("current_epoch",)).fetchone()
    return int(row["value"]) if row else 1


def count_current_epoch(conn) -> int:
    epoch = get_current_epoch(conn)
    row = conn.execute(
        "SELECT COALESCE(SUM(delta), 0) AS total FROM events WHERE epoch_id = ? AND event_type = ?",
        (epoch, "check"),
    ).fetchone()
    return int(row["total"]) if row else 0


def count_current_epoch_all_types(conn) -> int:
    """Sum of delta for current epoch (for display); admin_adjust and check count."""
    epoch = get_current_epoch(conn)
    row = conn.execute(
        "SELECT COALESCE(SUM(delta), 0) AS total FROM events WHERE epoch_id = ? AND event_type IN ('check', 'admin_adjust')",
        (epoch,),
    ).fetchone()
    return int(row["total"]) if row else 0


def record_event(conn, user_id: str, event_type: str, delta: int = 1):
    epoch = get_current_epoch(conn)
    conn.execute(
        "INSERT INTO events (timestamp, user_id, epoch_id, event_type, delta) VALUES (?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), user_id, epoch, event_type, delta),
    )


def purge_old_events(conn):
    """Delete events older than RETENTION_DAYS (lazy cleanup)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    conn.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))


def rate_limit_check(conn, user_id: str) -> tuple[bool, int]:
    """
    Return (allowed, retry_after_seconds).
    - If allowed: (True, 0).
    - If blocked: (False, retry_after_seconds).
    Uses rolling 10-minute window: count events of type 'check' in last 10 minutes.
    If >= RATE_LIMIT_COUNT, block for BLOCK_DURATION_SECONDS.
    Also check: if user has a 'blocked' event in last BLOCK_DURATION_SECONDS, still blocked.
    """
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)).isoformat()
    block_start = (now - timedelta(seconds=BLOCK_DURATION_SECONDS)).isoformat()

    # Count checks in rolling window
    row = conn.execute(
        """SELECT COUNT(*) AS c FROM events
           WHERE user_id = ? AND event_type = ? AND timestamp >= ?""",
        (user_id, "check", window_start),
    ).fetchone()
    check_count = row["c"] if row else 0

    # If over limit, user is blocked for BLOCK_DURATION_SECONDS
    if check_count >= RATE_LIMIT_COUNT:
        return False, BLOCK_DURATION_SECONDS

    # Check if user was recently blocked (had a blocked attempt recorded)
    row = conn.execute(
        """SELECT 1 FROM events
           WHERE user_id = ? AND event_type = ? AND timestamp >= ? LIMIT 1""",
        (user_id, "blocked", block_start),
    ).fetchone()
    if row:
        return False, BLOCK_DURATION_SECONDS

    return True, 0


def do_check(user_id: str) -> dict:
    """
    Try to record a 'check' event. Returns dict:
    - success: { "count": N, "epoch": E }
    - rate limited: raises or returns error response; caller should return 429 with blocked/retry_after_seconds
    """
    with get_db() as conn:
        allowed, retry_after = rate_limit_check(conn, user_id)
        if not allowed:
            # Log blocked attempt (per plan: log blocked attempts)
            record_event(conn, user_id, "blocked", 0)
            return {"blocked": True, "retry_after_seconds": retry_after}

        record_event(conn, user_id, "check", 1)
        purge_old_events(conn)
        count = count_current_epoch_all_types(conn)
        epoch = get_current_epoch(conn)
        return {"count": count, "epoch": epoch}


def do_check_bypass(user_id: str) -> dict:
    """Record a 'check' event without rate limiting. Used when X-Load-Test-Key matches LOAD_TEST_BYPASS_KEY."""
    with get_db() as conn:
        record_event(conn, user_id, "check", 1)
        purge_old_events(conn)
        count = count_current_epoch_all_types(conn)
        epoch = get_current_epoch(conn)
        return {"count": count, "epoch": epoch}


def get_count() -> dict:
    """Current count and epoch for GET /api/count."""
    with get_db() as conn:
        count = count_current_epoch_all_types(conn)
        epoch = get_current_epoch(conn)
        return {"count": count, "epoch": epoch}


def admin_reset():
    """Increment current_epoch; do not delete data."""
    with get_db() as conn:
        epoch = get_current_epoch(conn)
        conn.execute("UPDATE meta SET value = ? WHERE key = ?", (str(epoch + 1), "current_epoch"))
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            ("last_reset_ts", datetime.now(timezone.utc).isoformat()),
        )


def admin_adjust(user_id: str, delta: int):
    """Record admin_adjust event (delta can be negative)."""
    with get_db() as conn:
        record_event(conn, user_id, "admin_adjust", delta)
        purge_old_events(conn)


def dashboard_stats():
    """Stats for current epoch: total events (check+admin_adjust), unique users, peak per minute.
    Optional: daily counts (day = midnight Berlin).
    """
    tz = zoneinfo.ZoneInfo("Europe/Berlin")

    with get_db() as conn:
        epoch = get_current_epoch(conn)
        # Total count (same as API)
        row = conn.execute(
            """SELECT COALESCE(SUM(delta), 0) AS total FROM events
               WHERE epoch_id = ? AND event_type IN ('check', 'admin_adjust')""",
            (epoch,),
        ).fetchone()
        total = int(row["total"]) if row else 0

        # Distinct user_id in current epoch
        row = conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS u FROM events WHERE epoch_id = ?",
            (epoch,),
        ).fetchone()
        unique_users = int(row["u"]) if row else 0

        # Peak per minute: group by minute (UTC), then take max
        rows = conn.execute(
            """SELECT strftime('%Y-%m-%dT%H:%M', timestamp) AS min_utc, SUM(delta) AS c
               FROM events WHERE epoch_id = ? AND event_type IN ('check', 'admin_adjust')
               GROUP BY min_utc""",
            (epoch,),
        ).fetchall()
        peak_per_minute = max((int(r["c"]) for r in rows), default=0)

        # Daily counts: day boundary midnight Berlin
        # Convert UTC timestamp to Berlin date and group
        rows = conn.execute(
            """SELECT timestamp, delta FROM events
               WHERE epoch_id = ? AND event_type IN ('check', 'admin_adjust')""",
            (epoch,),
        ).fetchall()
        daily = {}
        for r in rows:
            dt_utc = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
            dt_berlin = dt_utc.astimezone(tz)
            day = dt_berlin.strftime("%Y-%m-%d")
            daily[day] = daily.get(day, 0) + int(r["delta"])

        return {
            "epoch": epoch,
            "total": total,
            "unique_users": unique_users,
            "peak_per_minute": peak_per_minute,
            "daily": daily,
        }
