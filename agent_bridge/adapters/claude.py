"""Claude Code adapter: parses ~/.claude/projects/*/*.jsonl transcripts."""

import json
import re
from pathlib import Path

from ..core import Session, first_line

MAX_ERRORS = 5


def _strip_reminders(text):
    return re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S).strip()


def _iso_ts(s):
    from datetime import datetime

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def collect(cfg):
    opts = cfg["adapters"]["claude"]
    projects = Path(opts["projects"]).expanduser()
    for path in projects.glob("*/*.jsonl"):
        mtime = path.stat().st_mtime
        if mtime < cfg["baseline_ts"]:
            continue
        yield _parse(path, mtime)


def _parse(path, mtime):
    s = Session(source="claude", sid=path.stem, last_activity=mtime)
    users = assistants = 0
    ts_first = ts_last = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = o.get("type")
            if o.get("gitBranch"):
                s.branch = o["gitBranch"]
            if o.get("cwd"):
                s.cwd = o["cwd"]
            if o.get("timestamp"):
                ts_last = o["timestamp"]
                ts_first = ts_first or o["timestamp"]
            if t == "ai-title":
                s.title = o.get("title") or o.get("text") or s.title
            elif t == "assistant" and not o.get("isSidechain"):
                assistants += 1
            elif t == "user" and not o.get("isSidechain"):
                c = (o.get("message") or {}).get("content")
                blocks = c if isinstance(c, list) else [{"type": "text", "text": c}]
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    if (
                        b.get("type") == "tool_result"
                        and b.get("is_error")
                        and len(s.errors) < MAX_ERRORS
                    ):
                        raw = b.get("content")
                        if isinstance(raw, list):
                            raw = " ".join(
                                x.get("text", "") for x in raw if isinstance(x, dict)
                            )
                        snippet = first_line(_strip_reminders(str(raw or "")), 160)
                        if snippet and snippet not in s.errors:
                            s.errors.append(snippet)
                    elif b.get("type") == "text" and isinstance(b.get("text"), str):
                        text = _strip_reminders(b["text"])
                        if text and not text.startswith("<"):
                            users += 1
                            if s.first_prompt is None:
                                s.first_prompt = text[:300]
    if users < 2:
        s.first_prompt = None  # trivial
    s.started = _iso_ts(ts_first)
    s.last_activity = _iso_ts(ts_last) or mtime
    s.counts = f"{users} user / {assistants} assistant msgs"
    return s
