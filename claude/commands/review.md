Review the current changes for issues.

1. Run `git diff` to see unstaged changes and `git diff --cached` for staged changes
2. Review for:
   - Correctness and logic errors
   - Security issues (exposed secrets, injection, etc.)
   - Consistency with existing conventions in the codebase
   - Missing cleanup patterns in Dockerfiles (apt-get autoclean, etc.)
3. Report findings concisely — only flag real issues, not style nits

$ARGUMENTS
