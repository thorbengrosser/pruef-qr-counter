"""All routes: pages, API, admin, dashboard, health, legal."""
import logging
from flask import (
    Blueprint,
    request,
    jsonify,
    render_template,
    Response,
    current_app,
)
from functools import wraps

from .config import ADMIN_KEY, DASHBOARD_USER, DASHBOARD_PASSWORD
from .db import (
    get_client_ip,
    user_id_from_ip,
    get_count,
    do_check,
    admin_reset,
    admin_adjust,
    dashboard_stats,
    get_db,
)

logger = logging.getLogger(__name__)

bp = Blueprint("main", __name__)


def require_admin(f):
    """Admin key via X-Admin-Key header only (avoids query params in access logs)."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        key = request.headers.get("X-Admin-Key")
        if not ADMIN_KEY or key != ADMIN_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapped


def require_dashboard_auth(f):
    """Flask-level HTTP Basic Auth for dashboard."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == DASHBOARD_USER and auth.password == DASHBOARD_PASSWORD):
            return Response(
                "Login required",
                401,
                {"WWW-Authenticate": 'Basic realm="Dashboard"'},
            )
        return f(*args, **kwargs)
    return wrapped


# ----- Pages (mobile-first, German copy) -----


@bp.route("/")
def landing():
    return render_template("landing.html")


@bp.route("/form")
def form():
    return render_template("form.html")


@bp.route("/processing")
def processing():
    return render_template("processing.html")


@bp.route("/bescheid")
def bescheid():
    return render_template("bescheid.html")


@bp.route("/widerspruch-pruefung")
def widerspruch_pruefung():
    """Intermediate re-check screen: spinner + lines for 1.2–2s, then redirect to result."""
    return render_template("widerspruch_pruefung.html")


@bp.route("/widerspruch")
def widerspruch():
    return render_template("widerspruch.html")


@bp.route("/info")
def info():
    return render_template("info.html")


@bp.route("/impressum")
def impressum():
    return render_template("impressum.html")


@bp.route("/datenschutz")
def datenschutz():
    return render_template("datenschutz.html")


# ----- API (no auth for count; check records action) -----


@bp.route("/api/count")
def api_count():
    """ESP32-compatible: Cache-Control: no-store, minimal JSON."""
    data = get_count()
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/api/check", methods=["POST"])
def api_check():
    """Validate rate limit, record check or blocked, return count or 429."""
    ip = get_client_ip()
    user_id = user_id_from_ip(ip)

    result = do_check(user_id)

    if result.get("blocked"):
        return (
            jsonify({
                "blocked": True,
                "retry_after_seconds": result["retry_after_seconds"],
            }),
            429,
            {"Retry-After": str(result["retry_after_seconds"])},
        )
    return jsonify({"count": result["count"], "epoch": result["epoch"]})


# ----- Admin (key via header or query param) -----


@bp.route("/api/admin/reset", methods=["POST"])
@require_admin
def api_admin_reset():
    admin_reset()
    data = get_count()
    return jsonify({"ok": True, "epoch": data["epoch"]})


@bp.route("/api/admin/adjust", methods=["POST"])
@require_admin
def api_admin_adjust():
    data = request.get_json(force=True, silent=True) or {}
    delta = data.get("delta")
    if delta is None:
        return jsonify({"error": "delta required"}), 400
    try:
        delta = int(delta)
    except (TypeError, ValueError):
        return jsonify({"error": "delta must be integer"}), 400
    if abs(delta) > 10000:
        return jsonify({"error": "delta out of range (max ±10000)"}), 400
    # Use a synthetic admin user_id for adjust events (no real IP)
    admin_user_id = user_id_from_ip("admin-adjust")
    admin_adjust(admin_user_id, delta)
    return jsonify(get_count())


# ----- Dashboard (Flask Basic Auth) -----


@bp.route("/dashboard")
@require_dashboard_auth
def dashboard():
    stats = dashboard_stats()
    return render_template("dashboard.html", stats=stats)


# ----- Health -----


@bp.route("/healthz")
def healthz():
    """200 OK; optional SQLite writable check."""
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return "", 200
    except Exception as e:
        logger.warning("healthz check failed: %s", e)
        return "", 503
