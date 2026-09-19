# CLAUDE.md

Guidance for Claude Code when working in this repo (alma-lead-scheduler).

## Stack

- **Backend** (`backend/`): FastAPI, SQLAlchemy, SQLite
- **Frontend** (`frontend/`): Next.js (App Router)

## Repo layout

```
backend/
  app/
    main.py            # FastAPI app creation, router registration only
    core/              # config (env-driven), db session/engine, shared deps
    routers/           # HTTP layer
    schemas/           # Pydantic request/response models
    services/          # business logic
    data_acceses/      # database access (SQLAlchemy queries)
    storage/           # file storage (resume interface, validation, local-disk implementation)
    models/            # SQLAlchemy ORM models
  tests/
frontend/
  app/                 # App Router routes, layouts, pages
  components/
  lib/                 # API client, helpers
```

This layout is the target; create directories as needed and keep to it.

## Backend architecture (layered)

Dependency direction is strictly downward:

`routers -> services -> data_acceses / storage -> models/DB or disk`

- **Routers**: parse/validate input via schemas, call a service, return a response. Map service errors to HTTP status codes. **No business logic, no DB queries, no SQLAlchemy imports.**
- **Schemas**: Pydantic models for API input/output. Never return ORM models directly from routers.
- **Services**: all business rules and orchestration. Framework-agnostic (no `Request`/`Response`, no HTTP concerns). Raise domain exceptions, not `HTTPException`.
- **Data_acceses**: the only layer that touches the SQLAlchemy session. Expose intent-revealing methods (`get_by_id`, `list_by_status`), no business decisions.
- **Storage**: the only layer that touches the file system (or object storage). Defines the `ResumeStorage` interface and its implementations; no business decisions.
- A layer must not import from a layer above it, and must not skip a layer (routers never call data_accesses directly).

## Configuration and secrets

- All config is env-driven, loaded in one place (`backend/app/core/config.py`, e.g. Pydantic `BaseSettings`). Never read `os.environ` scattered through the code.
- Frontend: only `NEXT_PUBLIC_*` variables are exposed to the browser; everything else stays server-side. Read env in one module (`frontend/lib/config.ts`).
- **No secrets in code**, tests, fixtures, or commits. Do not hardcode keys, tokens, passwords, or DB URLs with credentials.
- Commit `.env.example` files with placeholder values; keep real `.env*` files git-ignored.
- SQLite path comes from config (e.g. `DATABASE_URL`), not a literal in code.

## Authentication

- Auth is Google SSO; FastAPI verifies the bearer token from the `Authorization` header in one dependency (`get_current_attorney`).
- **Never accept identity or credentials in a request body** (no user id, email, or token fields in schemas). Derive the acting user from the verified token server-side.
- Authorization is a separate env-driven attorney allowlist; a valid login alone is not enough.

## Database

- SQLite via SQLAlchemy; one engine/session factory in `core/`, injected into data-access classes through FastAPI dependencies.
- Schema changes go through migrations (Alembic) once introduced; do not edit the DB by hand.

## Frontend conventions

- Use the App Router: server components by default, `"use client"` only where interactivity requires it.
- All backend calls go through a single API client in `frontend/lib/`; no ad hoc `fetch` scattered in components.
- Keep types for API payloads aligned with backend schemas.

## Git workflow

- **Small commits**: one logical change per commit, each leaving the repo in a working state.
- Imperative, concise messages (e.g. `Add lead data access`, not `updates`).
- Do not mix refactors with behavior changes or backend with unrelated frontend work in one commit.
- Never commit secrets, `.env`, SQLite DB files, `node_modules`, or virtualenvs.

## Working agreements for Claude

- Follow the layering rules above before adding any endpoint: schema -> data_acceses -> service -> router.
- Prefer minimal changes that match surrounding code; do not add dependencies without a clear need.
- Add or update tests alongside the code they cover (services tested without HTTP; routers tested via the test client).
- Ask before making architectural changes that deviate from this file.

## Commands

Fill these in as the project is scaffolded:

- Backend run: _TBD_ (e.g. `uvicorn app.main:app --reload` from `backend/`)
- Backend tests: _TBD_ (e.g. `pytest`)
- Frontend dev: _TBD_ (e.g. `npm run dev` from `frontend/`)
- Frontend lint/test: _TBD_
