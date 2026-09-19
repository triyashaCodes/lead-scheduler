import os
import tempfile

# Dummy values so the app can be imported without a .env file (e.g. in CI).
# Real environment variables and .env are overridden on purpose: tests must not
# depend on a developer's local configuration.
_TEST_ENV = {
    "DATABASE_URL": "sqlite://",
    "FRONTEND_ORIGIN": "http://localhost:3000",
    "RESUME_STORAGE_DIR": os.path.join(tempfile.gettempdir(), "alma-test-resumes"),
    "RESUME_MAX_BYTES": "1024",
    "GOOGLE_CLIENT_ID": "test-client-id",
    "ATTORNEY_EMAILS": "one@firm.example,two@firm.example",
    "SMTP_HOST": "",
    "EMAIL_FROM": "no-reply@firm.example",
}
os.environ.update(_TEST_ENV)
