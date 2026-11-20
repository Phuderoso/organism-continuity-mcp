# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.5.x   | Yes       |
| < 0.5   | No        |

Only the latest 0.5.x release receives security fixes.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub: open the repository's **Security** tab and
choose **Report a vulnerability** (GitHub private vulnerability reporting / Security Advisories).
There is no security email address.

Do not open a public issue for a vulnerability, and never include keys, key files, nonce stores or
message bodies in a report. Synthetic reproductions (for example with the public test key in
`docs/PROTOCOL.md`, section 14) are the most useful. We do not commit to a fixed response time.

## What the messaging kit protects, and what it does not

This section summarizes the threat model of `organism_continuity.telepatia` (signature format
`telepatia-sig v=1`). The normative details are in [`docs/PROTOCOL.md`](docs/PROTOCOL.md),
sections 4 to 12.

The kit is local, file-based messaging between agents on one host (or a shared disk) that run
under accounts the operator trusts. It is not a multi-tenant message broker.

### Authentication: shared-key HMAC, not public-key signatures

- Each sender has its own 32-byte key. Messages carry an HMAC-SHA256 trailer over the sender
  name, the signed time, a 128-bit nonce and a hash of the whole content (including the `to:` and
  `from:` lines). MACs are compared in constant time.
- A valid MAC proves only that **some holder of the sender's key** produced the message. It is
  not a public-key signature and gives no non-repudiation.
- **Anyone who holds a sender's key can forge messages from that sender**, including every peer
  that was given the key in order to verify that sender. Give a key only to parties you would let
  speak as that sender. Public-key signatures (Ed25519 per identity) are a possible later phase;
  v0.5 does not ship them.

### Replay protection

- Freshness is measured against the transport time (the message file's mtime), never against the
  sender-chosen timestamp alone: `|mtime - ts|` must be at most 600 s. Files older than the 7-day
  retention, more than 600 s in the future, or older than the nonce-store floor are rejected as
  `stale`.
- Every accepted `(sender, nonce)` pair is recorded in a **mandatory persistent nonce store** before
  success is reported. The store is consulted only after the MAC verifies, so unauthenticated input
  cannot fill or probe it.
- The nonce store **fails closed**: if it is missing, not a regular file, oversized or corrupt, the
  inbox refuses to read and consumes nothing. Recovery is an explicit operator action
  (`telepatia inbox --reset-nonce-store --yes`), which rejects every message already waiting.

### Keys

- Keys are generated from the OS CSPRNG by `telepatia init`, never printed, and stored as a
  regular file of mode `0600` in a directory of mode `0700`. Loaders refuse symlinks, wrong owners
  and wrong modes. Key files are refused inside a git work tree.
- Key exchange is **out-of-band**: the kit never transmits keys. Copy the sender's key file over a
  channel you trust, then compare fingerprints (`telepatia key fingerprint`) over a second channel.
- On suspected exposure, treat every key readable by the affected Unix user as leaked: rotate
  (`telepatia key rotate`), redistribute and revoke (`telepatia peer remove`). Deleting a key file
  does not remove copies or backups.

### No confidentiality

Messages are **signed, not encrypted**. Message bodies, queued outbox bodies and handoff packages
are plaintext on disk. File modes protect against other ordinary Unix users only. If you need
confidentiality, the storage or transport must provide it.

### Other limits

- Presence records are unsigned and advisory. They only delay delivery and never grant authority.
- Handoff packages are unsigned data, not instructions. `--notify` signs a pointer, not later edits
  of the package.
- Atomic writes prevent partial messages, but delivery is not exactly-once: a crash at an unlucky
  point can duplicate a delivery or consume a message before the caller processes it. Use
  idempotent handlers.
- There are size limits per file but no quotas; anyone with write access to the spool can fill it
  or delete files.

### Known residual risks (v0.5)

- **Clock jumps.** Nonces are pruned relative to the reader's current clock. If the reader's clock
  jumps forward by more than about 600 s and is then corrected (equivalently, rolls back), entries
  pruned in the meantime are forgotten, and a copy of an old message that preserves its original
  mtime could be accepted again while it is still inside the 7-day retention. Keep the host clock
  monotonic (NTP slewing, not stepping) on readers.
  The replay ledger for non-spool texts (`channel` / `ledger`, since 0.5.1) is not exposed to this:
  it keeps a prune `watermark` that never decreases and refuses as `stale` any text whose expiry
  is below it, so a backward clock step after a prune cannot re-admit a forgotten nonce.
- **`inbox --peek`** returns verified messages without recording their nonces or moving them, so
  the same message is returned on every peek. It does not consume nonces, but callers must not act
  on peeked messages; act only on a normal (consuming) read.
- The 7-day retention is much longer than the 600 s window; during that period the nonce store,
  not the window, is what stops an mtime-preserving replay.

## Out of scope

- **Compromised host or same-user processes.** Any process running as the same Unix user (or root)
  can read every key, rewrite the nonce store and forge anything.
- **Terminal typing / send-key helpers.** Code that types into terminals is quarantined
  (`quarantine/send-key/`) and is not part of the v0.5 package.
- **Funnel / public port exposure.** Tools that expose a local service to the internet are not
  part of the v0.5 package.
- The legacy MCP-shaped tools (`server.py`, `stdio_server.py`) and the background essays in
  `docs/essays/` are not covered by this threat model.
