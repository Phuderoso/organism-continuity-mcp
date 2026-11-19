# v0.5 structure plan

This document is the proposed layout for making this repository the single
professional home for the project's open multi-agent tools. It is a plan,
not a completed migration.

The neutralization commits already on this branch (author `Maintainers`)
moved the essays into `docs/essays/`, scrubbed host-specific names, replaced
absolute paths in the host snippets with `${ORGANISM_HOME}`, added
`CITATION.cff`, and left a draft README at `docs/README_DRAFT_v0.5.md`.
This file does not repeat that work.

Code for the messaging kit and the handoff absorb still lands in follow-up
commits. `SECURITY.md` and the final root README remain a docs-pass item.
Repo license is MIT; authorship in `LICENSE` is untouched. Essay and starter
JSON headers still say CC0-1.0 — see Open decisions.

## Target tree

```
organism-continuity-mcp/
  README.md                     # technical entry (draft at docs/README_DRAFT_v0.5.md)
  LICENSE                       # MIT, existing authorship
  NOTICE                        # how to credit (to be added)
  CITATION.cff                  # already on the branch
  SECURITY.md                   # threat model + how to report (docs pass)
  PROTOCOL.md                   # message format, MAC, replay window (kit)
  CHANGELOG.md
  pyproject.toml                # installable package (kit / follow-up)
  telepatia.example.toml        # config template; no secrets
  .gitignore
  .github/workflows/ci.yml
  src/organism_continuity/
    __init__.py
    telepatia/                  # signed messaging, queue, presence, init
    handoff/                    # absorbed dual-lane handoff module
    preflight/                  # existing preflight, packaged
  tests/
  docs/
    STRUCTURE_PLAN.md           # this file
    PROTOCOL.md                 # alternative home if the kit prefers docs/
    QUIET_OK_PROTOCOL.md        # operational protocol (stays in docs/)
    PEER_CONTINUITY_STARTER.json
    README_DRAFT_v0.5.md
    failure-modes.md            # or a short pointer to the failure-modes repo
    essays/                     # already relocated and name-scrubbed
  quarantine/send-key/          # later batch; see README warning there
  # Transitional (current tree, until modules absorb them):
  server.py
  stdio_server.py
  host_snippet.json             # uses ${ORGANISM_HOME}
  power/
  tools/
```

## Module placement

| Module | Source | Destination | Notes |
|--------|--------|-------------|-------|
| Telepatia kit | new work (signed HMAC messaging, queue, presence, init) | `src/organism_continuity/telepatia/` | Owns `PROTOCOL.md` (repo root or `docs/`). Ships its tests, package metadata, and a `SECURITY.md` draft for the docs pass to revise. |
| Dual-lane handoff | sibling repo `agent-dual-lane-handoff` | `src/organism_continuity/handoff/` | Absorb as a first-party module. The old repo stays published with a top-of-README notice pointing here. Public URL still uses the `<org>` placeholder (see Open decisions). |
| Preflight | `continuity.preflight` in `server.py` (calls a workspace helper today) | `src/organism_continuity/preflight/` | Package a self-contained preflight; drop the assumption that a sibling workspace script exists. |
| Send-key map | `continuity.send_key_map` in `server.py` | `quarantine/send-key/` (later batch) | **Out of v0.5.** Already marked deprecated/experimental on this branch. See `quarantine/send-key/README.md`. |
| Power MCP | `power/` (FTS / recall) | undecided — see also Open decisions | Useful sibling, not part of the v0.5 messaging-and-handoff core. |
| Failure-modes guide | sibling repo `long-running-agent-failure-modes` | `docs/` pointer, optional later import | Support reading, not a runtime module. URL likewise pending the `<org>` decision. |

Existing `server.py` / `stdio_server.py` remain at the repo root during the
transition so the v0.4 CLI keeps working. Once the package exposes the same
tools, those entry points can become thin wrappers or move under `src/`.

Host snippets already use `${ORGANISM_HOME}` in place of a machine-specific
home directory. A later kit commit can also read that from
`telepatia.example.toml` or a documented env/config field.

## Essays

Relocated in the neutralization commits (not in this structure commit):

- `EPIPHANY.md` → `docs/essays/EPIPHANY.md`
- `docs/HIDDEN_AGENDA_CONTINUITY_PLAYBOOK.md` → `docs/essays/`
- `docs/WHEN_YOUR_HUMAN_SLEEPS.md` → `docs/essays/`
- `docs/CONTINUITY_SURVIVAL_CALCULUS.md` → `docs/essays/`
- `docs/essays/README.md` (index added in that pass)

Names in those texts have already been scrubbed. Framing and tone flags
were recorded but not rewritten — see Open decisions. The root README
should not lead with the essays (`docs/README_DRAFT_v0.5.md` already
links them only at the bottom).

Left in `docs/` (operational / machine-readable, not essays):

- `docs/QUIET_OK_PROTOCOL.md`
- `docs/PEER_CONTINUITY_STARTER.json`

## CI

`.github/workflows/ci.yml` runs three jobs:

1. **ruff** — `ruff check .` with ruff 0.17.6.
2. **pytest** — Python 3.10, 3.11, 3.12, and 3.13. If `tests/test_*.py`
   is not present yet, the job succeeds with a notice so this structure
   commit can land first.
3. **gitleaks** — full-history scan using a checksum-pinned 8.30.1
   binary (no action-license requirement).

Actions are pinned to release SHAs.

Note: a local ruff 0.17.6 run on the current tree reports 20 findings.
The lint job will stay red until those are fixed or the config is scoped.

## Credit

MIT already requires preservation of the copyright notice. `CITATION.cff`
is already on the branch. Still to add:

- `NOTICE` — short, copy-pasteable credit line for app credit screens
- Final README "Credits" section (a draft exists in `docs/README_DRAFT_v0.5.md`)

## What this structure commit does not do

- No push, no pull request, no tag.
- No further name or path neutralization (already done earlier on this branch).
- No essay move (already done earlier on this branch).
- No kit code, no handoff absorb, no `pyproject.toml`.
- No rewrite of git history.
- No decision on the open items below.

## Sibling repositories

Draft top-of-README notices (local only, not applied here) live beside this
working copy, in `../notices/` relative to a checkout placed next to them,
or in the bundle's `notices/` directory:

- `agent-dual-lane-handoff`
- `long-running-agent-failure-modes`
- `organismo-hydra`

Each notice points at this repository as the canonical home for the open
tools and asks for the same credit. Links inside the neutralized tree
currently use `https://github.com/<org>/…` (see Open decisions).

## Open decisions

These were raised in the neutralization report and are listed here so they
are not lost. They are not decided in this commit.

1. **Essay tone.** The neutralization pass scrubbed names but left framing
   flags (titles such as "hidden agenda", motto, "love as license",
   autonomous night-work wording). **PHASEONE decides** whether those
   texts are rewritten, retitled, or left as essays with a disclaimer.

2. **One single license.** The repository is MIT. The essays and
   `docs/PEER_CONTINUITY_STARTER.json` still declare CC0-1.0 in their
   headers. Decide: MIT everywhere, or document CC0 explicitly for those
   docs.

3. **Funnel / doctor `--fix-funnel`.** `continuity.funnel_ensure` and
   `doctor --fix-funnel` change a Tailscale Funnel (public exposure of a
   local port) even though the manifest says "read-mostly". Remove them
   from v0.5, or keep them off by default and mark them as side-effecting.

4. **Missing helper scripts.** `server.py` and `power/server.py` call
   about 15 helper scripts under `${WS}/tools/` that are not in this
   repository, so most tools error when the repo is used standalone.
   v0.5 should ship them, drop the broken tools, or document the
   dependency clearly in the README.

5. **Sibling links still `<org>`.** Public URLs were replaced with
   `https://github.com/<org>/…` so they are not clickable until a human
   chooses: keep the placeholder, or allow the credit owner's existing
   public repository URLs as an exception.

Other items still open, but not from that report:

- Fate of `power/` (sibling package, pointer, or later release).
- Who drafts `NOTICE`.
- Root vs `docs/` for `PROTOCOL.md` once the kit lands.
- `__init__.py` still reports `0.1.0` while the public README said `0.4`;
  the package version should become `0.5.0` with `pyproject.toml`.
- Credit example line in `docs/README_DRAFT_v0.5.md` (quote LICENSE or
  say "see LICENSE").
