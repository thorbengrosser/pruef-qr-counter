# PRÜF QR Counter

Privacy-conscious QR-code based counter: no cookies, no user accounts, HMAC(IP) for rate limiting. Flask + Docker + SQLite.

## Quick start (clone & run with Docker)

```bash
git clone https://github.com/thorbengrosser/pruef-qr-counter.git
cd pruef-qr-counter
cp .env.example .env
# Edit .env: set SERVER_SECRET, ADMIN_KEY, DASHBOARD_USER, DASHBOARD_PASSWORD
docker compose up -d
```

Open http://localhost:5050

## Run locally (without Docker)

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env as needed
export DATABASE_PATH=./data/pruef.db
mkdir -p data
cd web-app && python run.py
```

Then open http://127.0.0.1:5000

## Run with Docker (manual)

```bash
docker build -t pruef-qr .
docker run -p 5050:5000 \
  -v pruef-data:/data \
  -e SERVER_SECRET=your-secret \
  -e ADMIN_KEY=your-admin-key \
  -e DASHBOARD_USER=admin \
  -e DASHBOARD_PASSWORD=your-password \
  pruef-qr
```

## Pushing to GitHub

1. Create a new repository on GitHub (do not initialize with README).
2. Run:

```bash
git init
git add .
git commit -m "Initial commit: PRÜF QR Counter"
git branch -M main
git remote add origin https://github.com/thorbengrosser/pruef-qr-counter.git
git push -u origin main
```

## Environment

See `.env.example`. Required in production: `SERVER_SECRET`, `ADMIN_KEY`. Dashboard: `DASHBOARD_USER`, `DASHBOARD_PASSWORD`. Optional: `DATABASE_PATH` (default `/data/pruef.db`).

## APIs

- `GET /api/count` — returns `{ "count", "epoch" }`; `Cache-Control: no-store`. No auth.
- `POST /api/check` — records one Prüfung (rate limited: 10 per 10 min per user). Returns count or 429 with `retry_after_seconds`.
- `POST /api/admin/reset` — increment epoch (key via `X-Admin-Key` header).
- `POST /api/admin/adjust` — add delta to count (same auth).
- `GET /dashboard` — internal stats (Flask HTTP Basic Auth). Not linked from public UI.
- `GET /healthz` — 200 OK (optional SQLite check).

## Verification (no cookies)

The app does not use Flask session or set any cookies. You can verify: `curl -I http://localhost:5050/` and `curl -I http://localhost:5050/api/count` should show no `Set-Cookie` header.
