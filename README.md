# Alma Lead Scheduler

Public lead intake form plus an auth-guarded internal UI for attorneys to review leads and mark them as reached out.

- **Backend:** FastAPI + SQLAlchemy + SQLite (`backend/`)
- **Frontend:** Next.js App Router (`frontend/`)

Design decisions live in [docs/Decisions.MD](docs/Decisions.MD). Contributor and architecture rules live in [CLAUDE.md](CLAUDE.md). A PDF copy of the guide below is at [docs/Running-Locally.pdf](docs/Running-Locally.pdf).

## Deliverables

| Deliverable | Where |
| --- | --- |
| Public GitHub repo | [github.com/triyashaCodes/lead-scheduler](https://github.com/triyashaCodes/lead-scheduler) |
| How to run locally | [Running locally](#running-locally) below, also as a [PDF](docs/Running-Locally.pdf) |
| Design document (why and how) | [docs/Design.md](docs/Design.md): summary, tradeoffs and production changes, with the [architecture diagram](docs/architecture-hld.png). Full reasoning and rejected alternatives: [docs/Decisions.MD](docs/Decisions.MD) |
| Coding-agent usage: short writeup (½ page) | [docs/AI-Usage-Writeup.md](docs/AI-Usage-Writeup.md) |
| Coding-agent usage: prompt logs | [docs/Prompt-Logs.md](docs/Prompt-Logs.md) (excerpts), per-prompt notes in [docs/prompt-logs/](docs/prompt-logs/) |
| Coding-agent usage: attribution (agent vs hand-written) | [NOTES.md](NOTES.md), plus a `Co-Authored-By: Claude` trailer on agent commits |
| GitHub link uploaded to the assignment document | Pending |
| Screen recording of the end-to-end workflow | Pending |

## Running locally

### Prerequisites

- Python 3.12 and Node.js 20 or newer (with npm)
- Docker, to run Mailhog (a local inbox that catches outgoing email)
- A Google OAuth client ID, for attorney sign-in (see step 3)

### 1. Start Mailhog

Mailhog accepts email on port 1025 and shows it at http://localhost:8025. Nothing is delivered to real addresses.

```bash
docker run -d --name mailhog --platform linux/amd64 -p 1025:1025 -p 8025:8025 mailhog/mailhog
```

Later, use `docker start mailhog` and `docker stop mailhog`. To skip Mailhog, leave `SMTP_HOST` empty in the backend `.env`: emails are then only logged to the console.

### 2. Set up the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env`:

| Variable | Value for local use |
| --- | --- |
| `DATABASE_URL` | `sqlite:///./app.db` (default) |
| `FRONTEND_ORIGIN` | `http://localhost:3000` |
| `RESUME_STORAGE_DIR` | `./storage/resumes` (default) |
| `RESUME_MAX_BYTES` | `5242880` (5 MB) |
| `GOOGLE_CLIENT_ID` | your Google OAuth client ID |
| `ATTORNEY_EMAILS` | comma-separated Google accounts allowed to sign in; they also receive lead notifications |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS` | `localhost`, `1025`, `false` for Mailhog |
| `EMAIL_FROM` | any sender address, e.g. `no-reply@example.com` |

### 3. Create a Google OAuth client

1. In Google Cloud Console, open APIs & Services, then Credentials, and create an OAuth client ID of type **Web application**.
2. Add `http://localhost:3000` under **Authorized JavaScript origins**.
3. If the consent screen is in "Testing", add your Google account as a test user.
4. Use the client ID in both `GOOGLE_CLIENT_ID` (backend) and `NEXT_PUBLIC_GOOGLE_CLIENT_ID` (frontend).

### 4. Start the backend

From `backend/` with the virtualenv active:

```bash
uvicorn app.main:app --reload
```

The API runs at http://localhost:8000 and its docs are at http://localhost:8000/docs. Tables are created automatically on startup, and `backend/app.db` is created on first run.

### 5. Set up and start the frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Edit `frontend/.env.local`:

| Variable | Value for local use |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000/api` |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | the same client ID as the backend |
| `NEXT_PUBLIC_RESUME_MAX_BYTES` | `5242880` (must match the backend) |

The app runs at http://localhost:3000.

### 6. Try the whole flow

1. Open http://localhost:3000/apply and submit the form with a PDF, DOC or DOCX resume.
2. Open http://localhost:8025. Two emails should be there: a confirmation to the prospect and a notification to the attorney, which links to the lead and has no attachment.
3. Open http://localhost:3000/leads and sign in with a Google account listed in `ATTORNEY_EMAILS`.
4. Open the lead, download the resume, and mark it as reached out. Doing it a second time is rejected.

### Running the tests

```bash
cd backend
source .venv/bin/activate
pytest
```

### Inspecting the database

The database is a plain SQLite file. Reading it while the app runs is safe:

```bash
sqlite3 backend/app.db "SELECT id, email, state FROM leads ORDER BY created_at DESC;"
```

### Troubleshooting

- **Frontend fails at startup with "Missing required environment variable":** fill in every value in `frontend/.env.local`, then restart `npm run dev`.
- **Browser shows a CORS error:** `FRONTEND_ORIGIN` must exactly match the frontend URL, including the port. Restart uvicorn after changing `.env`.
- **Google sign-in is refused:** check the authorized JavaScript origin, and that your account is a test user if the consent screen is in "Testing".
- **Signed in but get "not on the attorney list":** add that exact Google email to `ATTORNEY_EMAILS` and restart the backend.
- **No emails appear in Mailhog:** confirm the container is running, `SMTP_HOST=localhost`, `SMTP_PORT=1025` and `SMTP_STARTTLS=false`, then restart the backend.
- **Errors about missing columns or tables after a model change:** there are no migrations yet. Stop the backend, delete `backend/app.db` and start it again. This erases all local leads.

## Status

Working locally: public lead form, resume storage, email notifications, attorney sign-in and lead review. Not yet built: rate limiting or CAPTCHA on the public form, email retries, delivery tracking, Alembic migrations, and S3 resume storage.
