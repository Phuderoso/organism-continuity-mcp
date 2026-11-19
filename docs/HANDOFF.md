# Handoff between two sessions

Two long-running agent sessions ("lanes") do not share internal state. When one session has
grown large, it is often better to continue in a fresh session from a short, structured package
than to replay a long transcript. `telepatia-handoff` writes and tracks such packages.

The handoff code is its own package, `organism_continuity.handoff`, separate from the messaging package
`organism_continuity.telepatia`. It depends on `organism_continuity.telepatia` for storage helpers and, for `--notify`, imports
its signing and delivery (`organism_continuity.telepatia.inbox.deliver`, which signs with
`organism_continuity.telepatia.signing`). It contains no cryptography of its own. Run it as `telepatia-handoff`
or `python -m organism_continuity.handoff`; an example config section and demo are in `examples/handoff/`.

## Pressure

`telepatia-handoff status` measures each configured lane from file sizes only:

- the summed size of `*.jsonl` files directly inside the lane's session directory, and
- the number of entries in an optional `compaction_checkpoints/` subdirectory.

| Level   | Default trigger |
|---------|-----------------|
| warn    | logs >= 40 MiB or checkpoints >= 40 |
| handoff | logs >= 100 MiB or checkpoints >= 80 |

File contents are never read. When the highest lane is at least `warn` and higher than the
lowest, `status` recommends a direction (`source` -> `dest`). Nothing happens automatically.

## Package

`telepatia-handoff package --source long --dest fresh --note "..."` writes:

- `<id>.md` with five layers: state (the measured metrics), narrative, intent, priority paths
  and protocol. Layers 2 to 4 are left for the source session to fill in.
- `<id>.json` metadata, `LATEST.md` and `PENDING.json`.

Notes are limited to 2000 characters, and notes that look like credentials (private key
headers, 64-hex strings, common token prefixes) are refused. Do not put secrets in packages.

With `--notify agent-b`, a signed message pointing to the package is delivered to `agent-b`.

## Absorb

The destination session reads the package, then runs
`telepatia-handoff absorb <id> --by fresh`. Ids are matched exactly (no globbing).

## Configuration

```toml
[handoff]
dir = "handoffs"                 # default: <spool>/handoffs

[handoff.lanes]
long  = "/path/to/session-a"
fresh = "/path/to/session-b"

[handoff.thresholds]
log_warn_mb = 40
log_handoff_mb = 100
checkpoints_warn = 40
checkpoints_handoff = 80
```

The `[handoff]` tables live in the agent's `telepatia.toml` (see `examples/handoff/handoff.example.toml`).
Lanes can also be passed as `--lane NAME=DIR`, and `--dir` works without an agent config.
