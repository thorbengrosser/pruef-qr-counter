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

**After git pull:** the database lives in the Docker volume `pruef-qr_pruef-data`. Do **not** run `docker compose down -v` (the `-v` removes volumes and deletes the DB). Use `docker compose down` then `up -d` (or `up -d --build`) to rebuild without losing data. The compose file sets a fixed project name (`pruef-qr`) so the same volume is used whether you run from `web-app/` or from the repo root with `-f web-app/docker-compose.yml`.

## Run locally (no Docker)

```bash
pip install -r requirements.txt
cp .env.example .env
export DATABASE_PATH=./data/pruef.db
mkdir -p data
python run.py
```

Open http://127.0.0.1:5000

**Remote / deploy:** set `DATABASE_PATH` to a path *outside* the repo (e.g. `/var/lib/pruef-qr/pruef.db`) so `git pull` or deploy scripts never delete it. Create the dir and point `.env` at it.

## Database persistence (avoid losing data on pull)

- **Docker:** DB is in the named volume `pruef-qr_pruef-data`. Never use `docker compose down -v`; use `down` then `up -d` (or `--build`) to rebuild. If you used to run from a different path and had data in another volume (e.g. `web-app_pruef-data`), copy `/data/pruef.db` from the old volume into the new one once.
- **No Docker:** Set `DATABASE_PATH` in `.env` to a path **outside the repo** (e.g. `/var/lib/pruef-qr/pruef.db`). Create that directory once; then `git pull` and any clean/deploy won’t touch the DB.

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
