---
name: text-summarize
description: Summarize text by extracting key sentences. Use when asked to summarize a file, passage, or document.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# text-summarize

Extractive text summarization using sentence scoring.

## Usage

```bash
# Summarize from stdin
echo "Long text here..." | python scripts/summarize.py

# Summarize a file
python scripts/summarize.py --file document.txt

# Control number of sentences
python scripts/summarize.py --file doc.txt --sentences 3

# Output as JSON
python scripts/summarize.py --file doc.txt --json
```

## Dependencies

Python 3.6+ (standard library only)
