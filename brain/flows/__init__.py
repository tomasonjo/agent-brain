"""Flow registry. Every flow exposes `run(params: dict, *, fire_id: str) -> list[str]`
returning the memory paths written.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class Flow(Protocol):
    def __call__(self, params: dict, *, fire_id: str) -> list[str]: ...


from brain.flows.daily_brief import run as _daily_brief_run  # noqa: E402
from brain.flows.dream_session import run as _dream_session_run  # noqa: E402
from brain.flows.dream_synthesis import run as _dream_synthesis_run  # noqa: E402

FLOWS: dict[str, Callable[..., list[str]]] = {
    "daily_brief": _daily_brief_run,
    "dream_session": _dream_session_run,
    "dream_synthesis": _dream_synthesis_run,
}


def get(flow_id: str) -> Callable[..., list[str]]:
    if flow_id not in FLOWS:
        raise KeyError(f"unknown flow: {flow_id}. Known: {sorted(FLOWS)}")
    return FLOWS[flow_id]
