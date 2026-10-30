# Home Energy Intelligence (HEI)

A UK-focused, multi-user energy intelligence platform. The first release focuses on electricity and starts with an extensible supplier-provider architecture, beginning with Octopus Energy.

## Current status

**Foundation / early development.** This repository is a starting point, not a production-ready energy service. The Octopus adapter is intentionally a placeholder until authentication, account linking, tariff retrieval, and consumption ingestion are implemented and tested.

## Planned architecture

- **API:** FastAPI, Python 3.12
- **Database:** PostgreSQL with SQLAlchemy
- **Cache / background work foundation:** Redis
- **Clients:** web app, Android app, and Home Assistant integration (planned)
- **Providers:** supplier-neutral interface; Octopus Energy first
- **Deployment:** Docker Compose for local development

## Quick start

1. Copy `.env.example` to `.env` and change the development secrets.
2. Start services:

   ```bash
   docker compose up --build
   ```

3. Open the API docs at http://localhost:8000/docs.
4. Health check: http://localhost:8000/health.

The API currently exposes health and basic platform metadata only. No supplier credentials are required or collected by this scaffold.

## Project layout

```
backend/
  app/
    api/          # HTTP routes
    core/         # configuration
    db/           # database setup and models
    providers/    # supplier integrations
    schemas/      # API schemas
  tests/
docs/
.github/workflows/
```

## Development

Install dependencies and run the API:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --app-dir backend
```

Apply database migrations (using the `DATABASE_URL` from `.env`):

```bash
alembic upgrade head
```

Create a new migration after changing SQLAlchemy models:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

Run tests:

```bash
pytest backend/tests
```

## Security principles

- Never commit `.env`, API keys, account numbers, MPANs, or personal energy data.
- Supplier credentials must be stored encrypted at rest before real account linking is introduced.
- Keep supplier access read-only unless a future feature has a clear, separately reviewed need.
- Use per-user authorization and tenant isolation for every account, meter, and reading.
- Do not expose raw supplier responses or personal data in logs.

See [SECURITY.md](SECURITY.md) and [docs/ROADMAP.md](docs/ROADMAP.md).
