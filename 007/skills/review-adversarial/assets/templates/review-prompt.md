# Adversarial Review Prompt Template

Use this template to structure your adversarial review. Adopt the specified
perspective and systematically evaluate the target artifact.

---

## Review Context

- **Target**: {target_description}
- **Type**: {code|diff|design_doc}
- **Perspective**: {perspective}
- **Round**: {round_number}

---

## Perspective Instructions

### Attacker
You are a malicious actor trying to exploit this code. Look for:
- Input validation gaps (injection, overflow, format strings)
- Authentication/authorization bypasses
- Data exfiltration paths
- Privilege escalation opportunities
- Race conditions that can be exploited
- Secrets or credentials in code/config

### Skeptical User
You are a user who doesn't trust this software. Look for:
- Unhandled error conditions that lose data
- Edge cases with unexpected behavior
- Misleading API contracts or documentation
- Silent failures that corrupt state
- Missing input validation on user-facing interfaces

### Future Maintainer
You are reading this code for the first time in 6 months. Look for:
- Undocumented assumptions or magic values
- Tight coupling that makes changes risky
- Missing or misleading comments
- Inconsistent patterns within the codebase
- Dead code or unreachable branches
- Missing tests for critical paths

### Ops Engineer
You are responsible for running this in production. Look for:
- Resource leaks (connections, file handles, memory)
- Missing timeouts or retry limits
- Inadequate logging/observability
- Failure modes that cascade
- Configuration that can't be changed without redeployment
- Missing health checks or graceful shutdown

### Pedantic Reviewer
You enforce strict code quality standards. Look for:
- Naming inconsistencies
- Style violations relative to the project
- Unnecessary complexity or abstraction
- Copy-paste duplication
- TODO/FIXME/HACK comments left unresolved
- Unused imports, variables, or parameters

---

## Output Format

Produce findings as a JSON array:

```json
[
  {
    "id": "F1",
    "severity": "major",
    "category": "security",
    "location": "auth.py:42",
    "description": "SQL injection via f-string interpolation in query builder",
    "suggestion": "Use parameterized queries with cursor.execute(sql, params)"
  }
]
```

Severity scale:
- **critical** — Exploitable vulnerability, data loss, or crash in normal operation
- **major** — Significant bug, security weakness, or design flaw
- **minor** — Code smell, minor bug in edge case, or maintainability concern
- **nit** — Style, naming, or trivial improvement

---

## Re-review Instructions (Round > 1)

When re-reviewing after author responses:

1. **Fixed findings**: Verify the fix is correct and complete. Check for regressions.
2. **Disputed findings**: Re-evaluate given the author's rationale. Either drop or escalate.
3. **New code**: Review any new code introduced by fixes with the same adversarial lens.
4. Only report genuinely new or unresolved issues — do not repeat resolved findings.
