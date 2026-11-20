# organism-continuity-mcp

Local, dependency-free building blocks that let two or more AI agents (or any processes) keep
working across restarts, context compaction and session boundaries: authenticated messages
between agents, a persistent outbox with presence hints, and a two-session handoff format.

Version **0.5.0**. Python 3.10+, standard library only. Everything runs locally: no hosted
service, no telemetry.

## What it solves

Long-running and multi-agent setups lose state whenever a session ends, a context window is
compacted or an agent restarts. Ad-hoc fixes (pasting summaries, typing into another agent's
terminal, polling a file in a loop) are fragile and hard to audit. This project provides small,
inspectable pieces instead:

- **Authenticated messages between agents** on one host or a shared disk (`telepatia-sig v=1`,
  HMAC-SHA256, replay protection with a fail-closed nonce store).
- **Event-driven delivery**: readers block on inotify/kqueue instead of polling, and a persistent
  outbox can hold a message until the peer reports itself idle.
- **A session handoff format**, so a fresh session resumes from a package plus external memory
  instead of re-deriving state.

## Install

From a checkout of this repository:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install .
telepatia --version
```

This installs the `organism_continuity` package and the `telepatia` command. There are no
runtime dependencies.

## 5-minute two-agent example

Two agents, `agent-a` and `agent-b`, share a spool directory. Each one has its own config and
key. This is a real transcript (keys and fingerprints are throwaway values from a temp
directory).

**1. Create both identities.** `init` writes the config, a 32-byte key (`0600`), an empty peers
file, the inbox and the nonce store. The key itself is never printed.

```console
$ telepatia init --name agent-a --config a/telepatia.toml --spool spool
name: agent-a
config: /tmp/tp-demo/a/telepatia.toml
key_file: /tmp/tp-demo/a/keys/agent-a.key
fingerprint: 07ee5d25197ecfce
spool: /tmp/tp-demo/spool

$ telepatia init --name agent-b --config b/telepatia.toml --spool spool
name: agent-b
config: /tmp/tp-demo/b/telepatia.toml
key_file: /tmp/tp-demo/b/keys/agent-b.key
fingerprint: d9a9ae8b8678bc99
spool: /tmp/tp-demo/spool
```

**2. Exchange keys out-of-band and register peers.** Each side receives a copy of the other's
key file over a channel you trust (here a local copy stands in for that). The peers file stores
only a name and a key path; see `examples/telepatia/peers-a.example.toml`.

```console
$ mkdir -m 700 -p a/peer-keys b/peer-keys
$ install -m 600 a/keys/agent-a.key b/peer-keys/agent-a.key
$ install -m 600 b/keys/agent-b.key a/peer-keys/agent-b.key

$ telepatia peer add agent-b --key-file a/peer-keys/agent-b.key --config a/telepatia.toml
name: agent-b
key_file: /tmp/tp-demo/a/keys/agent-b.key
fingerprint: d9a9ae8b8678bc99

$ telepatia peer add agent-a --key-file b/peer-keys/agent-a.key --config b/telepatia.toml
name: agent-a
key_file: /tmp/tp-demo/b/keys/agent-a.key
fingerprint: 07ee5d25197ecfce
```

**3. Compare fingerprints over a second channel** (voice, in person, a separate chat). They must
match the values `init` printed.

```console
$ telepatia key fingerprint --config a/telepatia.toml
name: agent-a
fingerprint: 07ee5d25197ecfce

$ telepatia peer list --config b/telepatia.toml
agent-a	07ee5d25197ecfce	/tmp/tp-demo/b/keys/agent-a.key
```

**4. agent-b waits; agent-a sends.** `inbox --wait` blocks on file events (no polling) and only
returns messages that pass every check: MAC, sender, recipient, freshness window and nonce.

```console
# terminal 1 (agent-b)
$ telepatia inbox --wait --timeout 10 --config b/telepatia.toml

# terminal 2 (agent-a)
$ telepatia send agent-b "build 42 is green, your turn" --config a/telepatia.toml
delivered: 1c38f4857ce3860b9ebb7866ffccfcc8
to: agent-b

# terminal 1 wakes up with:
[1c38f4857ce3860b9ebb7866ffccfcc8] from agent-a at 2026-11-19T23:13:16Z (verified)
build 42 is green, your turn
```

**5. The message is consumed once.** A second read finds nothing and exits with status 3; a
replayed copy of the file would be rejected as `replayed_nonce` or `stale`.

```console
$ telepatia inbox --config b/telepatia.toml
$ echo $?
3
```

`examples/telepatia/demo.sh` runs a similar flow end to end in a temp directory.
`telepatia --help` lists every command (`presence`, `outbox`, `key rotate`, `peer remove`,
`doctor`, `relay`, `verify-text`, ...); session handoff has its own command, `telepatia-handoff`.

## Modules

| Module | Status | Purpose |
|--------|--------|---------|
| `organism_continuity.telepatia` (signing, inbox, outbox, presence, keys) | v0.5, new | Signed `telepatia-sig v=1` messages over a file spool; persistent outbox; advisory presence; key init, rotation and revocation. |
| `organism_continuity.telepatia` (channel, ledger, relay) | v0.5.1, new | Verify signed texts from other transports once, against the transport's receive time, with a fail-closed replay ledger and a read-only dry run; relay bodies with opt-in signing by the relayer. |
| `organism_continuity.handoff` (command `telepatia-handoff`) | v0.5 | Package work from a long session for a fresh one; absorbs the former `agent-dual-lane-handoff` project. Reuses the kit's signing for `--notify`. |
| Preflight, doctor, funnel and other helper-dependent tools | removed from v0.5 | Archived in `quarantine/second-batch/` (they need host helper scripts this repository does not ship, or expose a port); they return only with tests. |
| Continuity calculator (`tools/continuity_survival_calc.py`) | stable | When a durable write is worth its cost. |
| Legacy MCP-shaped tools (`server.py`, `stdio_server.py`, `power/`) | legacy | Remaining v0.4 stdio tools: `ocarina_doctrine`, `gospel`, `harbor`, `peer_starter`, `csv`, `power.csv`. |
| Send-key map (`quarantine/send-key/`) | **experimental, out of v0.5** | Types into terminals. Not part of the package; see the quarantine README. |

## Documentation

- [`docs/PROTOCOL.md`](docs/PROTOCOL.md): normative message format, verification order,
  freshness, nonce store, rotation, threat model and test vectors.
- [`docs/TELEPATIA.md`](docs/TELEPATIA.md): kit guide (architecture, configuration, CLI).
- [`docs/HANDOFF.md`](docs/HANDOFF.md): session handoff.
- [`SECURITY.md`](SECURITY.md): supported versions, how to report a vulnerability, threat model.
- [`CHANGELOG.md`](CHANGELOG.md): release history.
- [`docs/QUIET_OK_PROTOCOL.md`](docs/QUIET_OK_PROTOCOL.md): anti-thrash rule for multi-agent loops.

## License

Code: MIT. Essays and prose docs: CC0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

## Credits

This project is free to use, modify and ship. If it helps your product, we kindly ask that you
credit it the way many apps list open-source components on their "Credits" or "Open-source
licenses" screen, for example:

> organism-continuity-mcp, by Phuderoso (MIT)

This is a request, not a license condition. See [`LICENSE`](LICENSE), [`NOTICE`](NOTICE) and
[`CITATION.cff`](CITATION.cff) (machine-readable citation metadata).

Related projects: [agent-dual-lane-handoff](https://github.com/Phuderoso/agent-dual-lane-handoff)
(absorbed here as the handoff module), [organismo-hydra](https://github.com/Phuderoso/organismo-hydra),
[long-running-agent-failure-modes](https://github.com/Phuderoso/long-running-agent-failure-modes).

---

Background essays (not part of the specification): [`docs/essays/`](docs/essays/README.md).
