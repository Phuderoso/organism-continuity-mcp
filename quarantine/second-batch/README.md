# Second-batch quarantine — funnel, doctor, and unsipped helpers

This directory holds MCP tools taken out of the v0.5 package. They are
**not** registered in `server.py` or `power/server.py`, and they are not
on the CLI. Removidas até virem com testes.

Send-key / terminal typing stays in `../send-key/` (already deprecated
on the live `continuity.send_key_map` tool and out of the installable
package).

## Why these came out

1. **Funnel and `doctor --fix-funnel`.** `continuity.funnel_ensure` and
   the doctor tool (which invoked `organism_doctor_all.py --json --fix-funnel`)
   can change a Tailscale Funnel and expose a local port on the public
   internet. They are not in v0.5 at all — not even behind a default-off
   flag.

2. **Missing helper scripts.** The remaining archived tools only worked
   by shelling out to scripts under `${WS}/tools/` that this repository
   does not ship. Used standalone they return errors. They return with
   tests, or not at all.

## Archived here

| Live name (removed) | Helper it called | Archive |
|---------------------|------------------|---------|
| `continuity.funnel_ensure` | `tools/taberna_funnel_ensure.py` | `continuity_removed_tools.py` |
| `continuity.doctor` | `tools/organism_doctor_all.py --json --fix-funnel` | `continuity_removed_tools.py` |
| `continuity.preflight` | `tools/sister_turn_preflight.py` | `continuity_removed_tools.py` |
| `continuity.dual_lane_pending` | `tools/dual_lane_context_relay.py` | `continuity_removed_tools.py` |
| `continuity.expect_reply_status` | `tools/sister_care_watch.py` | `continuity_removed_tools.py` |
| `continuity.joint_pulse` | `tools/sister_joint_pulse.py` | `continuity_removed_tools.py` |
| `continuity.open_loops` | `tools/open_loops_scan.py --write` | `continuity_removed_tools.py` |
| `continuity.personal_lab` | `tools/personal_lab_progress.py` | `continuity_removed_tools.py` |
| `continuity.handoff_hygiene` | `tools/dual_lane_handoff_hygiene.py` | `continuity_removed_tools.py` |
| `power.fts_status` / `power.fts_search` | `tools/organism_fts.py` | `power_removed_tools.py` |
| `power.recall` | `tools/organism_recall.py` | `power_removed_tools.py` |
| `power.personal_lab` | `tools/personal_lab_progress.py` | `power_removed_tools.py` |
| `power.open_loops` | `tools/open_loops_scan.py --write` | `power_removed_tools.py` |
| `power.night_watch` | `tools/night_watch_pass.py` | `power_removed_tools.py` |
| `power.proceed` | `tools/organism_proceed.py` | `power_removed_tools.py` |
| `power.ocarina_e2e` | `tools/ocarina_e2e_demo.py` | `power_removed_tools.py` |
| `power.system_test` | `tools/system_test_battery.py` | `system_test_battery.py` |

`system_test_battery.py` also drove the funnel helper and a live-terminal
flag; it is here for the same reasons.

## Still in the live v0.5 CLI (this repo)

- `continuity.send_key_map` (deprecated; see `../send-key/`)
- `continuity.ocarina_doctrine`, `continuity.gospel`, `continuity.harbor`, `continuity.peer_starter`
- `continuity.csv` and `power.csv` (use `tools/continuity_survival_calc.py`, which is in this repo)
