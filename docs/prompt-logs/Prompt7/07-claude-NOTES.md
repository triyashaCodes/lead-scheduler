## Prompt

The user pasted a set of Google settings (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback`) and asked: do we not need all of these, along with the authorized list?

## Human edits

- After the AI explained the options, the user chose **A**: Google's browser sign-in, with the frontend sending the ID token to the API.
- The user asked for the reason B (Auth.js) is not needed to be logged in Decisions.MD, and for this note to live under Prompt7.

## AI notes

- The backend needs only `GOOGLE_CLIENT_ID` (token audience) and `ATTORNEY_EMAILS` (the authorized list); both were already in `backend/.env.example`. The secret and redirect URI belong to the OAuth code flow, which the backend does not run.
- The pasted redirect URI pointed at a backend callback, which would be a different design (backend-run sign-in with its own session). The AI flagged this instead of adding unused config.
- No code changed. The decision is recorded in Decisions.MD under "Attorney sign-in method".
