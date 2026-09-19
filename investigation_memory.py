"""Investigation memory and case history for INSITEVA.

Stores structured investigation cases so a project can answer:
- Has this problem happened before?
- Did the previous problem improve?
- Which investigations remain unresolved?
- What evidence and next actions were recorded last time?

Memory is local, project-scoped, deterministic, and serializable to JSON.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import hashlib
import json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signature(finding: Dict[str, Any]) -> str:
    basis = {
        "type": finding.get("type"),
        "metric": finding.get("metric"),
        "dimension": finding.get("dimension"),
        "title": finding.get("title"),
    }
    return hashlib.sha1(json.dumps(basis, sort_keys=True, default=str).encode()).hexdigest()[:16]


@dataclass
class InvestigationCase:
    case_id: str
    created_at: str
    dataset_name: str
    title: str
    signature: str
    status: str = "open"
    severity: str = ""
    confidence: float = 0.0
    summary: str = ""
    finding_type: str = ""
    metric: Optional[str] = None
    dimension: Optional[str] = None
    strongest_hypothesis: Optional[str] = None
    hypothesis_verdict: Optional[str] = None
    hypothesis_score: Optional[float] = None
    evidence: List[str] = None
    next_actions: List[str] = None
    result: Dict[str, Any] = None
    resolved_at: Optional[str] = None
    resolution_note: str = ""

    def __post_init__(self):
        self.evidence = list(self.evidence or [])
        self.next_actions = list(self.next_actions or [])
        self.result = dict(self.result or {})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InvestigationCase":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


class InvestigationMemory:
    """Project-scoped investigation case history."""

    VERSION = 1
    MAX_CASES = 200

    def __init__(self, cases: Optional[List[Dict[str, Any]]] = None):
        self.cases: List[InvestigationCase] = []
        for item in cases or []:
            try:
                self.cases.append(InvestigationCase.from_dict(item))
            except Exception:
                continue

    def to_dict(self) -> Dict[str, Any]:
        return {"version": self.VERSION, "cases": [c.to_dict() for c in self.cases]}

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "InvestigationMemory":
        if not data:
            return cls()
        return cls(data.get("cases", []))

    def add_case(self, dataset_name: str, finding: Dict[str, Any], investigation: Optional[Dict[str, Any]] = None,
                 hypotheses: Optional[Dict[str, Any]] = None, next_actions: Optional[List[str]] = None,
                 status: str = "open") -> InvestigationCase:
        investigation = investigation or {}
        hypotheses = hypotheses or {}
        ranked = hypotheses.get("hypotheses", []) if isinstance(hypotheses, dict) else []
        strongest = None
        if ranked:
            supported = [h for h in ranked if h.get("verdict") in {"SUPPORTED", "STRONGLY SUPPORTED"}]
            strongest = supported[0] if supported else ranked[0]
        if not strongest and investigation.get("hypotheses"):
            hs = investigation.get("hypotheses", [])
            strongest = hs[0] if hs else None
        evidence = list(finding.get("evidence", []))
        evidence.extend(investigation.get("evidence", [])[:8] if isinstance(investigation.get("evidence"), list) else [])
        case = InvestigationCase(
            case_id=f"CASE-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{len(self.cases)+1:03d}",
            created_at=_now(),
            dataset_name=dataset_name or "",
            title=str(finding.get("title", "Business investigation")),
            signature=_signature(finding),
            status=status,
            severity=str(finding.get("severity", "")),
            confidence=float(finding.get("confidence", 0) or 0),
            summary=str(finding.get("summary", "")),
            finding_type=str(finding.get("type", "")),
            metric=finding.get("metric"),
            dimension=finding.get("dimension"),
            strongest_hypothesis=(strongest or {}).get("hypothesis") if strongest else None,
            hypothesis_verdict=(strongest or {}).get("verdict") if strongest else None,
            hypothesis_score=(strongest or {}).get("score") if strongest else None,
            evidence=evidence[:16],
            next_actions=list(next_actions or finding.get("next_step", "") and [finding.get("next_step")]),
            result={"finding": finding, "investigation": investigation, "hypotheses": hypotheses},
        )
        self.cases.append(case)
        self.cases = self.cases[-self.MAX_CASES:]
        return case

    def find_related(self, finding: Dict[str, Any], dataset_name: Optional[str] = None) -> List[InvestigationCase]:
        sig = _signature(finding)
        return [c for c in reversed(self.cases)
                if c.signature == sig and (dataset_name is None or c.dataset_name == dataset_name)]

    def unresolved(self, dataset_name: Optional[str] = None) -> List[InvestigationCase]:
        return [c for c in reversed(self.cases) if c.status != "resolved" and (dataset_name is None or c.dataset_name == dataset_name)]

    def mark_resolved(self, case_id: str, note: str = "") -> bool:
        for c in self.cases:
            if c.case_id == case_id:
                c.status = "resolved"
                c.resolved_at = _now()
                c.resolution_note = note
                return True
        return False

    def compare(self, finding: Dict[str, Any], dataset_name: str, current_investigation: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        related = self.find_related(finding, dataset_name)
        current = current_investigation or {}
        if not related:
            return {"status": "no_history", "message": "No previous case with the same investigation signature was found.", "related_cases": []}
        previous = related[0]
        current_change = finding.get("change_pct")
        previous_finding = previous.result.get("finding", {}) if isinstance(previous.result, dict) else {}
        previous_change = previous_finding.get("change_pct")
        delta = None
        if isinstance(current_change, (int, float)) and isinstance(previous_change, (int, float)):
            delta = float(current_change) - float(previous_change)
        if delta is not None:
            trend = "improved" if abs(current_change) < abs(previous_change) else "worsened" if abs(current_change) > abs(previous_change) else "unchanged"
            comparison = f"The measured change {trend}: {previous_change:+.1f}% previously vs {current_change:+.1f}% now."
        else:
            comparison = "The same investigation pattern was recorded before; compare the saved evidence and hypotheses below."
        return {
            "status": "history_found",
            "message": comparison,
            "related_cases": [c.to_dict() for c in related[:5]],
            "latest_case": previous.to_dict(),
            "current_change_pct": current_change,
            "previous_change_pct": previous_change,
            "change_delta_points": delta,
            "previous_status": previous.status,
            "previous_hypothesis": previous.strongest_hypothesis,
            "previous_actions": previous.next_actions,
        }

    def summary(self, dataset_name: Optional[str] = None) -> Dict[str, Any]:
        cases = [c for c in self.cases if dataset_name is None or c.dataset_name == dataset_name]
        return {
            "total": len(cases),
            "open": sum(c.status != "resolved" for c in cases),
            "resolved": sum(c.status == "resolved" for c in cases),
            "repeat_patterns": sum(1 for c in cases if len(self.find_related(c.result.get("finding", {}) if isinstance(c.result, dict) else {}, dataset_name)) > 1),
        }
