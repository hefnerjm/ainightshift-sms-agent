"""
Redis-backed conversation store.
Tracks SMS conversation state per phone number.
"""
import json
import os
import redis

TIMEOUT_SECONDS = 600

_redis = redis.from_url(os.environ["REDIS_URL"])

def get(phone):
    data = _redis.get(f"conv:{phone}")
    if not data:
        return None
    return json.loads(data)

def set_stage(phone, stage, history=None):
    existing = get(phone) or {}
    entry = {
        "stage": stage,
        "history": history or existing.get("history", []),
    }
    _redis.setex(f"conv:{phone}", TIMEOUT_SECONDS, json.dumps(entry))

def append_message(phone, role, content):
    existing = get(phone)
    if not existing:
        set_stage(phone, "started")
        existing = get(phone)
    existing["history"].append({"role": role, "content": content})
    _redis.setex(f"conv:{phone}", TIMEOUT_SECONDS, json.dumps(existing))

def clear(phone):
    _redis.delete(f"conv:{phone}")
