# Changelog — agent-team

## [1.1.0] - 2026-09-07

- **Findings are proposals, not work orders** (new Important Rule 8). Never dispatch a fix for a
  tester or reviewer finding the human has not dispositioned.
- Review Loop now requires a **per-finding** disposition with the orchestrator's own
  recommendation on each; approving "the rework" as a block is explicitly not a disposition, since
  the point is to kill findings that should not be acted on at all. Only the `fix` set goes back to
  implementation.
- The same gate now explicitly covers the **Tester's** output, not just the Reviewer's.

## 1.0 (2026-08-12)

- Initial release
- Orchestrator state machine with 8 phases
- Agent config management (install/list/uninstall)
- HITL checkpoint protocol (approve/revise/skip/abort)
- SDLC integration for developer and reviewer agents
- Context threading between phases
- Review loop with max 2 iterations
