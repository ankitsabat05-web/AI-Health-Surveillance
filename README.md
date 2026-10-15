# AI-Health-Surveillance

## Frontend

The static web interface is in `frontend/`. Start the FastAPI service using
the command in `docs/api.md`, then, from the project root in a second terminal,
run `python -m http.server 5500 --directory frontend` and open
`http://127.0.0.1:5500`. By default, the client connects to
`http://127.0.0.1:8000/api/v1`; set `window.HEALTH_API_BASE` before the
frontend scripts load to use a different API URL.

Registration creates a personal user account only. Health-official pages
require an active, verified health-official account provisioned by an
administrator. Report counts and AI screening results are decision-support
signals, not confirmed diagnoses or outbreaks.