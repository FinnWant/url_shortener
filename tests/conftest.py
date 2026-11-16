import os

# app.main builds a module-level app at import time, which requires these.
os.environ.setdefault("ADMIN_TOKEN", "test-import-token")
os.environ.setdefault("DB_PATH", os.path.join(os.environ.get("TMPDIR", "/tmp"), "import-test.db"))
