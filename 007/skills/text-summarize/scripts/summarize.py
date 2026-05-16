#!/usr/bin/env python3
"""Text Summarize - Agent Skill

Extractive summarization by scoring sentences on word frequency.

Dependencies: None (Python 3.6+ standard library only)

Usage:
    python summarize.py [--file PATH] [--sentences N] [--json]

Examples:
    cat essay.txt | python summarize.py
    python summarize.py --file essay.txt --sentences 3
    python summarize.py --file essay.txt --json
"""

import argparse
import json
import re
import sys
from collections import Counter


def split_sentences(text):
    """Split text into sentences."""
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def summarize(text, num_sentences=3):
    """Extract top sentences by word-frequency scoring."""
    sentences = split_sentences(text)
    if len(sentences) <= num_sentences:
        return sentences

    # Score words (lowercase, alpha-only)
    words = re.findall(r'[a-z]+', text.lower())
    freq = Counter(words)

    # Score each sentence
    scored = []
    for i, sent in enumerate(sentences):
        sent_words = re.findall(r'[a-z]+', sent.lower())
        score = sum(freq[w] for w in sent_words) / (len(sent_words) + 1)
        scored.append((score, i, sent))

    # Pick top sentences, preserve original order
    top = sorted(scored, key=lambda x: x[0], reverse=True)[:num_sentences]
    top_ordered = sorted(top, key=lambda x: x[1])
    return [s[2] for s in top_ordered]


def main():
    parser = argparse.ArgumentParser(description="Extractive text summarization.")
    parser.add_argument("--file", help="Path to text file (reads stdin if omitted)")
    parser.add_argument("--sentences", type=int, default=3, help="Number of sentences (default: 3)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.file:
        with open(args.file) as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("Error: no input text provided.", file=sys.stderr)
        sys.exit(1)

    result = summarize(text, args.sentences)

    if args.json:
        print(json.dumps({"sentences": args.sentences, "summary": result}))
    else:
        print(" ".join(result))


if __name__ == "__main__":
    main()
