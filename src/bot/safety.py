from __future__ import annotations

import re


MASS_MENTION_REPLACEMENTS = {
    "@everyone": "@\u200beveryone",
    "@here": "@\u200bhere",
}

BLOCKED_MEMORY_PATTERNS = (
    re.compile(r"\b(?:DISCORD_BOT_TOKEN|MINIMAX_API_KEY)\s*=", re.IGNORECASE),
    re.compile(r"\b(?:api[_ -]?key|token|secret)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bignore\s+(?:previous|all)\s+instructions\b", re.IGNORECASE),
)


def sanitize_discord_output(text: str) -> str:
    sanitized = text
    for mention, replacement in MASS_MENTION_REPLACEMENTS.items():
        sanitized = sanitized.replace(mention, replacement)
    return sanitized


def contains_blocked_memory_content(text: str) -> bool:
    return any(pattern.search(text) for pattern in BLOCKED_MEMORY_PATTERNS)
