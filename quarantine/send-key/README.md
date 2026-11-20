# Send-key map — quarantined (later batch)

This directory is a placeholder. The v0.5 package does **not** ship the
host send-key map.

## Why it is not in v0.5

The current tree exposes a `continuity.send_key_map` tool in `server.py`.
That tool documents host-specific editor keybindings and refers to a local
helper that can type into terminal sessions. It is tightly coupled to one
machine layout and is not a portable, safe-by-default library feature.

An engineering team adopting this repository should be able to install the
messaging, queue, presence, handoff, and preflight modules without also
pulling in terminal-injection helpers.

## Later batch

A future release may move the map here, behind an explicit extra or a
clearly documented, disabled-by-default tool, with:

- no hardcoded session names or home-directory paths
- a warning that the helper types into a local terminal only when the
  operator opts in
- tests that do not require a live terminal session

Until then, do not add send-key or terminal-injection code to the
installable package.
