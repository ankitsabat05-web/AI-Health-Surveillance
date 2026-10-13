# API Reference

## Base URL and availability

The default versioned API prefix is `/api/v1`. Start the application from the
project root with:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

The routers are mounted by `backend/app/main.py`. Interactive OpenAPI docs are
available at `/docs` and the JSON schema at `/openapi.json` when the app is not
running in production. Both are disabled in production.

Use ISO 8601 dates and timestamps. Invalid request values return HTTP 422.
Schemas that explicitly forbid extra fields also reject unexpected fields.

## Authentication

Protected routes use a bearer access token:

```http
Authorization: Bearer <access_token>
```

Registration creates an ordinary user account. Official and administrator
access requires the corresponding active, verified official record; it is not
granted by public registration.

### `POST /api/v1/auth/register`

Create a user account.

```json
{
  "full_name": "Example User",
  "email": "user@example.com",
  "password": "use-a-long-unique-password"
}
```

Password length: 12–128 characters. Returns `201 Created` with the user
profile (never the password or its hash).

### `POST /api/v1/auth/login`

Authenticate with form-encoded OAuth2 password fields, not JSON:

```text
username=user@example.com&password=use-a-long-unique-password
```

Returns an access token and its lifetime in seconds:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 900
}
```

### `GET /api/v1/auth/me`

Return the authenticated user's profile. Requires a bearer token.

## Users

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/users/me` | Authenticated user | Read own profile |
| `PATCH` | `/api/v1/users/me` | Authenticated user | Update own full name |
| `POST` | `/api/v1/users/me/change-password` | Authenticated user | Change password; returns 204 |
| `GET` | `/api/v1/users/{user_id}` | Verified health official | Read a user's profile |
| `PATCH` | `/api/v1/users/{user_id}/deactivate` | Verified administrator | Deactivate another account |

`PATCH /users/me` request:

```json
{
  "full_name": "Updated Name"
}
```

`POST /users/me/change-password` request:

```json
{
  "current_password": "current-password",
  "new_password": "a-different-long-password"
}
```

## Health reports

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/reports/` | Authenticated user | Submit a health report |
| `GET` | `/api/v1/reports/my-reports` | Authenticated user | List own reports |
| `GET` | `/api/v1/reports/{report_id}` | Owner or health official/admin | Read one report |
| `GET` | `/api/v1/reports/` | Verified health official | List reports for surveillance |
| `PATCH` | `/api/v1/reports/{report_id}/status` | Verified health official | Change a report's review status |

Create-report example:

```json
{
  "disease_name": "Dengue",
  "symptoms": ["fever", "headache", "joint pain"],
  "region_id": "IN-MH-MUM",
  "description": "Symptoms began yesterday."
}
```

List endpoints accept `limit` (1–100) and `offset` (0 or greater). The
official report list also accepts `report_status` (`submitted`,
`under_review`, `verified`, or `rejected`) and `region_id`.

Responses contain report metadata such as `id`, `user_id`, symptoms, region,
status, and creation time. Reported disease names and symptoms are user input,
not verified diagnoses.

## Dashboards and administration

These endpoints require a verified health official according to the current
route dependencies.

| Method | Path | Query parameters | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/dashboard/overview` | None | Totals, today's reports, last-seven-day reports, distinct diseases |
| `GET` | `/api/v1/admin/dashboard` | `report_date` (optional, `YYYY-MM-DD`) | Daily totals, top reported diseases, busiest regions |
| `GET` | `/api/v1/admin/reports/daily` | `report_date` (optional, `YYYY-MM-DD`) | Daily report status counts |
| `GET` | `/api/v1/admin/trends/disease` | `disease_name`, `start_date`, `end_date` | Daily reports for one disease; range is limited to 366 days |

These summaries count reports, not necessarily laboratory-confirmed cases.

## Alerts

All alert routes require a verified health official.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/alerts` | List/filter alerts |
| `GET` | `/api/v1/alerts/{alert_id}` | Read an alert |
| `POST` | `/api/v1/alerts/{alert_id}/acknowledge` | Acknowledge an alert |
| `POST` | `/api/v1/alerts/{alert_id}/resolve` | Resolve an alert |

List filters: `severity`, `status`, `disease_name`, `region_id`, `limit`
(1–100), and `offset`. Alert statuses are `new`, `acknowledged`, and
`resolved`; severities are `low`, `moderate`, `high`, and `critical`.
Acknowledging or resolving an alert is an administrative workflow action, not
confirmation of an outbreak.

## AI health intelligence

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/ai/health` | Authenticated user | Check AI API-layer availability |
| `POST` | `/api/v1/ai/symptoms/analyze` | Authenticated user | Preliminary symptom screening |
| `POST` | `/api/v1/ai/trends/forecast` | Verified health official | Forecast a disease trend from supplied history |
| `POST` | `/api/v1/ai/outbreaks/analyze` | Verified health official | Screen supplied case counts for unusual increases |
| `POST` | `/api/v1/ai/hotspots/analyze` | Verified health official | Compare regional rates with historical data |
| `POST` | `/api/v1/ai/risk/assess` | Verified health official | Calculate a preliminary risk assessment |
| `POST` | `/api/v1/ai/recommendations` | Verified health official | Generate recommendations for official review |

AI request and response schemas are defined next to the analysis modules in
`backend/app/ai/`. Consult `/docs` for the complete field constraints and
current response shapes. The symptom endpoint provides screening, not a
diagnosis. Trend, outbreak, hotspot, risk, and recommendation results require
human review and must not be presented as confirmed public-health findings.

## System endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Application name, version, and status |
| `GET` | `/health` | Lightweight liveness check |

## Error responses

Errors use a JSON envelope. HTTP errors generally look like:

```json
{
  "success": false,
  "error": {
    "code": 401,
    "message": "Invalid or expired authentication credentials."
  }
}
```

Validation errors use HTTP 422 and may include a `details` array with field
paths and validation messages. Common status codes include:

| Status | Meaning |
|---|---|
| `201` | Resource created |
| `204` | Request succeeded with no response body |
| `401` | Missing, invalid, or expired credentials |
| `403` | Authenticated user lacks the required role |
| `404` | Resource not found or not visible to the caller |
| `409` | State or uniqueness conflict |
| `422` | Request validation failed |
| `503` | A required database or analysis service is unavailable |
| `500` | Unexpected server error |
