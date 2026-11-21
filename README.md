# agent-bridge

**Crash-safe session ledger for multi-agent setups.** Every AI harness on your
machine — Claude Code, Hermes, OpenCode, Goose, Gemini CLI, Qwen Code, pi, your
own scripts hitting model APIs directly — logs what it did to one shared
Markdown file, even when the session was hard-quit and the agent never got to
say goodbye.

Memory-sharing tools generally assume the agent cooperates at runtime. agent-bridge
is *post-mortem*: it reads each harness's native session store (transcripts,
sqlite, JSONL) after the fact, so dead agents still report.

> **TL;DR.** One shared Markdown ledger of what every AI harness on your machine did —
> read post-mortem from native session stores, so hard-quit sessions still report.
> Idempotent sync, flock append, eight adapters + zero-code generic JSONL.
> **Verified 2026-11-21:** pytest suite 5/5 green; fresh-HOME record→sync→ledger demo
> works end to end. Default ledger: `~/.hermes/BRIDGE.md`. MIT.
> Walkthrough: [docs/walkthrough-crash-safe-ledger.md](docs/walkthrough-crash-safe-ledger.md).

## How it works

```
harness session stores ──> adapters ──> normalized Session ──> BRIDGE.md
(jsonl / sqlite / logs)                 (dedup: marker + state cache, flock append)
```

Each unrecorded session becomes one entry: first prompt, errors seen, span,
message counts, hard-quit flag. Agents (and you) read the bridge to know what
every other agent did.

## Usage

```bash
python3 -m agent_bridge sync      # scan everything, append what's new
python3 -m agent_bridge doctor    # which adapters find their stores
python3 -m agent_bridge sync --adapter opencode
```

Idempotent: dedup via `<!-- <source>-session: <id> -->` markers in the bridge
file plus per-source state caches (`~/.agent-bridge/state/`). Live sessions are
left alone until quiet for 30 min.

**Wire it to run automatically:**
- Claude Code: SessionStart hook running `sync` (stdin hook JSON excludes the live session)
- anything else: cron every 30 min

## Built-in adapters

| adapter  | store |
|----------|-------|
| claude   | `~/.claude/projects/*/*.jsonl` |
| hermes   | `~/.hermes/state.db` (read-only) |
| opencode | `~/.local/share/opencode/opencode.db` (read-only) |
| goose    | `~/.local/share/goose/sessions/sessions.db` (read-only) |
| gemini   | `~/.gemini/tmp/*/logs.json` |
| qwen     | `~/.qwen/projects/*/chats/*.json` |
| pi       | `~/.pi/agent/sessions/**/*.jsonl` |
| raw      | `~/.agent-bridge/raw/*.jsonl` (see below) |

Missing stores are skipped silently; a broken adapter never kills the sync.

## Raw API scripts (no harness at all)

```python
from agent_bridge.record import record_session

with record_session("my-batch-job") as rec:
    rec.prompt("classify 400 leads")
    ...
    rec.error("HTTP 429 from provider")
```

or wrap any command:

```bash
python3 -m agent_bridge.record --name nightly-job -- python3 nightly.py
```

Exceptions and nonzero exits are recorded automatically; the `raw` adapter
picks the file up on the next sync.

## Any other CLI tool

If it writes JSONL somewhere, no code needed — declare it in
`~/.agent-bridge/config.json`:

```json
{
  "generic": [
    {"name": "mytool", "glob": "~/.mytool/sessions/*.jsonl",
     "role_key": "role", "content_key": "content", "user_role": "user"}
  ]
}
```

## Config

`~/.agent-bridge/config.json`, everything optional. Default ledger path:
`~/.hermes/BRIDGE.md` (the example below overrides it to `~/BRIDGE.md`):

```json
{
  "bridge_path": "~/BRIDGE.md",
  "quiet_secs": 1800,
  "baseline": "2026-07-13",
  "adapters": {"goose": {"enabled": false}}
}
```

`baseline` keeps the first run from flooding the bridge with your entire history.

## Verified 2026-11-21

Portfolio audit, fresh checkout:

- `uv run --with pytest --python 3.12 python -m pytest -q`: **5 passed** (raw JSONL
  prompt/error recording, nonzero-exit recording, repeat-sync dedup, missing-store skip,
  fresh-HOME regression).
- Found and fixed in PR #1 (merged 2026-11-21): the first-ever sync on a clean machine crashed with
  `FileNotFoundError` — the lock file's parent dir was never created. `append_entries()`
  now creates it; the regression test fails against the pre-fix code with the exact error.
- Fresh-HOME end-to-end demo (isolated HOME): record → sync → one ledger entry with the
  prompt and the 429 error. Output in the walkthrough.

## License

MIT
