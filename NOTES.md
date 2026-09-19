# NOTES: agent-generated vs hand-written

**Tool:** Claude Code (Claude Sonnet 5). Every commit with agent-written code ends with a `Co-Authored-By: Claude` trailer (`git log --grep='Co-Authored-By: Claude'`). Merge commits are the author's own. Per-prompt detail is in `docs/prompt-logs/`.

| Category | Agent-generated | Hand-written / human-directed |
| --- | --- | --- |
| Backend (`backend/app/`) | Models, schemas, data access, storage, services, routers, auth | Renamed `repositories/` to `data_acceses/`; overrode the email design (`PENDING` rows in the lead's transaction, no personal data in logs), reviewed and accepted the schema before proceedind with code |
| Backend tests | All of `backend/tests/` | Reviewed and accepted |
| Frontend (`frontend/`) | Public form, attorney pages, API client, confirm dialog | Chose Google browser sign-in; asked for the confirm-before-mark step |
| Infra (`docker-compose.yml`, `.env.example`) | Written by agent | Real `.env` values and Google OAuth client set up by hand |
| Docs (`docs/`, `README.md`) | Written up by agent | Every decision in `Decisions.MD` was made by the author |
| Process | | Design debates, PR merges, running the app, demo recording |
