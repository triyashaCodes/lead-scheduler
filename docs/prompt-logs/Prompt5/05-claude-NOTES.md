## Prompt

Add email sending per Decisions.MD and CLAUDE.md. Add `EmailEvent` model and data access first if missing. No router or BackgroundTasks wiring.

- `EmailService` interface in `services/`, with an SMTP implementation and a console fallback when SMTP env vars are unset. Config in `core/config.py` and `.env.example`.
- `send_lead_emails(lead_id)`: a confirmation to the prospect and a notification to the attorney allowlist. The attorney email links to the lead and never attaches the resume. It opens its own session.
- One `EmailEvent` per email: PENDING, then SENT or FAILED. Failures are recorded and logged, never raised. Strip newlines from name and subject.
- Tests with a fake `EmailService`: both sent and recorded SENT, failure recorded FAILED without raising, and the fallback is used when SMTP is unset.

## Human edits

2. After the first implementation the AI listed five points to confirm. The user's answers:
   - **#1 changed:** the PENDING `EmailEvent` rows must be written in the same transaction as the lead (as Decisions.MD already says), not inside `send_lead_emails`. Result: `create_lead` writes the rows, and `send_lead_emails` only sends the lead's PENDING rows.
   - **#2 kept as-is:** `EmailService` stays in `services/`, even though resume storage was moved to `storage/`.
   - **#4 changed:** clear `SMTP_HOST` in the local `.env` so the console fallback is used.
   - **#5 changed:** the console fallback must not put personal data in default logs. Result: a WARNING with no names or addresses, and the full message at DEBUG only.
   - #3 (the service opening its own session from a session factory) was not commented on, so it stayed as built.

## AI notes

- The AI's first version wrote the PENDING rows inside `send_lead_emails`, which contradicted the "Email tracking" decision. It flagged this itself as a deviation, and the user chose to fix it.
- The attorney allowlist (`ATTORNEY_EMAILS`) replaced the separate `ATTORNEY_NOTIFICATION_EMAIL` setting, so there is one list of attorney addresses.
- Full suite after the changes: 46 tests passing.
