# SPDX-License-Identifier: MIT
"""Command-line interface: ``telepatia-handoff <status|package|absorb|pending> ...``.

Settings come from flags, then from the ``[handoff]`` table of a telepatia agent config.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from organism_continuity.handoff import __version__, core
from organism_continuity.handoff.notify import notify
from organism_continuity.telepatia import inbox, keys
from organism_continuity.telepatia._compat import tomllib
from organism_continuity.telepatia.config import Config, ConfigError, default_config_path, load_config
from organism_continuity.telepatia.keys import KeyFileError
from organism_continuity.telepatia.storage import UnsafePath

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def _config_path(args: argparse.Namespace) -> Path:
    return (keys.expand(args.config) if args.config else default_config_path()).absolute()


def settings(args: argparse.Namespace) -> tuple[Path, dict[str, str], core.Thresholds, Config | None]:
    """Resolve handoff dir, lanes and thresholds from flags, then ``[handoff]`` in the config."""
    cfg: Config | None = None
    table: dict[str, Any] = {}
    cfg_path = _config_path(args)
    if args.config or cfg_path.exists():
        cfg = load_config(cfg_path)
        table = tomllib.loads(cfg.path.read_text(encoding="utf-8")).get("handoff") or {}
    lanes: dict[str, str] = {}
    for k, v in (table.get("lanes") or {}).items():
        lanes[core.check_lane(k)] = str(
            keys.expand(v) if Path(v).is_absolute() or cfg is None else (cfg.path.parent / keys.expand(v))
        )
    for item in args.lane or []:
        name, sep, path = item.partition("=")
        if not sep or not path:
            raise ValueError(f"lane_must_be_name=path: {item!r}")
        lanes[core.check_lane(name)] = str(keys.expand(path))
    t = table.get("thresholds") or {}
    th = core.Thresholds(
        **{k: t[k] for k in ("log_warn_mb", "log_handoff_mb", "checkpoints_warn", "checkpoints_handoff") if k in t}
    )
    if args.dir:
        hdir = keys.expand(args.dir).absolute()
    elif table.get("dir"):
        hdir = keys.expand(table["dir"])
        hdir = hdir if hdir.is_absolute() or cfg is None else cfg.path.parent / hdir
    elif cfg is not None:
        hdir = cfg.spool / "handoffs"
    else:
        raise ValueError("handoff_dir_required: pass --dir or --config")
    return hdir, lanes, th, cfg


def run(args: argparse.Namespace) -> int:
    """External-memory handoff packages between two sessions."""
    hdir, lanes, th, cfg = settings(args)
    if args.action == "status":
        out = core.status(hdir, lanes, th)
    elif args.action == "pending":
        out = core.pending(hdir)
    elif args.action == "absorb":
        if not args.id:
            print("absorb needs an id", file=sys.stderr)
            return EXIT_USAGE
        out = core.absorb(hdir, args.id, args.by)
    else:
        if not (args.source and args.dest):
            print("package needs --source and --dest", file=sys.stderr)
            return EXIT_USAGE
        out = core.package(hdir, args.source, args.dest, lanes=lanes, note=args.note, th=th)
        if args.notify:
            if cfg is None:
                raise ValueError("notify_needs_config")
            msg = notify(cfg, args.notify, out["id"], hdir / out["md"])
            out = {**out, "notified": {"to": args.notify, "message_id": msg.id}}
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """Build the ``telepatia-handoff`` argument parser."""
    p = argparse.ArgumentParser(prog="telepatia-handoff", description="External-memory handoff between two sessions.")
    p.add_argument("--version", action="version", version=f"telepatia-handoff {__version__}")
    p.add_argument("action", choices=("status", "package", "absorb", "pending"))
    p.add_argument("id", nargs="?", help="handoff id (absorb)")
    p.add_argument("--config", help="telepatia agent config (default: $TELEPATIA_CONFIG or ~/.config/telepatia/...)")
    p.add_argument("--dir", help="handoff directory (default: [handoff] dir, else <spool>/handoffs)")
    p.add_argument("--lane", action="append", help="NAME=SESSION_DIR (repeatable)")
    p.add_argument("--source")
    p.add_argument("--dest")
    p.add_argument("--note", default="")
    p.add_argument("--by", default="peer", help="lane that absorbed the package (absorb)")
    p.add_argument("--notify", help="also send a signed telepatia message to this peer (package)")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code; known errors are printed, not raised."""
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (
        ConfigError,
        KeyFileError,
        UnsafePath,
        inbox.PeerInboxMissing,
        FileExistsError,
        FileNotFoundError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as exc:
        print(f"telepatia-handoff: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
