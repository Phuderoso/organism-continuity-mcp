#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Synthetic handoff demo: package a "long" lane for a "fresh" one and notify a peer.
# All state is created outside the checkout.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEMO="$(mktemp -d)"
A="$DEMO/a/telepatia.toml"
B="$DEMO/b/telepatia.toml"
telepatia init --name agent-a --config "$A" --spool "$DEMO/spool"
telepatia init --name agent-b --config "$B" --spool "$DEMO/spool"
telepatia peer add agent-a --key-file "$DEMO/a/keys/agent-a.key" --config "$B"
mkdir -p "$DEMO/sessions/long" "$DEMO/sessions/fresh"
sed -n '/^\[handoff\]/,$p' "$HERE/handoff.example.toml" >> "$A"
telepatia-handoff status --config "$A"
telepatia-handoff package --source long --dest fresh --note "synthetic handoff" --notify agent-b --config "$A"
telepatia inbox --config "$B"
printf 'Demo state: %s\n' "$DEMO"
