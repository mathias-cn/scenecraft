"""Sobe um worker Celery por fila, cada um com concorrência própria."""

from __future__ import annotations

import signal
import subprocess
import sys
import time

from app.core.config import settings
from app.core.queues import QUEUE_NAMES


def _workers() -> list[subprocess.Popen]:
    procs: list[subprocess.Popen] = []
    for queue in QUEUE_NAMES:
        concurrency = str(settings.concurrency_for(queue))
        procs.append(
            subprocess.Popen(
                [
                    "celery",
                    "-A",
                    "app.celery_app:celery_app",
                    "worker",
                    "--loglevel",
                    settings.celery_loglevel,
                    "-Q",
                    queue,
                    "-c",
                    concurrency,
                    "-n",
                    f"{queue}@%h",
                ]
            )
        )
    return procs


def main() -> None:
    procs = _workers()

    def shutdown(_signum=None, _frame=None) -> None:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        while True:
            for proc in procs:
                if proc.poll() is not None:
                    shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
