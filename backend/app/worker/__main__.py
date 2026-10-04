import argparse
import logging
from threading import Event

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.worker.handlers import production_registry
from app.worker.runtime import OperationWorker, WorkerPolicy, install_signal_handlers


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the durable MealCraft Operations worker.")
    parser.add_argument("--once", action="store_true", help="claim at most one job, then exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    stop_event = Event()
    install_signal_handlers(stop_event)
    worker = OperationWorker(
        session_factory=SessionLocal,
        database_url=settings.database_url,
        registry=production_registry(),
        policy=WorkerPolicy(
            poll_seconds=settings.ops_worker_poll_seconds,
            lease_seconds=settings.ops_worker_lease_seconds,
            heartbeat_seconds=settings.ops_worker_heartbeat_seconds,
            timeout_seconds=settings.ops_worker_job_timeout_seconds,
            max_attempts=settings.ops_worker_max_attempts,
        ),
        stop_event=stop_event,
    )
    if args.once:
        worker.run_once()
    else:
        worker.run_forever()


if __name__ == "__main__":
    main()
