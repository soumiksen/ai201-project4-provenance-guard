"""
Structured audit log, persisted as JSON on disk.

Every call to /submit appends one structured entry here. Entries are never
edited or removed by the submission flow — appeals (Milestone 5) append
further entries against the same content_id rather than mutating history.
"""

import json
import os
import threading

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_log.json")
_lock = threading.Lock()


def _read_all():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def append_entry(entry: dict) -> None:
    with _lock:
        entries = _read_all()
        entries.append(entry)
        with open(LOG_PATH, "w") as f:
            json.dump(entries, f, indent=2)


def get_recent(limit: int = 20):
    entries = _read_all()
    return list(reversed(entries[-limit:]))


def get_by_content_id(content_id: str):
    return [e for e in _read_all() if e.get("content_id") == content_id]
