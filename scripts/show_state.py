#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bot.memory.store import MemoryStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show compact bot state sections.")
    parser.add_argument(
        "--state-dir",
        default="state",
        help="State directory to initialize and read. Defaults to ./state.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = MemoryStore(Path(args.state_dir)).load_snapshot()

    print_section("Bot Identity", snapshot.bot_identity)
    print_section("Owner Profile", snapshot.owner_profile)
    print_section("Avatar Prompt", snapshot.avatar_prompt)
    print_section("Relationship Journal", snapshot.relationship_journal)
    print_section(
        "Runtime JSON",
        json.dumps(snapshot.runtime_state.to_json(), indent=2, sort_keys=True),
    )


def print_section(title: str, content: str) -> None:
    print(f"## {title}")
    print(_compact(content))
    print()


def _compact(content: str) -> str:
    value = content.strip()
    return value if value else "(empty)"


if __name__ == "__main__":
    main()
