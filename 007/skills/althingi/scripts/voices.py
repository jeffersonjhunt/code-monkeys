#!/usr/bin/env python3
"""voices.py — Voice registry for Althingi roundtable discussions.

Commands:
    list      List all available voices
    show      Show a voice's full persona
    suggest   Suggest voices for a given topic

Usage:
    python voices.py list
    python voices.py show architect
    python voices.py suggest --topic "database migration strategy"
"""

import argparse
import json
import os
import sys
from pathlib import Path

VOICES_DIR = Path(__file__).resolve().parent.parent / "assets" / "voices"

# Topic keywords mapped to relevant voice IDs
TOPIC_HINTS = {
    "security": ["security", "skeptic", "architect"],
    "auth": ["security", "skeptic", "architect"],
    "performance": ["architect", "pragmatist", "skeptic"],
    "scale": ["architect", "pragmatist", "skeptic"],
    "migration": ["architect", "skeptic", "pragmatist", "security"],
    "api": ["architect", "user-advocate", "security"],
    "ui": ["user-advocate", "pragmatist", "devils-advocate"],
    "ux": ["user-advocate", "pragmatist", "devils-advocate"],
    "design": ["architect", "skeptic", "user-advocate"],
    "deploy": ["security", "pragmatist", "architect"],
    "refactor": ["architect", "pragmatist", "skeptic"],
    "test": ["skeptic", "pragmatist", "security"],
}


def load_voices():
    voices = {}
    if not VOICES_DIR.is_dir():
        return voices
    for f in sorted(VOICES_DIR.glob("*.json")):
        try:
            with open(f) as fh:
                v = json.load(fh)
                voices[v["id"]] = v
        except (json.JSONDecodeError, KeyError):
            continue
    return voices


def cmd_list(args):
    voices = load_voices()
    out = [{"id": v["id"], "name": v["name"], "perspective": v["perspective"]} for v in voices.values()]
    print(json.dumps(out, indent=2))


def cmd_show(args):
    voices = load_voices()
    if args.voice_id not in voices:
        print(f"Error: unknown voice '{args.voice_id}'. Available: {', '.join(sorted(voices.keys()))}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(voices[args.voice_id], indent=2))


def cmd_suggest(args):
    voices = load_voices()
    topic_lower = args.topic.lower()
    suggested = set()
    for keyword, voice_ids in TOPIC_HINTS.items():
        if keyword in topic_lower:
            suggested.update(voice_ids)
    # Default: architect + skeptic + pragmatist if no keywords match
    if not suggested:
        suggested = {"architect", "skeptic", "pragmatist"}
    # Filter to voices that actually exist
    result = [vid for vid in suggested if vid in voices]
    print(json.dumps({"topic": args.topic, "suggested_voices": sorted(result)}))


def main():
    parser = argparse.ArgumentParser(description="Althingi voice registry.")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all available voices")

    p_show = sub.add_parser("show", help="Show a voice's persona")
    p_show.add_argument("voice_id", help="Voice ID (e.g., architect)")

    p_suggest = sub.add_parser("suggest", help="Suggest voices for a topic")
    p_suggest.add_argument("--topic", required=True, help="Discussion topic")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {"list": cmd_list, "show": cmd_show, "suggest": cmd_suggest}[args.command](args)


if __name__ == "__main__":
    main()
