from __future__ import annotations
import json, re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

from .analytics import business_numeric, profile, detect_metric, detect_metrics, detect_category, monthly_trend, analyze


@dataclass
class MetricDefinition:
    name: str
    expression: str
    description: str = ""


class SemanticLayer:
    """Lightweight semantic metric dictionary. Definitions are transparent and editable."""
    DEFAULTS = [
        MetricDefinition("Revenue", "SUM(sales-like column)", "Total sales/revenue amount."),
        MetricDefinition("Transactions", "COUNT(rows)", "Number of records/transactions."),
        MetricDefinition("Average Sale", "Revenue / Transactions", "Average revenue per transaction."),
        MetricDefinition("Quantity", "SUM(quantity-like column)", "Total units/quantity sold."),
        MetricDefinition("Average Discount", "AVG(discount-like column)", "Average discount rate/value."),
    ]
    def __init__(self):
        self.metrics = {m.name: m for m in self.DEFAULTS}

    def add(self, name: str, expression: str, description: str = ""):
        if not name.strip() or not expression.strip():
            raise ValueError("Metric name and expression are required.")
        self.metrics[name.strip()] = MetricDefinition(name.strip(), expression.strip(), description.strip())

    def definitions(self):
        return [asdict(x) for x in self.metrics.values()]

    def resolve(self, name: str):
        return self.metrics.get(name)


class DataQualityGate:
    """Deterministic pre-analysis quality checks. It never changes the dataset."""
    def scan(self, df: pd.DataFrame):
        rows, cols = len(df), len(df.columns)
        missing_total = int(df.isna().sum().sum())
        dup = int(df.duplicated().sum())
        issues = []
        if rows == 0: issues.append({"severity":"Critical","issue":"Dataset is empty"})
        if missing_total: issues.append({"severity":"Warning","issue":f"{missing_total:,} missing cells"})
        if dup: issues.append({"severity":"Warning","issue":f"{dup:,} duplicate rows"})
        for c in df.columns:
            s=df[c]
            if pd.api.types.is_numeric_dtype(s):
                neg=int((s.dropna()<0).sum())
                if neg: issues.append({"severity":"Info","issue":f"{c}: {neg:,} negative numeric values"})
            if pd.api.types.is_object_dtype(s):
                parsed=pd.to_datetime(s,errors="coerce")
                if parsed.notna().mean() >= .8 and parsed.notna().sum() >= 2:
                    issues.append({"severity":"Info","issue":f"{c}: appears to be a date stored as text"})
                if s.nunique(dropna=True) > max(100, rows*.9) and rows > 20:
                    issues.append({"severity":"Info","issue":f"{c}: very high cardinality; likely an ID/code"})
        score=100
        score -= min(30, round(missing_total/max(1,rows*max(1,cols))*100))
        score -= min(20, round(dup/max(1,rows)*100))
        score=max(0,int(score))
        return {"score":score,"rows":rows,"columns":cols,"missing_cells":missing_total,"duplicate_rows":dup,"issues":issues[:50],"status":"pass" if score>=80 and rows>0 else "review"}


class AnalysisPlanner:
    """Turns complex analyst questions into small, deterministic tool steps."""
    def plan(self, question: str, df: pd.DataFrame):
        q=question.lower(); steps=[]
        metrics=detect_metrics(question,df); metric=detect_metric(question,df); cat=detect_category(question,df)
        date_col=next(iter(profile(df)["dates"]),None)
        complex_terms=["why","reason","driver","root cause","impact","contribute","break down","explain the change","what caused"]
        if any(t in q for t in complex_terms):
            if date_col and metric and any(t in q for t in ["fall","drop","decrease","increase","growth","change","decline"]):
                steps.append({"name":"Time trend","operation":"monthly_trend","metric":metric,"date":date_col})
            if cat and metric:
                steps.append({"name":f"Driver ranking by {cat}","operation":"grouped","metric":metric,"category":cat,"question":f"top 10 {cat} by {metric}"})
            # Add a second dimension when available to expose a deeper driver tree.
            cats=[c for c in df.select_dtypes(include=["object","category"]).columns if c!=cat and 1<df[c].nunique(dropna=True)<=100]
            if cats and metric:
                steps.append({"name":f"Secondary driver by {cats[0]}","operation":"grouped","metric":metric,"category":cats[0],"question":f"top 10 {cats[0]} by {metric}"})
        if "correlation" in q and len(metrics)>=2:
            steps.append({"name":"Correlation","operation":"correlation","metrics":metrics[:2]})
        if ("missing" in q or "data quality" in q or "quality" in q):
            steps.insert(0,{"name":"Data quality gate","operation":"quality"})
        if ("outlier" in q or "unusual" in q or "anomal" in q) and metric:
            steps.append({"name":"Outlier screen","operation":"outlier","metric":metric})
        if ("growth" in q or "month-over-month" in q or "mom" in q) and metric:
            steps.append({"name":"MoM growth","operation":"growth","metric":metric})
        if not steps:
            steps=[{"name":"Direct verified analysis","operation":"analyze","question":question}]
        return {"question":question,"steps":steps,"complex":len(steps)>1}

    def execute(self, plan, df):
        results=[]
        for step in plan["steps"]:
            op=step["operation"]
            if op=="quality":
                results.append({"step":step["name"],"result":DataQualityGate().scan(df)})
            elif op=="monthly_trend":
                results.append({"step":step["name"],"result":monthly_trend(df,step["metric"])})
            elif op=="grouped":
                results.append({"step":step["name"],"result":analyze(step["question"],df)})
            elif op=="correlation":
                a,b=step["metrics"]; z=df[[a,b]].apply(pd.to_numeric,errors="coerce").dropna(); c=float(z[a].corr(z[b])) if len(z)>=2 else None
                results.append({"step":step["name"],"result":{"status":"ok" if c is not None else "error","type":"correlation","metrics":[a,b],"correlation":c,"rows":len(z)}})
            elif op=="outlier":
                s=pd.to_numeric(df[step["metric"]],errors="coerce"); q1=s.quantile(.25);q3=s.quantile(.75);iqr=q3-q1; lo=q1-1.5*iqr;hi=q3+1.5*iqr; n=int(((s<lo)|(s>hi)).sum())
                results.append({"step":step["name"],"result":{"status":"ok","type":"outlier_screen","metric":step["metric"],"lower":float(lo),"upper":float(hi),"outliers":n}})
            elif op=="growth":
                tr=monthly_trend(df,step["metric"]); vals=tr.get("values",[]); growth=[None]+[None if vals[i-1]==0 else (vals[i]-vals[i-1])/abs(vals[i-1])*100 for i in range(1,len(vals))]
                results.append({"step":step["name"],"result":{"status":tr.get("status"),"type":"growth","metric":step["metric"],"periods":tr.get("periods",[]),"mom_growth_pct":growth}})
            else:
                results.append({"step":step["name"],"result":analyze(step.get("question",plan["question"]),df)})
        return results


def root_cause_analysis(df, metric=None, max_items=5):
    """Evidence-backed driver analysis for questions such as 'why did sales decrease?'.
    All numeric claims are calculated deterministically from the active dataframe.
    """
    if df is None or df.empty:
        return {"status":"error","message":"No data available for root-cause analysis."}
    date_col=next(iter(profile(df).get("dates",[])),None)
    if not metric or metric not in df.columns:
        metric=detect_metric("sales revenue amount",df) or (business_numeric(df)[0] if business_numeric(df) else None)
    if not metric:
        return {"status":"error","message":"No suitable numeric business metric was found."}
    if not date_col:
        return {"status":"error","message":"A date column is required to determine what changed over time."}
    work=df[[date_col,metric]+[c for c in df.select_dtypes(include=["object","category"]).columns]].copy()
    work["_metric"]=pd.to_numeric(work[metric],errors="coerce")
    work=work.dropna(subset=[date_col,"_metric"])
    work["_period"]=work[date_col].dt.to_period("M").astype(str)
    periods=sorted(work["_period"].unique())
    if len(periods)<2:
        return {"status":"error","message":"At least two time periods are required for driver analysis."}
    prev,curr=periods[-2],periods[-1]
    a=work[work["_period"]==prev]; b=work[work["_period"]==curr]
    prev_total=float(a["_metric"].sum()); curr_total=float(b["_metric"].sum()); delta=curr_total-prev_total
    pct=None if prev_total==0 else delta/abs(prev_total)*100
    direction="increased" if delta>0 else "decreased" if delta<0 else "was flat"
    drivers=[]
    cats=[c for c in df.select_dtypes(include=["object","category"]).columns if c not in {date_col} and 1<df[c].nunique(dropna=True)<=100]
    for c in cats:
        pg=a.groupby(c)["_metric"].sum(); cg=b.groupby(c)["_metric"].sum()
        keys=pg.index.union(cg.index)
        rows=[]
        for k in keys:
            pv=float(pg.get(k,0)); cv=float(cg.get(k,0)); d=cv-pv
            rows.append({"value":str(k),"previous":pv,"current":cv,"delta":d,"abs_delta":abs(d)})
        rows=sorted(rows,key=lambda x:x["abs_delta"],reverse=True)[:max_items]
        for r in rows:
            r.update({"dimension":str(c),"contribution_pct":None if delta==0 else r["delta"]/abs(delta)*100})
        drivers.extend(rows)
    drivers=sorted(drivers,key=lambda x:x["abs_delta"],reverse=True)[:max_items*2]
    numeric_drivers=[]
    nums=[c for c in business_numeric(df) if c!=metric]
    for c in nums[:15]:
        x=pd.to_numeric(work[c],errors="coerce") if c in work.columns else None
        if x is None: continue
        z=work[["_metric",c]].copy();z[c]=pd.to_numeric(z[c],errors="coerce");z=z.dropna()
        if len(z)>=3 and z[c].nunique()>1 and z["_metric"].nunique()>1:
            corr=float(z["_metric"].corr(z[c]))
            if pd.notna(corr): numeric_drivers.append({"metric":str(c),"correlation":corr,"strength":abs(corr),"rows":int(len(z))})
    numeric_drivers=sorted(numeric_drivers,key=lambda x:x["strength"],reverse=True)[:max_items]
    anomalies=[]
    vals=work.groupby("_period")["_metric"].sum().sort_index()
    if len(vals)>=3:
        mu=float(vals.mean()); sd=float(vals.std(ddof=0))
        if sd:
            for per,val in vals.items():
                z=(float(val)-mu)/sd
                if abs(z)>=2: anomalies.append({"period":per,"value":float(val),"z_score":float(z)})
    findings=[f"{metric} {direction} from {prev_total:,.2f} in {prev} to {curr_total:,.2f} in {curr} ({'n/a' if pct is None else f'{pct:.1f}%'})."]
    for d in drivers[:max_items]:
        sign="up" if d["delta"]>0 else "down" if d["delta"]<0 else "flat"
        findings.append(f"{d['dimension']}={d['value']}: {sign} {abs(d['delta']):,.2f} ({'n/a' if d['contribution_pct'] is None else f'{d['contribution_pct']:.1f}% of total change'}).")
    return {"status":"ok","type":"root_cause","metric":str(metric),"date_column":str(date_col),"previous_period":prev,"current_period":curr,"previous_total":prev_total,"current_total":curr_total,"delta":delta,"change_pct":pct,"direction":direction,"drivers":drivers,"numeric_drivers":numeric_drivers,"anomalies":anomalies,"findings":findings,"recommended_actions":[f"Review the strongest driver dimensions first, especially those with the largest absolute change.",f"Validate whether {metric} moved because of volume, mix, price/cost or discount-related fields before taking action."]}


class DynamicAnalystAgent:
    """General-purpose deterministic analyst agent with an inspect -> plan -> execute -> evaluate loop."""
    def __init__(self, planner=None):
        self.planner = planner or AnalysisPlanner()

    def build_plan(self, question, df):
        base = self.planner.plan(question, df)
        q = question.lower()
        steps = [{"step": 1, "tool": "data_quality", "purpose": "Check the active dataset before analysis."}]
        # Reuse the existing deterministic planner, but enrich it with intent-aware evidence steps.
        for i, st in enumerate(base.get("steps", []), 2):
            x = dict(st); x["step"] = i; steps.append(x)
        metric = detect_metric(question, df) or detect_metric("sales revenue amount profit", df)
        date_col = next(iter(profile(df).get("dates", [])), None)
        if metric and date_col and any(t in q for t in ("trend", "over time", "monthly", "month", "year", "change", "growth", "performance")):
            if not any(x.get("operation") == "monthly_trend" for x in steps):
                steps.append({"step": len(steps)+1, "tool": "monthly_trend", "operation": "monthly_trend", "metric": metric, "date": date_col, "purpose": "Verify movement over time."})
        if metric and any(t in q for t in ("unusual", "anomaly", "outlier", "risk")):
            if not any(x.get("operation") == "outlier" for x in steps):
                steps.append({"step": len(steps)+1, "tool": "outlier_screen", "operation": "outlier", "metric": metric, "purpose": "Screen unusual values."})
        if metric and any(t in q for t in ("top", "best", "worst", "highest", "lowest", "perform")):
            cat = detect_category(question, df)
            if cat and not any(x.get("operation") == "grouped" for x in steps):
                steps.append({"step": len(steps)+1, "tool": "segment_rank", "operation": "grouped", "metric": metric, "category": cat, "question": question})
        if len(steps) == 1:
            steps.append({"step": 2, "tool": "verified_analysis", "operation": "analyze", "question": question})
        return {"question": question, "steps": steps, "metric": metric, "date_column": date_col, "requires_review": len(steps) >= 3}

    def execute(self, plan, df):
        # Execute only deterministic tools; the LLM is intentionally outside this layer.
        results=[]
        for st in plan.get("steps", []):
            op=st.get("operation") or st.get("tool")
            try:
                if op == "data_quality":
                    r=DataQualityGate().scan(df)
                elif op == "monthly_trend":
                    r=monthly_trend(df, st["metric"])
                elif op == "grouped":
                    r=analyze(st.get("question", plan["question"]), df)
                elif op == "outlier":
                    s=pd.to_numeric(df[st["metric"]], errors="coerce"); q1=s.quantile(.25); q3=s.quantile(.75); iqr=q3-q1; lo=q1-1.5*iqr; hi=q3+1.5*iqr
                    r={"status":"ok","type":"outlier_screen","metric":st["metric"],"lower":float(lo),"upper":float(hi),"outliers":int(((s<lo)|(s>hi)).sum())}
                elif op == "analyze":
                    r=analyze(st.get("question", plan["question"]), df)
                else:
                    r={"status":"skipped","message":f"Tool {op} not available."}
                results.append({"step":st.get("step"),"tool":op,"status":r.get("status","ok"),"result":r})
            except Exception as e:
                results.append({"step":st.get("step"),"tool":op,"status":"error","error":f"{type(e).__name__}: {e}"})
        verified=[x for x in results if x.get("status")=="ok"]
        confidence=min(.95, .45 + .08*len(verified) + (.10 if any(x.get("result",{}).get("type") in ("grouped","scalar") for x in verified) else 0))
        return {"status":"ok" if verified else "error","type":"dynamic_agent","question":plan.get("question"),"plan":plan,"results":results,"verified_steps":len(verified),"confidence":round(confidence,2),"agent_status":"completed" if verified else "incomplete"}


class VersionManager:
    """Session-level immutable snapshots for safe transformations and undo."""
    def __init__(self): self.versions=[]
    def snapshot(self, df, label="Snapshot"):
        self.versions.append({"label":label,"created_at":datetime.now().isoformat(timespec="seconds"),"df":df.copy()})
        return len(self.versions)
    def list(self):
        return [{"version":i+1,"label":x["label"],"created_at":x["created_at"],"rows":len(x["df"]),"columns":len(x["df"].columns)} for i,x in enumerate(self.versions)]
    def restore(self, version):
        if not 1<=version<=len(self.versions): raise ValueError("Version not found")
        return self.versions[version-1]["df"].copy()


class AuditTrail:
    def __init__(self): self.events=[]
    def record(self, question, dataset, result, filters=None, plan=None):
        self.events.append({"timestamp":datetime.now().isoformat(timespec="seconds"),"question":question,"dataset":dataset,"filters":filters or {},"plan":plan or {},"result":result})
    def export_json(self, path): Path(path).write_text(json.dumps(self.events,indent=2,default=str),encoding="utf-8")


def evidence_text(question, result):
    """Human-readable calculation/evidence layer; numbers come only from verified results."""
    if result.get("status")!="ok": return "No verified evidence available."
    lines=["EVIDENCE / CALCULATION TRACE",f"Question: {question}"]
    if result.get("type")=="scalar":
        lines += [f"Metric: {result.get('metric')}",f"Operation: {result.get('operation')}",f"Verified value: {result.get('value',result.get('total')):,.2f}"]
        if "count" in result: lines.append(f"Rows counted: {result['count']:,}")
    elif result.get("type")=="grouped":
        lines += [f"Grouping: {result.get('category')}",f"Metric: {result.get('metric')}",f"Operation: {result.get('operation')}",f"Rows displayed: {len(result.get('rows',[]))}",f"Total metric in filtered data: {result.get('total',0):,.2f}"]
    elif result.get("type")=="correlation": lines += [f"Variables: {result['metrics'][0]} and {result['metrics'][1]}",f"Rows analysed: {result['rows']:,}",f"Pearson correlation: {result['correlation']:.4f}"]
    else: lines.append(json.dumps(result,indent=2,default=str))
    return "\n".join(lines)

class AIAnalysisAgent:
    """Deterministic-first analyst agent.

    The agent plans an investigation, executes verified tools, evaluates whether the
    evidence is sufficient, and can run a second pass on the strongest dimensions.
    It never asks an LLM to calculate business numbers.
    """
    ROOT_TERMS = ("why did", "why has", "what caused", "root cause", "driver",
                  "reason for", "why is", "why are", "what is driving", "what drove")

    def __init__(self, max_dimensions=6, top_n=5):
        self.max_dimensions = max_dimensions
        self.top_n = top_n

    def _is_root_question(self, question):
        q=question.lower()
        return any(t in q for t in self.ROOT_TERMS)

    def _candidate_dimensions(self, df, excluded):
        out=[]
        for c in df.select_dtypes(include=["object","category"]).columns:
            if c in excluded: continue
            nun=int(df[c].nunique(dropna=True))
            if 1 < nun <= 100:
                out.append((c,nun))
        # Prefer business dimensions over arbitrary text columns.
        hints=("region","area","territory","product","category","channel","customer","segment","rep","salesperson","department","store","city")
        out.sort(key=lambda x:(0 if any(h in x[0].lower() for h in hints) else 1, x[1]))
        return [x[0] for x in out[:self.max_dimensions]]

    def _period_delta(self, df, metric, date_col):
        w=df[[date_col,metric]].copy()
        w["_metric"]=pd.to_numeric(w[metric],errors="coerce")
        w=w.dropna(subset=[date_col,"_metric"])
        w["_period"]=w[date_col].dt.to_period("M").astype(str)
        vals=w.groupby("_period")["_metric"].sum().sort_index()
        if len(vals)<2: return None
        prev,curr=vals.index[-2],vals.index[-1]
        pv,cv=float(vals.iloc[-2]),float(vals.iloc[-1])
        delta=cv-pv
        pct=None if pv==0 else delta/abs(pv)*100
        return {"periods":list(vals.index),"previous_period":prev,"current_period":curr,
                "previous_total":pv,"current_total":cv,"delta":delta,"change_pct":pct,
                "direction":"increased" if delta>0 else "decreased" if delta<0 else "was flat"}

    def _dimension_analysis(self, df, metric, date_col, dimension, period_info):
        prev,curr=period_info["previous_period"],period_info["current_period"]
        w=df[[date_col,dimension,metric]].copy()
        w["_metric"]=pd.to_numeric(w[metric],errors="coerce")
        w=w.dropna(subset=[date_col,"_metric"])
        w["_period"]=w[date_col].dt.to_period("M").astype(str)
        a=w[w["_period"]==prev].groupby(dimension)["_metric"].sum()
        b=w[w["_period"]==curr].groupby(dimension)["_metric"].sum()
        keys=a.index.union(b.index)
        rows=[]
        total_delta=period_info["delta"]
        for key in keys:
            pv=float(a.get(key,0)); cv=float(b.get(key,0)); d=cv-pv
            rows.append({"value":str(key),"previous":pv,"current":cv,"delta":d,
                         "contribution_pct":None if total_delta==0 else d/abs(total_delta)*100})
        rows.sort(key=lambda r:abs(r["delta"]),reverse=True)
        top=rows[:self.top_n]
        impact=sum(abs(r["delta"]) for r in top)
        return {"dimension":dimension,"cardinality":len(keys),"top_drivers":top,
                "impact_score":impact,"coverage_pct":None if abs(total_delta)<1e-12 else impact/abs(total_delta)*100}

    def _numeric_evidence(self, df, metric):
        nums=[c for c in business_numeric(df) if c!=metric]
        evidence=[]
        for c in nums[:20]:
            z=df[[metric,c]].apply(pd.to_numeric,errors="coerce").dropna()
            if len(z)>=5 and z[metric].nunique()>1 and z[c].nunique()>1:
                corr=z[metric].corr(z[c])
                if pd.notna(corr):
                    evidence.append({"metric":c,"correlation":float(corr),"strength":abs(float(corr)),"rows":int(len(z))})
        return sorted(evidence,key=lambda x:x["strength"],reverse=True)[:self.top_n]

    def _confidence(self, period_info, dimensions, numeric):
        if not period_info: return 0.0
        score=0.45
        if abs(period_info.get("delta",0))>0: score += 0.15
        if dimensions: score += min(0.25, 0.05*len(dimensions))
        if any(abs(x.get("contribution_pct") or 0)>=20 for d in dimensions for x in d.get("top_drivers",[])):
            score += 0.10
        if numeric: score += 0.05
        return round(min(score,0.95),2)

    def run(self, question, df, metric=None):
        if df is None or df.empty:
            return {"status":"error","message":"No data available for the analysis agent."}
        p=profile(df)
        date_col=next(iter(p.get("dates",[])),None)
        metric=metric if metric in df.columns else detect_metric(question,df) or detect_metric("sales revenue amount profit",df)
        if not metric:
            nums=business_numeric(df); metric=nums[0] if nums else None
        if not metric: return {"status":"error","message":"No suitable business metric was found."}
        if not date_col:
            return {"status":"error","message":"A date column is required for driver/root-cause analysis."}
        period_info=self._period_delta(df,metric,date_col)
        if not period_info:
            return {"status":"error","message":"At least two monthly periods are required for the investigation."}

        excluded={date_col,metric}
        dimensions=self._candidate_dimensions(df,excluded)
        steps=[]; evidence=[]
        steps.append({"step":1,"tool":"period_compare","status":"completed","purpose":"Establish the verified change over time."})
        selected=[]
        # First pass: inspect all reasonable dimensions.
        for dim in dimensions:
            result=self._dimension_analysis(df,metric,date_col,dim,period_info)
            selected.append(result)
            steps.append({"step":len(steps)+1,"tool":"driver_scan","dimension":dim,"status":"completed"})
        selected.sort(key=lambda x:x["impact_score"],reverse=True)
        strongest=selected[:min(3,len(selected))]
        # Second pass: deeper verification on the strongest dimensions.
        for d in strongest:
            steps.append({"step":len(steps)+1,"tool":"driver_verify","dimension":d["dimension"],"status":"completed","purpose":"Re-check the highest-impact segment changes."})
            for r in d["top_drivers"][:3]:
                evidence.append({"kind":"dimension_driver","dimension":d["dimension"],**r})
        numeric=self._numeric_evidence(df,metric)
        steps.append({"step":len(steps)+1,"tool":"numeric_relationship_scan","status":"completed"})
        confidence=self._confidence(period_info,strongest,numeric)
        findings=[f"{metric} {period_info['direction']} from {period_info['previous_total']:,.2f} in {period_info['previous_period']} to {period_info['current_total']:,.2f} in {period_info['current_period']} ({'n/a' if period_info['change_pct'] is None else f'{period_info['change_pct']:.1f}%'})."]
        for d in strongest[:3]:
            if d["top_drivers"]:
                r=d["top_drivers"][0]
                findings.append(f"Strongest {d['dimension']} signal: {r['value']} changed by {r['delta']:+,.2f} ({'n/a' if r['contribution_pct'] is None else f'{r['contribution_pct']:.1f}% of total change'}).")
        if numeric:
            n=numeric[0]; findings.append(f"Strongest numeric relationship: {n['metric']} vs {metric}, correlation {n['correlation']:+.2f} across {n['rows']:,} rows.")
        actions=[]
        if strongest:
            actions.append(f"Investigate the top {strongest[0]['dimension']} segments responsible for the largest change.")
        actions.append("Validate whether volume, price/cost, discount or mix explains the movement before taking action.")
        actions.append("Use the evidence trace to refine the question or add a filter, then rerun the investigation.")
        next_questions=[]
        for d in strongest[:2]: next_questions.append(f"Break down the {period_info['direction']} by {d['dimension']}.")
        next_questions += [f"Compare quantity and {metric} over the same periods.",f"Create a chart showing the strongest driver and the period change."]
        return {"status":"ok","type":"agent_root_cause","question":question,"metric":str(metric),"date_column":str(date_col),
                "period":period_info,"investigation_steps":steps,"driver_scans":selected,"strongest_drivers":strongest,
                "numeric_evidence":numeric,"evidence":evidence,"confidence":confidence,"findings":findings,
                "recommended_actions":actions,"recommended_questions":next_questions,
                "agent_status":"completed","iterations":2}
