from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


from config import LabConfig
from memory_store import CompactMemoryManager, UserProfileStore
from model_provider import ProviderConfig


def make_config(tmp_path: Path) -> LabConfig:
    """Build an isolated config for tests with small compact threshold."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "profiles").mkdir(parents=True, exist_ok=True)

    return LabConfig(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=state_dir,
        compact_threshold_tokens=80,  # Small threshold to trigger compaction quickly
        compact_keep_messages=2,
        model=ProviderConfig(provider="openai", model_name="stub", temperature=0.0),
        judge_model=ProviderConfig(provider="openai", model_name="stub", temperature=0.0),
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Verify `User.md` can be created, updated, edited, and queried for file size."""
    cfg = make_config(tmp_path)
    store = UserProfileStore(cfg.state_dir / "profiles")

    user_id = "test_user"
    init_content = "# User Profile\n- **name**: DũngCT\n- **location**: Đà Nẵng\n"
    store.write_text(user_id, init_content)

    # Read verification
    content = store.read_text(user_id)
    assert "Đà Nẵng" in content
    assert "DũngCT" in content

    # Edit verification (correction)
    edited = store.edit_text(user_id, "Đà Nẵng", "Huế")
    assert edited is True

    updated_content = store.read_text(user_id)
    assert "Huế" in updated_content
    assert "Đà Nẵng" not in updated_content

    # File size verification
    assert store.file_size(user_id) > 0


def test_compact_trigger(tmp_path: Path) -> None:
    """Verify long threads trigger compaction and summarize older messages."""
    cfg = make_config(tmp_path)
    manager = CompactMemoryManager(
        threshold_tokens=cfg.compact_threshold_tokens,
        keep_messages=cfg.compact_keep_messages,
    )

    long_chunk = "Đoạn văn bản dài để kiểm tra trigger nén bộ nhớ vượt ngưỡng token. " * 8
    # Append enough messages to exceed 80 tokens
    manager.append("t1", "user", f"Turn 1: {long_chunk}")
    manager.append("t1", "assistant", f"Turn 2: {long_chunk}")
    manager.append("t1", "user", f"Turn 3: {long_chunk}")
    manager.append("t1", "assistant", f"Turn 4: {long_chunk}")

    assert manager.compaction_count("t1") > 0
    ctx = manager.context("t1")
    assert len(ctx["messages"]) <= cfg.compact_keep_messages
    assert len(str(ctx["summary"])) > 0


def test_cross_session_recall(tmp_path: Path) -> None:
    """Verify advanced remembers across sessions and baseline does not."""
    cfg = make_config(tmp_path)
    adv = AdvancedAgent(cfg, force_offline=True)
    base = BaselineAgent(cfg, force_offline=True)

    user_id = "dungct_test"

    # Session 1: introduce user facts
    adv.reply(user_id, "thread-1", "Chào bạn, mình tên là DũngCT, hiện ở Huế và làm MLOps engineer.")
    base.reply(user_id, "thread-1", "Chào bạn, mình tên là DũngCT, hiện ở Huế và làm MLOps engineer.")

    # Session 2: fresh thread asking for recall
    adv_resp = adv.reply(user_id, "thread-2", "Mình tên gì và hiện đang ở đâu?")
    base_resp = base.reply(user_id, "thread-2", "Mình tên gì và hiện đang ở đâu?")

    adv_text = adv_resp.get("response", "")
    base_text = base_resp.get("response", "")

    # Advanced MUST recall persistent facts from User.md
    assert "DũngCT" in adv_text
    assert "Huế" in adv_text

    # Baseline MUST NOT remember facts across fresh threads
    assert "DũngCT" not in base_text
    assert "Huế" not in base_text


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Compare prompt load of baseline vs advanced on a long thread."""
    cfg = make_config(tmp_path)
    adv = AdvancedAgent(cfg, force_offline=True)
    base = BaselineAgent(cfg, force_offline=True)

    user_id = "dungct_load"
    thread_id = "thread-stress-test"

    long_payload = "Đây là dữ liệu dài để làm lộ chi phí ngữ cảnh prompt tokens processed của hệ thống agent. " * 6

    for i in range(8):
        adv.reply(user_id, thread_id, f"Lượt {i}: {long_payload}")
        base.reply(user_id, thread_id, f"Lượt {i}: {long_payload}")

    adv_prompt_tokens = adv.prompt_token_usage(thread_id)
    base_prompt_tokens = base.prompt_token_usage(thread_id)

    # Advanced should have triggered compaction and significantly reduced prompt tokens
    assert adv.compaction_count(thread_id) > 0
    assert adv_prompt_tokens < base_prompt_tokens


def test_normalize_provider() -> None:
    """Verify provider alias mapping across all supported providers."""
    from model_provider import normalize_provider

    assert normalize_provider("anthorpic") == "anthropic"
    assert normalize_provider("claude") == "anthropic"
    assert normalize_provider("openai") == "openai"
    assert normalize_provider("gpt") == "openai"
    assert normalize_provider("google-genai") == "gemini"
    assert normalize_provider("gemini") == "gemini"
    assert normalize_provider("local-ollama") == "ollama"
    assert normalize_provider("ollama") == "ollama"
    assert normalize_provider("open-router") == "openrouter"
    assert normalize_provider("custom") == "custom"


def test_token_estimator_and_conflict_handling(tmp_path: Path) -> None:
    """Verify token estimator properties and conflict handling in profile store."""
    from memory_store import estimate_tokens

    # Estimator properties
    assert estimate_tokens("") == 0
    assert estimate_tokens("   ") == 0
    assert estimate_tokens("abc") >= 1
    assert estimate_tokens("a" * 100) >= estimate_tokens("a" * 20)

    # Conflict handling & tech merging
    cfg = make_config(tmp_path)
    store = UserProfileStore(cfg.state_dir / "profiles")
    user = "conflict_user"

    # Initial fact
    store.upsert_fact(user, "location", "Đà Nẵng")
    assert store.get_facts(user)["location"] == "Đà Nẵng"

    # Correction / Conflict resolution
    store.upsert_fact(user, "location", "Huế")
    facts = store.get_facts(user)
    assert facts["location"] == "Huế"
    # Ensure Đà Nẵng is not duplicated
    content = store.read_text(user)
    assert content.count("location") == 1

    # Tech interest merging
    store.upsert_fact(user, "tech", "Python")
    store.upsert_fact(user, "tech", "AI")
    facts = store.get_facts(user)
    assert "Python" in facts["tech"]
    assert "AI" in facts["tech"]


