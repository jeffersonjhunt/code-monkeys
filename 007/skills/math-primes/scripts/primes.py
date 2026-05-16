#!/usr/bin/env python3
"""Prime Numbers - Agent Skill

Generate primes, test primality, and factorize numbers.

Dependencies: None (Python 3.6+ standard library only)

Usage:
    python primes.py [--count N] [--limit N] [--test N] [--factor N]

Examples:
    python primes.py --count 10        # First 10 primes
    python primes.py --limit 50        # All primes up to 50
    python primes.py --test 97         # Test if 97 is prime
    python primes.py --factor 360      # Prime factorization of 360
"""

import argparse
import json
import sys


def sieve(limit):
    """Return all primes up to limit using Sieve of Eratosthenes."""
    if limit < 2:
        return []
    is_prime = [True] * (limit + 1)
    is_prime[0] = is_prime[1] = False
    for i in range(2, int(limit**0.5) + 1):
        if is_prime[i]:
            for j in range(i * i, limit + 1, i):
                is_prime[j] = False
    return [i for i, v in enumerate(is_prime) if v]


def is_prime(n):
    """Test if n is prime."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


def factorize(n):
    """Return prime factorization of n as a list of factors."""
    if n < 2:
        return []
    factors = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return factors


def first_n_primes(count):
    """Return the first count prime numbers."""
    primes = []
    candidate = 2
    while len(primes) < count:
        if is_prime(candidate):
            primes.append(candidate)
        candidate += 1
    return primes


def main():
    parser = argparse.ArgumentParser(description="Prime number utilities.")
    parser.add_argument("--count", type=int, help="Generate first N primes")
    parser.add_argument("--limit", type=int, help="Generate all primes up to N")
    parser.add_argument("--test", type=int, help="Test if N is prime")
    parser.add_argument("--factor", type=int, help="Prime factorization of N")
    args = parser.parse_args()

    if not any([args.count, args.limit, args.test, args.factor]):
        args.count = 10

    if args.test is not None:
        result = {"test": args.test, "is_prime": is_prime(args.test)}
    elif args.factor is not None:
        factors = factorize(args.factor)
        result = {"number": args.factor, "factors": factors}
    elif args.limit is not None:
        primes = sieve(args.limit)
        result = {"limit": args.limit, "count": len(primes), "primes": primes}
    else:
        primes = first_n_primes(args.count)
        result = {"count": args.count, "primes": primes}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
