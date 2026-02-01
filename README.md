# PRÜF QR Counter

Privacy-conscious QR-code counter for the [PRÜF](https://pruef-demos.de/) campaign. No cookies, no user accounts, HMAC(IP) rate limiting.

## Repo structure

| Directory   | Description |
|------------|-------------|
| **web-app/** | Flask app, UI, Docker. Run the counter and public flow. See [web-app/README.md](web-app/README.md). |
| **esp32/**   | ESP32 display code (placeholder). Polls `/api/count`. See [esp32/README.md](esp32/README.md). |

## Quick start

**Web app (Docker):**

```bash
cd web-app
cp .env.example .env
# Edit .env: SERVER_SECRET, ADMIN_KEY, DASHBOARD_USER, DASHBOARD_PASSWORD
docker compose up -d
```

Open http://localhost:5050

**Web app (local):**

```bash
cd web-app
pip install -r requirements.txt
cp .env.example .env
DATABASE_PATH=./data/pruef.db python run.py
```

Open http://127.0.0.1:5000

## Tech

- **web-app:** Flask, SQLite, Docker. Mobile-first UI, institutional design.
- **esp32:** Intended to poll `GET /api/count` and show the count.

See each subdirectory’s README for details.
