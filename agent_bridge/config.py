"""Config: ~/.agent-bridge/config.json overlaid on defaults."""

import json
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path.home() / ".agent-bridge" / "config.json"

DEFAULTS = {
    "bridge_path": "~/.hermes/BRIDGE.md",
    "state_dir": "~/.agent-bridge/state",
    "raw_dir": "~/.agent-bridge/raw",
    "quiet_secs": 1800,
    "baseline": "2026-07-13",  # sessions older than this are ignored
    "exclude_session": None,
    # adapter name -> enabled / options; unknown stores are skipped silently
    "adapters": {
        "claude": {"enabled": True, "projects": "~/.claude/projects"},
        "hermes": {"enabled": True, "db": "~/.hermes/state.db"},
        "opencode": {"enabled": True, "db": "~/.local/share/opencode/opencode.db"},
        "goose": {"enabled": True, "db": "~/.local/share/goose/sessions/sessions.db"},
        "gemini": {"enabled": True, "logs": "~/.gemini/tmp/*/logs.json"},
        "qwen": {"enabled": True, "chats": "~/.qwen/projects/*/chats/*.json"},
        "pi": {"enabled": True, "sessions": "~/.pi/agent/sessions/**/*.jsonl"},
        "raw": {"enabled": True},
    },
    # extra config-only adapters for arbitrary CLI tools that write JSONL:
    # {"name": "mytool", "glob": "~/.mytool/sessions/*.jsonl",
    #  "role_key": "role", "content_key": "content", "user_role": "user",
    #  "time_key": "timestamp"}
    "generic": [],
}


def load():
    cfg = dict(DEFAULTS)
    try:
        user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for k, v in user.items():
            if k == "adapters" and isinstance(v, dict):
                merged = dict(DEFAULTS["adapters"])
                for name, opts in v.items():
                    merged[name] = {**merged.get(name, {}), **opts}
                cfg["adapters"] = merged
            else:
                cfg[k] = v
    except (OSError, json.JSONDecodeError):
        pass
    cfg["baseline_ts"] = (
        datetime.strptime(cfg["baseline"], "%Y-%m-%d")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    return cfg
