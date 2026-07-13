"""Generic JSONL adapter: config-driven, for any CLI tool that writes JSONL.

Configure in ~/.agent-bridge/config.json:

    "generic": [
      {"name": "mytool",
       "glob": "~/.mytool/sessions/*.jsonl",
       "role_key": "role", "content_key": "content",
       "user_role": "user", "error_key": "error"}
    ]

Each matching file = one session (sid = filename stem, activity = mtime).
"""

import glob
import json
from pathlib import Path

from ..core import Session, first_line

MAX_ERRORS = 5


def make_collector(spec):
    def collect(cfg):
        pattern = str(Path(spec["glob"]).expanduser())
        role_key = spec.get("role_key", "role")
        content_key = spec.get("content_key", "content")
        user_role = spec.get("user_role", "user")
        error_key = spec.get("error_key", "error")
        for path in glob.glob(pattern, recursive=True):
            p = Path(path)
            mtime = p.stat().st_mtime
            if mtime < cfg["baseline_ts"]:
                continue
            s = Session(source=spec["name"], sid=p.stem, last_activity=mtime)
            n = 0
            with open(p, encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        o = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(o, dict):
                        continue
                    n += 1
                    if (
                        s.first_prompt is None
                        and o.get(role_key) == user_role
                        and o.get(content_key)
                    ):
                        s.first_prompt = first_line(o[content_key], 300)
                    if o.get(error_key) and len(s.errors) < MAX_ERRORS:
                        snippet = first_line(o[error_key], 160)
                        if snippet and snippet not in s.errors:
                            s.errors.append(snippet)
            s.counts = f"{n} records"
            if n < spec.get("min_records", 2):
                s.first_prompt = None
            yield s

    return collect
