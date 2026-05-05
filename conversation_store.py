"""
Simple in-memory conversation store.
Tracks SMS conversation state per phone number.
On VPS migration, swap this for SQLite/Postgres.
"""

import time

# In-memory store: { phone_number: { "stage": str, "history": [], "last_active": float } }
_store = {}

TIMEOUT_SECONDS = 600  # 10 minutes of inactivity ends conversation

def get(phone):
    """Get conversation state for a number. Returns None if expired or new."""
    entry = _store.get(phone)
    if not entry:
        return None
    if time.time() - entry["last_active"] > TIMEOUT_SECONDS:
        clear(phone)
        return None
    return entry

def set_stage(phone, stage, history=None):
    """Create or update conversation state."""
    existing = _store.get(phone, {})
    _store[phone] = {
        "stage": stage,
        "history": history or existing.get("history", []),
        "last_active": time.time()
    }

def append_message(phone, role, content):
    """Add a message to conversation history."""
    if phone not in _store:
        set_stage(phone, "started")
    _store[phone]["history"].append({"role": role, "content": content})
    _store[phone]["last_active"] = time.time()

def clear(phone):
    """End a conversation."""
    _store.pop(phone, None)
