"""Environment loading helpers for Yak runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

_LOADED = False


# Legacy flat env names -> canonical Pydantic BaseSettings keys.
_LEGACY_TO_CANONICAL: dict[str, str] = {
    "OLLAMA_BASE_URL": "YAK_OLLAMA__BASE_URL",
    "OLLAMA_MODEL": "YAK_OLLAMA__MODEL",
    "OLLAMA_FALLBACK_MODEL": "YAK_OLLAMA__FALLBACK_MODEL",
    "OLLAMA_TOOL_FAILOVER_THRESHOLD": "YAK_OLLAMA__TOOL_FAILOVER_THRESHOLD",
    "OLLAMA_TIMEOUT_SECONDS": "YAK_OLLAMA__TIMEOUT_SECONDS",
    "BRAVE_API_KEY": "YAK_TOOLS__WEB__SEARCH__API_KEY",
    "TELEGRAM_BOT_TOKEN": "YAK_CHANNELS__TELEGRAM__TOKEN",
    "TELEGRAM_GROQ_API_KEY": "YAK_CHANNELS__TELEGRAM__GROQ_API_KEY",
    "DISCORD_BOT_TOKEN": "YAK_CHANNELS__DISCORD__TOKEN",
    "SLACK_BOT_TOKEN": "YAK_CHANNELS__SLACK__BOT_TOKEN",
    "SLACK_APP_TOKEN": "YAK_CHANNELS__SLACK__APP_TOKEN",
    "EMAIL_IMAP_HOST": "YAK_CHANNELS__EMAIL__IMAP_HOST",
    "EMAIL_IMAP_PORT": "YAK_CHANNELS__EMAIL__IMAP_PORT",
    "EMAIL_IMAP_USERNAME": "YAK_CHANNELS__EMAIL__IMAP_USERNAME",
    "EMAIL_IMAP_PASSWORD": "YAK_CHANNELS__EMAIL__IMAP_PASSWORD",
    "EMAIL_SMTP_HOST": "YAK_CHANNELS__EMAIL__SMTP_HOST",
    "EMAIL_SMTP_PORT": "YAK_CHANNELS__EMAIL__SMTP_PORT",
    "EMAIL_SMTP_USERNAME": "YAK_CHANNELS__EMAIL__SMTP_USERNAME",
    "EMAIL_SMTP_PASSWORD": "YAK_CHANNELS__EMAIL__SMTP_PASSWORD",
}


def _candidate_env_files() -> list[Path]:
    """Return candidate .env paths in priority order."""
    candidates: list[Path] = []

    cwd_env = Path.cwd() / ".env"
    candidates.append(cwd_env)

    # repo root is two levels above this file: yak/config/env.py -> project root
    repo_env = Path(__file__).resolve().parents[2] / ".env"
    if repo_env != cwd_env:
        candidates.append(repo_env)

    home_env = Path.home() / ".yak" / ".env"
    if home_env not in candidates:
        candidates.append(home_env)

    # De-duplicate while preserving order.
    unique: list[Path] = []
    seen: set[Path] = set()
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _map_legacy_keys(env_items: Iterable[tuple[str, str]]) -> None:
    """Promote legacy env names to canonical YAK_ settings when missing."""
    env_map = dict(env_items)

    for legacy_key, canonical_key in _LEGACY_TO_CANONICAL.items():
        if canonical_key in env_map:
            continue
        legacy_value = env_map.get(legacy_key)
        if legacy_value:
            os.environ[canonical_key] = legacy_value
            env_map[canonical_key] = legacy_value

    # Backward compatibility for single-credential email setups.
    email_user = env_map.get("EMAIL_USERNAME", "")
    email_pass = env_map.get("EMAIL_PASSWORD", "")
    if email_user:
        os.environ.setdefault("YAK_CHANNELS__EMAIL__IMAP_USERNAME", email_user)
        os.environ.setdefault("YAK_CHANNELS__EMAIL__SMTP_USERNAME", email_user)
    if email_pass:
        os.environ.setdefault("YAK_CHANNELS__EMAIL__IMAP_PASSWORD", email_pass)
        os.environ.setdefault("YAK_CHANNELS__EMAIL__SMTP_PASSWORD", email_pass)


def load_runtime_env(force: bool = False) -> list[Path]:
    """Load .env files and normalize env aliases.

    Returns loaded file paths.
    """
    global _LOADED
    if _LOADED and not force:
        return []

    loaded: list[Path] = []
    for env_path in _candidate_env_files():
        if env_path.exists() and env_path.is_file():
            load_dotenv(env_path, override=False)
            loaded.append(env_path)

    _map_legacy_keys(os.environ.items())
    _LOADED = True
    return loaded
