# Home Energy Intelligence (HEI)

A UK-focused, multi-user energy intelligence platform. The first release focuses on electricity and starts with an extensible supplier-provider architecture, beginning with Octopus Energy.

## Current status

**Early development.** The API foundation, secure account lifecycle, and first responsive account-recovery frontend are in place. The Octopus adapter remains a placeholder: live supplier linking is deliberately held back until credential storage, consent, and ingestion are ready.

## Architecture

- **API:** FastAPI, Python 3.12
- **Database:** PostgreSQL with SQLAlchemy and Alembic
- **Rate limiting / revocation:** Redis
- **Web client:** responsive static web application served by Nginx
- **Providers:** supplier-neutral interface; Octopus Energy first
- **Deployment:** Docker Compose

## Quick start

1. Copy `.env.example` to `.env`.
2. Set a unique `SECRET_KEY` and configure SMTP values. Email verification and password recovery require working SMTP.
3. Start the services:

   ```bash
   docker compose up --build
   ```

4. Open the web client at http://localhost:3000.
5. Open API documentation at http://localhost:8000/docs.
6. Health check: http://localhost:8000/health.

The web client is served through Nginx. It proxies `/api/` and `/health` to the API, so browser requests remain same-origin. Password reset links use `FRONTEND_BASE_URL` (default `http://localhost:3000`).

## Account recovery

- The forgot-password form posts to `POST /api/v1/auth/forgot-password`.
- The reset link opens `/reset-password?token=...`.
- The new-password form posts to `POST /api/v1/auth/reset-password`.
- Reset tokens are random, hashed at rest, expire after the configured period, and can only be used once.
- A successful reset revokes all refresh sessions and invalidates access tokens across devices.

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and `SMTP_USE_STARTTLS` in `.env`. Never commit real credentials.

## Project layout

```
backend/
  app/
    api/          # HTTP routes
    core/         # configuration, security, email
    db/           # database setup and models
    providers/    # supplier integrations
    schemas/      # API schemas
  alembic/
  tests/
frontend/
  index.html      # account recovery screens
  app.js          # API interactions
  styles.css      # responsive UI
  nginx.conf      # same-origin API proxy
docs/
.github/workflows/
```

## Development

Install backend dependencies and run the API:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --app-dir backend
```

Run backend tests:

```bash
PYTHONPATH=backend pytest backend/tests
```

Check frontend JavaScript syntax:

```bash
node --check frontend/app.js
```

## Security principles

- Never commit `.env`, API keys, account numbers, MPANs, or personal energy data.
- Supplier credentials must be stored encrypted at rest before real account linking is introduced.
- Keep supplier access read-only unless a future feature has a clear, separately reviewed need.
- Use per-user authorization and tenant isolation for every account, meter, and reading.
- Do not expose raw supplier responses or personal data in logs.
- Do not expose whether an email address has an account during password recovery.

See [SECURITY.md](SECURITY.md) and [docs/ROADMAP.md](docs/ROADMAP.md).
