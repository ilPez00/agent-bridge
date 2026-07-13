"""Core: normalized Session record, state cache, dedup, flock append.

Every adapter yields Session objects; the core decides what gets written to
the bridge file. Dedup is two-layer: a marker comment in the bridge itself
(source of truth, survives state loss) and a per-source state cache keyed by
last-activity timestamp (skips re-parsing unchanged sessions).
"""

import fcntl
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Session:
    source: str            # adapter name, e.g. "claude", "hermes", "opencode"
    sid: str
    last_activity: float   # unix ts of last observed activity (dedup key)
    first_prompt: str | None = None
    started: float | None = None
    ended: float | None = None   # None = no clean end recorded
    end_note: str | None = None  # e.g. "cli_close", "hard-quit"
    title: str | None = None
    cwd: str | None = None
    branch: str | None = None
    counts: str | None = None    # freeform, e.g. "48 user / 1762 assistant msgs"
    errors: list = field(default_factory=list)

    @property
    def marker(self):
        return f"{self.source}-session: {self.sid}"

    @property
    def trivial(self):
        return not self.first_prompt


def _iso(ts):
    if not ts:
        return "?"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_entry(s: Session) -> str:
    date = _iso(s.started)[:10] if s.started else "unknown-date"
    lines = [
        f"## {date} — {s.source} session {s.sid[:24]} (auto-logged)",
        f"<!-- {s.marker} -->",
        "",
    ]
    if s.title:
        lines.append(f"**Title:** {s.title}")
    if s.cwd or s.branch:
        lines.append(f"**Where:** {s.cwd or '?'}" + (f" @ `{s.branch}`" if s.branch else ""))
    ending = f"ended: {s.end_note or 'clean'}" if s.ended else "NO clean end (hard-quit or still open at scan)"
    span = f"**Span:** {_iso(s.started)} → {_iso(s.ended or s.last_activity)}"
    if s.counts:
        span += f" ({s.counts}; {ending})"
    else:
        span += f" ({ending})"
    lines.append(span)
    lines.append(f'**First prompt:** "{s.first_prompt}"')
    if s.errors:
        lines.append(f"**Errors seen (first {len(s.errors)}):**")
        lines.extend(f"- `{e}`" for e in s.errors)
    else:
        lines.append("**Errors seen:** none")
    lines.append(
        "**Summary:** auto-logged by agent-bridge (session ended without a live "
        "summary). Enrich manually if this session mattered."
    )
    lines.append("")
    return "\n".join(lines)


class StateCache:
    def __init__(self, state_dir: Path, source: str):
        self.path = state_dir / f"{source}.json"
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.data = {}

    def unchanged(self, sid, last_activity):
        prev = self.data.get(sid)
        return bool(prev and prev.get("last") == last_activity)

    def record(self, sid, last_activity, verdict):
        self.data[sid] = {"last": last_activity, "verdict": verdict}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data), encoding="utf-8")
        tmp.replace(self.path)


def append_entries(bridge: Path, entries: list) -> None:
    if not entries:
        return
    lock = bridge.with_name(bridge.name + ".lock")
    with open(lock, "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        text = bridge.read_text(encoding="utf-8") if bridge.exists() else ""
        with open(bridge, "a", encoding="utf-8") as f:
            if text and not text.endswith("\n"):
                f.write("\n")
            f.write("\n" + "\n".join(entries))


def sync(cfg, adapters: dict) -> dict:
    """Run enabled adapters, append unrecorded sessions. Returns {source: n}."""
    bridge = Path(cfg["bridge_path"]).expanduser()
    state_dir = Path(cfg["state_dir"]).expanduser()
    quiet = cfg.get("quiet_secs", 1800)
    now = time.time()
    bridge_text = bridge.read_text(encoding="utf-8") if bridge.exists() else ""
    logged = {}
    entries = []

    for name, adapter in adapters.items():
        state = StateCache(state_dir, name)
        count = 0
        try:
            sessions = list(adapter.collect(cfg))
        except Exception as e:  # one broken adapter must not kill the sync
            print(f"agent-bridge: adapter {name} failed: {e}")
            continue
        for s in sessions:
            if s.sid == cfg.get("exclude_session"):
                continue
            if s.started and s.started < cfg["baseline_ts"]:
                continue
            if not s.ended and now - s.last_activity < quiet:
                continue
            if state.unchanged(s.sid, s.last_activity):
                continue
            if f"<!-- {s.marker} -->" in bridge_text or s.marker in bridge_text:
                state.record(s.sid, s.last_activity, "logged")
                continue
            if s.trivial:
                state.record(s.sid, s.last_activity, "trivial")
                continue
            entries.append(format_entry(s))
            state.record(s.sid, s.last_activity, "logged")
            count += 1
        state.save()
        if count:
            logged[name] = count

    append_entries(bridge, entries)
    return logged


def first_line(text, limit):
    return " ".join(str(text or "").split("\n")[0].split())[:limit]
