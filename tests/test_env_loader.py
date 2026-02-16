from __future__ import annotations

import os
from pathlib import Path

from yak.config.env import load_runtime_env


def test_load_runtime_env_maps_legacy_keys(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OLLAMA_MODEL=nemotron-test",
                "EMAIL_USERNAME=test@example.com",
                "EMAIL_PASSWORD=app_pw",
                "BRAVE_API_KEY=brave_test",
                "FAL_KEY=fal_test",
            ]
        ),
        encoding="utf-8",
    )

    for key in [
        "OLLAMA_MODEL",
        "YAK_OLLAMA__MODEL",
        "EMAIL_USERNAME",
        "EMAIL_PASSWORD",
        "YAK_CHANNELS__EMAIL__IMAP_USERNAME",
        "YAK_CHANNELS__EMAIL__SMTP_USERNAME",
        "YAK_CHANNELS__EMAIL__IMAP_PASSWORD",
        "YAK_CHANNELS__EMAIL__SMTP_PASSWORD",
        "BRAVE_API_KEY",
        "YAK_TOOLS__WEB__SEARCH__API_KEY",
        "FAL_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.chdir(tmp_path)

    loaded = load_runtime_env(force=True)

    assert env_file in loaded
    assert "nemotron-test" == __import__("os").environ.get("YAK_OLLAMA__MODEL")
    assert "test@example.com" == __import__("os").environ.get("YAK_CHANNELS__EMAIL__IMAP_USERNAME")
    assert "test@example.com" == __import__("os").environ.get("YAK_CHANNELS__EMAIL__SMTP_USERNAME")
    assert "app_pw" == __import__("os").environ.get("YAK_CHANNELS__EMAIL__IMAP_PASSWORD")
    assert "app_pw" == __import__("os").environ.get("YAK_CHANNELS__EMAIL__SMTP_PASSWORD")
    assert "brave_test" == __import__("os").environ.get("YAK_TOOLS__WEB__SEARCH__API_KEY")
    assert "fal_test" == __import__("os").environ.get("FAL_KEY")
