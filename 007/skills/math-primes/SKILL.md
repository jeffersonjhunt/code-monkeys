---
name: math-primes
description: Generate prime numbers, test primality, and run sieve algorithms. Use when asked about primes, prime factorization, or primality testing.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# math-primes

Prime number generation and primality testing.

## Usage

```bash
# Generate first 20 primes
python scripts/primes.py --count 20

# Generate primes up to a limit
python scripts/primes.py --limit 100

# Test if a number is prime
python scripts/primes.py --test 97

# Prime factorization
python scripts/primes.py --factor 360
```

## Dependencies

Python 3.6+ (standard library only)
