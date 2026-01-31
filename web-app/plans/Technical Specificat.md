# PRÜF QR Counter — Technical Specification (LLM Implementation Guide)
Version: 1.0  
Status: Approved  
Scope: Backend logic, APIs, data model, constraints  
Hosting: VPS with Apache reverse proxy  
Preferred stack: Flask + Docker + SQLite (LLM may adjust details, not constraints)

---

## 1. Core Requirements

This project implements a lightweight, privacy-conscious QR scan counter with:
- no cookies
- no user accounts
- no third-party services
- minimal infrastructure
- predictable low load

Primary purpose:
- count explicit user actions (“Prüfungen”)
- expose a real-time counter via API
- provide basic statistics for internal use

---

## 2. Privacy & Tracking Constraints

### 2.1 Cookies
- The system MUST NOT set cookies.
- No session cookies.
- No tracking cookies.
- No consent banner required.

### 2.2 User Identification (Anonymised)

User identity is derived from the **client IP address**, anonymised via cryptographic hashing.

#### Specification:
- Extract client IP address from request (respect reverse proxy headers).
- Compute:
  - `user_id = HMAC-SHA256(ip_address, SERVER_SECRET)`
- Store ONLY the resulting hash.
- Never store raw IP addresses in the application database.
- Hash must be irreversible (HMAC, not plain hash).

Purpose:
- approximate unique users
- enable rate limiting
- generate statistics

Note:
- Apache access logs may still contain IPs; this is outside application scope.

---

## 3. Action Definition (“Prüfung”)

- A “Prüfung” is recorded **only** when the user explicitly triggers the primary action
  (e.g. presses “Antrag faxen”).
- Page loads do NOT increment the counter.

Each valid action creates one database record.

---

## 4. Rate Limiting / Abuse Control

Rate limiting is applied **per user_id**.

Rules:
- Allow up to **10 Prüfungen per 10-minute rolling window**.
- If limit exceeded:
  - user enters blocked state for **10 minutes**
  - blocked actions are NOT counted
  - return HTTP `429 Too Many Requests`
  - response payload includes retry time

Example response:
```json
{
  "blocked": true,
  "retry_after_seconds": 600
}
````

---

## 5. Data Retention

* All events older than **90 days** may be automatically purged.
* Purging may be implemented via:

  * scheduled task
  * lazy cleanup on write
* Retention applies to all event types.

---

## 6. Epoch / Reset Logic

The system supports logical resets **without deleting data**.

### 6.1 Epoch Concept

* Maintain a global `current_epoch` value.
* Each event stores:

  * `epoch_id`

### 6.2 Reset Behaviour

* Reset increments `current_epoch`.
* API counters only count events in `current_epoch`.
* Old data remains stored but ignored.

Purpose:

* allows resets during live demos
* preserves historical data for analysis

---

## 7. Database (SQLite)

SQLite is sufficient. No external DB installation.

### Required Tables (conceptual)

#### events

* id (integer, primary key)
* timestamp (UTC)
* user_id (hashed)
* ip_hash (same as user_id, optional duplication allowed)
* epoch_id (integer)
* event_type (string: "check", "admin_adjust", etc.)
* delta (integer, default 1)

#### meta

* key (string)
* value (string/int)
  Examples:
* current_epoch
* last_reset_ts

---

## 8. APIs

### 8.1 Public Count API (ESP32 compatible)

Endpoint:

```
GET /api/count
```

Response:

```json
{
  "count": 12345,
  "epoch": 7
}
```

Requirements:

* extremely small payload
* safe to poll every 1–5 seconds
* must send `Cache-Control: no-store`

---

### 8.2 Action API (Increment)

Endpoint:

```
POST /api/check
```

Behaviour:

* validates rate limits
* records event if allowed
* returns updated count or status

---

### 8.3 Admin APIs (Protected via Key)

Admin endpoints MUST require an admin key.

Authentication:

* `X-Admin-Key` header OR query param
* key is stored server-side (env var)
* never exposed to frontend JS

#### Reset

```
POST /api/admin/reset
```

Effect:

* increments epoch
* does NOT delete data

#### Manual Adjust

```
POST /api/admin/adjust
```

Payload example:

```json
{
  "delta": 50
}
```

Notes:

* Prefer delta-based adjustment (not absolute set)
* Adjustment events must be logged

---

## 9. Dashboard (Internal)

Purpose:

* internal visibility
* not public

Security:

* simple password protection (e.g. HTTP Basic Auth)
* may be enforced at reverse proxy or app level

Metrics:

* total events (current epoch)
* unique users (distinct user_id)
* peak rate (max per minute)
* optionally: daily counts

UI can be minimal and unstyled.

---

## 10. Frontend Assumptions

* JavaScript is allowed and expected.
* Frontend does NOT need to know:

  * admin keys
  * reset logic
  * internal stats
* Frontend only calls:

  * `/api/check`
  * `/api/count`

---

## 11. Deployment Constraints

* Application must run in Docker.
* SQLite database stored on persistent volume.
* Reverse proxied via Apache.
* Low load expected (50–1000 users over ~3 hours).

---

## 12. Non-Goals

* No authentication system
* No user profiles
* No cookies
* No analytics SDKs
* No external services
* No tracking pixels

---

## 13. Success Criteria

The implementation is correct if:

* counter increments reliably
* no cookies are set
* no raw IPs are stored in DB
* ESP32 can poll count reliably
* reset does not delete data
* dashboard shows sane numbers
* system survives live demo without intervention

```

