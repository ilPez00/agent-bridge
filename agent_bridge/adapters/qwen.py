"""Qwen Code adapter: reads ~/.qwen/projects/*/chats/*.json.

Chat files vary by qwen version; runtime.json holds metadata, full chat
files hold {messages|history: [{role/type, content/text, ...}]}. Tolerant:
extracts whatever is present.
"""

import glob
import json
from pathlib import Path

from ..core import Session, first_line


def collect(cfg):
    pattern = str(Path(cfg["adapters"]["qwen"]["chats"]).expanduser())
    for path in glob.glob(pattern):
        p = Path(path)
        mtime = p.stat().st_mtime
        if mtime < cfg["baseline_ts"]:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(d, dict):
            continue
        sid = str(d.get("session_id") or p.stem)
        s = Session(
            source="qwen",
            sid=sid,
            last_activity=mtime,
            started=None,
            cwd=d.get("work_dir"),
        )
        msgs = d.get("messages") or d.get("history") or []
        n = 0
        for m in msgs:
            if not isinstance(m, dict):
                continue
            n += 1
            role = m.get("role") or m.get("type")
            text = m.get("content") if isinstance(m.get("content"), str) else m.get("text")
            if s.first_prompt is None and role == "user" and text:
                s.first_prompt = first_line(text, 300)
        s.counts = f"{n} msgs"
        started = d.get("started_at")
        if isinstance(started, (int, float)):
            s.started = started / (1000 if started > 1e12 else 1)
        if n < 2:
            s.first_prompt = None
        yield s
