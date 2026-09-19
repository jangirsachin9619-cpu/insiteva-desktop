"""Conversation context for INSITEVA's conversational analyst."""
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import re


@dataclass
class ConversationTurn:
    question: str
    answer: str
    spec: Dict[str, Any]
    result_type: str = "analysis"


class ConversationManager:
    """Keeps lightweight analyst context without sending raw datasets to an LLM."""

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self.turns: List[ConversationTurn] = []
        self.dataset_name = ""
        self.active_filters: Dict[str, Any] = {}
        self.active_metric: Optional[str] = None
        self.active_category: Optional[str] = None
        self.last_chart: Optional[Dict[str, Any]] = None
        self.last_result: Optional[Dict[str, Any]] = None

    def set_dataset(self, name: str):
        if name != self.dataset_name:
            self.clear()
        self.dataset_name = name or ""

    def clear(self):
        self.turns = []
        self.active_metric = None
        self.active_category = None
        self.last_chart = None
        self.last_result = None
        self.active_filters = {}

    def add_turn(self, question: str, answer: str, spec: Optional[Dict[str, Any]] = None,
                 result_type: str = "analysis", result: Optional[Dict[str, Any]] = None):
        spec = spec or {}
        self.turns.append(ConversationTurn(question, answer, spec, result_type))
        self.turns = self.turns[-self.max_turns:]
        self.active_metric = spec.get("metric") or (spec.get("metrics") or [None])[0] or self.active_metric
        self.active_category = spec.get("category") or self.active_category
        if result is not None:
            self.last_result = result

    @property
    def last_turn(self):
        return self.turns[-1] if self.turns else None

    def contextualize(self, question: str) -> str:
        """Resolve common follow-up language into an explicit analytical request."""
        q = (question or "").strip()
        if not q or not self.turns:
            return q
        low = q.lower()
        prev = self.last_turn
        metric = self.active_metric
        category = self.active_category

        if low in {"why?", "why", "why did it?", "why did that happen?"}:
            return f"Why did {metric or 'the main metric'} change?"
        if re.search(r"^(what about|and)\s+", low):
            subject = re.sub(r"^(what about|and)\s+", "", q, flags=re.I).strip(" ?")
            return f"Compare {metric or 'the main metric'} for {subject} using the same context as the previous analysis."
        if low in {"show the trend", "show me the trend", "trend", "what is the trend?"}:
            return f"Show the monthly trend of {metric or 'the main metric'}."
        if low in {"compare", "compare that", "compare it"}:
            return f"Compare {metric or 'the main metric'} using the previous analysis context."
        if any(x in low for x in ["now", "also", "then"]):
            if metric and len(q.split()) <= 10:
                return f"{q} for {metric} using the previous analysis context."
        # Short follow-ups such as "top 5" or "bottom 3" inherit the metric.
        if metric and re.match(r"^(top|bottom)\s+\d+\b", low):
            return f"{q} by {metric}."
        return q

    def context_summary(self) -> str:
        parts = []
        if self.dataset_name:
            parts.append(f"Dataset: {self.dataset_name}")
        if self.active_metric:
            parts.append(f"Metric: {self.active_metric}")
        if self.active_category:
            parts.append(f"Dimension: {self.active_category}")
        if self.active_filters:
            parts.append("Filters: " + ", ".join(f"{k}={v}" for k, v in self.active_filters.items()))
        if self.last_turn:
            parts.append(f"Last question: {self.last_turn.question}")
        return " • ".join(parts) if parts else "New conversation"

    def to_dict(self):
        return {
            "dataset_name": self.dataset_name,
            "active_filters": self.active_filters,
            "active_metric": self.active_metric,
            "active_category": self.active_category,
            "last_chart": self.last_chart,
            "last_result": self.last_result,
            "turns": [asdict(t) for t in self.turns],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        obj = cls()
        obj.dataset_name = data.get("dataset_name", "")
        obj.active_filters = data.get("active_filters", {}) or {}
        obj.active_metric = data.get("active_metric")
        obj.active_category = data.get("active_category")
        obj.last_chart = data.get("last_chart")
        obj.last_result = data.get("last_result")
        for t in data.get("turns", []):
            obj.turns.append(ConversationTurn(t.get("question", ""), t.get("answer", ""), t.get("spec", {}) or {}, t.get("result_type", "analysis")))
        obj.turns = obj.turns[-obj.max_turns:]
        return obj
