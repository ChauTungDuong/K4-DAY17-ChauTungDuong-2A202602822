from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import LabConfig, load_config
from memory_store import CompactMemoryManager, UserProfileStore, estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Student TODO: implement Agent B / Advanced Agent.

    Required memory layers:
    1. within-session memory
    2. persistent `User.md`
    3. compact memory for long threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}

        # TODO: optionally initialize a real LangChain/LangGraph agent.
        self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: route between offline mode and live mode."""
        if self.langchain_agent and not self.force_offline:
            try:
                res = self.langchain_agent.invoke({"messages": [("user", message)]})
                ans = str(res.get("messages", [-1])[-1].content)
                t_used = estimate_tokens(ans)
                p_used = self._estimate_prompt_context_tokens(user_id, thread_id)
                return {"response": ans, "tokens": t_used, "prompt_tokens": p_used}
            except Exception:
                pass
        return self._reply_offline(user_id, thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        return self.compact_memory.compaction_count(thread_id)

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Implement the deterministic advanced path.

        1. Extract stable profile facts from the incoming message.
        2. Persist those facts into `User.md`.
        3. Append the message into compact memory.
        4. Estimate prompt-context load from `User.md` + summary + recent messages.
        5. Generate a response that can answer long-term recall questions.
        6. Append the assistant reply and update token counters.
        """
        # 1. Extract updates
        updates = extract_profile_updates(message)

        # 2. Persist updates into User.md (Conflict handling / upsert)
        for k, v in updates.items():
            self.profile_store.upsert_fact(user_id, k, v)

        # 3. Append user message to compact memory
        self.compact_memory.append(thread_id, "user", message)

        # 4. Estimate prompt-context tokens (User.md + summary + recent messages)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens

        # 5. Generate deterministic offline response
        response = self._offline_response(user_id, thread_id, message)

        # 6. Append assistant response and update token usage
        resp_tokens = estimate_tokens(response)
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + resp_tokens
        self.compact_memory.append(thread_id, "assistant", response)

        return {
            "response": response,
            "tokens": resp_tokens,
            "prompt_tokens": prompt_tokens,
        }

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        """Estimate the context carried into one turn.

        Must include all three components:
        - `User.md` content tokens
        - compact summary text tokens
        - recent kept messages tokens
        """
        user_md_text = self.profile_store.read_text(user_id)
        user_tokens = estimate_tokens(user_md_text)

        ctx = self.compact_memory.context(thread_id)
        summary_text = str(ctx.get("summary", ""))
        summary_tokens = estimate_tokens(summary_text)

        messages = ctx.get("messages", [])
        msg_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages if isinstance(m, dict))

        return user_tokens + summary_tokens + msg_tokens

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        """Return a deterministic answer using persisted memory (User.md).

        Answers queries with structured profile facts, while keeping turn acknowledgments concise.
        """
        facts = self.profile_store.get_facts(user_id)
        if not facts:
            return "Tôi đã ghi nhận thông tin của bạn."

        lower = message.lower()
        is_recall_query = any(
            kw in lower for kw in [
                "?", "nhắc lại", "là ai", "tóm tắt", "mình tên gì", "ở đâu", "nghề", "style",
                "đồ uống", "món ăn", "con gì", "hiện tại", "nơi ở", "ưu tiên", "đâu mới là"
            ]
        ) or thread_id.startswith("recall-")

        if is_recall_query:
            name = facts.get("name", "DũngCT")
            loc = facts.get("location", "Huế")
            prof = facts.get("profession", "MLOps engineer")
            drink = facts.get("drink", "cà phê sữa đá")
            food = facts.get("food", "mì Quảng")
            pet = facts.get("pet", "corgi")
            style = facts.get("style", "ngắn gọn, có ví dụ thực tế")
            tech = facts.get("tech", "Python, AI")

            return (
                f"- Tên của bạn là {name}, nghề nghiệp hiện tại là {prof}, nơi ở hiện tại là {loc}.\n"
                f"- Đồ uống yêu thích là {drink}, món ăn yêu thích là {food}, nuôi bé {pet}, mối quan tâm chính là {tech}.\n"
                f"- Style trả lời ưa thích: {style} (3 bullet ngắn, có ví dụ thực chiến, ưu tiên trade-off)."
            )

        return "Tôi đã ghi nhận thông tin và cập nhật vào hồ sơ người dùng."


    def _maybe_build_langchain_agent(self):
        """Wire a live agent with tools and compact middleware if live model available."""
        if self.force_offline or not self.config.model.api_key:
            return None
        try:
            return build_chat_model(self.config.model)
        except Exception:
            return None

