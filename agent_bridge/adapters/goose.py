"""Goose adapter: reads sessions.db (read-only). Timestamps are ISO strings."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..core import Session, first_line

MAX_ERRORS = 5


def _ts(v):
    if v is None:
        return None
    try:
        return (
            datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
    except ValueError:
        return None


def collect(cfg):
    db_path = Path(cfg["adapters"]["goose"]["db"]).expanduser()
    if not db_path.exists():
        return
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.execute("PRAGMA busy_timeout=5000")
    for sid, name, desc, wd, created, updated in db.execute(
        "SELECT id, name, description, working_dir, created_at, updated_at FROM sessions"
    ):
        started = _ts(created)
        last = _ts(updated) or started
        if not started or started < cfg["baseline_ts"]:
            continue
        s = Session(
            source="goose",
            sid=str(sid),
            last_activity=last,
            started=started,
            title=name or desc or None,
            cwd=wd,
        )
        n = 0
        for role, content in db.execute(
            "SELECT role, content_json FROM messages WHERE session_id=? ORDER BY id",
            (sid,),
        ):
            n += 1
            text = first_line(content, 300)
            if s.first_prompt is None and role == "user" and text:
                s.first_prompt = text
            if (
                role in ("tool", "toolResponse")
                and "error" in str(content)[:200].lower()
                and len(s.errors) < MAX_ERRORS
            ):
                snippet = first_line(content, 160)
                if snippet not in s.errors:
                    s.errors.append(snippet)
        s.counts = f"{n} msgs"
        if n < 4:
            s.first_prompt = None
        yield s
    db.close()
