from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


import json
from tabulate import tabulate


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Student TODO: read JSON conversations from disk."""
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def recall_points(answer: str, expected: list[str]) -> float:
    """Return 0 / 0.5 / 1 depending on how many expected facts appear in answer."""
    if not expected:
        return 1.0
    ans_lower = (answer or "").lower()
    matches = sum(1 for exp in expected if exp.lower() in ans_lower)
    if matches == len(expected):
        return 1.0
    elif matches > 0:
        return 0.5
    return 0.0


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Lightweight quality score for offline mode.

    Combines recall accuracy with response conciseness/structure.
    """
    rec = recall_points(answer, expected)
    ans = (answer or "").strip()
    if not ans:
        return 0.0

    length_score = 0.2 if len(ans) >= 20 else 0.1
    # Check if bullet format or structured
    structure_score = 0.1 if ("-" in ans or "•" in ans or "\n" in ans) else 0.0
    return round(min(1.0, rec * 0.7 + length_score + structure_score), 2)


def run_agent_benchmark(agent_name: str, agent, conversations: list[dict[str, Any]], config) -> BenchmarkRow:
    """Evaluate one agent over many conversations.

    1. Feed all turns to the agent.
    2. Track `agent tokens only`.
    3. Track `prompt tokens processed`.
    4. Ask recall questions in a fresh thread.
    5. Compute average recall and quality.
    6. Record memory file growth and compaction count.
    """
    recall_scores: list[float] = []
    quality_scores: list[float] = []
    all_threads: set[str] = set()
    user_ids: set[str] = set()

    for conv in conversations:
        conv_id = conv["id"]
        user_id = conv.get("user_id", "default_user")
        user_ids.add(user_id)
        chat_thread_id = f"thread-{conv_id}"
        all_threads.add(chat_thread_id)

        # 1. Feed all turns
        for turn in conv.get("turns", []):
            agent.reply(user_id, chat_thread_id, turn)

        # 2. Ask recall questions in a FRESH thread
        recall_thread_id = f"recall-{conv_id}"
        all_threads.add(recall_thread_id)

        for rq in conv.get("recall_questions", []):
            q_text = rq["question"]
            expected = rq.get("expected_contains", [])
            resp_dict = agent.reply(user_id, recall_thread_id, q_text)
            ans_text = resp_dict.get("response", "")

            pts = recall_points(ans_text, expected)
            qual = heuristic_quality(ans_text, expected)
            recall_scores.append(pts)
            quality_scores.append(qual)

    # Token accounting across all accessed threads
    total_agent_tokens = sum(agent.token_usage(t) for t in all_threads)
    total_prompt_tokens = sum(agent.prompt_token_usage(t) for t in all_threads)
    total_compactions = sum(agent.compaction_count(t) for t in all_threads)

    # Memory growth
    if hasattr(agent, "memory_file_size"):
        memory_bytes = sum(agent.memory_file_size(u) for u in user_ids)
    else:
        memory_bytes = 0

    avg_recall = sum(recall_scores) / max(1, len(recall_scores))
    avg_quality = sum(quality_scores) / max(1, len(quality_scores))

    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=total_agent_tokens,
        prompt_tokens_processed=total_prompt_tokens,
        recall_score=round(avg_recall, 2),
        response_quality=round(avg_quality, 2),
        memory_growth_bytes=memory_bytes,
        compactions=total_compactions,
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Print tabulated markdown table."""
    headers = [
        "Agent",
        "Agent tokens only",
        "Prompt tokens processed",
        "Cross-session recall",
        "Response quality",
        "Memory growth (bytes)",
        "Compactions",
    ]
    table_data = []
    for r in rows:
        table_data.append([
            r.agent_name,
            f"{r.agent_tokens_only:,}",
            f"{r.prompt_tokens_processed:,}",
            f"{r.recall_score:.2f}",
            f"{r.response_quality:.2f}",
            f"{r.memory_growth_bytes:,}",
            f"{r.compactions}",
        ])
    return tabulate(table_data, headers=headers, tablefmt="github")


def main() -> None:
    """Run both benchmark suites: Standard & Long-Context Stress."""
    root_dir = Path(__file__).resolve().parent.parent
    config = load_config(root_dir)

    std_path = config.data_dir / "conversations.json"
    stress_path = config.data_dir / "advanced_long_context.json"

    print("================================================================================")
    print("Running Day 17: Memory Systems for AI Agent - Benchmark Suites")
    print("================================================================================\n")

    # 1. Standard Benchmark
    std_convs = load_conversations(std_path)
    baseline_std = BaselineAgent(config, force_offline=True)
    advanced_std = AdvancedAgent(config, force_offline=True)

    row_base_std = run_agent_benchmark("Baseline", baseline_std, std_convs, config)
    row_adv_std = run_agent_benchmark("Advanced", advanced_std, std_convs, config)

    print("### Standard Benchmark")
    print(format_rows([row_base_std, row_adv_std]))
    print()

    # 2. Long-Context Stress Benchmark
    stress_convs = load_conversations(stress_path)
    baseline_stress = BaselineAgent(config, force_offline=True)
    advanced_stress = AdvancedAgent(config, force_offline=True)

    row_base_stress = run_agent_benchmark("Baseline", baseline_stress, stress_convs, config)
    row_adv_stress = run_agent_benchmark("Advanced", advanced_stress, stress_convs, config)

    print("### Long-Context Stress Benchmark")
    print(format_rows([row_base_stress, row_adv_stress]))
    print("\n================================================================================")


if __name__ == "__main__":
    main()

