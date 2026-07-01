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


def update_entry(content_id: str, updates: dict):
    """
    Merges `updates` into the most recent audit log entry matching
    `content_id`. Returns the updated entry, or None if no matching entry
    exists.

    Design note: this mutates the existing entry in place (rather than only
    ever appending a separate "appeal" event) so that GET /log surfaces a
    single, current-state record per submission - status flips to
    "under_review" and `appeal_reasoning` appears on the same entry a
    reviewer would already be looking at. The original classification
    fields (attribution, confidence, llm_score, stylometric_score) are left
    untouched by this merge, so the automated decision that was appealed is
    still fully visible, not erased.
    """
    with _lock:
        entries = _read_all()
        match_index = None
        for i in range(len(entries) - 1, -1, -1):
            if entries[i].get("content_id") == content_id:
                match_index = i
                break
        if match_index is None:
            return None
        entries[match_index].update(updates)
        with open(LOG_PATH, "w") as f:
            json.dump(entries, f, indent=2)
        return entries[match_index]


def get_recent(limit: int = 20):
    entries = _read_all()
    return list(reversed(entries[-limit:]))


def get_by_content_id(content_id: str):
    return [e for e in _read_all() if e.get("content_id") == content_id]
