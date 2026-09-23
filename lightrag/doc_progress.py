"""Per-document progress published into ``pipeline_status``.

The pipeline already logs every step it takes, but only as English prose:
``Chunk 3 of 46 extracted …``, ``Analyzing table/tb-…: ok``. A UI that wants a
progress bar has to guess the numbers out of that text, and there are no
numbers at all for the analyze, merge and delete phases — which are the long
ones for a table-heavy document.

This module publishes the same numbers as data, per document and per phase::

    pipeline_status["doc_progress"] = {
        "doc-abc": {"phase": "analyze", "done": 12, "total": 57, "at": 1790…},
    }

Rules it follows, the same as ``PipelineStatusLogger``:

* **Status only.** Nothing here participates in coordination (``busy``,
  cancellation, reservations), so it is written lock-free.
* **Never raises.** A progress write must not break the work it describes.
* **Bounded.** At most :data:`MAX_DOCS` entries survive; the oldest are
  dropped, so a long run cannot grow the status dict without limit.

Concurrent documents may interleave their read-modify-write, so an update can
be lost. That is acceptable: the next update of that document restores it, and
a reader is expected to ignore entries for documents that are no longer
active (a stale entry outlives its document only until the next write).
"""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional

#: Where the mapping lives inside ``pipeline_status``.
KEY = "doc_progress"

#: Phases, in the order a document goes through them.
PARSE = "parse"
ANALYZE = "analyze"
EXTRACT = "extract"
MERGE = "merge"
DELETE = "delete"
PHASES = (PARSE, ANALYZE, EXTRACT, MERGE, DELETE)

#: Most documents tracked at once. Three parallel inserts plus their
#: predecessors is the realistic maximum; the cap only guards against a leak.
MAX_DOCS = 16


def _entries(pipeline_status: Any) -> dict[str, dict[str, Any]]:
    current = pipeline_status.get(KEY)
    if not isinstance(current, Mapping):
        return {}
    # Copy: a Manager DictProxy value must be replaced wholesale, never
    # mutated in place (the nested dict is a plain value, not a proxy).
    return {
        str(k): dict(v) for k, v in current.items() if isinstance(v, Mapping)
    }


def publish(
    pipeline_status: Any,
    doc_id: str,
    phase: str,
    done: int = 0,
    total: int = 0,
) -> None:
    """Record that ``doc_id`` is in ``phase`` at ``done``/``total``."""
    if pipeline_status is None or not doc_id:
        return
    try:
        entries = _entries(pipeline_status)
        entries[doc_id] = {
            "phase": phase,
            "done": max(int(done), 0),
            "total": max(int(total), 0),
            "at": time.time(),
        }
        if len(entries) > MAX_DOCS:
            oldest = sorted(entries.items(), key=lambda kv: kv[1].get("at", 0))
            entries = dict(oldest[-MAX_DOCS:])
        pipeline_status[KEY] = entries
    except Exception:  # noqa: BLE001 - status writes never break the work
        pass


def advance(
    pipeline_status: Any,
    doc_id: str,
    step: int = 1,
    phase: Optional[str] = None,
    total: Optional[int] = None,
) -> None:
    """Add ``step`` to the document's counter, keeping phase and total.

    ``phase`` and ``total`` override what was published before, which is what
    a phase that discovers more work as it goes (one sidecar after another)
    needs.
    """
    if pipeline_status is None or not doc_id:
        return
    try:
        entry = _entries(pipeline_status).get(doc_id) or {}
        publish(
            pipeline_status,
            doc_id,
            phase or str(entry.get("phase") or ""),
            int(entry.get("done") or 0) + step,
            total if total is not None else int(entry.get("total") or 0),
        )
    except Exception:  # noqa: BLE001
        pass


def clear(pipeline_status: Any, doc_id: str) -> None:
    """Forget a document: it finished, failed or was cancelled."""
    if pipeline_status is None or not doc_id:
        return
    try:
        entries = _entries(pipeline_status)
        if entries.pop(doc_id, None) is not None:
            pipeline_status[KEY] = entries
    except Exception:  # noqa: BLE001
        pass


def snapshot(pipeline_status: Any) -> dict[str, dict[str, Any]]:
    """What every tracked document is doing, for a reader (never raises)."""
    if pipeline_status is None:
        return {}
    try:
        return _entries(pipeline_status)
    except Exception:  # noqa: BLE001
        return {}


__all__ = [
    "ANALYZE",
    "DELETE",
    "EXTRACT",
    "KEY",
    "MAX_DOCS",
    "MERGE",
    "PARSE",
    "PHASES",
    "advance",
    "clear",
    "publish",
    "snapshot",
]
