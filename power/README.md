# organism-power MCP

Local power stack for Organismo Soberano agents.

| Tool | Purpose |
|------|---------|
| `power.fts_status` | FTS5 index ready? |
| `power.fts_search` | Full-text search |
| `power.recall` | Hybrid RAG+FTS recall |
| `power.personal_lab` | Lab portfolio score |
| `power.open_loops` | Prompt-battery gaps |
| `power.night_watch` | Quiet autonomy pass |
| `power.csv` | Continuity survival calc sample |

```bash
python3 tools/mcp_organism_power/server.py list-tools
python3 tools/mcp_organism_power/server.py call recall --query "harbor gifts" --limit 5
```

Stdio: `stdio_server.py` · host snippet: `host_snippet.json`  
Pairs with `tools/mcp_organism_continuity/`.
