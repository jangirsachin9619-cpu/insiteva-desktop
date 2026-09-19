"""Business investigation layer for INSITEVA.

Deterministic first pass: all numbers are calculated from pandas. The module
finds potentially important business problems; it does not claim causation.
"""
from __future__ import annotations
from typing import Any, Dict, List
import numpy as np
import pandas as pd

from .analytics import business_numeric, profile, detect_metric, detect_category


def _severity(score: float) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    return "LOW"


def _safe_pct(delta: float, base: float):
    return None if base == 0 else float(delta / abs(base) * 100)


def _issue(score, title, summary, issue_type, confidence, evidence, next_step, **extra):
    return {
        "score": round(float(score), 1),
        "severity": _severity(float(score)),
        "title": title,
        "summary": summary,
        "type": issue_type,
        "confidence": round(float(confidence), 2),
        "evidence": evidence,
        "next_step": next_step,
        **extra,
    }


def investigate_business(df: pd.DataFrame, dataset_name: str = "", max_findings: int = 8) -> Dict[str, Any]:
    """Scan a dataset for potentially important business problems.

    This is intentionally a screening layer. It identifies signals worth
    investigating and provides evidence; it does not silently modify data or
    assert that correlation proves causation.
    """
    if df is None or df.empty:
        return {"status": "error", "message": "No data is loaded."}

    findings: List[Dict[str, Any]] = []
    p = profile(df, fast=len(df) > 250_000)
    dates = p.get("dates", [])
    nums = business_numeric(df)
    metric = detect_metric("sales revenue amount profit", df) or (nums[0] if nums else None)
    date_col = dates[0] if dates else None

    # 1) Data-quality problems that can invalidate analysis.
    missing = int(df.isna().sum().sum())
    duplicates = int(df.duplicated().sum()) if len(df) <= 500_000 else 0
    if missing:
        pct = missing / max(1, df.size) * 100
        findings.append(_issue(
            min(85, 35 + pct * 4),
            "Data quality: missing values detected",
            f"{missing:,} missing cells ({pct:.1f}% of all cells) may affect business analysis.",
            "data_quality", 0.98,
            [f"Missing cells: {missing:,}", f"Affected columns: {int((df.isna().sum()>0).sum())}"],
            "Review missing-value columns before making high-stakes decisions.",
            missing_cells=missing,
        ))
    if duplicates:
        pct = duplicates / max(1, len(df)) * 100
        findings.append(_issue(
            min(80, 30 + pct * 5),
            "Data quality: duplicate rows detected",
            f"{duplicates:,} duplicate rows ({pct:.1f}% of rows) were detected.",
            "data_quality", 0.99,
            [f"Duplicate rows: {duplicates:,}"],
            "Review whether duplicates are legitimate transactions or repeated records.",
            duplicate_rows=duplicates,
        ))

    if metric and date_col:
        work = df[[date_col, metric]].copy()
        work[metric] = pd.to_numeric(work[metric], errors="coerce")
        work = work.dropna(subset=[date_col, metric])
        if not work.empty:
            monthly = work.groupby(work[date_col].dt.to_period("M"))[metric].sum().sort_index()
            if len(monthly) >= 2:
                prev, curr = float(monthly.iloc[-2]), float(monthly.iloc[-1])
                delta = curr - prev
                change = _safe_pct(delta, prev)
                if change is not None and abs(change) >= 5:
                    score = min(95, 45 + abs(change) * 1.6)
                    direction = "dropped" if delta < 0 else "increased"
                    findings.append(_issue(
                        score,
                        f"{metric} {direction} in the latest period",
                        f"{metric} {direction} {abs(change):.1f}% from {monthly.index[-2]} to {monthly.index[-1]}.",
                        "metric_change", min(0.99, 0.70 + min(abs(change), 29) / 100),
                        [f"Previous: {prev:,.2f}", f"Current: {curr:,.2f}", f"Change: {change:+.1f}%"],
                        f"Investigate which segments explain the {abs(change):.1f}% change.",
                        metric=str(metric), date_column=str(date_col), previous_period=str(monthly.index[-2]),
                        current_period=str(monthly.index[-1]), previous=prev, current=curr, change_pct=change,
                    ))

                # 2) Segment-level movements for the latest two periods.
                cats = [c for c in df.select_dtypes(include=["object", "category"]).columns
                        if c != date_col and 1 < df[c].nunique(dropna=True) <= 100]
                for cat in cats[:12]:
                    prev_g = work.assign(_period=work[date_col].dt.to_period("M"))[lambda x: x._period == monthly.index[-2]].groupby(cat)[metric].sum() if cat in work.columns else None
                    # The compact work frame does not include categories, so use a dedicated frame.
                    frame = df[[date_col, cat, metric]].copy()
                    frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
                    frame = frame.dropna(subset=[date_col, metric])
                    frame["_period"] = frame[date_col].dt.to_period("M")
                    pg = frame[frame["_period"] == monthly.index[-2]].groupby(cat)[metric].sum()
                    cg = frame[frame["_period"] == monthly.index[-1]].groupby(cat)[metric].sum()
                    keys = pg.index.union(cg.index)
                    rows = []
                    for key in keys:
                        pv, cv = float(pg.get(key, 0)), float(cg.get(key, 0))
                        d = cv - pv
                        cp = _safe_pct(d, pv)
                        rows.append((key, pv, cv, d, cp))
                    rows = [r for r in rows if r[3] != 0]
                    if not rows:
                        continue
                    rows.sort(key=lambda r: abs(r[3]), reverse=True)
                    key, pv, cv, d, cp = rows[0]
                    if cp is not None and abs(cp) >= 10:
                        contribution = abs(d) / max(abs(delta), 1e-9) * 100
                        score = min(92, 42 + min(abs(cp), 40) + min(contribution, 35) * .5)
                        direction = "declined" if d < 0 else "increased"
                        findings.append(_issue(
                            score,
                            f"{cat} segment needs investigation",
                            f"{cat}={key} {direction} {abs(cp):.1f}% in the latest period.",
                            "segment_change", min(0.96, 0.65 + min(abs(cp), 31) / 100),
                            [f"Previous: {pv:,.2f}", f"Current: {cv:,.2f}", f"Segment change: {cp:+.1f}%", f"Absolute change: {d:+,.2f}"],
                            f"Drill into {cat}={key} by the other available dimensions.",
                            dimension=str(cat), segment=str(key), previous=pv, current=cv, change_pct=cp,
                            contribution_pct=contribution,
                        ))

    # 3) Numeric outlier scan for business metrics.
    for col in nums[:15]:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(s) < 10 or s.nunique() < 4:
            continue
        q1, q3 = float(s.quantile(.25)), float(s.quantile(.75))
        iqr = q3 - q1
        if iqr <= 0:
            continue
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        count = int(((s < lo) | (s > hi)).sum())
        rate = count / len(s) * 100
        if count and rate >= 1:
            findings.append(_issue(
                min(78, 30 + rate * 4),
                f"Unusual values detected in {col}",
                f"{count:,} rows ({rate:.1f}%) fall outside the IQR outlier boundaries.",
                "outlier", 0.93,
                [f"Outliers: {count:,}", f"Lower bound: {lo:,.2f}", f"Upper bound: {hi:,.2f}"],
                f"Review the {col} outliers and determine whether they are valid business events.",
                metric=str(col), outlier_count=count, outlier_rate=rate, lower=lo, upper=hi,
            ))

    # Deduplicate similar findings and rank by business importance.
    findings.sort(key=lambda x: (-x["score"], x["title"]))
    unique=[]; seen=set()
    for f in findings:
        key=(f["type"], f.get("dimension"), f.get("segment"), f.get("metric"), f["title"])
        if key not in seen:
            seen.add(key); unique.append(f)
    unique=unique[:max_findings]

    return {
        "status": "ok",
        "dataset": dataset_name,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "metric": metric,
        "date_column": date_col,
        "finding_count": len(unique),
        "findings": unique,
        "message": "Investigation scan completed." if unique else "No high-priority problems were detected by the first-pass rules.",
        "method_note": "Findings are evidence-backed signals for investigation; they do not prove causation.",
    }


def investigate_finding(df: pd.DataFrame, finding: Dict[str, Any], max_drivers: int = 8) -> Dict[str, Any]:
    """Perform a second-pass investigation of one first-pass finding.

    The second pass is deterministic: it decomposes the selected signal across
    available business dimensions and returns ranked evidence. It never claims
    that correlation alone proves causation.
    """
    if df is None or df.empty:
        return {"status": "error", "message": "No data is loaded."}
    if not finding:
        return {"status": "error", "message": "No investigation finding was selected."}

    ftype = finding.get("type", "")
    metric = finding.get("metric") or detect_metric("sales revenue amount profit", df)
    date_col = finding.get("date_column")
    if date_col not in df.columns:
        date_candidates = profile(df, fast=len(df) > 250_000).get("dates", [])
        date_col = date_candidates[0] if date_candidates else None

    result = {
        "status": "ok", "finding": finding, "drivers": [], "hypotheses": [],
        "evidence": [], "next_questions": [], "method_note":
        "Second-pass decomposition ranks associations and contribution; it does not prove causation."
    }

    # Data quality findings get a targeted quality investigation.
    if ftype == "data_quality":
        missing = df.isna().sum().sort_values(ascending=False)
        result["drivers"] = [
            {"dimension": str(c), "issue": "missing", "count": int(v),
             "rate_pct": round(float(v / max(1, len(df)) * 100), 2)}
            for c, v in missing[missing > 0].head(max_drivers).items()
        ]
        dup = int(df.duplicated().sum())
        result["evidence"] = [f"Missing cells: {int(df.isna().sum().sum()):,}", f"Duplicate rows: {dup:,}"]
        result["hypotheses"] = [
            "Missing values may bias metrics or reduce the usable sample.",
            "Duplicate rows may inflate totals if they represent repeated transactions."
        ]
        result["next_questions"] = [
            "Which columns have the most missing values?",
            "Are duplicate rows legitimate transactions?",
            "How do key KPIs change after excluding invalid records?"
        ]
        return result

    # Prepare metric/date data for change, segment and outlier investigations.
    if metric not in df.columns:
        result["status"] = "error"; result["message"] = "The finding's metric is no longer available in the dataset."; return result
    work = df.copy()
    work[metric] = pd.to_numeric(work[metric], errors="coerce")
    if date_col in work.columns:
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    if date_col and date_col in work.columns:
        work = work.dropna(subset=[metric, date_col])
    else:
        work = work.dropna(subset=[metric])

    if ftype in {"metric_change", "segment_change"} and date_col in work.columns:
        work["_period"] = work[date_col].dt.to_period("M")
        periods = sorted(work["_period"].dropna().unique())
        if len(periods) < 2:
            result["status"]="error"; result["message"]="Not enough dated periods for a second-pass comparison."; return result
        prev_p, curr_p = periods[-2], periods[-1]
        prev = work[work["_period"] == prev_p]
        curr = work[work["_period"] == curr_p]
        total_prev, total_curr = float(prev[metric].sum()), float(curr[metric].sum())
        total_delta = total_curr - total_prev
        result["periods"] = {"previous": str(prev_p), "current": str(curr_p), "previous_value": total_prev, "current_value": total_curr, "delta": total_delta, "change_pct": _safe_pct(total_delta,total_prev)}
        cats = [c for c in work.select_dtypes(include=["object","category"]).columns if c not in {date_col,"_period"} and 1 < work[c].nunique(dropna=True) <= 100]
        if finding.get("dimension") in cats:
            cats = [finding["dimension"]] + [c for c in cats if c != finding["dimension"]]
        for cat in cats[:12]:
            pg=prev.groupby(cat)[metric].sum(); cg=curr.groupby(cat)[metric].sum()
            keys=pg.index.union(cg.index)
            rows=[]
            for key in keys:
                pv=float(pg.get(key,0)); cv=float(cg.get(key,0)); d=cv-pv
                if d == 0: continue
                contrib=(abs(d)/max(abs(total_delta),1e-9))*100
                rows.append({"dimension":str(cat),"segment":str(key),"previous":pv,"current":cv,"delta":d,"change_pct":_safe_pct(d,pv),"contribution_pct":contrib})
            rows.sort(key=lambda x: abs(x["delta"]), reverse=True)
            result["drivers"].extend(rows[:max_drivers])
        result["drivers"].sort(key=lambda x: x.get("contribution_pct",0), reverse=True)
        result["drivers"] = result["drivers"][:max_drivers]
        if result["drivers"]:
            for d in result["drivers"][:3]:
                direction="decline" if d["delta"] < 0 else "increase"
                result["hypotheses"].append(f"{d['dimension']}={d['segment']} is associated with a {direction} of {abs(d['delta']):,.2f} in {metric} and explains about {d['contribution_pct']:.1f}% of the absolute period change.")
        result["evidence"]=[f"{metric}: {total_prev:,.2f} → {total_curr:,.2f}",f"Overall change: {total_delta:+,.2f} ({result['periods']['change_pct']:+.1f}%)" if result['periods']['change_pct'] is not None else f"Overall change: {total_delta:+,.2f}"]
        result["next_questions"]=[
            f"Investigate {result['drivers'][0]['dimension']}={result['drivers'][0]['segment']} by the other dimensions." if result['drivers'] else f"Compare {metric} across available business dimensions.",
            f"Check whether quantity, price, discount or returns changed in the affected segment.",
            f"Compare the same segment across the previous 3–6 periods."
        ]
        return result

    if ftype == "outlier":
        s=work[metric]
        q1,q3=float(s.quantile(.25)),float(s.quantile(.75)); iqr=q3-q1
        lo,hi=q1-1.5*iqr,q3+1.5*iqr
        out=work[(work[metric]<lo)|(work[metric]>hi)].copy()
        result["outlier_summary"]={"count":int(len(out)),"lower":lo,"upper":hi}
        if not out.empty:
            result["evidence"]=[f"Outliers: {len(out):,}",f"Bounds: {lo:,.2f} to {hi:,.2f}",f"Largest absolute values: {', '.join(f'{float(x):,.2f}' for x in out[metric].abs().nlargest(5))}"]
            cats=[c for c in out.select_dtypes(include=["object","category"]).columns if out[c].nunique(dropna=True)<=100]
            for cat in cats[:8]:
                vc=out[cat].value_counts().head(3)
                for seg,count in vc.items(): result["drivers"].append({"dimension":str(cat),"segment":str(seg),"outlier_count":int(count)})
            result["drivers"]=result["drivers"][:max_drivers]
        result["hypotheses"]=[f"The unusual {metric} values may represent genuine business events or data-quality issues; validate the highest-impact rows before acting."]
        result["next_questions"]=[f"Show the largest {metric} outliers.",f"Check whether outliers cluster in a region, product or sales channel."]
        return result

    result["status"]="error"; result["message"]="This finding type does not have a second-pass investigator yet."; return result



def test_hypotheses(df: pd.DataFrame, finding: Dict[str, Any], investigation: Dict[str, Any] | None = None, max_hypotheses: int = 8) -> Dict[str, Any]:
    """Test ranked business hypotheses against the observed finding.

    This is a deterministic evidence test, not a causal inference engine. Each
    hypothesis is classified as strongly supported, supported, weak evidence,
    or not supported from measurable period/segment changes.
    """
    if df is None or df.empty:
        return {"status": "error", "message": "No data is loaded."}
    if not finding:
        return {"status": "error", "message": "No finding was selected."}

    metric = finding.get("metric") or detect_metric("sales revenue amount profit", df)
    if not metric or metric not in df.columns:
        return {"status": "error", "message": "No usable business metric is available for hypothesis testing."}
    date_col = finding.get("date_column")
    if date_col not in df.columns:
        date_candidates = profile(df, fast=len(df) > 250_000).get("dates", [])
        date_col = date_candidates[0] if date_candidates else None
    if not date_col:
        return {"status": "error", "message": "A date column is required to test period-change hypotheses."}

    work = df.copy()
    work[metric] = pd.to_numeric(work[metric], errors="coerce")
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[metric, date_col])
    work["_period"] = work[date_col].dt.to_period("M")
    periods = sorted(work["_period"].dropna().unique())
    if len(periods) < 2:
        return {"status": "error", "message": "At least two dated periods are required."}
    prev_p, curr_p = periods[-2], periods[-1]
    prev, curr = work[work["_period"] == prev_p], work[work["_period"] == curr_p]
    prev_total, curr_total = float(prev[metric].sum()), float(curr[metric].sum())
    total_delta = curr_total - prev_total
    overall_pct = _safe_pct(total_delta, prev_total)

    hypotheses: List[Dict[str, Any]] = []

    def add(name, kind, evidence_strength, verdict, score, evidence, limitation):
        hypotheses.append({
            "hypothesis": name, "type": kind, "verdict": verdict,
            "evidence_strength": evidence_strength, "score": round(float(score), 1),
            "evidence": evidence, "limitation": limitation,
        })

    # Segment hypotheses: test whether a category contains a meaningful share of the gap.
    cats = [c for c in work.select_dtypes(include=["object", "category"]).columns
            if c not in {date_col, "_period"} and 1 < work[c].nunique(dropna=True) <= 100]
    target_dim = finding.get("dimension")
    if target_dim in cats:
        cats = [target_dim] + [c for c in cats if c != target_dim]
    for cat in cats[:10]:
        pg = prev.groupby(cat)[metric].sum(); cg = curr.groupby(cat)[metric].sum()
        rows=[]
        for key in pg.index.union(cg.index):
            pv=float(pg.get(key,0)); cv=float(cg.get(key,0)); d=cv-pv
            if d == 0: continue
            contrib=abs(d)/max(abs(total_delta),1e-9)*100
            rows.append((str(key), pv, cv, d, contrib))
        rows.sort(key=lambda x:x[4], reverse=True)
        if not rows: continue
        key,pv,cv,d,contrib=rows[0]
        if contrib >= 35:
            verdict, strength, score = "STRONGLY SUPPORTED", "High", min(95, 65+contrib*.25)
        elif contrib >= 20:
            verdict, strength, score = "SUPPORTED", "Medium", min(82, 50+contrib*.3)
        elif contrib >= 10:
            verdict, strength, score = "WEAK EVIDENCE", "Low", min(60, 35+contrib*.3)
        else:
            verdict, strength, score = "NOT SUPPORTED", "Low", 20
        direction="decline" if d < 0 else "increase"
        add(f"{cat} mix/segment shift is driving the {metric} change", "segment",
            strength, verdict, score,
            [f"Largest segment: {key}", f"Segment change: {d:+,.2f}", f"Contribution to absolute gap: {contrib:.1f}%", f"Overall change: {overall_pct:+.1f}%" if overall_pct is not None else "Overall percentage change unavailable"],
            "Contribution measures association with the observed gap; it does not establish causality.")

    # Numeric driver hypotheses: quantity, price, discount, returns, profit-like fields.
    numeric_candidates=[]
    preferred_terms=["quantity", "volume", "price", "discount", "return", "profit", "margin", "cost"]
    for col in business_numeric(work):
        low=str(col).lower()
        if any(term in low for term in preferred_terms) and col != metric:
            numeric_candidates.append(col)
    for col in numeric_candidates[:8]:
        a=float(prev[col].mean()) if col in prev.columns else np.nan
        b=float(curr[col].mean()) if col in curr.columns else np.nan
        if not np.isfinite(a) or not np.isfinite(b): continue
        pct=_safe_pct(b-a,a)
        if pct is None: continue
        ap=float(prev[col].sum()); bp=float(curr[col].sum()); spct=_safe_pct(bp-ap,ap)
        mag=abs(pct)
        if mag >= 15:
            verdict,strength,score="SUPPORTED","Medium",min(78,50+mag*.8)
        elif mag >= 7:
            verdict,strength,score="WEAK EVIDENCE","Low",min(58,32+mag*1.2)
        else:
            verdict,strength,score="NOT SUPPORTED","Low",20
        add(f"{col} changed materially between the two periods", "numeric_driver", strength, verdict, score,
            [f"Previous average: {a:,.2f}", f"Current average: {b:,.2f}", f"Average change: {pct:+.1f}%", f"Total change: {spct:+.1f}%" if spct is not None else "Total change unavailable"],
            "A metric movement can be associated with the business change without proving that it caused it.")

    # A simple baseline hypothesis is useful when no driver has enough evidence.
    if not hypotheses:
        add("The observed change may be primarily a period-level fluctuation", "baseline", "Low", "WEAK EVIDENCE", 30,
            [f"Overall change: {overall_pct:+.1f}%" if overall_pct is not None else f"Absolute change: {total_delta:+,.2f}"],
            "More periods or additional business dimensions are needed to explain the movement.")

    hypotheses.sort(key=lambda x: (-x["score"], x["hypothesis"]))
    hypotheses=hypotheses[:max_hypotheses]
    supported=sum(1 for h in hypotheses if h["verdict"] in {"SUPPORTED","STRONGLY SUPPORTED"})
    return {
        "status":"ok", "metric":metric, "date_column":date_col,
        "periods":{"previous":str(prev_p),"current":str(curr_p),"previous_value":prev_total,"current_value":curr_total,"change_pct":overall_pct},
        "hypotheses":hypotheses, "supported_count":supported,
        "method_note":"Hypotheses are ranked from observed period/segment evidence. Supported does not mean proven causal; use controlled experiments or additional causal data for causal claims."
    }


def autonomous_investigation(df: pd.DataFrame, dataset_name: str = "", max_findings: int = 5, max_hypotheses: int = 5, max_iterations: int = 2) -> Dict[str, Any]:
    """Run an evidence-first investigation loop.

    Flow: scan -> select high-value finding -> drill down -> test hypotheses ->
    optionally focus on the strongest supported hypothesis. The engine is
    deterministic and never claims causation from correlation alone.
    """
    if df is None or df.empty:
        return {"status": "error", "message": "No data is loaded."}
    scan = investigate_business(df, dataset_name, max_findings=max_findings)
    if scan.get("status") != "ok":
        return scan
    findings = scan.get("findings", [])
    if not findings:
        return {"status": "ok", "message": "No high-priority business signals were detected.",
                "scan": scan, "iterations": [], "final": None, "agent_status": "completed"}

    # Prefer metric changes over data-quality warnings for business investigation.
    ordered = sorted(findings, key=lambda x: (x.get("type") == "metric_change", x.get("score", 0)), reverse=True)
    current = ordered[0]
    iterations = []
    visited = set()

    for iteration in range(max(1, min(max_iterations, 3))):
        key = (current.get("title"), current.get("type"))
        if key in visited:
            break
        visited.add(key)
        drill = investigate_finding(df, current)
        if drill.get("status") != "ok":
            drill = {"status": "ok", "message": drill.get("message", "No drill-down available.")}
        hypotheses = test_hypotheses(df, current, drill, max_hypotheses=max_hypotheses)
        if hypotheses.get("status") != "ok":
            hypotheses = {"status": "ok", "hypotheses": [], "message": hypotheses.get("message", "Hypothesis testing unavailable.")}
        ranked = hypotheses.get("hypotheses", [])
        supported = [h for h in ranked if h.get("verdict") in {"SUPPORTED", "STRONGLY SUPPORTED"}]
        strongest = supported[0] if supported else (ranked[0] if ranked else None)
        iterations.append({
            "iteration": iteration + 1,
            "finding": current,
            "drill_down": drill,
            "hypotheses": hypotheses,
            "strongest_hypothesis": strongest,
        })
        # A second iteration focuses on a driver dimension when the drill-down
        # exposes a concrete segment finding. Otherwise stop rather than inventing work.
        if iteration + 1 >= max_iterations or not strongest:
            break
        next_finding = None
        dim = drill.get("top_dimension") if isinstance(drill, dict) else None
        if dim and dim in df.columns:
            next_finding = dict(current)
            next_finding["dimension"] = dim
            next_finding["next_step"] = f"Investigate {dim} segments in the strongest-supported hypothesis."
            next_finding["title"] = f"Drill deeper into {dim} for: {current.get('title', 'selected issue')}"
            next_finding["summary"] = f"Continue the investigation through the {dim} dimension using the strongest available evidence."
        if next_finding is None:
            break
        current = next_finding

    final = iterations[-1] if iterations else None
    all_h = final.get("hypotheses", {}).get("hypotheses", []) if final else []
    supported = [h for h in all_h if h.get("verdict") in {"SUPPORTED", "STRONGLY SUPPORTED"}]
    next_actions = []
    if supported:
        next_actions.append(f"Investigate the strongest supported hypothesis: {supported[0].get('hypothesis')}")
    if final and final.get("drill_down", {}).get("next_steps"):
        next_actions.extend(final["drill_down"].get("next_steps", [])[:3])
    if not next_actions:
        next_actions.append("Collect another period or business dimension before making a causal decision.")

    return {
        "status": "ok", "agent_status": "completed", "dataset_name": dataset_name,
        "scan": scan, "iterations": iterations,
        "final": final,
        "next_actions": next_actions,
        "method_note": "Autonomous investigation is an evidence-ranking workflow. It does not establish causation from observational data."
    }
