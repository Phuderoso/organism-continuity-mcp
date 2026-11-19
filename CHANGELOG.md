# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repository layout plan for the v0.5 professional package (see `docs/STRUCTURE_PLAN.md`).
- GitHub Actions CI: pytest on Python 3.10–3.13, `ruff check`, and gitleaks on full git history.
- `CITATION.cff` and a draft technical README (`docs/README_DRAFT_v0.5.md`).
- Quarantine note for the host send-key map (`quarantine/send-key/`), deferred to a later batch.

### Changed

- Philosophical essays relocated to `docs/essays/` and host-specific names and paths neutralized (`${ORGANISM_HOME}` in host snippets; sibling URLs pending an `<org>` decision).
- `continuity.send_key_map` and the live terminal battery flag marked deprecated/experimental.

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

## [0.5.0] - TBD

Single, adoptable home for open multi-agent continuity tools.

### Planned

- Signed HMAC messaging kit (queue, presence, init) and `PROTOCOL.md`.
- Dual-lane session handoff absorbed as a first-party module.
- Preflight module.
- Installable package via `pyproject.toml`.
- Final technical README, `SECURITY.md`, and a credit/`NOTICE` section.
- Send-key map remains out of the v0.5 package (later batch).
- Open decisions recorded in `docs/STRUCTURE_PLAN.md` (essay tone, MIT vs CC0 on essays, funnel/doctor side effects, missing helper scripts, sibling-link `<org>` placeholder).

## [0.4.0] - 2026-08-01

- Public MCP tools: preflight, dual-lane pending, expect-reply, send-key map, ocarina doctrine, peer starter, funnel, personal lab, handoff hygiene.
- Sibling power MCP (full-text search and recall).
- Continuity Survival Calculus and peer continuity documents.
