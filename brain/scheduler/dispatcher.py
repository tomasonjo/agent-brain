"""Single entry point that the scheduler calls on every fire.

Wraps the flow invocation with :Fire bookkeeping and exception trapping.
"""

from __future__ import annotations

import logging

from brain.flows import get as get_flow
from brain.store import repo

log = logging.getLogger("brain.scheduler.dispatcher")


def dispatch(flow_id: str, trigger_id: str, params: dict) -> None:
    fire_id = repo.fire_record(trigger_id)
    try:
        fn = get_flow(flow_id)
        paths = fn(params or {}, fire_id=fire_id)
        repo.fire_finish(fire_id, succeeded=True, memory_paths=paths)
        log.info("fire %s/%s ok, wrote %d memories", trigger_id, fire_id, len(paths))
    except Exception as e:
        log.exception("fire %s/%s failed", trigger_id, fire_id)
        repo.fire_finish(fire_id, succeeded=False, error=str(e))
