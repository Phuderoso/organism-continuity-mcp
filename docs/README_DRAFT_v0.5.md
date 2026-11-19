<!-- DRAFT for v0.5.0 — not final. Sections marked TODO depend on the messaging kit landing. -->

# organism-continuity-mcp

Local, dependency-light tools that let two or more AI agents keep working
across restarts, context compaction and session boundaries, exposed as an
MCP stdio server and as a plain CLI.

## What it solves

Long-running and multi-agent setups lose state whenever a session ends, a
context window is compacted or an agent restarts. Ad-hoc fixes (pasting
summaries, typing into another agent's terminal, polling) are fragile and
hard to audit. This project provides small, inspectable building blocks:

- **Authenticated messages between agents** on the same host or shared disk.
- **A persistent queue and presence signals**, so messages survive restarts
  and agents can tell "busy" from "gone".
- **A two-session handoff format**, so a new session resumes from a package
  plus external memory instead of re-deriving state.
- **Preflight checks** run before an agent acts on another agent's session.

Everything runs locally. No hosted service, no telemetry.

## 5-minute two-agent example

> TODO: placeholder until the messaging kit lands in v0.5.0.

```bash
# 1. Install
#    TODO: install command from PyPI once the package name is confirmed

# 2. Create a shared config and key for two agents
#    TODO: command from the kit (e.g. `ocm init --agents agent-a,agent-b`)

# 3. agent-a sends a signed message
#    TODO

# 4. agent-b receives and verifies it
#    TODO
```

Expected output: TODO.

## Modules

| Module | Status | Purpose |
|--------|--------|---------|
| Signed messaging / queue / presence | v0.5 (new) | HMAC-authenticated messages, persistent queue, presence. See `PROTOCOL.md` (TODO). |
| Two-session handoff | stable | Package and resume state between two sessions via external memory. |
| Preflight | stable | Checks to run before acting on another agent's session. |
| Continuity calculator | stable | `tools/continuity_survival_calc.py`: when a durable write is worth its cost. |
| Send-key map (`continuity.send_key_map`) | **deprecated** | Types into terminals. Out of scope for v0.5; will move to a later release. |

## Configuration

Host snippets use `${ORGANISM_HOME}` as the workspace root. Replace it with an
absolute path before pasting into an MCP host config. TODO: full config reference.

## Documentation

- `PROTOCOL.md`: message format, signing, replay protection, key exchange (TODO, from the kit).
- `SECURITY.md`: threat model and how to report vulnerabilities (TODO, from the kit).
- `CHANGELOG.md`: release history (TODO).
- [`docs/QUIET_OK_PROTOCOL.md`](QUIET_OK_PROTOCOL.md): anti-thrash rule for multi-agent loops.
- [`docs/essays/`](essays/README.md): background essays; not part of the specification.

## License

MIT. See [`LICENSE`](../LICENSE).

## Credits

This project is free to use, modify and ship under the MIT license. If it
helps your product, we kindly ask that you credit it the same way many apps
list open-source components on their "Open-source licenses" or "Credits"
screen, for example:

> organism-continuity-mcp — MIT License — Copyright (c) 2026 Phuderoso / Organismo Soberano

Machine-readable citation metadata is in [`CITATION.cff`](../CITATION.cff).
