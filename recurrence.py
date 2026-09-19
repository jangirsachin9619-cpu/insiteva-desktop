"""Recurrence and learning intelligence for INSITEVA.

Deterministic project-scoped learning over saved investigation cases and actions.
It identifies repeated problem signatures, unresolved repeats, action effectiveness,
and simple before/after recurrence signals without claiming causal proof.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def _case_signature(case):
    return getattr(case, "signature", "") or ""


def recurrence_analysis(cases, actions=None, dataset_name: Optional[str] = None) -> Dict[str, Any]:
    cases = [c for c in (cases or []) if dataset_name is None or getattr(c, "dataset_name", "") == dataset_name]
    actions = actions or []
    groups: Dict[str, List[Any]] = {}
    for c in cases:
        groups.setdefault(_case_signature(c), []).append(c)
    repeated=[]
    for sig, xs in groups.items():
        if len(xs) < 2 or not sig: continue
        ordered=sorted(xs, key=lambda c: getattr(c,"created_at", ""))
        repeated.append({
            "signature": sig, "count": len(ordered),
            "latest_case_id": ordered[-1].case_id,
            "first_seen": ordered[0].created_at, "last_seen": ordered[-1].created_at,
            "open_count": sum(getattr(c,"status","") != "resolved" for c in ordered),
            "resolved_count": sum(getattr(c,"status","") == "resolved" for c in ordered),
            "title": ordered[-1].title,
            "severity": ordered[-1].severity,
            "cases": [c.case_id for c in ordered[-10:]],
        })
    repeated.sort(key=lambda x:(x["open_count"]>0, x["count"]), reverse=True)
    effective=sum(getattr(a,"effectiveness_status","") == "EFFECTIVE" for a in actions)
    partial=sum(getattr(a,"effectiveness_status","") == "PARTIALLY_EFFECTIVE" for a in actions)
    ineffective=sum(getattr(a,"effectiveness_status","") == "NOT_EFFECTIVE" for a in actions)
    verified=effective+partial+ineffective
    unresolved_repeats=[x for x in repeated if x["open_count"]>0]
    lessons=[]
    if repeated: lessons.append(f"{len(repeated)} recurring problem pattern(s) were detected from saved investigations.")
    if unresolved_repeats: lessons.append(f"{len(unresolved_repeats)} recurring pattern(s) still have an open case.")
    if verified: lessons.append(f"{effective} action(s) were verified effective, {partial} partially effective, and {ineffective} not effective.")
    if not lessons: lessons.append("Not enough investigation history exists yet to identify a recurring pattern.")
    return {"status":"ok","dataset_name":dataset_name or "","cases":len(cases),"repeat_patterns":repeated[:20],"unresolved_repeats":unresolved_repeats[:20],"actions":{"verified":verified,"effective":effective,"partially_effective":partial,"not_effective":ineffective,"pending":sum(getattr(a,"effectiveness_status","") == "PENDING" for a in actions)},"lessons":lessons,"trust_note":"Recurrence is a historical pattern signal. It does not prove that an action caused an improvement or that a repeated pattern has the same root cause."}


def action_learning(actions, cases=None) -> Dict[str, Any]:
    actions=actions or []
    by_type: Dict[str, Dict[str,int]]={}
    for a in actions:
        t=getattr(a,"action_type","Corrective")
        s=getattr(a,"effectiveness_status","PENDING")
        d=by_type.setdefault(t,{"total":0,"effective":0,"partial":0,"not_effective":0,"pending":0})
        d["total"]+=1
        d[{"EFFECTIVE":"effective","PARTIALLY_EFFECTIVE":"partial","NOT_EFFECTIVE":"not_effective"}.get(s,"pending")]+=1
    ranked=sorted(by_type.items(), key=lambda kv:(kv[1]["effective"],-kv[1]["not_effective"]), reverse=True)
    return {"status":"ok","by_type":dict(ranked),"learning_note":"Historical effectiveness is descriptive; use controlled tests or additional evidence before treating an action as causal."}
