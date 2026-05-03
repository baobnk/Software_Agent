# BnK Document Agent — Session Memory

This file is loaded at the start of each session and updated as work progresses.
The agent writes discoveries, decisions, and project context here to survive
context compression across long conversations.

## Project Context
<!-- Updated by orchestrator at session start -->
- project_name: (not set)
- project_code: (not set)
- output_dir: (from OUTPUT_DIR env var)
- session_id: (not set)

## Pipeline State
<!-- Updated after each major step -->
- [ ] Intake complete
- [ ] BRD drafted
- [ ] BRD passed critic
- [ ] WBS estimated
- [ ] WBS passed critic
- [ ] Export confirmed by user
- [ ] Files saved

## Key Decisions
<!-- Record scope decisions, client constraints, tech choices -->
(none yet)

## Critic History
<!-- Track retry counts to avoid infinite loops -->
- BRD retries: 0
- WBS retries: 0

## Output Locations
<!-- Updated by exporter -->
- BRD file: (not exported yet)
- WBS file: (not exported yet)

---
*This file is managed by the bnk-deepagent orchestrator.*
