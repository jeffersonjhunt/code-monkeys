# Changelog — review-adversarial

## [1.1.0] - 2026-09-07

- **Triage gate at steps 4-6.** A finding is a proposal, not a work order: nothing is
  implemented before the user dispositions it as fix / dispute / accept. The steps existed but
  read as advice and were easy to skip; the gate now states the rule, the three dispositions, and
  the real cost of skipping it. Applies to findings from a subagent and to your own.
- Agent Instructions step 7 strengthened to STOP-and-wait, and to forbid marking everything
  `fixed` at the end as bookkeeping.
