# Walkthrough — dead agents still report: a crash-safe session ledger

*Published 2026-11-21 as part of the portfolio evidence audit. agent-bridge is a small,
stdlib-only Python tool; everything below is reproducible from the public repo.*

## The problem

Run more than one AI harness on a machine — Claude Code, Hermes, OpenCode, Goose, Gemini
CLI, your own batch scripts — and each keeps its own session store. When a session is
hard-quit (crash, OOM, closed laptop), the agent never gets to say goodbye. Memory-sharing
tools that assume runtime cooperation lose exactly the sessions you most want to remember:
the ones that died.

## The idea: read the dead, post-mortem

agent-bridge does not ask agents to cooperate. After the fact it reads each harness's
**native session store** (JSONL transcripts, sqlite, logs), normalizes what it finds, and
appends one entry per unrecorded session to a single shared Markdown ledger (`BRIDGE.md`):
first prompt, errors seen, span, message counts, hard-quit flag.

```
harness session stores ──> adapters ──> normalized Session ──> BRIDGE.md
(jsonl / sqlite / logs)                 (dedup: marker + state cache, flock append)
```

- **Idempotent**: dedup via `<!-- <source>-session: <id> -->` markers + per-source state
  caches; a second sync appends nothing.
- **Crash-safe append**: flock on the ledger; a broken adapter never kills the sync;
  missing stores are skipped silently.
- **Live sessions left alone** until quiet for 30 minutes.
- Eight built-in adapters (claude, hermes, opencode, goose, gemini, qwen, pi, raw) plus a
  zero-code generic JSONL adapter via config.

## 60-second demo (no harness needed)

```bash
git clone https://github.com/ilPez00/agent-bridge && cd agent-bridge
python3 - <<'EOF'
from agent_bridge.record import record_session
with record_session("nightly-job") as rec:
    rec.prompt("classify 400 leads")
    rec.error("HTTP 429 from provider")
EOF
python3 -m agent_bridge sync --adapter raw
cat ~/BRIDGE.md    # one entry: prompt, the 429, span, hard-quit flag if it died
```

Or wrap any command — exceptions and nonzero exits are recorded automatically:

```bash
python3 -m agent_bridge.record --name nightly-job -- python3 nightly.py
```

Wire it automatic: Claude Code SessionStart hook running `sync`, or cron every 30 minutes.

## Audit finding (2026-11-21) — and why it matters

The portfolio audit ran this tool on a **fresh HOME** and found a real crash:
`append_entries()` opened `<bridge>.lock` without creating its parent directory, so the
first-ever sync on a clean machine died with `FileNotFoundError` — in the one tool whose
selling point is crash safety. A fix (`makedirs` before open) plus a pytest suite including
a fresh-HOME regression test is proposed on branch `portfolio/audit-2026-11`. The finding
is the point: claims get checked against running code, and failures are published.

## Limits

- Post-mortem, not live: entries appear after a session goes quiet (default 30 min).
- Adapters read native stores read-only; store format changes upstream can break an adapter
  (it is skipped, never fatal).
- The ledger is Markdown for humans and agents to read — not a database, not a query engine.

MIT licensed. [README](../README.md) · [repo](https://github.com/ilPez00/agent-bridge)