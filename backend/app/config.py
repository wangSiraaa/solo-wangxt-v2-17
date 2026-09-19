import os

# PostgreSQL in deployment (docker-compose), SQLite for local dev/tests.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

EXPORT_DIR = os.path.abspath(
    os.getenv("EXPORT_DIR", os.path.join(os.path.dirname(__file__), "..", "exports"))
)

# Background export worker.
RUN_WORKER = os.getenv("RUN_WORKER", "1") == "1"
EXPORT_WORKER_INTERVAL_SECONDS = float(os.getenv("EXPORT_WORKER_INTERVAL_SECONDS", "4"))
# Artificial delay between the two permission checkpoints of an export so the
# withdrawal-vs-export race is observable in the demo.
EXPORT_WORKER_DELAY_SECONDS = float(os.getenv("EXPORT_WORKER_DELAY_SECONDS", "3"))

# Download links are time-limited and re-validated on every access.
DOWNLOAD_LINK_TTL_HOURS = int(os.getenv("DOWNLOAD_LINK_TTL_HOURS", "72"))
