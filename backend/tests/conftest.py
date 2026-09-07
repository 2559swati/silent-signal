import os

# Ensure tests use an SQLite database instead of requiring a running Postgres instance.
# This is only for the test environment; the application itself still uses the PostgreSQL URL
# defined in settings.DATABASE_URL.
os.environ.setdefault("TEST_DATABASE_URL", "sqlite:///./test.db")
