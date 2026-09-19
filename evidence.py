from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Dict


def build_evidence(question: str, df, result: Dict[str, Any], spec: Dict[str, Any] | None = None, filters: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Build a transparent, deterministic evidence record for a verified analysis."""
    spec = spec or {}
    filters = filters or {}
    rows = int(len(df)) if df is not None else 0
    columns = int(len(df.columns)) if df is not None else 0
    evidence = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "dataset_rows": rows,
        "dataset_columns": columns,
        "active_filters": dict(filters),
        "operation": result.get("operation") or spec.get("operation") or result.get("type") or "analysis",
        "metric": result.get("metric") or spec.get("metric"),
        "category": result.get("category") or spec.get("category"),
        "result_type": result.get("type"),
        "result": result,
        "calculation_notes": [],
    }
    typ = result.get("type")
    op = result.get("operation")
    if typ == "scalar":
        evidence["calculation_notes"].append(f"{op or 'aggregation'} was calculated on the active filtered dataset.")
    elif typ == "correlation":
        evidence["calculation_notes"].append("Pearson correlation was calculated from numeric rows available after active filtering.")
    elif result.get("rows"):
        evidence["calculation_notes"].append("Grouped values were calculated deterministically from the active filtered dataset.")
    elif typ in {"growth", "trend"}:
        evidence["calculation_notes"].append("Time periods were derived from the detected date column and aggregated by month.")
    elif typ == "outlier_screen":
        evidence["calculation_notes"].append("Outliers were identified using the analysis engine's deterministic outlier method.")
    else:
        evidence["calculation_notes"].append("The result was produced by INSITEVA's deterministic analysis engine.")
    return evidence


def evidence_text(evidence: Dict[str, Any]) -> str:
    lines = ["EVIDENCE & CALCULATION TRACE", "", f"Question: {evidence.get('question','')}",
             f"Rows analyzed: {evidence.get('dataset_rows',0):,}",
             f"Columns available: {evidence.get('dataset_columns',0):,}",
             f"Operation: {evidence.get('operation','analysis')}"]
    if evidence.get("metric"): lines.append(f"Metric: {evidence['metric']}")
    if evidence.get("category"): lines.append(f"Dimension: {evidence['category']}")
    filters=evidence.get("active_filters") or {}
    lines.append("Filters: " + (", ".join(f"{k}={v}" for k,v in filters.items()) if filters else "None"))
    lines += ["", "Calculation notes:"]
    lines += [f"• {x}" for x in evidence.get("calculation_notes", [])]
    return "\n".join(lines)
