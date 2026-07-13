"""agent-bridge CLI: sync | doctor.

sync    scan all enabled adapters, append unrecorded sessions to the bridge.
        Reads Claude Code hook JSON from stdin if piped (session_id excluded).
doctor  show which adapters find their stores and how many candidate sessions.
"""

import json
import sys

from . import config
from .adapters import enabled_adapters
from .core import sync


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "sync"
    cfg = config.load()

    if not sys.stdin.isatty():
        try:
            cfg["exclude_session"] = json.load(sys.stdin).get("session_id")
        except (json.JSONDecodeError, ValueError):
            pass

    adapters = enabled_adapters(cfg)
    if cmd == "doctor":
        for name, adapter in adapters.items():
            try:
                n = sum(1 for _ in adapter.collect(cfg))
                print(f"{name:12} OK   {n} candidate session(s)")
            except Exception as e:
                print(f"{name:12} FAIL {e}")
        return 0

    if cmd == "sync":
        only = argv[argv.index("--adapter") + 1] if "--adapter" in argv else None
        if only:
            adapters = {only: adapters[only]}
        logged = sync(cfg, adapters)
        if logged:
            total = sum(logged.values())
            detail = ", ".join(f"{k}:{v}" for k, v in logged.items())
            print(f"agent-bridge: logged {total} session(s) ({detail})")
        return 0

    print("usage: agent-bridge [sync [--adapter NAME] | doctor]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
