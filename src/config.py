from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from model_provider import ProviderConfig


@dataclass
class LabConfig:
    """Student TODO: define the shared configuration for the lab.

    Hints:
    - Keep paths for the repo root, dataset directory, and state directory.
    - Add compact-memory settings such as threshold and number of messages to keep.
    - Add provider settings for `openai`, `custom`, `gemini`, `anthropic`, `ollama`, and `openrouter`.
    """

    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int
    compact_keep_messages: int
    model: ProviderConfig
    judge_model: ProviderConfig


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Student TODO: load environment variables and return a LabConfig.

    Pseudocode:
    1. Resolve the repo root or default to the current file parent.
    2. Optionally load values from `.env`.
    3. Create `state/` if it does not exist.
    4. Return a populated LabConfig instance.
    """
    import os
    try:
        from dotenv import load_dotenv
        root = (base_dir or Path(__file__).resolve().parent.parent).resolve()
        load_dotenv(root / ".env")
    except ImportError:
        root = (base_dir or Path(__file__).resolve().parent.parent).resolve()

    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "profiles").mkdir(parents=True, exist_ok=True)

    provider = os.getenv("LLM_PROVIDER", "openai")
    model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    api_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("CUSTOM_API_KEY")
    )
    base_url = os.getenv("CUSTOM_BASE_URL") or os.getenv("OLLAMA_BASE_URL")

    model_config = ProviderConfig(
        provider=provider,
        model_name=model_name,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
        api_key=api_key,
        base_url=base_url,
    )

    judge_provider = os.getenv("JUDGE_PROVIDER", provider)
    judge_model_name = os.getenv("JUDGE_MODEL", model_name)
    judge_config = ProviderConfig(
        provider=judge_provider,
        model_name=judge_model_name,
        temperature=0.0,
        api_key=api_key,
        base_url=base_url,
    )

    compact_threshold = int(os.getenv("COMPACT_THRESHOLD_TOKENS", "350"))
    compact_keep = int(os.getenv("COMPACT_KEEP_MESSAGES", "2"))

    return LabConfig(
        base_dir=root,
        data_dir=root / "data",
        state_dir=state_dir,
        compact_threshold_tokens=compact_threshold,
        compact_keep_messages=compact_keep,
        model=model_config,
        judge_model=judge_config,
    )

