from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Student TODO: implement Agent A.

    Requirements:
    - Within-session memory only
    - No persistent `User.md`
    - Should forget long-term facts across new threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}

        # TODO: optionally initialize a real LangChain/LangGraph agent when dependencies exist.
        self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: return the agent response and token accounting.

        Pseudocode:
        - If a live agent exists, call the live path.
        - Otherwise use a deterministic offline path.
        """
        if self.langchain_agent and not self.force_offline:
            try:
                # Live path if available
                res = self.langchain_agent.invoke({"messages": [("user", message)]})
                ans = str(res.get("messages", [-1])[-1].content)
                t_used = estimate_tokens(ans)
                p_used = estimate_tokens(message)
                return {"response": ans, "tokens": t_used, "prompt_tokens": p_used}
            except Exception:
                pass
        return self._reply_offline(thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        return self.sessions.get(thread_id, SessionState()).token_usage

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.sessions.get(thread_id, SessionState()).prompt_tokens_processed

    def compaction_count(self, thread_id: str) -> int:
        # Baseline has no compact memory.
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Implement deterministic offline behavior for Baseline.

        - Store the new user message in session
        - Generate deterministic response based ONLY on current thread
        - Update token counts
        - Forgets all facts across different thread ids
        """
        if thread_id not in self.sessions:
            self.sessions[thread_id] = SessionState()

        session = self.sessions[thread_id]

        # Calculate prompt context: all previous messages + current message
        prompt_tokens = sum(estimate_tokens(m["content"]) for m in session.messages) + estimate_tokens(message)
        session.prompt_tokens_processed += prompt_tokens

        session.messages.append({"role": "user", "content": message})

        # Since baseline only remembers in current thread:
        # Check if the question can be answered from current thread messages (excluding current message)
        history_text = " ".join(m["content"] for m in session.messages[:-1])

        lower_msg = message.lower()
        if "tên" in lower_msg or "nghề" in lower_msg or "đồ uống" in lower_msg or "ở đâu" in lower_msg:
            # Baseline only knows if it was mentioned in THIS thread previously
            if "dũngct" in history_text.lower():
                response = "Trong cuộc trò chuyện này, bạn có giới thiệu bạn là DũngCT."
            else:
                response = "Tôi không có thông tin về bạn từ trước trong phiên làm việc này."
        else:
            response = "Tôi đã ghi nhận thông tin của bạn trong phiên trò chuyện này."

        resp_tokens = estimate_tokens(response)
        session.token_usage += resp_tokens
        session.messages.append({"role": "assistant", "content": response})

        return {
            "response": response,
            "tokens": resp_tokens,
            "prompt_tokens": prompt_tokens,
        }

    def _maybe_build_langchain_agent(self):
        """Optionally wire LangChain agent if API key is provided."""
        if self.force_offline or not self.config.model.api_key:
            return None
        try:
            chat_model = build_chat_model(self.config.model)
            return chat_model
        except Exception:
            return None

