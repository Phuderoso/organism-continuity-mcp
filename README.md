# organism-continuity MCP

Multi-agent continuity tools (Organismo Soberano). Version **0.4**.

```bash
python3 tools/mcp_organism_continuity/server.py list-tools
python3 tools/mcp_organism_continuity/server.py call doctor
python3 tools/mcp_organism_continuity/server.py call peer_starter
```

Stdio: `stdio_server.py` · host: `host_snippet.json`  
Sibling: `tools/mcp_organism_power/` (FTS/recall).

Public mirror: https://github.com/Phuderoso/organism-continuity-mcp

## Configuration placeholders

`host_snippet.json` and `power/host_snippet.json` use `${ORGANISM_HOME}` as the
workspace root (for example `${ORGANISM_HOME}/tools/mcp_organism_continuity/stdio_server.py`).
Most MCP hosts do not expand environment variables in JSON config, so replace
`${ORGANISM_HOME}` with the absolute path of your workspace before pasting.
Links of the form `https://github.com/<org>/...` point to sibling repositories of
this project; replace `<org>` with the account that hosts them.

## Deprecated: terminal send-key features

> **Warning:** `continuity.send_key_map` and the `--live-agent-a` option of
> `power/system_test_battery.py` **type into terminals** (via tmux /
> terminal-control helpers). They are experimental, out of scope for v0.5, and
> will move to a later release. Do not enable them on shared or production hosts.

---

Background essays (not part of the tool's specification): [`docs/essays/`](docs/essays/README.md).
