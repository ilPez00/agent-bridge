"""Gemini CLI adapter: reads ~/.gemini/tmp/*/logs.json.

Each logs.json is a list of {sessionId, messageId, type, message, timestamp}.
A file can contain several sessions; group by sessionId.
"""

import glob
import json
from datetime import datetime
from pathlib import Path

from ..core import Session, first_line


def _ts(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def collect(cfg):
    pattern = str(Path(cfg["adapters"]["gemini"]["logs"]).expanduser())
    sessions = {}
    for path in glob.glob(pattern):
        try:
            items = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            sid = it.get("sessionId")
            if not sid:
                continue
            ts = _ts(it.get("timestamp"))
            s = sessions.get(sid)
            if s is None:
                s = sessions[sid] = Session(
                    source="gemini", sid=sid, last_activity=ts or 0, started=ts
                )
                s._n = 0
            s._n += 1
            if ts:
                s.last_activity = max(s.last_activity, ts)
                s.started = min(s.started or ts, ts)
            if it.get("type") == "user" and s.first_prompt is None:
                s.first_prompt = first_line(it.get("message"), 300)
    for s in sessions.values():
        if not s.started or s.started < cfg["baseline_ts"]:
            continue
        s.counts = f"{s._n} logged msgs"
        if s._n < 2:
            s.first_prompt = None
        yield s
