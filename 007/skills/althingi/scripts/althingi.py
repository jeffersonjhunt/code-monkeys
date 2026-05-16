#!/usr/bin/env python3
"""althingi.py — Roundtable discussion orchestrator.

Commands:
    init        Initialize a new roundtable session
    next        Get the next voice to speak (or signal completion)
    record      Record a voice's response
    status      Show session status
    transcript  Output the full discussion transcript

Usage:
    python althingi.py init --topic "..." --voices architect,skeptic [--rounds 2] [--solo] [--state PATH]
    python althingi.py next --state PATH
    python althingi.py record --voice architect --state PATH < response.txt
    python althingi.py status --state PATH
    python althingi.py transcript --state PATH [--format json|markdown]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

VOICES_DIR = Path(__file__).resolve().parent.parent / "assets" / "voices"


def load_voice(voice_id):
    path = VOICES_DIR / f"{voice_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: cannot read state '{path}': {e}", file=sys.stderr)
        sys.exit(1)


def save_state(path, state):
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def cmd_init(args):
    voices = [v.strip() for v in args.voices.split(",")]
    # Validate voices exist
    for vid in voices:
        if not (VOICES_DIR / f"{vid}.json").exists():
            available = [p.stem for p in sorted(VOICES_DIR.glob("*.json"))]
            print(f"Error: unknown voice '{vid}'. Available: {', '.join(available)}", file=sys.stderr)
            sys.exit(1)

    state = {
        "version": 1,
        "created": datetime.now(timezone.utc).isoformat(),
        "topic": args.topic,
        "mode": "solo" if args.solo else "subagent",
        "voices": voices,
        "rounds": args.rounds,
        "current_round": 1,
        "current_voice_idx": 0,
        "status": "active",
        "transcript": []
    }
    save_state(args.state, state)
    print(json.dumps({"initialized": args.state, "topic": args.topic, "voices": voices, "rounds": args.rounds, "mode": state["mode"]}))


def cmd_next(args):
    state = load_state(args.state)

    if state["status"] != "active":
        print(json.dumps({"result": "complete"}))
        return

    voice_id = state["voices"][state["current_voice_idx"]]
    voice = load_voice(voice_id)

    # Build context: prior responses in this session
    context_lines = []
    for entry in state["transcript"]:
        v = load_voice(entry["voice"])
        name = v["name"] if v else entry["voice"]
        context_lines.append(f"**{name}** (round {entry['round']}):\n{entry['response']}")

    output = {
        "result": "next",
        "voice": voice_id,
        "voice_name": voice["name"] if voice else voice_id,
        "round": state["current_round"],
        "mode": state["mode"],
        "topic": state["topic"],
        "context": "\n\n---\n\n".join(context_lines) if context_lines else ""
    }
    if voice:
        output["persona"] = voice

    print(json.dumps(output, indent=2))


def cmd_record(args):
    state = load_state(args.state)

    if state["status"] != "active":
        print("Error: session is already complete.", file=sys.stderr)
        sys.exit(1)

    response = sys.stdin.read().strip()
    if not response:
        print("Error: empty response (pipe text via stdin).", file=sys.stderr)
        sys.exit(1)

    state["transcript"].append({
        "round": state["current_round"],
        "voice": args.voice,
        "response": response
    })

    # Advance to next voice/round
    state["current_voice_idx"] += 1
    if state["current_voice_idx"] >= len(state["voices"]):
        state["current_voice_idx"] = 0
        state["current_round"] += 1
        if state["current_round"] > state["rounds"]:
            state["status"] = "complete"

    save_state(args.state, state)
    print(json.dumps({"recorded": args.voice, "round": state["transcript"][-1]["round"], "status": state["status"]}))


def cmd_status(args):
    state = load_state(args.state)
    total_turns = len(state["voices"]) * state["rounds"]
    completed_turns = len(state["transcript"])
    print(json.dumps({
        "status": state["status"],
        "topic": state["topic"],
        "mode": state["mode"],
        "voices": state["voices"],
        "rounds": state["rounds"],
        "current_round": state["current_round"],
        "turns_completed": completed_turns,
        "turns_total": total_turns
    }))


def cmd_transcript(args):
    state = load_state(args.state)

    if args.format == "json":
        print(json.dumps({"topic": state["topic"], "transcript": state["transcript"]}, indent=2))
    else:
        lines = [f"# Roundtable: {state['topic']}\n"]
        current_round = 0
        for entry in state["transcript"]:
            if entry["round"] != current_round:
                current_round = entry["round"]
                lines.append(f"\n## Round {current_round}\n")
            voice = load_voice(entry["voice"])
            name = voice["name"] if voice else entry["voice"]
            lines.append(f"### {name}\n\n{entry['response']}\n")
        print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Althingi roundtable orchestrator.")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize a roundtable session")
    p_init.add_argument("--topic", required=True, help="Discussion topic")
    p_init.add_argument("--voices", required=True, help="Comma-separated voice IDs")
    p_init.add_argument("--rounds", type=int, default=2, help="Number of rounds (default: 2)")
    p_init.add_argument("--solo", action="store_true", help="Solo mode: orchestrator roleplays all voices")
    p_init.add_argument("--state", default=".althingi-state.json", help="State file path")

    p_next = sub.add_parser("next", help="Get next voice to speak")
    p_next.add_argument("--state", default=".althingi-state.json", help="State file path")

    p_record = sub.add_parser("record", help="Record a voice's response")
    p_record.add_argument("--voice", required=True, help="Voice ID that spoke")
    p_record.add_argument("--state", default=".althingi-state.json", help="State file path")

    p_status = sub.add_parser("status", help="Show session status")
    p_status.add_argument("--state", default=".althingi-state.json", help="State file path")

    p_transcript = sub.add_parser("transcript", help="Output full transcript")
    p_transcript.add_argument("--state", default=".althingi-state.json", help="State file path")
    p_transcript.add_argument("--format", choices=["json", "markdown"], default="markdown", help="Output format")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {"init": cmd_init, "next": cmd_next, "record": cmd_record, "status": cmd_status, "transcript": cmd_transcript}[args.command](args)


if __name__ == "__main__":
    main()
