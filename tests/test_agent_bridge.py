"""Recording, dedup, missing-store and fresh-HOME regression tests.

Only stdlib + pytest. Every test isolates HOME/raw/bridge/state under tmp_path.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from agent_bridge import core, record
from agent_bridge.adapters import claude, raw

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_cfg(tmp_path):
    """Config with all paths under tmp_path and no baseline/quiet filtering."""
    return {
        "bridge_path": str(tmp_path / "bridge" / "BRIDGE.md"),
        "state_dir": str(tmp_path / "state"),
        "raw_dir": str(tmp_path / "raw"),
        "quiet_secs": 0,
        "baseline_ts": 0,
        "exclude_session": None,
        "adapters": {
            "claude": {"enabled": True, "projects": str(tmp_path / "no-claude-projects")},
            "raw": {"enabled": True},
        },
    }


def raw_events(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def write_raw_session(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )


def test_record_session_writes_prompt_and_error(tmp_path, monkeypatch):
    monkeypatch.setattr(record, "RAW_DIR", tmp_path / "raw")

    with record.record_session("job") as rec:
        rec.prompt("classify 400 leads")
        rec.error("HTTP 429 from provider")

    files = sorted((tmp_path / "raw").glob("*.jsonl"))
    assert len(files) == 1, files
    events = raw_events(files[0])
    assert [e["type"] for e in events] == ["start", "prompt", "error", "end"]
    assert events[1]["text"] == "classify 400 leads"
    assert events[2]["text"] == "HTTP 429 from provider"
    assert events[3]["note"] == "clean"


def test_record_cli_records_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(record, "RAW_DIR", tmp_path / "raw")

    rc = record.main(
        ["--name", "nightly", "--", sys.executable, "-c", "import sys; sys.exit(7)"]
    )

    assert rc == 7
    files = sorted((tmp_path / "raw").glob("*.jsonl"))
    assert len(files) == 1, files
    events = raw_events(files[0])
    assert events[1]["text"].endswith("sys.exit(7)")
    assert events[2]["type"] == "error"
    assert events[2]["text"] == "exit code 7"
    assert events[3]["note"] == "nonzero-exit"


def test_sync_dedup_second_sync_appends_nothing(tmp_path):
    cfg = make_cfg(tmp_path)
    write_raw_session(
        Path(cfg["raw_dir"]) / "s1.jsonl",
        [
            {"type": "start", "name": "job", "timestamp": 1_800_000_000},
            {"type": "prompt", "text": "do the work", "timestamp": 1_800_000_001},
            {"type": "end", "note": "clean", "timestamp": 1_800_000_002},
        ],
    )

    assert core.sync(cfg, {"raw": raw}) == {"raw": 1}
    bridge = Path(cfg["bridge_path"])
    first_text = bridge.read_text(encoding="utf-8")
    assert "do the work" in first_text
    assert "<!-- raw-session: s1 -->" in first_text

    assert core.sync(cfg, {"raw": raw}) == {}
    assert bridge.read_text(encoding="utf-8") == first_text


def test_missing_adapter_store_skipped_silently(tmp_path, capsys):
    cfg = make_cfg(tmp_path)

    assert core.sync(cfg, {"claude": claude}) == {}
    assert not Path(cfg["bridge_path"]).exists()
    assert capsys.readouterr().out == ""


def test_fresh_home_sync_creates_bridge_parent(tmp_path, monkeypatch):
    """Regression: append_entries must mkdir the default ~/.hermes parent."""
    home = tmp_path / "fresh-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(record, "RAW_DIR", home / ".agent-bridge" / "raw")

    with record.record_session("fresh") as rec:
        rec.prompt("first run on a fresh machine")

    bridge = home / ".hermes" / "BRIDGE.md"
    assert not bridge.parent.exists(), "precondition: .hermes must not exist"

    env = dict(os.environ, HOME=str(home), PYTHONPATH=str(REPO_ROOT))
    proc = subprocess.run(
        [sys.executable, "-m", "agent_bridge", "sync", "--adapter", "raw"],
        cwd=home,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert bridge.exists()
    assert "first run on a fresh machine" in bridge.read_text(encoding="utf-8")
