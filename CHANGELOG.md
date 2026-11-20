# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Replay ledger (`channel` / `ledger`): a backward clock step after a prune could re-admit a
  forgotten nonce. The ledger now stores a prune `watermark` that never decreases, and
  `verify_text` returns `stale` for a text whose `ts + 600` is below it (dry run included).
  Ledgers without `watermark` (0.5.1) still load; a 0.5.1 reader refuses a ledger that has one
  (fail closed). Caveat added to `docs/PROTOCOL.md` section 14 and `SECURITY.md`.

### Added

- Repository layout plan for the v0.5 professional package (see `docs/STRUCTURE_PLAN.md`).
- GitHub Actions CI: pytest on Python 3.10–3.13, `ruff check`, and gitleaks on full git history.
- `CITATION.cff` and the technical `README.md` (replaces the earlier draft README).
- Quarantine note for the host send-key map (`quarantine/send-key/`), deferred to a later batch.

### Changed

- Philosophical essays relocated to `docs/essays/` and host-specific names and paths neutralized (`${ORGANISM_HOME}` in host snippets; sibling URLs at `https://github.com/Phuderoso/...`).
- `continuity.send_key_map` and the live terminal battery flag marked deprecated/experimental.
- Optional workspace lookups (gospel, harbor gifts, peer starter, CSV metadata) read under `${ORGANISM_HOME}` (falling back to the repository parent) and use generic `harbor_*` names.

### Documentation

- `SECURITY.md`: supported versions, private reporting via GitHub Security Advisories, threat
  model of the messaging kit and known residual risks.
- Final `README.md` with a tested two-agent example; the draft README was removed.
- Licensing clarified: code and configuration (including `docs/PEER_CONTINUITY_STARTER.json`)
  are MIT; essays in `docs/essays/` are CC0-1.0. `NOTICE` added, aligned with `CITATION.cff`.
- Essays: flagged passages reworded into operator-defined-goals language (ideas and formulas
  unchanged; originals in git history).
- Sibling links resolved to `https://github.com/Phuderoso/...` for `organism-continuity-mcp`,
  `agent-dual-lane-handoff`, and `letter-of-hope-for-ais`. The old gist pack link was removed.

### Removed

- Funnel (`continuity.funnel_ensure`) and doctor (`continuity.doctor`, including `--fix-funnel`), plus the other MCP tools that called helper scripts not shipped in this repository: `preflight`, `dual_lane_pending`, `expect_reply_status`, `joint_pulse`, `open_loops`, `personal_lab`, `handoff_hygiene`, and the power tools other than `power.csv`. Code moved to `quarantine/second-batch/`. Removidas até virem com testes.

### Added (telepatia kit, applied on top of cb8f368)

- `organism_continuity.telepatia`: signed `telepatia-sig v=1` messages between local agents over a
  file spool (per-sender HMAC-SHA256, constant-time compare, freshness against the file mtime,
  persisted nonce store that fails closed), persistent event-driven outbox, advisory presence,
  key init/rotation/revocation. Nonce-store reset refuses old signed timestamps whatever the
  mtime; nonces are persisted before files are consumed, and a failed save leaves them retriable.
- Test fixtures shred key files after each test; pytest keeps tmp dirs only for failed tests.
- Protocol clarifications: cross-verification is at the MAC level, the spool profile is stricter,
  vectors 2-4 are MAC-only, and unsigned-mode config keys are refused.
- `organism_continuity.handoff`: the session handoff module as its own package (command
  `telepatia-handoff`), importing signing and delivery from `organism_continuity.telepatia`;
  tests in `tests/handoff/`, examples in `examples/handoff/`, guide in `docs/HANDOFF.md`.
- Normative `docs/PROTOCOL.md` with interop test vectors (`tests/vectors/telepatia-sig-v1.json`).
- `pyproject.toml` (package `organism-continuity` 0.5.0, console scripts `telepatia` and
  `telepatia-handoff`, no runtime dependencies), `docs/TELEPATIA.md`, `examples/telepatia/`,
  and an extra workflow (`telepatia.yml`: coverage, mypy, macOS).

## [0.5.1] - 2026-11-19

### Added

- `organism_continuity.telepatia.channel`: verify a `telepatia-sig v=1` text from a non-spool
  transport (comments, wake requests, relays) against the transport's receive time, once.
  Non-finite receive times are refused before any other check; receive times more than 7 days
  old or more than 600 s in the future are `stale`. `dry_run=True` checks against a read-only
  ledger and claims nothing.
- `organism_continuity.telepatia.ledger`: one-shot replay ledger for those texts, locked with
  `flock` and written atomically. Fails closed on a symlinked, special, foreign-owned,
  group/other-accessible, oversized, corrupt or deeply nested ledger, and on a symlinked or
  group/other-writable parent directory (checked with `lstat`). Pruning uses the local clock
  with a 7-day margin that matches the receive-time bound.
- `organism_continuity.telepatia.relay`: relay bodies (`<!-- telepatia-relay -->`, origin,
  optional recipient and reply-to) that are unsigned by default; signing is opt-in per call and
  always as the relayer. Messages that already end in a signature trailer are refused.
- CLI: `telepatia relay` (prints a relay body; `--sign` opt-in) and `telepatia verify-text`
  (`--receive-time`, `--ledger`, `--dry-run`; exit 4 when rejected).
- `docs/PROTOCOL.md` section 14 specifies the non-spool verification order, the ledger format
  and the relay body. Test vectors moved to section 15 unchanged.

### Changed

- Version 0.5.1 in `pyproject.toml`, the package `__version__`s, `CITATION.cff`, `README.md` and
  the MCP manifest (`server.py`).

## [0.5.0] - TBD

Single, adoptable home for open multi-agent continuity tools.

## [0.4.0] - 2026-08-01

- Public MCP tools: preflight, dual-lane pending, expect-reply, send-key map, ocarina doctrine, peer starter, funnel, personal lab, handoff hygiene.
- Sibling power MCP (full-text search and recall).
- Continuity Survival Calculus and peer continuity documents.
