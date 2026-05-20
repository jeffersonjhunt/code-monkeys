---
id: question-001
kind: question
title: Should we cache the result of expensive_compute()?
severity: minor
category: performance
location: utils/compute.py:88
status: open
created: 2026-05-19
labels: [performance]
target:
  github: null
  gitlab: null
---

## Question

`expensive_compute()` is called on every request and takes ~200ms. Should we
cache the result? If so, what's the appropriate cache key and TTL?

## Considerations

- Inputs are mostly stable per-user but change occasionally
- Memory budget per process is limited
- Some calls are truly unique and shouldn't be cached

## Decision Needed

- Cache strategy: per-user, global LRU, or no cache?
- Invalidation trigger: TTL, event-based, or both?
