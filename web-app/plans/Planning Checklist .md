# PRÜF QR Mini-App — Planning Checklist (Remaining Decisions & Risk Checks)
Goal: Identify remaining open decisions and demo-day risks.  
Scope: Tech/ops details only (flow, design, and main tech spec already agreed).

---

## A) Reverse Proxy & Real Client IP (CRITICAL)
- Confirm Apache reverse proxy forwards real client IP correctly:
  - `X-Forwarded-For` and/or `X-Real-IP` set as intended.
- Confirm Flask trusts only the known proxy (prevent spoofed headers).
- Decide exact IP source priority:
  - Prefer `X-Forwarded-For` (first non-proxy IP) vs. `X-Real-IP` fallback.
- Define canonical IP normalisation before HMAC:
  - IPv6 compressed/expanded forms
  - IPv4-mapped IPv6 (`::ffff:x.x.x.x`)
  - Strip whitespace, lower-case where applicable

**Outcome:** App computes stable user_id = HMAC(canonical_ip, SERVER_SECRET).

---

## B) Rate Limiting Behaviour (User Experience)
- Confirm rate limit rules exactly:
  - 10 checks per rolling 10 minutes per user_id
  - if exceeded: block 10 minutes
- Decide whether blocked attempts are logged (recommended: log as `blocked` event_type OR don’t log at all).
- Define response format for blocked:
  - HTTP 429
  - JSON includes `blocked: true` and `retry_after_seconds`
- Frontend behaviour on block:
  - show clear message + countdown hint (optional)
  - do not auto-retry

---

## C) Double Submit / Tap Spam Handling
- Decide UI rule for accidental double taps:
  - disable primary button for ~500ms after tap
- Confirm backend remains source of truth (rate limit still applies).
- Ensure no silent retry that might double-increment.

---

## D) “No Cookies” Enforcement (Framework Defaults)
- Confirm Flask app does not use sessions/flash/CSRF middleware that sets cookies.
- Confirm no third-party analytics/pixels.
- Confirm headers do not set cookies:
  - ensure no `Set-Cookie` in responses

---

## E) API Caching & Polling Correctness (ESP32)
- Ensure `/api/count` always returns fresh values:
  - add `Cache-Control: no-store`
  - `Content-Type: application/json`
- Keep payload minimal: `{ "count": n, "epoch": e }`
- Decide if optional ETag/304 is used (not required).

---

## F) Admin Key Handling & Safety
- Decide admin key transport:
  - `X-Admin-Key` header preferred (or query param if needed)
- Ensure admin key never appears in:
  - frontend JS
  - HTML
  - logs (avoid request dumps)
- Decide key rotation procedure:
  - update env var + restart container

---

## G) Dashboard Protection
- Decide where Basic Auth lives:
  - Preferred: Apache-level Basic Auth in reverse proxy
  - Alternative: Flask-level auth
- Decide dashboard URL path (not linked in UI).
- Confirm dashboard exposes only aggregated stats (no raw IPs, no keys).

---

## H) Data Retention (90 days) — Cleanup Mechanism
- Decide cleanup approach:
  - Lazy cleanup on write (simple)
  - Cron/scheduled job (more ops)
- Confirm retention applies to all event types (check, blocked, admin_adjust).

---

## I) Time & Timezone
- Confirm DB timestamps stored in UTC.
- Decide dashboard display timezone:
  - Europe/Berlin vs UTC
- Define “day boundary” used for daily charts.

---

## J) Minimal Ops Observability
- Decide minimal health check endpoint:
  - `/healthz` returns 200 OK + maybe sqlite writable check
- Decide logging level and log location (stdout for Docker).
- Confirm error messages are user-friendly but not verbose.

---

## K) Network Failure Behaviour
- Define frontend response on `/api/check` failure:
  - show “Fax fehlgeschlagen. Erneut faxen.”
- Confirm backend is idempotent only where intended (generally not idempotent; each allowed call counts).

---

## L) Legal Links on Every Screen
- Confirm Impressum/Datenschutz links exist on every screen (footer).
- Decide interim implementation:
  - static routes `/impressum`, `/datenschutz`
  - placeholder content until final text is ready

---

## Deliverable for Planning Mode
For each section A–L, the system should:
1) Ask only the missing question(s) required to decide.
2) Record the decision as a short “Resolved:” note.
3) Produce a final “Ops/Config checklist” that can be executed before demo day.
