"""Business action and resolution tracking for INSITEVA."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now():
    return datetime.now(timezone.utc).isoformat()

@dataclass
class BusinessAction:
    action_id: str
    case_id: str
    title: str
    action_type: str = "Corrective"
    owner: str = ""
    due_date: str = ""
    priority: str = "MEDIUM"
    status: str = "OPEN"
    created_at: str = ""
    completed_at: Optional[str] = None
    completion_note: str = ""
    effectiveness_status: str = "PENDING"
    effectiveness_note: str = ""
    effectiveness_date: str = ""

    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, d): return cls(**{k:d.get(k) for k in cls.__dataclass_fields__})

class ActionTracker:
    VERSION=1
    MAX_ACTIONS=1000
    def __init__(self, actions=None):
        self.actions=[]
        for x in actions or []:
            try:self.actions.append(BusinessAction.from_dict(x))
            except Exception:pass
    def to_dict(self): return {"version":self.VERSION,"actions":[x.to_dict() for x in self.actions]}
    @classmethod
    def from_dict(cls,d): return cls((d or {}).get("actions",[]))
    def add(self, case_id, title, action_type="Corrective", owner="", due_date="", priority="MEDIUM"):
        n=len(self.actions)+1
        a=BusinessAction(f"ACT-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{n:03d}",case_id,title,action_type,owner,due_date,priority,"OPEN",_now())
        self.actions.append(a); self.actions=self.actions[-self.MAX_ACTIONS:]; return a
    def for_case(self, case_id): return [a for a in reversed(self.actions) if a.case_id==case_id]
    def open_actions(self, case_id=None): return [a for a in self.actions if a.status!="COMPLETED" and (case_id is None or a.case_id==case_id)]
    def complete(self, action_id, note=""):
        for a in self.actions:
            if a.action_id==action_id:
                a.status="COMPLETED"; a.completed_at=_now(); a.completion_note=note; return True
        return False
    def verify_effectiveness(self, action_id, status, note="", date=""):
        allowed={"EFFECTIVE","PARTIALLY_EFFECTIVE","NOT_EFFECTIVE","PENDING"}
        if status not in allowed:return False
        for a in self.actions:
            if a.action_id==action_id:
                a.effectiveness_status=status; a.effectiveness_note=note; a.effectiveness_date=date or datetime.now().strftime('%Y-%m-%d'); return True
        return False
    def summary(self, case_id=None):
        xs=self.for_case(case_id) if case_id else list(self.actions)
        return {"total":len(xs),"open":sum(a.status!="COMPLETED" for a in xs),"completed":sum(a.status=="COMPLETED" for a in xs),"effective":sum(a.effectiveness_status=="EFFECTIVE" for a in xs),"pending_effectiveness":sum(a.effectiveness_status=="PENDING" for a in xs)}
