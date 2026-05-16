---
name: althingi
description: Orchestrate roundtable discussions with multiple agent voices. Use when asked to discuss, debate, or get multiple perspectives on a topic. Spawns real subagents by default; use --solo to roleplay all voices directly.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# Althingi

Roundtable discussion orchestrator. Named after the Icelandic Alþingi — the
general assembly. Each voice is a real subagent spawned independently so it
thinks for itself. You are the moderator, not a participant.

## When to Use

- User asks for multiple perspectives on a decision
- User wants a debate or roundtable on a topic
- User says "discuss", "what are the trade-offs", or "argue both sides"

## Orchestration Protocol (Default: Subagent Mode)

```
1. Pick voices:    python scripts/voices.py suggest --topic "..."
2. Initialize:     python scripts/althingi.py init --topic "..." --voices architect,skeptic,pragmatist [--rounds 2]
3. Loop:
   a. Get turn:    python scripts/althingi.py next --state .althingi-state.json
      → returns voice persona + accumulated context
   b. Spawn subagent via Agent tool using spawn-prompt.md template filled with:
      - voice persona (perspective, style, biases)
      - topic
      - discussion context so far
   c. Record:      echo "<subagent response>" | python scripts/althingi.py record --voice <id> --state .althingi-state.json
   d. Present the response to the user
   e. Repeat until next returns {"result": "complete"}
4. Transcript:     python scripts/althingi.py transcript --state .althingi-state.json
5. Synthesize:     Summarize points of agreement, disagreement, and open questions
```

**Critical rule:** In subagent mode, NEVER generate a voice's response yourself.
Every response must come from a spawned subagent. You are the moderator only.

## Solo Mode

When the Agent tool is unavailable or the user passes `--solo`:

```
python scripts/althingi.py init --topic "..." --voices architect,skeptic --solo
```

In solo mode, you roleplay each voice yourself using the persona definitions.
The scripts work identically — the only difference is you generate the responses
instead of spawning subagents.

## Scripts

### althingi.py — Session Orchestrator

```bash
python scripts/althingi.py init --topic "Should we use microservices?" --voices architect,skeptic,pragmatist --rounds 2
python scripts/althingi.py next --state .althingi-state.json
python scripts/althingi.py record --voice architect --state .althingi-state.json < response.txt
python scripts/althingi.py status --state .althingi-state.json
python scripts/althingi.py transcript --state .althingi-state.json --format markdown
python scripts/althingi.py transcript --state .althingi-state.json --format json
```

### voices.py — Voice Registry

```bash
python scripts/voices.py list                              # All available voices
python scripts/voices.py show architect                    # Full persona details
python scripts/voices.py suggest --topic "API design"      # Recommend voices for topic
```

## Available Voices

| ID | Name | Perspective |
|----|------|-------------|
| architect | The Architect | Systems design, scalability, long-term structure |
| skeptic | The Skeptic | Questions assumptions, finds gaps, stress-tests |
| pragmatist | The Pragmatist | Ship it — simplest thing that works today |
| security | The Security Engineer | Threat modeling, attack surface, trust boundaries |
| user-advocate | The User Advocate | End-user experience, accessibility, human impact |
| devils-advocate | The Devil's Advocate | Argues the opposite to stress-test ideas |

## Spawning a Subagent

Use the template in `assets/templates/spawn-prompt.md`. Fill placeholders from
the `next` command output:

```
{voice_name}    → output.voice_name
{perspective}   → output.persona.perspective
{style}         → output.persona.style
{biases}        → output.persona.biases
{topic}         → output.topic
{context}       → output.context
```

The subagent should receive ONLY the filled template as its prompt. Do not give
it access to tools or other context — it should respond purely from its persona.

## Agent Instructions

1. When the user asks for a roundtable/discussion/debate:
   - Use `voices.py suggest` to pick relevant voices (or let the user choose)
   - Initialize with `althingi.py init`
   - Loop: `next` → spawn → `record` → present → repeat
   - After completion, synthesize the discussion into actionable insights

2. Present each voice's response clearly labeled with the voice name.

3. After all rounds complete, provide a moderator's synthesis:
   - Points of agreement
   - Points of disagreement
   - Open questions or unresolved tensions
   - Recommended next steps (if applicable)

## Dependencies

Python 3.6+ (standard library only)
