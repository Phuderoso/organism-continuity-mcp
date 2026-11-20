# SPDX-License-Identifier: MIT
"""Command-line interface: ``telepatia <command> ...``.

Every command that reads messages goes through ``inbox.read_verified``; there is no command
that prints an unverified message.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from organism_continuity.telepatia import __version__, channel, inbox, keys, outbox, presence, relay
from organism_continuity.telepatia._compat import UTC, tomllib
from organism_continuity.telepatia.config import (
    Config,
    ConfigError,
    add_peer,
    default_config_path,
    load_config,
    remove_peer,
    render_config,
)
from organism_continuity.telepatia.events import EventsUnavailable
from organism_continuity.telepatia.keys import KeyFileError
from organism_continuity.telepatia.ledger import ReplayLedger, ReplayLedgerError
from organism_continuity.telepatia.storage import UnsafePath, atomic_write, private_dir

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_EMPTY = 3
EXIT_REJECTED = 4

CHANNEL_LEDGER_FILE = "channel-ledger.json"


def _out(obj: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, sort_keys=True))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            print(f"{k}: {v}")
    else:
        print(obj)


def _cfg(args: argparse.Namespace) -> Config:
    return load_config(args.config)


def _config_path(args: argparse.Namespace) -> Path:
    return (keys.expand(args.config) if args.config else default_config_path()).absolute()


# --- commands ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """Create config, a private keys dir (0700), our key (0600), peers file and our inbox."""
    name = keys.check_name(args.name)
    cfg_path = _config_path(args)
    if cfg_path.exists():
        raise ConfigError(f"config_exists: {cfg_path}")
    base = cfg_path.parent
    private_dir(base)
    keys_dir = (keys.expand(args.keys_dir) if args.keys_dir else base / "keys").absolute()
    spool = keys.expand(args.spool).absolute()
    info = keys.generate_key(keys_dir, name, allow_in_worktree=args.allow_in_worktree)
    peers_file = base / "peers.toml"
    if not peers_file.exists():
        atomic_write(peers_file, b"# name -> key_file only; never paste key material here\n")
    atomic_write(cfg_path, render_config(name, info["path"], str(spool), str(peers_file)).encode("utf-8"))
    inbox.init_inbox(spool, name)
    private_dir(presence.presence_dir(spool))
    _out(
        {
            "name": name,
            "config": str(cfg_path),
            "key_file": info["path"],
            "fingerprint": info["fingerprint"],
            "spool": str(spool),
        },
        args.json,
    )
    return EXIT_OK


def cmd_key(args: argparse.Namespace) -> int:
    """Key lifecycle on our own key directory. Never prints key material."""
    cfg = _cfg(args)
    keys_dir = cfg.key_file.parent
    name = args.name or cfg.name
    if args.action == "fingerprint":
        path = cfg.key_file if name == cfg.name else cfg.peers.get(name) or keys.key_path(keys_dir, name)
        _out({"name": name, "fingerprint": keys.fingerprint(keys.load_key(path))}, args.json)
    elif args.action == "rotate":
        _out(keys.rotate_key(keys_dir, name), args.json)
    elif args.action == "revoke":
        if not args.yes:
            print("revoke needs --yes", file=sys.stderr)
            return EXIT_USAGE
        info = keys.revoke_key(keys_dir, name)
        if name != cfg.name:
            remove_peer(cfg.peers_file, name)
        _out(info, args.json)
    return EXIT_OK


def cmd_peer(args: argparse.Namespace) -> int:
    """Manage peers: ``add`` copies a peer key (received out-of-band) into our keys dir."""
    cfg = _cfg(args)
    if args.action == "list":
        rows = []
        for peer, path in sorted(cfg.peers.items()):
            try:
                fp = keys.fingerprint(keys.load_key(path))
            except KeyFileError as exc:
                fp = f"unusable ({str(exc).split(':')[0]})"
            rows.append({"name": peer, "key_file": str(path), "fingerprint": fp})
        if args.json:
            _out(rows, True)
        else:
            for r in rows:
                print(f"{r['name']}\t{r['fingerprint']}\t{r['key_file']}")
        return EXIT_OK
    name = keys.check_name(args.name)
    if name == cfg.name:
        raise ConfigError("peer_is_self")
    if args.action == "remove":
        removed = remove_peer(cfg.peers_file, name)
        _out({"name": name, "removed": removed}, args.json)
        return EXIT_OK if removed else EXIT_ERROR
    # add
    if not args.key_file:
        print("peer add needs --key-file", file=sys.stderr)
        return EXIT_USAGE
    src = keys.expand(args.key_file)
    key = keys.load_key(src)  # refuses unsafe source files
    dest = keys.key_path(cfg.key_file.parent, name)
    if os.path.lexists(dest):
        raise FileExistsError(f"key_exists: {dest}")
    keys.ensure_private_dir(dest.parent)
    shutil.copyfile(src, dest, follow_symlinks=False)
    os.chmod(dest, keys.KEY_FILE_MODE)
    add_peer(cfg.peers_file, name, str(dest))
    _out({"name": name, "key_file": str(dest), "fingerprint": keys.fingerprint(key)}, args.json)
    return EXIT_OK


def cmd_chama(args: argparse.Namespace) -> int:
    """Send a signed message to a peer's inbox. ``--when-idle`` holds it in the outbox first."""
    cfg = _cfg(args)
    to = keys.check_name(args.peer)
    body = " ".join(args.text)
    if args.when_idle:
        pres = presence.read_presence(cfg.spool, to)
        if pres.state != presence.IDLE:
            mid = outbox.Outbox(cfg).enqueue(to, body, reason=f"held_{pres.state}")
            _out({"queued": mid, "to": to, "presence": pres.state}, args.json)
            return EXIT_OK
    try:
        msg = inbox.deliver(cfg, to, body)
    except inbox.PeerInboxMissing:
        if not args.queue_if_missing:
            raise
        mid = outbox.Outbox(cfg).enqueue(to, body, reason="peer_inbox_missing")
        _out({"queued": mid, "to": to, "reason": "peer_inbox_missing"}, args.json)
        return EXIT_OK
    _out({"delivered": msg.id, "to": to}, args.json)
    return EXIT_OK


def cmd_relay(args: argparse.Namespace) -> int:
    """Print a relay body for ORIGIN. Unsigned unless ``--sign`` (then signed as our own name)."""
    text = " ".join(args.text)
    if not args.sign:
        sys.stdout.write(relay.relay_text(args.origin, text, to=args.to or "", reply_to=args.reply_to))
        return EXIT_OK
    cfg = _cfg(args)
    body = relay.relay_text(
        args.origin,
        text,
        to=args.to or "",
        reply_to=args.reply_to,
        sign=True,
        relayer=cfg.name,
        key=cfg.signing_key(),
    )
    sys.stdout.write(body)
    return EXIT_OK


def cmd_verify_text(args: argparse.Namespace) -> int:
    """Verify a signed text from another transport against its receive time, once."""
    cfg = _cfg(args)
    try:
        receive_time: float | None = float(args.receive_time)
    except ValueError:
        receive_time = presence.parse_ts(args.receive_time)
    if receive_time is not None and not math.isfinite(receive_time):
        receive_time = None
    if receive_time is None:
        print("verify-text: --receive-time must be epoch seconds or ISO-8601", file=sys.stderr)
        return EXIT_USAGE
    if args.file in (None, "-"):
        raw = sys.stdin.buffer.read(channel.MAX_TEXT_BYTES + 1)
    else:
        with open(keys.expand(args.file), "rb") as fh:
            raw = fh.read(channel.MAX_TEXT_BYTES + 1)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    ledger_path = (
        keys.expand(args.ledger) if args.ledger else inbox.state_dir(cfg.spool, cfg.name) / CHANNEL_LEDGER_FILE
    )
    if text is None:
        res = channel.ChannelCheck("malformed", dry_run=args.dry_run)
    else:
        res = channel.verify_text(
            text,
            keyring=cfg.keyring(),
            receive_time=receive_time,
            ledger=ReplayLedger(ledger_path),
            dry_run=args.dry_run,
        )
    out: dict[str, object] = {
        "status": res.status,
        "signer": res.signer,
        "ts": res.ts,
        "claimed": res.claimed,
        "dry_run": res.dry_run,
    }
    if res.relay is not None:
        out["relay_origin"] = res.relay.origin
    if res.verified:
        out["content"] = res.relay.message if res.relay is not None else res.content
    _out(out, args.json)
    return EXIT_OK if res.verified else EXIT_REJECTED


def _print_messages(res: inbox.ReadResult, as_json: bool) -> None:
    for m in res.messages:
        if as_json:
            print(
                json.dumps(
                    {"id": m.id, "from": m.sender, "ts": m.ts, "body": m.body, "verified": True},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            when = datetime.fromtimestamp(m.ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"[{m.id}] from {m.sender} at {when} (verified)\n{m.body}\n")
    if res.rejected:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(res.rejected.items()))
        print(f"telepatia: rejected and quarantined (not shown): {summary}", file=sys.stderr)


def cmd_inbox(args: argparse.Namespace) -> int:
    """Read verified messages. ``--wait`` blocks on file events until one arrives."""
    cfg = _cfg(args)
    if args.reset_nonce_store:
        if not args.yes:
            print("reset-nonce-store needs --yes (unread messages older than now will be rejected)", file=sys.stderr)
            return EXIT_USAGE
        path = inbox.reset_nonce_store(cfg.spool, cfg.name)
        _out({"reset_nonce_store": str(path)}, args.json)
        return EXIT_OK
    if args.wait:
        res = inbox.wait_verified(cfg, timeout=args.timeout)
    else:
        res = inbox.read_verified(cfg, mark_read=not args.peek)
    _print_messages(res, args.json)
    return EXIT_OK if res.messages else EXIT_EMPTY


def cmd_presence(args: argparse.Namespace) -> int:
    """Publish our presence (``set``) or read an agent's presence (``get``)."""
    cfg = _cfg(args)
    if args.action == "set":
        path = presence.write_presence(cfg.spool, cfg.name, args.state, task=args.task or "")
        _out({"name": cfg.name, "state": args.state, "file": str(path)}, args.json)
        return EXIT_OK
    name = keys.check_name(args.name or cfg.name)
    p = presence.read_presence(cfg.spool, name)
    _out({"name": name, "state": p.state, "reason": p.reason, "task": p.task}, args.json)
    return EXIT_OK


def cmd_outbox(args: argparse.Namespace) -> int:
    """List, flush, or run (event-driven) the persistent outbox."""
    cfg = _cfg(args)
    box = outbox.Outbox(cfg, log=lambda m: print(m, file=sys.stderr))
    if args.action == "list":
        rows = [
            {
                "message_id": r["message_id"],
                "to": r["to"],
                "reason": r.get("reason", ""),
                "attempts": r.get("attempts", 0),
            }
            for r in box.pending()
        ]
        if args.json:
            _out(rows, True)
        else:
            for r in rows:
                print(f"{r['message_id']}\t{r['to']}\t{r['reason']}\tattempts={r['attempts']}")
        return EXIT_OK
    rep = box.run(timeout=args.timeout) if args.action == "run" else box.flush()
    _out({"delivered": rep.delivered, "held": rep.held}, args.json)
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check that config, keys and inbox are present and private. Prints no secrets."""
    cfg = _cfg(args)
    problems: list[str] = []
    try:
        cfg.signing_key()
    except KeyFileError as exc:
        problems.append(str(exc))
    for peer, path in cfg.peers.items():
        try:
            keys.load_key(path)
        except KeyFileError as exc:
            problems.append(f"peer {peer}: {exc}")
    for d in (inbox.inbox_dir(cfg.spool, cfg.name), inbox.state_dir(cfg.spool, cfg.name)):
        try:
            st = os.lstat(d)
            if st.st_mode & 0o077:
                problems.append(f"dir_mode_too_open: {d}")
        except OSError:
            problems.append(f"missing: {d}")
    try:
        inbox.check_nonce_store(cfg.spool, cfg.name)
    except inbox.NonceStoreError as exc:
        problems.append(f"{exc} (recover with: telepatia inbox --reset-nonce-store --yes)")
    _out({"name": cfg.name, "peers": len(cfg.peers), "ok": not problems, "problems": problems}, args.json)
    return EXIT_OK if not problems else EXIT_ERROR


# --- parser -----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for every subcommand."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config", help="agent config (default: $TELEPATIA_CONFIG or ~/.config/telepatia/telepatia.toml)"
    )
    common.add_argument("--json", action="store_true", help="machine-readable output")

    p = argparse.ArgumentParser(prog="telepatia", description="Signed, file-based messages between local agents.")
    p.add_argument("--version", action="version", version=f"telepatia {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", parents=[common], help="create config, key, peers file and inbox")
    s.add_argument("--name", required=True)
    s.add_argument("--spool", required=True, help="shared directory for inboxes, presence and queues")
    s.add_argument("--keys-dir", help="default: <config dir>/keys")
    s.add_argument(
        "--allow-in-worktree", action="store_true", help="allow the keys dir inside a git worktree (not recommended)"
    )
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("key", parents=[common], help="fingerprint, rotate or revoke a key")
    s.add_argument("action", choices=("fingerprint", "rotate", "revoke"))
    s.add_argument("name", nargs="?", help="default: our own name")
    s.add_argument("--yes", action="store_true", help="confirm revoke")
    s.set_defaults(func=cmd_key)

    s = sub.add_parser("peer", parents=[common], help="add, remove or list peers")
    s.add_argument("action", choices=("add", "remove", "list"))
    s.add_argument("name", nargs="?")
    s.add_argument("--key-file", help="peer key received out-of-band (add)")
    s.set_defaults(func=cmd_peer)

    for cmd in ("chama", "send"):
        s = sub.add_parser(cmd, parents=[common], help="send a signed message to a peer")
        s.add_argument("peer")
        s.add_argument("text", nargs="+")
        s.add_argument("--when-idle", action="store_true", help="hold in the outbox unless the peer is idle")
        s.add_argument(
            "--queue-if-missing", action="store_true", help="hold in the outbox if the peer inbox does not exist yet"
        )
        s.set_defaults(func=cmd_chama)

    s = sub.add_parser("inbox", parents=[common], help="read verified messages")
    s.add_argument("--wait", action="store_true", help="block on file events until a message arrives")
    s.add_argument("--timeout", type=float, default=None, help="with --wait: give up after N seconds")
    s.add_argument("--peek", action="store_true", help="do not mark messages as read")
    s.add_argument("--reset-nonce-store", action="store_true", help="recover a bad nonce store; rejects old mail")
    s.add_argument("--yes", action="store_true", help="confirm nonce-store reset")
    s.set_defaults(func=cmd_inbox)

    s = sub.add_parser("presence", help="publish or read presence")
    psub = s.add_subparsers(dest="action", required=True)
    ps = psub.add_parser("set", parents=[common])
    ps.add_argument("state", choices=presence.STATES)
    ps.add_argument("--task", default="")
    ps.set_defaults(func=cmd_presence)
    pg = psub.add_parser("get", parents=[common])
    pg.add_argument("name", nargs="?")
    pg.set_defaults(func=cmd_presence)

    s = sub.add_parser("outbox", parents=[common], help="list, flush or run the persistent outbox")
    s.add_argument("action", choices=("list", "flush", "run"))
    s.add_argument("--timeout", type=float, default=None, help="with run: give up after N seconds")
    s.set_defaults(func=cmd_outbox)

    s = sub.add_parser("relay", parents=[common], help="print a relay body for another agent (unsigned unless --sign)")
    s.add_argument("origin", help="who the relayed message is from")
    s.add_argument("text", nargs="+")
    s.add_argument("--to", default=None, help="recipient line")
    s.add_argument("--reply-to", dest="reply_to", type=int, default=None, metavar="ID")
    s.add_argument("--sign", action="store_true", help="opt-in: sign with our own key (needs --config)")
    s.set_defaults(func=cmd_relay)

    s = sub.add_parser("verify-text", parents=[common], help="verify a signed text from another transport, once")
    s.add_argument("file", nargs="?", help="text file (default: stdin)")
    s.add_argument("--receive-time", required=True, help="transport receive time (epoch seconds or ISO-8601)")
    s.add_argument("--ledger", help="replay ledger (default: <spool>/state/<name>/channel-ledger.json)")
    s.add_argument("--dry-run", action="store_true", help="check only; read-only ledger, claims nothing")
    s.set_defaults(func=cmd_verify_text)

    s = sub.add_parser("doctor", parents=[common], help="check file modes and keys")
    s.set_defaults(func=cmd_doctor)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code; known errors are printed, not raised."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (
        ConfigError,
        KeyFileError,
        UnsafePath,
        EventsUnavailable,
        inbox.PeerInboxMissing,
        inbox.NonceStoreError,
        ReplayLedgerError,
        FileExistsError,
        FileNotFoundError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as exc:
        print(f"telepatia: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
