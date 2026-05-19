---
id: bug-001
kind: bug
title: SQL injection in auth.py
severity: major
category: security
location: auth.py:42
status: open
created: 2026-05-19
source: review-adversarial:F1
labels: [security, auth]
target:
  github: null
  gitlab: null
---

## Description

SQL injection via f-string interpolation in the query builder. User input is
concatenated directly into the SQL string without escaping.

## Suggested Fix

Use parameterized queries with `cursor.execute(sql, params)`. Never interpolate
user input into SQL strings.

## Context

Found during adversarial review on 2026-05-19 from the Attacker perspective.
