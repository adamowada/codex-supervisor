#!/usr/bin/env python3
"""Tiny cross-platform HITL loop template for diagnosis sessions."""

from __future__ import annotations


def step(instruction: str) -> None:
    print(f"\n{instruction}")
    input("Press Enter when done...")


def capture(question: str) -> str:
    print(f"\n{question}")
    return input("> ").strip()


def main() -> int:
    step("Reproduce the issue using the narrowest known trigger.")
    observed = capture("What happened?")
    print(f"\nObserved: {observed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
