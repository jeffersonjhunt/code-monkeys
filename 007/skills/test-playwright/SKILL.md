---
name: test-playwright
description: Manage, create, and run Playwright end-to-end tests. Use when asked to set up Playwright, scaffold test files, run tests, debug failures, generate code, or view reports.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# test-playwright

Unified skill for Playwright end-to-end testing workflows.

## Usage

```bash
playwright.sh init                     # Set up Playwright in a project
playwright.sh create <name>            # Scaffold a new test file
playwright.sh run [filter]             # Run tests (all or filtered)
playwright.sh run --headed             # Run with browser visible
playwright.sh run --browser=firefox    # Specific browser
playwright.sh debug [filter]           # Run with trace + headed + slow-mo
playwright.sh codegen [url]            # Launch test recorder
playwright.sh report                   # Open last HTML report
playwright.sh ci                       # CI mode (all browsers, retries)
```

## Dependencies

- Node.js >= 18
- npm or pnpm

Playwright itself is installed per-project via `playwright.sh init`.

## Templates

The `assets/templates/` directory contains starter files:

- `basic.spec.ts` — Simple test with navigation and assertions
- `page-object.ts` — Page Object Model pattern
- `playwright.config.ts` — Recommended config with sensible defaults
