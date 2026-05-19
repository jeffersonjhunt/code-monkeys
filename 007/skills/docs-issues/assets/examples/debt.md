---
id: debt-001
kind: debt
title: Refactor user service to use dependency injection
severity: minor
category: maintainability
location: services/user.py
status: open
created: 2026-05-19
labels: [refactor]
target:
  github: null
  gitlab: null
---

## Description

`UserService` instantiates its dependencies (DB connection, cache, mailer)
directly in `__init__`. This makes it hard to test in isolation and couples
the service to specific implementations.

## Suggested Refactor

Accept dependencies as constructor parameters. Use a small DI container
(or factory function) at the composition root.

## Risk

Low — public API unchanged. Internal refactor only.
