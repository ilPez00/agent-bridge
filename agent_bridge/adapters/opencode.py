"""OpenCode adapter: reads opencode.db (read-only). Times are unix millis."""

import json
import sqlite3
from pathlib import Path

from ..core import Session, first_line

MAX_ERRORS = 5


def collect(cfg):
    db_path = Path(cfg["adapters"]["opencode"]["db"]).expanduser()
    if not db_path.exists():
        return
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.execute("PRAGMA busy_timeout=5000")
    rows = db.execute(
        """
        SELECT id, directory, title, time_created, time_updated
        FROM session WHERE parent_id IS NULL AND time_created >= ?
        """,
        (cfg["baseline_ts"] * 1000,),
    ).fetchall()
    for sid, directory, title, created, updated in rows:
        s = Session(
            source="opencode",
            sid=sid,
            last_activity=(updated or created) / 1000,
            started=created / 1000,
            title=title or None,
            cwd=directory,
        )
        n = 0
        for (data,) in db.execute(
            "SELECT data FROM message WHERE session_id=? ORDER BY time_created",
            (sid,),
        ):
            try:
                m = json.loads(data)
            except json.JSONDecodeError:
                continue
            n += 1
            if s.first_prompt is None and m.get("role") == "user":
                # content lives in the part table; fall back to session title
                pass
        if s.first_prompt is None:
            row = db.execute(
                """
                SELECT p.data FROM part p JOIN message m ON p.message_id = m.id
                WHERE m.session_id=? ORDER BY m.time_created, p.id LIMIT 20
                """,
                (sid,),
            ).fetchall() if _has_part(db) else []
            for (pdata,) in row:
                try:
                    p = json.loads(pdata)
                except json.JSONDecodeError:
                    continue
                if p.get("type") == "text" and p.get("text"):
                    s.first_prompt = first_line(p["text"], 300)
                    break
        if s.first_prompt is None and title:
            s.first_prompt = first_line(title, 300)
        # error parts
        if _has_part(db):
            for (pdata,) in db.execute(
                """
                SELECT p.data FROM part p JOIN message m ON p.message_id = m.id
                WHERE m.session_id=? AND p.data LIKE '%error%' ORDER BY m.time_created
                """,
                (sid,),
            ):
                try:
                    p = json.loads(pdata)
                except json.JSONDecodeError:
                    continue
                state = p.get("state") if isinstance(p.get("state"), dict) else {}
                err = state.get("error") or p.get("error")
                if err and len(s.errors) < MAX_ERRORS:
                    snippet = first_line(str(err), 160)
                    if snippet and snippet not in s.errors:
                        s.errors.append(snippet)
        s.counts = f"{n} msgs"
        if n < 2:
            s.first_prompt = None  # trivial
        yield s
    db.close()


_part_cache = {}


def _has_part(db):
    key = id(db)
    if key not in _part_cache:
        _part_cache[key] = bool(
            db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='part'"
            ).fetchone()
        )
    return _part_cache[key]
