"""Background worker: runs scheduled job discovery separately from the API.

Usage: ``python -m backend.worker`` (set RUN_SCHEDULER=false on the API container)."""
from __future__ import annotations

import logging
import signal
import threading

from backend.db import init_db
from backend.jobs.scheduler import discover_for_all_users, start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    init_db()
    start_scheduler()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    threading.Thread(target=discover_for_all_users, daemon=True).start()  # run once at startup
    stop.wait()
    stop_scheduler()


if __name__ == "__main__":
    main()
