---
id: feature-001
kind: feature
title: Add rate limiting to public API
severity: minor
category: security
location: api/routes.py
status: open
created: 2026-05-19
labels: [api, security, enhancement]
target:
  github: null
  gitlab: null
---

## Description

The public API has no rate limiting. Adding per-IP and per-user rate limits
would prevent abuse and reduce load from misbehaving clients.

## Suggested Implementation

Use a sliding-window rate limiter (e.g., Redis-backed) with configurable limits:
- 100 req/min per IP for unauthenticated endpoints
- 1000 req/min per user for authenticated endpoints

## Acceptance Criteria

- [ ] Limits configurable via env vars
- [ ] 429 response with Retry-After header on limit exceeded
- [ ] Metrics emitted for limit hits
