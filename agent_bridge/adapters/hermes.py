"""Hermes agent adapter: reads ~/.hermes/state.db (read-only)."""

import json
import sqlite3
from pathlib import Path

from ..core import Session, first_line

MAX_ERRORS = 5


def _looks_like_error(content):
    try:
        obj = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return "error" in str(content or "")[:200].lower()
    if not isinstance(obj, dict):
        return False
    return bool(
        obj.get("error")
        or obj.get("exit_code") not in (0, None)
        or obj.get("status") == "timeout"
    )


def collect(cfg):
    db_path = Path(cfg["adapters"]["hermes"]["db"]).expanduser()
    if not db_path.exists():
        return
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.execute("PRAGMA busy_timeout=5000")
    rows = db.execute(
        """
        SELECT s.id, s.started_at, s.ended_at, s.end_reason, s.message_count,
               s.tool_call_count, s.title, s.cwd, s.git_branch,
               (SELECT MAX(m.timestamp) FROM messages m WHERE m.session_id = s.id)
        FROM sessions s
        WHERE s.started_at >= ? AND s.parent_session_id IS NULL
        """,
        (cfg["baseline_ts"],),
    ).fetchall()
    for sid, started, ended, reason, msgs, tools, title, cwd, branch, last in rows:
        s = Session(
            source="hermes",
            sid=sid,
            last_activity=ended or last or started,
            started=started,
            ended=ended,
            end_note=reason,
            title=title,
            cwd=cwd,
            branch=branch,
            counts=f"{msgs} msgs, {tools} tool calls",
        )
        row = db.execute(
            "SELECT content FROM messages WHERE session_id=? AND role='user' "
            "ORDER BY timestamp LIMIT 1",
            (sid,),
        ).fetchone()
        if row and row[0] and (msgs or 0) >= 4:
            s.first_prompt = first_line(row[0], 300)
        for (content,) in db.execute(
            "SELECT content FROM messages WHERE session_id=? AND role='tool' "
            "ORDER BY timestamp",
            (sid,),
        ):
            if not _looks_like_error(content):
                continue
            snippet = first_line(content, 160)
            if snippet and snippet not in s.errors:
                s.errors.append(snippet)
                if len(s.errors) >= MAX_ERRORS:
                    break
        yield s
    db.close()
