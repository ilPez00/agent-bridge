"""Recorder for scripts that call model APIs directly (raw API keys).

Two ways to use:

1. Python context manager:

    from agent_bridge.record import record_session

    with record_session("verona-rag-demo") as rec:
        rec.prompt("summarize these leads")   # first call wins as first_prompt
        ...
        rec.error("HTTP 429 from provider")   # optional, repeatable

2. Wrap any command (stdout/stderr passed through; nonzero exit recorded):

    python3 -m agent_bridge.record --name nightly-update -- python3 update.py

Each session writes one JSONL file to ~/.agent-bridge/raw/; the `raw`
adapter picks it up on the next sync. No daemon, no lock contention.
"""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

RAW_DIR = Path(os.environ.get("AGENT_BRIDGE_RAW", "~/.agent-bridge/raw")).expanduser()


class _Recorder:
    def __init__(self, name):
        self.name = name
        self.sid = f"{name}-{time.strftime('%Y%m%d_%H%M%S')}-{uuid.uuid4().hex[:6]}"
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        self.path = RAW_DIR / f"{self.sid}.jsonl"
        self._write({"type": "start", "name": name, "cwd": os.getcwd()})

    def _write(self, obj):
        obj["timestamp"] = time.time()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj) + "\n")

    def prompt(self, text):
        self._write({"type": "prompt", "text": str(text)})

    def event(self, text):
        self._write({"type": "event", "text": str(text)})

    def error(self, text):
        self._write({"type": "error", "text": str(text)})

    def end(self, note="clean"):
        self._write({"type": "end", "note": note})


class record_session:
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.rec = _Recorder(self.name)
        return self.rec

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            self.rec.error(f"{exc_type.__name__}: {exc}")
            self.rec.end("exception")
        else:
            self.rec.end()
        return False


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    name = "raw"
    if argv[:1] == ["--name"]:
        name = argv[1]
        argv = argv[2:]
    if argv[:1] == ["--"]:
        argv = argv[1:]
    if not argv:
        print("usage: python3 -m agent_bridge.record --name NAME -- CMD [ARGS...]")
        return 2
    rec = _Recorder(name)
    rec.prompt(" ".join(argv))
    proc = subprocess.run(argv)
    if proc.returncode != 0:
        rec.error(f"exit code {proc.returncode}")
        rec.end("nonzero-exit")
    else:
        rec.end()
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
