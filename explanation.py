from __future__ import annotations
import json
from typing import Any, Dict


def _fmt(v):
    if isinstance(v, (int, float)):
        return f"{v:,.2f}"
    return str(v)


def explain_result(question: str, result: Dict[str, Any] | None, spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Create a business-friendly explanation from verified deterministic results.
    Never invents numeric facts; every numeric statement comes from `result`.
    """
    result = result or {}
    spec = spec or {}
    if result.get("status") != "ok":
        return {"status": "error", "summary": result.get("message", "No verified result is available."), "facts": [], "interpretation": [], "actions": []}
    typ = result.get("type")
    facts, interpretation, actions = [], [], []
    metric = result.get("metric") or spec.get("metric")
    category = result.get("category") or spec.get("category")
    if typ == "scalar":
        value = result.get("value", result.get("total"))
        op = result.get("operation", "aggregation")
        facts.append(f"{metric or 'The selected metric'} is {_fmt(value)} using {op}.")
        interpretation.append("This is the verified result for the active dataset and filters.")
        actions.append("Break the metric down by a business dimension if you want to understand its drivers.")
    elif typ == "grouped":
        rows = result.get("rows", [])
        vals = []
        key = category
        for row in rows:
            val = row.get("sum", row.get("count", row.get("value")))
            if val is not None:
                vals.append((str(row.get(key, "Unknown")), float(val)))
        if vals:
            top = vals[0]
            facts.append(f"{metric or 'The metric'} is highest for {top[0]} at {_fmt(top[1])}.")
            if len(vals) > 1:
                facts.append(f"The result contains {len(vals)} analyzed {category or 'segments'}.")
            interpretation.append(f"The strongest segment shown is {top[0]}. This identifies where the metric is currently concentrated, not necessarily why it is performing that way.")
            actions.append(f"Drill into {top[0]} by another dimension to identify the underlying driver.")
    elif typ in {"trend", "growth"}:
        growth = result.get("mom_growth_pct", [])
        latest = next((x for x in reversed(growth) if x is not None), None)
        if latest is not None:
            direction = "increased" if latest > 0 else "decreased" if latest < 0 else "was flat"
            facts.append(f"The latest available month-over-month change is {latest:.2f}%.")
            interpretation.append(f"The metric {direction} versus the previous available month.")
            actions.append("Compare the strongest positive and negative segments to explain the movement.")
        else:
            interpretation.append("There is not enough period-over-period history to describe the latest change reliably.")
            actions.append("Load more time periods or use a categorical drill-down.")
    elif typ == "correlation":
        corr = result.get("correlation")
        ms = result.get("metrics", ["Metric A", "Metric B"])
        facts.append(f"The correlation between {ms[0]} and {ms[1]} is {corr:.4f} across {result.get('rows', 0):,} rows.")
        interpretation.append("Correlation describes association, not causation.")
        actions.append("Use a segment or time-based drill-down before treating the relationship as a business cause.")
    elif typ == "outlier_screen":
        facts.append("An outlier screen was completed using the deterministic analysis engine.")
        interpretation.append("Flagged observations should be reviewed for unusual business conditions or data-quality issues.")
        actions.append("Inspect flagged periods or records before taking corrective action.")
    elif result.get("findings"):
        facts.extend([str(x) for x in result.get("findings", [])[:5]])
        interpretation.extend([str(x) for x in result.get("recommended_actions", [])[:3]])
        actions.extend([str(x) for x in result.get("recommended_questions", [])[:3]])
    else:
        facts.append("The analysis engine returned a verified result.")
        interpretation.append("Use the Evidence panel to inspect the calculation and active filters.")
        actions.append("Ask a follow-up question or use Drill Down for a deeper explanation.")
    summary = facts[0] if facts else "The analysis completed successfully."
    return {"status":"ok", "question":question, "summary":summary, "facts":facts, "interpretation":interpretation, "actions":actions}


def explanation_text(explanation: Dict[str, Any]) -> str:
    if explanation.get("status") != "ok":
        return "AI EXPLANATION\n\n" + explanation.get("summary", "No explanation available.")
    lines=["INSITEVA — BUSINESS EXPLANATION", "", "WHAT HAPPENED", explanation.get("summary", "")]
    if explanation.get("facts"):
        lines += ["", "VERIFIED FACTS"] + [f"• {x}" for x in explanation["facts"]]
    if explanation.get("interpretation"):
        lines += ["", "WHAT IT MEANS"] + [f"• {x}" for x in explanation["interpretation"]]
    if explanation.get("actions"):
        lines += ["", "WHAT TO DO NEXT"] + [f"• {x}" for x in explanation["actions"]]
    lines += ["", "Trust note: numeric claims above come from the verified analysis result. Interpretation is guidance, not a new calculation."]
    return "\n".join(lines)
