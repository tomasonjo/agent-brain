"""APScheduler daemon. Reads triggers/*.yaml on boot, hot-reloads on file changes.

Run: brain scheduler  (or python -m brain.scheduler.main)
"""

from __future__ import annotations

import logging
import signal
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from brain.config import SETTINGS
from brain.scheduler.dispatcher import dispatch
from brain.scheduler.loader import load_all

log = logging.getLogger("brain.scheduler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class _TriggerSync:
    """Owns the scheduler and the set of currently-registered jobs."""

    def __init__(self, scheduler: BackgroundScheduler):
        self.scheduler = scheduler
        self._known: set[str] = set()

    def reconcile(self) -> None:
        configs = {c["id"]: c for c in load_all()}
        desired = {tid for tid, cfg in configs.items() if cfg.get("status") == "active"}

        for stale in self._known - desired:
            self._remove(stale)
        for tid in desired:
            self._upsert(configs[tid])

    def _job_id(self, trigger_id: str) -> str:
        return f"trigger:{trigger_id}"

    def _upsert(self, cfg: dict) -> None:
        tid = cfg["id"]
        sched = cfg.get("schedule") or {}
        if sched.get("type") != "cron":
            log.warning("skipping %s: only cron schedules supported", tid)
            return
        try:
            ct = CronTrigger.from_crontab(sched["expr"], timezone=sched.get("tz") or SETTINGS.tz)
        except Exception as e:
            log.warning("skipping %s: bad cron %r (%s)", tid, sched.get("expr"), e)
            return
        flow_id = cfg.get("flow")
        params = cfg.get("params") or {}
        self.scheduler.add_job(
            dispatch,
            trigger=ct,
            id=self._job_id(tid),
            args=[flow_id, tid, params],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        self._known.add(tid)
        log.info("registered %s: %s %s", tid, sched.get("expr"), sched.get("tz"))

    def _remove(self, trigger_id: str) -> None:
        try:
            self.scheduler.remove_job(self._job_id(trigger_id))
        except Exception:
            pass
        self._known.discard(trigger_id)
        log.info("unregistered %s", trigger_id)


class _Watcher(FileSystemEventHandler):
    def __init__(self, sync: _TriggerSync):
        self.sync = sync

    def _on_change(self, src: str) -> None:
        if not src.endswith(".yaml"):
            return
        log.info("trigger file changed: %s", src)
        try:
            self.sync.reconcile()
        except Exception:
            log.exception("reconcile failed")

    def on_created(self, event: FileSystemEvent) -> None:
        self._on_change(str(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        self._on_change(str(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._on_change(str(event.src_path))

    def on_moved(self, event):  # type: ignore[override]
        self._on_change(str(getattr(event, "dest_path", event.src_path)))


def run() -> None:
    SETTINGS.triggers_dir.mkdir(parents=True, exist_ok=True)
    scheduler = BackgroundScheduler(timezone=SETTINGS.tz)
    sync = _TriggerSync(scheduler)
    scheduler.start()
    sync.reconcile()

    observer = Observer()
    observer.schedule(_Watcher(sync), str(SETTINGS.triggers_dir), recursive=False)
    observer.start()
    log.info("brain scheduler running. watching %s", SETTINGS.triggers_dir)

    stop = {"flag": False}

    def _stop(signum, frame):  # noqa: ARG001
        stop["flag"] = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        while not stop["flag"]:
            time.sleep(0.5)
    finally:
        observer.stop()
        observer.join()
        scheduler.shutdown(wait=False)
        log.info("brain scheduler stopped")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
