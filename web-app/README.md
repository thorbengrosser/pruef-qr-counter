# PRÜF QR — Web App

Privacy-conscious QR-code counter: no cookies, no user accounts, HMAC(IP) rate limiting. Flask + SQLite.

## Quick start (Docker)

From this directory (`web-app/`):

```bash
cp .env.example .env
# Edit .env: set SERVER_SECRET, ADMIN_KEY, DASHBOARD_USER, DASHBOARD_PASSWORD
docker compose up -d
```

Open http://localhost:5050

## Run locally (no Docker)

```bash
pip install -r requirements.txt
cp .env.example .env
export DATABASE_PATH=./data/pruef.db
mkdir -p data
python run.py
```

Open http://127.0.0.1:5000

## Environment

See `.env.example`. Required in production: `SERVER_SECRET`, `ADMIN_KEY`. Dashboard: `DASHBOARD_USER`, `DASHBOARD_PASSWORD`.

## APIs

- `GET /api/count` — `{ "count", "epoch" }`; `Cache-Control: no-store`. No auth.
- `POST /api/check` — records one Prüfung (rate limited). Returns count or 429.
- `POST /api/admin/reset` — increment epoch (`X-Admin-Key` or query param).
- `POST /api/admin/adjust` — add delta (same auth).
- `GET /dashboard` — internal stats (HTTP Basic Auth). Not linked from public UI.
- `GET /healthz` — 200 OK.

## No cookies

The app does not set cookies. Verify: `curl -I http://localhost:5050/api/count` — no `Set-Cookie` header.
