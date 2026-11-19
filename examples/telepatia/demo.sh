#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Synthetic two-agent local demo. All state is created outside the checkout.
set -euo pipefail
DEMO="$(mktemp -d)"
A="$DEMO/a/telepatia.toml"
B="$DEMO/b/telepatia.toml"
telepatia init --name agent-a --config "$A" --spool "$DEMO/spool"
telepatia init --name agent-b --config "$B" --spool "$DEMO/spool"
telepatia peer add agent-a --key-file "$DEMO/a/keys/agent-a.key" --config "$B"
telepatia peer add agent-b --key-file "$DEMO/b/keys/agent-b.key" --config "$A"
telepatia key fingerprint --config "$A"
telepatia peer list --config "$B"
telepatia chama agent-b "synthetic build complete" --config "$A"
telepatia inbox --wait --timeout 5 --config "$B"
printf 'Demo state: %s\n' "$DEMO"
