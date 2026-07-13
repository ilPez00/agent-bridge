"""pi (badlogic/pi-mono) adapter: reads session JSONL files.

pi stores sessions as JSONL under ~/.pi/agent/sessions/ (path configurable).
Entries carry {type/role, content, timestamp}-style records; tolerant parse.
"""

import glob
import json
from pathlib import Path

from ..core import Session, first_line

MAX_ERRORS = 5


def collect(cfg):
    pattern = str(Path(cfg["adapters"]["pi"]["sessions"]).expanduser())
    for path in glob.glob(pattern, recursive=True):
        p = Path(path)
        mtime = p.stat().st_mtime
        if mtime < cfg["baseline_ts"]:
            continue
        s = Session(source="pi", sid=p.stem, last_activity=mtime)
        n = 0
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                n += 1
                role = o.get("role") or o.get("type")
                msg = o.get("message") if isinstance(o.get("message"), dict) else o
                content = msg.get("content")
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict)
                    )
                if s.first_prompt is None and role == "user" and content:
                    text = first_line(content, 300)
                    if text and not text.startswith("<"):
                        s.first_prompt = text
                if (
                    o.get("isError") or o.get("is_error")
                ) and len(s.errors) < MAX_ERRORS:
                    snippet = first_line(content, 160)
                    if snippet and snippet not in s.errors:
                        s.errors.append(snippet)
        s.counts = f"{n} records"
        if n < 4:
            s.first_prompt = None
        yield s
