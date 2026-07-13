"""Raw adapter: sessions written by agent_bridge.record (direct API scripts)."""

import json
from pathlib import Path

from ..core import Session, first_line

MAX_ERRORS = 5


def collect(cfg):
    raw_dir = Path(cfg.get("raw_dir", "~/.agent-bridge/raw")).expanduser()
    if not raw_dir.exists():
        return
    for p in raw_dir.glob("*.jsonl"):
        mtime = p.stat().st_mtime
        if mtime < cfg["baseline_ts"]:
            continue
        s = Session(source="raw", sid=p.stem, last_activity=mtime)
        n = 0
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            n += 1
            ts = o.get("timestamp")
            if ts:
                s.started = min(s.started or ts, ts)
                s.last_activity = max(s.last_activity, ts)
            t = o.get("type")
            if t == "start":
                s.title = o.get("name")
                s.cwd = o.get("cwd")
            elif t == "prompt" and s.first_prompt is None:
                s.first_prompt = first_line(o.get("text"), 300)
            elif t == "error" and len(s.errors) < MAX_ERRORS:
                snippet = first_line(o.get("text"), 160)
                if snippet and snippet not in s.errors:
                    s.errors.append(snippet)
            elif t == "end":
                s.ended = ts
                s.end_note = o.get("note")
        s.counts = f"{n} records"
        yield s
