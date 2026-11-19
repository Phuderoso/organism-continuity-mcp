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
