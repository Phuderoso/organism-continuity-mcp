# telepatia-sig v=1 and the telepatia-kit file spool

Status: normative for telepatia-kit 0.5.x. Protocol version: `v=1` (domain `telepatia-sig/v1`).

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. An implementation in
another language that follows sections 2 to 8 interoperates with this kit. The test vectors in
section 15 (and `tests/vectors/telepatia-sig-v1.json`) are part of this specification.

## 1. Scope: which format is v0.5

- v0.5 ships exactly **one** signature format: `telepatia-sig v=1` (sections 2 to 4). It is
  byte-for-byte the trailer format already used by the text channel this kit was extracted from.
  Cross-verification holds **at the MAC level**: the same content, signer, ts and nonce give the
  same MAC on both sides, and every message the kit signs is accepted by the channel verifier.
  The kit's spool reader is deliberately **stricter** than the channel: it rejects a `ts` with
  leading zeros and a non-canonical (for example uppercase) `from` as `malformed`, requires the
  spool content profile (section 5), and rejects a message for another recipient as
  `wrong_recipient`. So a channel-signed text is accepted by the kit only if it already has the
  spool profile, a lowercase canonical `from` and the reader as recipient.
- The kit's transport is a **file spool** on one host (section 5). Transports that carry the same
  trailer elsewhere (for example comments on a code-hosting service) are out of scope for this
  document except for the requirement they share: freshness is measured against the transport's
  own time (section 7).
- The earlier JSON envelope `telepatia-msg/v1` from pre-release drafts is **not** part of v0.5.
  No JSON message format exists in this version.
- Presence records (section 11) are unsigned and advisory. They never authorize anything.
- There is no unsigned mode. The configuration keys `legacy_unsigned_wake`, `allow_unsigned` and
  `accept_unsigned` (in any table) are refused: loading a config that contains any of them fails
  with a configuration error.

What a valid signature grants: the reader learns that the holder of the sender's key produced
this content for this recipient within the window, once. It grants nothing else. Delivery and
listing of files do not depend on signatures; acting on a message (waking an agent, executing
an instruction) MUST depend on status `verified`.

## 2. Trailer grammar

A signed text is `content` followed by exactly one trailer line. The trailer is the **last
non-empty line** of the text; trailing `\n` characters after it are ignored. Any other line that
looks like a trailer (earlier in the text) is ordinary content.

```
trailer  = "<!--" WS "telepatia-sig" WS1 "v=1" WS1 "from=" from WS1 "ts=" ts WS1
           "nonce=" nonce WS1 "mac=" mac WS "-->"
WS       = *( " " / HTAB )            ; regex \s*, applied after stripping the line
WS1      = 1*( " " / HTAB )
from     = 1*( any char except whitespace, "<", ">" )
ts       = 1*12DIGIT                  ; decimal Unix seconds
nonce    = 16*64( %x30-39 / %x61-66 ) ; lowercase hex
mac      = 64( %x30-39 / %x61-66 )    ; lowercase hex HMAC-SHA256
```

Reference regex (Python `re`, matched against the stripped last line):

```
^<!--\s*telepatia-sig\s+v=1\s+from=(?P<from>[^\s<>]+)\s+ts=(?P<ts>\d{1,12})\s+nonce=(?P<nonce>[0-9a-f]{16,64})\s+mac=(?P<mac>[0-9a-f]{64})\s*-->$
```

Signers MUST emit exactly one space between fields, `ts` without leading zeros, and a 128-bit
random nonce (32 hex characters). A text whose last non-empty line does not match is `unsigned`.

## 3. Content and canonical form

**Content.** Given the text, strip trailing `\n`, split off the last line (the trailer). The
content is everything before it plus exactly one `\n`; if there is nothing before it, content is
the empty string. When signing, if the content does not end in `\n`, one `\n` is appended; an
existing trailer is replaced, not stacked.

No normalization of any kind is applied: no Unicode normalization, no `\r\n` to `\n` conversion,
no trimming. A text rewritten with CRLF line endings fails as `bad_mac` (fail closed).
Content MUST be encodable as UTF-8; a signer MUST refuse content with lone surrogates, and a
reader MUST decode the raw bytes as strict UTF-8 and treat failure as `malformed` (section 6).

**base_key(name).** Applied to `from` before it enters the MAC:

1. replace every run of Unicode whitespace with one space and trim both ends;
2. apply Unicode full case folding (`str.casefold()`; for example `STRASSE` and `Straße` both
   become `strasse`);
3. strip the characters `*`, backtick, `'` and `"` from both ends (repeatedly);
4. remove one trailing tag matching `\s*\[[^\]]*\]$`, then trim again.

Aliases, display names and any other mapping MUST NOT enter the MAC; only `base_key(from)` does.

**Canonical form** (UTF-8 bytes, no trailing newline):

```
"telepatia-sig/v1\n" + base_key(from) + "\n" + decimal(ts) + "\n" + nonce + "\n" + hex(sha256(utf8(content)))
```

`decimal(ts)` is the integer value written without leading zeros. `hex` is lowercase.
`mac = hex(HMAC-SHA256(key, canonical))`. Verifiers MUST compare the MAC in constant time
(`hmac.compare_digest` or equivalent).

**Known malleability.** Because the MAC covers `int(ts)` and `base_key(from)`, the generic
grammar admits several trailers with the same MAC: `ts=0170...` equals `ts=170...`, and
`from=Agent-A`, `from=AGENT-A`, `from=agent-a[x]` equal `from=agent-a`. This does not change who
signed. The trailer is therefore not unique and deduplication MUST be done by
`(base_key(from), nonce)`, never by trailer bytes. The spool profile (section 5) removes the
ambiguity by rejecting non-canonical `ts` and `from` as `malformed`.

## 4. Keys

- A key is 32 random bytes from a CSPRNG (`secrets.token_bytes(32)`). Verifiers MUST refuse keys
  shorter than 32 bytes.
- Key file: the key as 64 lowercase hex characters followed by `\n`, a regular file (not a
  symlink) owned by the current user, mode `0600`, in a directory of mode `0700`. Loaders MUST
  refuse anything else. Key files MUST NOT be created inside a git work tree.
- Fingerprint: the first 16 hex characters of `sha256("telepatia-key-fingerprint/v1\n" + key)`.
  Two parties compare fingerprints over a second channel (voice, in person, a separate
  authenticated chat), never the key itself.
- The keyring of a verifier maps `base_key(name)` to that peer's key. The peers file holds only a
  name and a key path; no key material is ever stored in configuration.
- Distribution is out-of-band: the receiver gets a copy of the sender's key file through a
  channel the operator trusts. The kit never transmits keys.

## 5. Spool transport profile

Layout under the spool directory, all directories `0700`, all files `0600`:

```
inbox/<name>/            one file per message: <ts>-<nonce[:16]>.msg
inbox/<name>/read/       verified and consumed
inbox/<name>/rejected/   quarantined as <file>.<reason>
state/<name>/nonces.json persisted nonce store (section 8)
state/<name>/inbox.lock  reader lock (flock)
```

Writers create a temp file starting with `.`, fsync it and rename it into place; readers ignore
names starting with `.` and names not ending in `.msg`. Files larger than 65536 bytes, symlinks
and non-regular files are rejected without being parsed.

**Content profile.** On top of section 3 the spool requires exactly this content shape:

```
"to: " <recipient> "\n" "from: " <sender> "\n" "\n" <body> "\n"
```

`recipient` and `sender` match `^[a-z0-9][a-z0-9._-]{0,63}$`. `body` is non-empty after
trimming whitespace; senders refuse bodies over 32768 characters. There are no other fields and
no optional headers; any deviation is `malformed`. The trailer `from` MUST equal its own
`base_key` and match the name grammar, and `ts` MUST match `^(0|[1-9][0-9]{0,11})$`; otherwise
the message is `malformed`. The message id is the nonce.

## 6. Verification (normative order)

A reader with name `me`, keyring `K`, a transport time `T` and a nonce store `S` processes the
raw bytes of one message in this order and stops at the first failure:

| Step | Check | Status on failure |
|---|---|---|
| 1 | size at most 65536 bytes | `too_large` (a non-regular file or symlink: `not_regular_or_too_large`) |
| 2 | strict UTF-8 decode | `malformed` |
| 3 | last non-empty line matches the trailer grammar | `unsigned` |
| 4 | spool profile (section 5): canonical `ts` and `from`, content shape | `malformed` |
| 5 | `K[base_key(from)]` exists | `unknown_key` |
| 6 | constant-time MAC compare | `bad_mac` |
| 7 | `base_key(trailer from) == base_key(from: header)` | `sender_mismatch` |
| 8 | `to: header == me` | `wrong_recipient` |
| 9 | transport checks and window (section 7) | `stale` |
| 10 | `(base_key(from), nonce)` not in `S` | `replayed_nonce` |

Only a message that passes all ten steps is `verified`. The nonce store is consulted only after
the MAC is valid, so unauthenticated input cannot fill or probe it. After a verified message is
consumed, its `(base_key(from), nonce)` MUST be recorded in `S` and `S` MUST be persisted before
the reader reports success. The kit saves `S` first and only then moves the consumed files to
`read/`; if saving fails, the read fails, nothing is reported and the files stay in the inbox to
be retried. A peek (`--peek`, `mark_read=False`) reports verified messages without consuming them
and persists nothing. Rejected files are moved to `rejected/` and never wake a reader.

## 7. Freshness against transport time

The signed `ts` is chosen by the sender and MUST NOT be used as the clock. Freshness is
measured against the **transport time** `T`, a time the transport (not the message) provides:

- for the spool, `T` is the file's mtime as seen by the reader;
- for other transports, the server-assigned creation time (for example a receive timestamp).

A verifier MUST reject as `stale` when `|T - ts| > 600` seconds, in both directions. The spool
reader additionally rejects as `stale` a file whose mtime is more than 7 days (`RETENTION_S`)
older than the reader's clock, more than 600 s in its future, or older than the nonce-store
floor (section 8, with 2 s slack for coarse filesystem clocks), and a message whose signed `ts`
is older than the floor, whatever its mtime.

Consequence: a copy of an old message dropped into an inbox gets a fresh mtime and fails the
600 s window; a copy that preserves the old mtime is within retention only while its nonce is
still in the store, and is then `replayed_nonce`. A verifier that has no trustworthy transport
time loses freshness protection and MUST NOT accept messages; the API makes the transport time
and the nonce store mandatory parameters.

The 600 s window bounds clock skew between writer and transport, not how long a message may
wait. The 7-day retention bounds how long a delivered file may sit unread. Neither is a delivery
deadline; the outbox (section 10) holds messages for at most 30 minutes before giving up.

## 8. Nonce store

- Format: `{"v": 1, "floor": <unix seconds>, "nonces": {"<base_key>:<nonce>": <ts>, ...}}`, a
  regular `0600` file of at most 4 MiB, rewritten atomically under the reader lock.
- Entries are kept for `RETENTION_S + 2 * 600` seconds past their `ts`, which covers every
  message that could still pass section 7.
- The store is created by `telepatia init`. It **fails closed**: when it is missing, not a
  regular file, oversized, not valid JSON, or not of the exact shape above, the reader refuses to
  read (`NonceStoreError`, CLI exit 1) and consumes nothing.
- Recovery is explicit: `telepatia inbox --reset-nonce-store --yes` moves the old file aside
  (`nonces.json.bad-<ts>`) and writes an empty store whose `floor` is the current time. Every
  file with an mtime below the floor, and every message whose signed `ts` is below the floor, is
  then `stale`. The second rule matters: a writer could copy a message consumed shortly before
  the reset and give the copy an mtime after the floor (within 600 s of its `ts`); the signed `ts`
  still predates the reset, so the copy is refused. Messages already in the inbox before the
  reset are not delivered; senders must resend them.

## 9. Rotation and revocation

There is no key id in the trailer. After a rotation, messages signed with the old key are
`bad_mac` and are quarantined, never acted upon.

Rotation procedure: quiesce the sender (flush its outbox), `telepatia key rotate`, distribute the
new key file out-of-band to every verifier, compare fingerprints on a second channel, send a
synthetic smoke message. The old and new key cannot coexist under one name in v1.

Revocation: remove the peer from every verifier (`telepatia peer remove`, then delete the key
file); its messages become `unknown_key`. If any key file of a Unix user may have leaked,
consider every key readable by that user leaked and rotate all of them.

## 10. Outbox

The outbox stores unsigned bodies with an allowlisted set of fields and never stores keys, MACs
or nonces. Each delivery attempt signs anew with a fresh `ts` and nonce, so a queued message is
never delivered with a stale timestamp. Delivery is driven by an explicit flush or by events on
the presence directory, never by clock polling.

## 11. Presence (advisory, unsigned)

A presence record is a JSON object of at most 4096 bytes with a `state` in `idle`, `busy`,
`absent` and a `ts` as epoch seconds or ISO 8601. A record is fresh when at most 120 s old; a
`ts` more than 30 s in the future, a missing or unreadable file, or any invalid field yields
`unknown`. Presence is only a scheduling hint (for `--when-idle`).

## 12. Threat model

In scope (protected against):

- a party without the sender's key that can write files into the spool: forging a message,
  editing content, removing or replacing the trailer, redirecting to another recipient;
- replay of an old message into an inbox (section 7) and duplicate delivery (section 8);
- malformed or oversized input, symlink tricks in the spool (rejected without being followed).

Out of scope (not protected against):

- **Any verifier can forge the sender.** HMAC is symmetric: a peer that holds `agent-a.key` to
  verify messages from `agent-a` can sign messages "from agent-a" to any third party that also
  trusts that key. Give a key only to parties you would let speak as that sender.
- **Processes of the same Unix user** can read every key, rewrite the nonce store and forge
  anything. The file modes protect against other users only.
- **Confidentiality.** Messages are plaintext on disk.
- **Availability.** Anyone with write access to the spool can fill it or delete files.
- Presence is unsigned and can be spoofed by anyone who can write the presence directory.

Accepted risks of phase 1: symmetric keys under one Unix user; the 7-day retention is much
longer than the 600 s window of the transport-time check, so the nonce store, not the window,
is what stops a mtime-preserving replay during that period. Phase 2 SHOULD move to Ed25519 (a
private key per identity, public keys for verifiers), which removes verifier forgery.

## 13. Versioning

The version is carried twice: `v=1` in the trailer and the domain string `telepatia-sig/v1` in
the canonical form. A verifier MUST treat any other `v` as `unsigned`. A future `v=2` is expected
to: bind the recipient and transport context (for example the channel identifier) into the MAC,
carry a key id to allow overlapping rotation, and sign the literal canonical `ts` string.

## 14. Other transports and relays (0.5.1)

This section applies the same trailer to texts that do not travel over the spool (for example
comments on a code-hosting service, wake requests, relayed texts). Reference implementation:
`organism_continuity.telepatia.channel`, `.ledger` and `.relay`.

Verification of such a text (`channel.verify_text`), in this order:

1. The receive time `T` MUST be supplied by the transport and MUST be a finite number;
   otherwise the call fails before any other check. The signed `ts` is never the clock.
2. Grammar as in section 2 (any content; no spool profile, no recipient check). Missing trailer:
   `unsigned`. Text over 64 KiB: `too_large`. Not UTF-8 encodable: `malformed`.
3. Key lookup by `base_key(from)` (`unknown_key`), constant-time MAC compare (`bad_mac`).
4. `stale` when `|T - ts| > 600`, when `T` is more than 7 days older than the verifier's clock,
   or when `T` is more than 600 s ahead of it.
5. The nonce is checked and claimed in a replay ledger under one exclusive lock
   (`replayed_nonce` when already present; `stale` when `ts + 600` is below the ledger's
   `watermark`). Only after this step is the text `verified`.

Replay ledger: `{"v": 1, "nonces": {"<base_key>:<nonce>": <ts + 600>}, "watermark": <epoch>}`
(`watermark` optional; files without it are read as having none), a regular `0600` file
of at most 4 MiB in a directory not writable by group or other, never followed through a
symlink. Any deviation (symlink, special file, other owner, group/other permission bits,
oversize, invalid or deeply nested JSON, non-finite values, extra keys) is an error and the
verifier MUST NOT act on the text (fail closed). Entries are pruned against the verifier's own
clock, never the transport's, and only once they are more than 7 days past expiry, which is
the same bound as the receive-time check in step 4, so a pruned entry cannot be replayed while
the clock only moves forward. Caveat: if the clock steps back by more than that margin after a
prune, step 4 alone would re-admit a forgotten nonce; the `watermark` (the highest prune horizon
ever used, never lowered) closes this, because a text whose `ts + 600` is below it is `stale`.

Dry run: all checks run against a shared-locked, read-only view of the ledger. Nothing is
created or claimed, so a text that was only checked can still be verified for real once. A
caller that defers acting on a text SHOULD dry-run first and claim only when it acts.

Relay body (`relay.format_relay`):

```
<!-- telepatia-relay -->
<!-- reply-to: <id> -->        (optional)
**from: <origin>**
to: <recipient>                (optional)

<message>
```

A relay is unsigned unless the caller opts in for that call. A signed relay carries an
ordinary `telepatia-sig v=1` trailer made by the **relayer** with the relayer's key, so a
verifier learns that the relayer vouched for it; the `from:` line is informational and MUST NOT
grant the origin's authority. A message that already ends in a trailer is refused when the relay
body is built, so it cannot pass for the origin's own signature.

## 15. Test vectors

TEST KEY (for test vectors only, public, never use it for anything else):
`000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f`

Vector 1, recipient `agent-b`, transport time `1700000000`:

```
content   = "to: agent-b\nfrom: agent-a\n\nhello, synthetic test vector\n"
sha256    = 64b83f11a483c1a5ce1f72d392e497adcba0dffafea2bea471d09c313725ca83
canonical = "telepatia-sig/v1\nagent-a\n1700000000\n00112233445566778899aabbccddeeff\n64b83f11a483c1a5ce1f72d392e497adcba0dffafea2bea471d09c313725ca83"
mac       = ee31e8717c8a8322d964c9c00f7088cc8e8042d28a057a95b750202f3650d1c2
trailer   = <!-- telepatia-sig v=1 from=agent-a ts=1700000000 nonce=00112233445566778899aabbccddeeff mac=ee31e8717c8a8322d964c9c00f7088cc8e8042d28a057a95b750202f3650d1c2 -->
```

Only positive vector 1 is a complete spool message that a reader accepts (`verified`). Positive
vectors 2 to 4 exercise only the MAC and the canonical form (content, `base_key`, canonical bytes,
MAC); as messages they are not accepted by either verifier (the spool reader returns `malformed`,
the channel `sender_mismatch`).

`tests/vectors/telepatia-sig-v1.json` holds 4 positive vectors (spool profile, plain text, multi-line
content, and `base_key` folding of `Agent-A[tag]` with non-ASCII content) and 12 negative vectors, at least one per rejection status:
`unsigned`, `malformed` (leading-zero `ts`, non-canonical `from`, missing profile),
`unknown_key`, `bad_mac` (edited body, CRLF rewrite), `sender_mismatch`, `wrong_recipient`,
`stale` (601 s after and before), `replayed_nonce`. `too_large` and invalid UTF-8 are covered by
unit tests because they are not representable as JSON text.
