"""Adapter registry. Each adapter module exposes collect(cfg) -> iter[Session]."""

from . import claude, gemini, goose, hermes, opencode, pi, qwen, raw
from .generic import make_collector

BUILTIN = {
    "claude": claude,
    "hermes": hermes,
    "opencode": opencode,
    "goose": goose,
    "gemini": gemini,
    "qwen": qwen,
    "pi": pi,
    "raw": raw,
}


class _Wrapped:
    def __init__(self, fn):
        self.collect = fn


def enabled_adapters(cfg):
    out = {}
    for name, mod in BUILTIN.items():
        if cfg["adapters"].get(name, {}).get("enabled"):
            out[name] = mod
    for spec in cfg.get("generic", []):
        out[spec["name"]] = _Wrapped(make_collector(spec))
    return out
