# Decisions

Status: **Decided** = confirmed by the user. **Proposed** = recommended in the design review, not yet explicitly confirmed.

## Auth: Decided
- Google SSO (hosted OIDC) instead of our own auth service; FastAPI only verifies the Google-issued JWT.
- Authorization is a separate attorney email allowlist from env config, so a valid Google login alone grants no access.
- Identity never travels in a request body: the token goes in the `Authorization` header only, and the caller is derived server-side from the verified token (e.g. `reached_out_by`), so no schema has a user or credential field.

## Database: Decided
- SQLite via SQLAlchemy, per the original stack; path comes from `DATABASE_URL`, not code.
- Postgres is the production upgrade path (concurrent writes, row locking for email retries); the data-access layer keeps that swap small.

## Email tracking: Decided
- `email_events` is a core entity: rows are written `PENDING` in the same transaction as the lead, then updated to `SENT` or `FAILED`.
- `SENT` means accepted by the provider, not delivered; delivery and bounce webhooks are a production item.

## Resume storage: Proposed
- Files live outside the DB behind a `ResumeStorage` interface (local disk now, S3 in production); the DB holds only key and metadata.
- Downloads go through an authenticated endpoint only; validate type by magic bytes and cap size via env.

## Email delivery: Proposed
- `EmailService` interface with SMTP (Mailhog in dev); the attorney email carries a link to the lead, not the resume attachment.
- FastAPI `BackgroundTasks` plus a retry sweep over `email_events` now; a queue and worker in production.

## Lead state machine: Proposed
- `PENDING` -> `REACHED_OUT` only, set manually by an attorney; the service enforces it and records `reached_out_at` and `reached_out_by`.
- Repeating the transition returns 409 rather than silently succeeding.

## API shape: Proposed
- `PATCH /api/leads/{id}` accepting only `state`, and a single multipart `POST /api/leads` for public submission.
- Public POST gets a size cap and a honeypot field now; rate limiting and CAPTCHA are production items.

## Duplicate leads: Proposed
- No unique constraint on email, so a prospect can resubmit; the list shows newest first.

## Layering: Decided
- `routers -> services -> data_acceses -> models`, with no business logic in routers (see `CLAUDE.md`).
