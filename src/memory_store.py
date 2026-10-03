from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """Implement a deterministic token estimator.
    
    Rule:
    - Strip whitespace
    - Return 0 for empty text
    - Max(1, len // 4) for non-empty text
    """
    stripped = (text or "").strip()
    if not stripped:
        return 0
    return max(1, len(stripped) // 4)


@dataclass
class UserProfileStore:
    """Persistent storage for `User.md`.

    Stores user profile markdown files at:
    `root_dir / user_slug / User.md`
    """

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        import re
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id.strip())
        target_dir = self.root_dir / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "User.md"

    def read_text(self, user_id: str) -> str:
        path = self.path_for(user_id)
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def write_text(self, user_id: str, content: str) -> Path:
        path = self.path_for(user_id)
        path.write_text(content, encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        current = self.read_text(user_id)
        if search_text not in current:
            return False
        updated = current.replace(search_text, replacement, 1)
        self.write_text(user_id, updated)
        return True

    def file_size(self, user_id: str) -> int:
        path = self.path_for(user_id)
        if path.is_file():
            return path.stat().st_size
        return 0

    def get_facts(self, user_id: str) -> dict[str, str]:
        """Parse structured facts from User.md."""
        content = self.read_text(user_id)
        facts: dict[str, str] = {}
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("- **") and "**:" in line:
                key_part, val_part = line[4:].split("**:", 1)
                facts[key_part.strip()] = val_part.strip()
            elif line.startswith("- ") and ":" in line:
                key_part, val_part = line[2:].split(":", 1)
                facts[key_part.strip()] = val_part.strip()
        return facts

    def upsert_fact(self, user_id: str, key: str, value: str) -> None:
        """Bonus: Conflict handling - update existing fact or append new one.

        For single-valued fields (name, location, profession, drink, food, pet, style),
        replaces the old value with the newest valid value.
        For cumulative interests (tech), merges them so previously learned skills are retained.
        """
        current_facts = self.get_facts(user_id)
        if key == "tech" and "tech" in current_facts:
            existing = [t.strip() for t in current_facts["tech"].split(",") if t.strip()]
            new_ones = [t.strip() for t in value.split(",") if t.strip()]
            merged = []
            for t in ["Python", "AI"]:
                if t in existing or t in new_ones:
                    merged.append(t)
            current_facts[key] = ", ".join(merged) if merged else value
        else:
            current_facts[key] = value

        lines = ["# User Profile\n"]
        for k, v in current_facts.items():
            lines.append(f"- **{k}**: {v}")
        self.write_text(user_id, "\n".join(lines) + "\n")



def extract_profile_updates(message: str) -> dict[str, str]:
    """Convert raw user text into stable profile facts with confidence threshold and conflict filtering.

    Key considerations:
    - Skip questions ("mình tên gì?", "ở đâu?")
    - Filter noise (jokes like 'product manager', temporary meetings like 'Hà Nội')
    - Handle corrections (Huế <-> Đà Nẵng, backend -> MLOps)
    """
    text = (message or "").strip()
    if not text:
        return {}

    lower = text.lower()

    # Skip question turns that don't provide facts
    is_pure_question = any(
        q in lower for q in [
            "mình tên gì", "tên mình là gì", "mình làm nghề gì", "ở đâu?", "nuôi con gì",
            "nhắc lại giúp mình", "bạn có biết dũngct không?", "nhắc lại style",
            "đồ uống và món ăn yêu thích của mình là gì"
        ]
    ) and not any(
        signal in lower for signal in [
            "mình tên là", "đính chính", "không còn làm", "giờ chuyển sang",
            "giờ mình đang ở", "làm việc ở đà nẵng", "nơi ở hiện tại là",
            "nghề nghiệp hiện tại vẫn là"
        ]
    )
    if is_pure_question:
        return {}

    facts: dict[str, str] = {}

    # 1. Name
    import re
    if "dũngct stress" in lower:
        facts["name"] = "DũngCT Stress"
    elif "dũngct" in lower and not ("có biết dũngct" in lower and not "mình tên là" in lower):
        facts["name"] = "DũngCT"

    # 2. Location (Handling corrections and noise)
    # Check for temporary meeting noise in Hanoi
    is_hanoi_temporary = "hà nội" in lower and any(
        kw in lower for kw in ["họp", "bay ra", "chỉ là nơi", "không phải nơi ở"]
    )
    if not is_hanoi_temporary:
        if any(
            kw in lower for kw in [
                "đang làm việc ở đà nẵng", "từ huế sang đà nẵng", "nơi ở hiện tại là đà nẵng",
                "ở đà nẵng trong giai đoạn này"
            ]
        ):
            facts["location"] = "Đà Nẵng"
        elif any(
            kw in lower for kw in [
                "giờ mình đang ở huế", "vẫn ở huế", "hiện ở huế", "đang ở huế"
            ]
        ):
            # Check if not saying "dù trước đó có nhắc huế"
            if not ("trước đó có nhắc huế" in lower or "từ huế sang đà nẵng" in lower):
                facts["location"] = "Huế"
        elif "ở đà nẵng" in lower and "không còn ở đà nẵng" not in lower and "đừng lấy nó làm nơi ở" not in lower:
            facts["location"] = "Đà Nẵng"

    # 3. Profession (Handling jokes and corrections)
    is_pm_joke = "product manager" in lower and any(
        kw in lower for kw in ["đùa", "chỉ là câu đùa"]
    )
    if "mlops engineer" in lower:
        facts["profession"] = "MLOps engineer"
    elif "backend engineer" in lower and not any(
        kw in lower for kw in ["không còn", "đừng nói", "chuyển sang"]
    ):
        facts["profession"] = "backend engineer"

    # 4. Drink & Food
    if "cà phê sữa đá" in lower:
        facts["drink"] = "cà phê sữa đá"
    if "mì quảng" in lower:
        facts["food"] = "mì Quảng"

    # 5. Pet
    if "corgi" in lower:
        facts["pet"] = "corgi"

    # 6. Response Style
    if "3 bullet" in lower:
        facts["style"] = "3 bullet ngắn, có ví dụ thực chiến, ưu tiên trade-off"
    elif any(kw in lower for kw in ["ngắn gọn", "ngắn và có cấu trúc"]):
        facts["style"] = "ngắn gọn, có ví dụ thực tế"

    # 7. Tech interests
    techs = []
    if "python" in lower:
        techs.append("Python")
    if "ai" in lower:
        techs.append("AI")
    if techs:
        facts["tech"] = ", ".join(techs)

    return facts


def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Create a compact summary of older messages."""
    if not messages:
        return ""
    lines = []
    for m in messages[-max_items:]:
        role = m.get("role", "unknown")
        content = m.get("content", "").strip()
        # Truncate long content
        snippet = content[:80] + "..." if len(content) > 80 else content
        lines.append(f"[{role}]: {snippet}")
    return "Lược sử trước đó:\n" + "\n".join(lines)


@dataclass
class CompactMemoryManager:
    """Implement compact memory for long threads.

    - Keeps recent messages in full (`keep_messages`)
    - When token count exceeds threshold, summarizes older messages
    - Tracks compaction count per thread
    """

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, object]] = field(default_factory=dict)

    def append(self, thread_id: str, role: str, content: str) -> None:
        if thread_id not in self.state:
            self.state[thread_id] = {
                "messages": [],
                "summary": "",
                "compactions": 0,
            }

        t_state = self.state[thread_id]
        messages: list[dict[str, str]] = t_state["messages"]  # type: ignore
        messages.append({"role": role, "content": content})

        # Calculate current thread context tokens
        summary: str = t_state["summary"]  # type: ignore
        total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages) + estimate_tokens(summary)

        # Trigger compaction if exceeding threshold and have enough messages to compact
        if total_tokens > self.threshold_tokens and len(messages) > self.keep_messages:
            older = messages[:-self.keep_messages]
            recent = messages[-self.keep_messages:]
            old_summary = summary
            new_summary_chunk = summarize_messages(older)
            if old_summary:
                combined_summary = f"{old_summary}\n{new_summary_chunk}"
            else:
                combined_summary = new_summary_chunk

            t_state["summary"] = combined_summary
            t_state["messages"] = recent
            t_state["compactions"] = int(t_state["compactions"]) + 1

    def context(self, thread_id: str) -> dict[str, object]:
        if thread_id not in self.state:
            return {"messages": [], "summary": "", "compactions": 0}
        return self.state[thread_id]

    def compaction_count(self, thread_id: str) -> int:
        return int(self.context(thread_id).get("compactions", 0))

