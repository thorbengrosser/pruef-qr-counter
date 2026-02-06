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

## Deployment

**Docker on a VPS or server (recommended)**

1. On the server (any Linux with Docker and Docker Compose):
   ```bash
   git clone <this-repo> && cd pruef_counter/web-app
   cp .env.example .env
   ```
2. Edit `.env`: set `SERVER_SECRET`, `ADMIN_KEY`, `DASHBOARD_USER`, `DASHBOARD_PASSWORD` (use strong values).
3. Start the app:
   ```bash
   docker compose up -d --build
   ```
4. The app listens on port 5050 (host) → 5000 (container). To expose it on the internet, put a **reverse proxy** in front with TLS (HTTPS):
   - **Caddy:** `caddy reverse-proxy --from your-domain.de --to localhost:5050` (Caddy gets a certificate automatically).
   - **nginx:** Proxy `https://your-domain.de` to `http://127.0.0.1:5050` and configure SSL (e.g. certbot).

After that, open `https://your-domain.de`; the QR flow and `/admin/control` work over HTTPS.

**PaaS (Railway, Fly.io, Render, etc.)**  
Use the same Docker setup if the platform supports Docker. Set the same env vars; point `DATABASE_PATH` at a persistent volume they provide. Ensure the app gets `PORT` from the environment if they inject it (the Dockerfile uses 5000; many PaaS set `PORT` and the app already reads it in `run.py` for non-Docker runs).

## Environment

See `.env.example`. Required in production: `SERVER_SECRET`, `ADMIN_KEY`. Dashboard: `DASHBOARD_USER`, `DASHBOARD_PASSWORD`.

## APIs

- `GET /api/count` — `{ "count", "epoch" }`; `Cache-Control: no-store`. No auth.
- `POST /api/check` — records one Prüfung (rate limited). Returns count or 429.
- `POST /api/admin/reset` — increment epoch (`X-Admin-Key` header).
- `POST /api/admin/adjust` — add delta (same auth).
- `GET /dashboard` — internal stats (HTTP Basic Auth). Not linked from public UI.
- `GET /admin/control` — mobile-friendly control: reset and adjust (same Basic Auth as dashboard).
- `GET /healthz` — 200 OK.

## Controlling the API from a phone (field use)

**Option A — Admin control page (recommended)**  
Bookmark `https://<your-domain>/admin/control` on your iPhone. Log in with the same dashboard user/password (Basic Auth; Safari can remember it). Use the buttons to reset the counter or adjust by +1 / −1 / custom value. No API key on the device.

**Option B — iOS Shortcuts**  
If you prefer not to open a browser, use the Shortcuts app:

1. **Reset:** New Shortcut → Add action “Get Contents of URL” → URL: `https://<your-domain>/api/admin/reset` → Method: POST → Add header: `X-Admin-Key` = your `ADMIN_KEY` value. Run to reset.
2. **Adjust:** Same, URL: `https://<your-domain>/api/admin/adjust`, Method: POST, header `X-Admin-Key`, Request Body: JSON `{"delta": 1}` (or −1). You can duplicate the shortcut and change the body for +1 and −1.

The admin key is stored inside the shortcut; use this only on a device you control.

## No cookies

The app does not set cookies. Verify: `curl -I http://localhost:5050/api/count` — no `Set-Cookie` header.
