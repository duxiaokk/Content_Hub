from __future__ import annotations

import signal
import time

from scheduler_center.database import Base, engine
from scheduler_center.dispatcher import SchedulerDispatcher


def main() -> int:
    Base.metadata.create_all(bind=engine)
    dispatcher = SchedulerDispatcher()
    dispatcher.start()

    stop = False

    def _handle_signal(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while not stop:
            time.sleep(0.2)
    finally:
        dispatcher.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

