from __future__ import annotations
import re, json, csv
from pathlib import Path
import pandas as pd
import numpy as np

EXCLUDE_NUMERIC = {"id", "product_id", "customer_id", "user_id"}
SYNONYMS = {
    "sales": ["sales", "sale", "revenue", "turnover", "sales amount", "amount"],
    "quantity": ["quantity", "qty", "units", "units sold", "volume"],
    "profit": ["profit", "margin", "gross profit"],
    "cost": ["cost", "unit cost", "expense", "expenses"],
    "discount": ["discount", "discounts"],
}


def load_file(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    suffix = p.suffix.lower()
    if suffix == ".csv":
        last_error = None
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
            try:
                # Sniff only a small sample; then use pandas' fast C parser.
                with p.open("r", encoding=enc, errors="replace", newline="") as fh:
                    sample = fh.read(65536)
                try:
                    delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
                except csv.Error:
                    delimiter = ","
                df = pd.read_csv(p, encoding=enc, sep=delimiter, low_memory=True)
                break
            except Exception as exc:
                last_error = exc
        else:
            raise ValueError(f"Could not read CSV: {last_error}")
    elif suffix == ".xlsx":
        try:
            df = pd.read_excel(p, engine="openpyxl", sheet_name=0)
        except Exception as exc:
            raise ValueError(f"Could not read Excel XLSX file: {exc}") from exc
    elif suffix == ".xls":
        try:
            df = pd.read_excel(p, engine="xlrd", sheet_name=0)
        except Exception as exc:
            raise ValueError(f"Could not read Excel XLS file: {exc}") from exc
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Use CSV, XLSX or XLS.")
    if df is None or df.empty:
        raise ValueError("The selected file contains no data rows.")
    df = df.dropna(how="all").copy()
    df.columns = [str(c).strip() if str(c).strip() else f"Column_{i+1}" for i,c in enumerate(df.columns)]
    sample_n = min(len(df), 10000)
    for c in df.columns:
        if df[c].dtype == "object":
            sample = df[c].head(sample_n).astype(str).str.strip()
            parsed = pd.to_datetime(sample, errors="coerce")
            if parsed.notna().mean() >= 0.8 and parsed.notna().sum() >= 2:
                try: df[c] = pd.to_datetime(df[c], errors="coerce")
                except Exception: pass
    return df


def profile(df, fast=False):
    missing = int(df.isna().sum().sum())
    duplicates = int(df.duplicated().sum()) if not fast else None
    return {"rows": int(len(df)), "columns": int(len(df.columns)), "missing": missing,
            "duplicates": duplicates,
            "numeric": [str(c) for c in df.select_dtypes(include=np.number).columns],
            "categorical": [str(c) for c in df.select_dtypes(include=["object", "category"]).columns],
            "dates": [str(c) for c in df.select_dtypes(include=["datetime", "datetimetz"]).columns]}


def business_numeric(df):
    return [c for c in df.select_dtypes(include=np.number).columns
            if str(c).lower() not in EXCLUDE_NUMERIC and not str(c).lower().endswith("_id")
            and str(c).lower() != "id" and "code" not in str(c).lower()]


def detect_metric(question, df):
    q = question.lower(); cols = business_numeric(df)
    for c in cols:
        lc = str(c).lower()
        if lc in q or lc.replace("_", " ") in q: return c
    for key, words in SYNONYMS.items():
        if any(w in q for w in words):
            for c in cols:
                lc = str(c).lower()
                if key in lc or (key == "sales" and any(w in lc for w in ["amount", "sales", "revenue"])) or (key == "quantity" and any(w in lc for w in ["quantity", "qty", "units"])):
                    return c
    return cols[0] if cols else None


def detect_metrics(question, df):
    q = question.lower(); found=[]
    for c in business_numeric(df):
        lc=str(c).lower()
        if lc in q or lc.replace("_", " ") in q: found.append(c)
    for key, words in SYNONYMS.items():
        if any(w in q for w in words):
            for c in business_numeric(df):
                lc=str(c).lower()
                if c not in found and (key in lc or (key=="sales" and any(w in lc for w in ["amount","sales","revenue"])) or (key=="quantity" and any(w in lc for w in ["quantity","qty","units"]))): found.append(c)
    return found[:3]


def detect_category(question, df):
    q = question.lower(); cats = df.select_dtypes(include=["object", "category"]).columns.tolist()
    for c in cats:
        lc=str(c).lower()
        if lc in q or lc.replace("_", " ") in q: return c
    aliases = {
        "region": ["region", "area", "territory", "location"],
        "sales_rep": ["sales rep", "representative", "salesperson", "rep"],
        "product_category": ["product category", "category", "product", "products"],
        "customer_type": ["customer", "customer type", "segment"],
        "sales_channel": ["channel", "sales channel", "online", "offline"],
        "payment_method": ["payment", "payment method"],
    }
    for c in cats:
        lc = str(c).lower()
        for key, words in aliases.items():
            if (key in lc or key.replace("_", " ") in lc) and any(w in q for w in words): return c
    # semantic fallback for common single-word dimensions
    for c in cats:
        lc=str(c).lower()
        if any(w in q for w in ["product","category","region","channel","customer","segment","payment","rep"]):
            if any(w in lc for w in ["product","category","region","channel","customer","segment","payment","rep"]): return c
    return None


def detect_operation(q):
    q=q.lower()
    m=re.search(r"top\s+(\d+)",q)
    if m:return "top",int(m.group(1))
    m=re.search(r"bottom\s+(\d+)",q)
    if m:return "bottom",int(m.group(1))
    if any(x in q for x in ["highest","maximum","max","best","largest"]):return "max",1
    if any(x in q for x in ["lowest","minimum","min","worst","smallest"]):return "min",1
    if "median" in q:return "median",None
    if any(x in q for x in ["average","avg","mean"]):return "mean",None
    if any(x in q for x in ["count","how many","number of","transactions"]):return "count",None
    if any(x in q for x in ["growth","increase","decrease","trend","over time","monthly"]):return "trend",None
    if any(x in q for x in ["percentage","percent","share"]):return "share",None
    if any(x in q for x in ["compare","comparison","versus"," vs "]):return "compare",None
    return "sum",None


def detect_chart_type(q):
    q=q.lower()
    if any(x in q for x in ["scatter","relationship","correlation","against"," vs "]): return "scatter"
    if any(x in q for x in ["pie","donut"]): return "donut" if "donut" in q else "pie"
    if any(x in q for x in ["histogram","distribution"]): return "hist"
    if any(x in q for x in ["box plot","boxplot","box-and-whisker"]): return "box"
    if any(x in q for x in ["area","filled trend"]): return "area"
    if any(x in q for x in ["line","trend","over time","monthly"]): return "line"
    if any(x in q for x in ["heatmap","heat map"]): return "heatmap"
    return "bar"


def understand(question,df,previous=None):
    q=question.lower(); metric=detect_metric(question,df); metrics=detect_metrics(question,df); category=detect_category(question,df); op,n=detect_operation(question)
    if previous:
        if not metric and previous.get("metric") in business_numeric(df): metric=previous.get("metric")
        if not metrics and previous.get("metrics"): metrics=previous.get("metrics")
        if not category and any(x in q for x in ["by ","per ","against ","vs ","versus "]): category=previous.get("category")
    filters={}
    for c in df.select_dtypes(include=["object","category"]).columns:
        values=df[c].dropna().astype(str).unique()
        for v in values:
            if len(str(v))>1 and str(v).lower() in q: filters[str(c)]=v
    visualization=any(x in q for x in ["graph","chart","plot","visualize","visualisation","dashboard","visualization","visualisation"])
    dashboard=any(x in q for x in ["build dashboard","create dashboard","executive dashboard","dashboard for me","auto dashboard"])
    return {"question":question,"intent":"dashboard" if dashboard else ("visualization" if visualization else "analysis"),
            "metric":metric,"metrics":metrics or ([metric] if metric else []),"category":category,"operation":op,"n":n,
            "chart_type":detect_chart_type(q),"filters":filters,"follow_up":bool(previous)}


def _filtered(df,spec):
    out=df.copy()
    for c,v in spec.get("filters",{}).items():
        if c in out.columns: out=out[out[c].astype(str).str.lower()==str(v).lower()]
    return out


def analyze(question_or_spec,df):
    spec=question_or_spec if isinstance(question_or_spec,dict) else understand(question_or_spec,df)
    work=_filtered(df,spec); metric=spec.get("metric"); cat=spec.get("category"); op=spec.get("operation")
    if op=="count":
        if cat and cat in work.columns:
            g=work.groupby(cat).size().sort_values(ascending=False)
            return {"status":"ok","type":"grouped","metric":"count","category":cat,"operation":op,"total":int(len(work)),"rows":[{str(cat):str(k),"count":int(v)} for k,v in g.head(15).items()]}
        return {"status":"ok","type":"scalar","metric":"count","operation":op,"value":int(len(work))}
    if not metric or metric not in work.columns:return {"status":"error","message":"I could not identify a suitable numeric metric."}
    s=pd.to_numeric(work[metric],errors="coerce").dropna()
    if s.empty:return {"status":"error","message":f"No numeric values available for {metric}."}
    if cat and cat in work.columns:
        g=work.groupby(cat)[metric].agg(["sum","mean","max","min","count"]).sort_values("sum",ascending=False)
        if op in {"top","bottom"}: rows=g.sort_values("sum",ascending=(op=="bottom")).head(spec.get("n") or 5)
        elif op=="max": rows=g.sort_values("max",ascending=False).head(1)
        elif op=="min": rows=g.sort_values("min",ascending=True).head(1)
        elif op=="mean": rows=g.sort_values("mean",ascending=False).head(10)
        elif op=="share": rows=g.copy(); rows["share_pct"]=rows["sum"]/rows["sum"].sum()*100
        else: rows=g.head(15)
        return {"status":"ok","type":"grouped","metric":str(metric),"category":str(cat),"operation":op,"total":float(s.sum()),"rows":json.loads(rows.reset_index().to_json(orient="records",date_format="iso"))}
    vals={"sum":float(s.sum()),"mean":float(s.mean()),"median":float(s.median()),"max":float(s.max()),"min":float(s.min()),"count":int(s.count())}
    if op=="trend":
        dcol=next(iter(profile(work)["dates"]),None)
        if dcol:
            tmp=work[[dcol,metric]].dropna().copy();tmp["period"]=tmp[dcol].dt.to_period("M").astype(str);vals["trend"]=tmp.groupby("period")[metric].sum().sort_index().to_dict()
    return {"status":"ok","type":"scalar","metric":str(metric),"operation":op,"value":vals.get(op,vals["sum"]),"total":float(s.sum()),"mean":float(s.mean())}


def monthly_trend(df,metric):
    dcol=next(iter(profile(df)["dates"]),None)
    if not dcol:return {"status":"error","message":"No date column found."}
    if metric not in df.columns:return {"status":"error","message":"Metric not found."}
    t=df[[dcol,metric]].dropna().copy();t["period"]=t[dcol].dt.to_period("M").astype(str);g=t.groupby("period")[metric].sum().sort_index()
    return {"status":"ok","periods":g.index.tolist(),"values":[float(x) for x in g.values]}


def forecast(df,metric,periods=3):
    tr=monthly_trend(df,metric)
    if tr.get("status")!="ok" or len(tr["values"])<2:return {"status":"error","message":"At least two months are required."}
    y=np.array(tr["values"],dtype=float);x=np.arange(len(y));slope,intercept=np.polyfit(x,y,1)
    return {"status":"ok","metric":metric,"history":tr,"forecast":[float(slope*(len(y)+i)+intercept) for i in range(periods)],"method":"linear baseline"}


def anomalies(df,metric):
    tr=monthly_trend(df,metric)
    if tr.get("status")!="ok":return tr
    vals=np.array(tr["values"],float);mean=vals.mean();sd=vals.std(ddof=0);scores=np.zeros_like(vals) if sd==0 else (vals-mean)/sd
    return {"status":"ok","metric":metric,"items":[{"period":p,"value":float(v),"z_score":float(z),"anomaly":bool(abs(z)>=2)} for p,v,z in zip(tr["periods"],vals,scores)]}


def insights(df):
    out=[];nums=business_numeric(df);cats=df.select_dtypes(include=["object","category"]).columns
    for c in cats:
        if len(df[c].dropna().unique())<2 or not nums:continue
        m=nums[0];g=df.groupby(c)[m].sum().sort_values(ascending=False)
        if not g.empty:out.append({"title":f"Top {c}","message":f"{g.index[0]} leads {m} with {g.iloc[0]:,.2f}."})
    return out[:5]


def recommendations(df):
    out=[];nums=business_numeric(df);cats=df.select_dtypes(include=["object","category"]).columns
    for c in cats:
        if not nums:continue
        g=df.groupby(c)[nums[0]].sum().sort_values()
        if len(g)>1:out.append({"priority":"Medium","title":f"Review lowest {c}","message":f"{g.index[0]} has the lowest {nums[0]} total ({g.iloc[0]:,.2f}). Investigate root causes."})
    return out[:4]


def _first_matching(cols, words):
    for c in cols:
        lc=str(c).lower()
        if any(w in lc for w in words): return c
    return None


def kpis(df):
    nums=business_numeric(df); out={"Transactions":int(len(df))}
    sales=_first_matching(nums,["sales","revenue","amount","turnover"])
    qty=_first_matching(nums,["quantity","qty","units"])
    discount=_first_matching(nums,["discount"])
    if sales is not None:
        s=pd.to_numeric(df[sales],errors="coerce");out["Total Sales"]=float(s.sum());out["Average Sale"]=float(s.mean())
    elif nums:
        s=pd.to_numeric(df[nums[0]],errors="coerce");out[f"Total {nums[0]}"]=float(s.sum());out[f"Average {nums[0]}"]=float(s.mean())
    if qty is not None: out["Total Quantity"]=float(pd.to_numeric(df[qty],errors="coerce").sum())
    if discount is not None: out["Average Discount"]=float(pd.to_numeric(df[discount],errors="coerce").mean())
    out["Missing Values"]=int(df.isna().sum().sum());out["Duplicates"]=int(df.duplicated().sum())
    return out


def auto_dashboard_specs(df):
    nums=business_numeric(df); cats=[c for c in df.select_dtypes(include=["object","category"]).columns if 1<df[c].nunique(dropna=True)<=100]
    dates=profile(df)["dates"]; specs=[]
    primary=_first_matching(nums,["sales","revenue","amount","turnover","profit"]) or (nums[0] if nums else None)
    region=_first_matching(cats,["region","area","territory"])
    product=_first_matching(cats,["product","category"])
    channel=_first_matching(cats,["channel","type"])
    customer=_first_matching(cats,["customer","segment"])
    rep=_first_matching(cats,["rep","salesperson"])
    if dates and primary: specs.append({"kind":"line","title":f"{primary} Trend","date":dates[0],"metric":primary})
    for c,title in [(region,"Performance by Region"),(product,"Performance by Product / Category"),(channel,"Performance by Channel"),(customer,"Performance by Customer Segment"),(rep,"Performance by Sales Rep")]:
        if c and primary and c not in [s.get("category") for s in specs]: specs.append({"kind":"bar","title":title,"category":c,"metric":primary})
    qty=_first_matching(nums,["quantity","qty","units"])
    if qty and primary and qty!=primary: specs.append({"kind":"scatter","title":f"{primary} vs {qty}","x":qty,"y":primary})
    if not specs and primary and cats: specs.append({"kind":"bar","title":f"{primary} by {cats[0]}","category":cats[0],"metric":primary})
    return specs[:6]


def ollama_explain(question,result):
    try:
        import requests
        prompt=("You are INSITEVA, a business analyst. Explain ONLY the verified result below. "
                "Never change, invent, or recalculate numbers. Separate facts, interpretation, and recommendations.\n"
                f"Question: {question}\nVerified result: {json.dumps(result,default=str)}")
        r=requests.post("http://localhost:11434/api/generate",json={"model":"llama3.2","prompt":prompt,"stream":False},timeout=20)
        if r.ok:return r.json().get("response","").strip()
    except Exception: pass
    return ""



def smart_analysis(df, max_items=5):
    """Automatic AI-analyst briefing. Deterministic facts only; safe to edit/refine later."""
    if df is None or df.empty:
        return {"status":"error","message":"No data available for automatic analysis."}
    p=profile(df, fast=False)
    nums=business_numeric(df)
    dates=p.get("dates",[])
    cats=[c for c in df.select_dtypes(include=["object","category"]).columns if df[c].nunique(dropna=True)>1]
    result={"status":"ok","profile":p,"kpis":kpis(df),"quality":{"missing_by_column":df.isna().sum().astype(int).to_dict(),"duplicate_rows":int(df.duplicated().sum())},"findings":[],"trends":[],"anomalies":[],"recommended_questions":[]}
    primary=detect_metric("sales revenue amount profit",df) or (nums[0] if nums else None)
    if primary:
        x=pd.to_numeric(df[primary],errors="coerce").dropna()
        if not x.empty:
            result["findings"].append({"title":"Primary metric","metric":primary,"total":float(x.sum()),"average":float(x.mean()),"median":float(x.median()),"max":float(x.max()),"min":float(x.min())})
            oc=outlier_counts(df,primary)
            if oc["iqr"]:
                result["anomalies"].append({"metric":primary,"method":"IQR","count":oc["iqr"]})
    for c in cats[:3]:
        if primary:
            g=df.groupby(c)[primary].sum().sort_values(ascending=False).head(max_items)
            result["findings"].append({"title":f"Top {c}","dimension":c,"metric":primary,"rows":[{"value":str(k),"total":float(v)} for k,v in g.items()]})
    if dates and primary:
        tr=monthly_trend(df,primary)
        if tr.get("status")=="ok":
            vals=tr.get("values",[])
            result["trends"].append({"metric":primary,"periods":tr.get("periods",[]),"values":vals,"latest_growth_pct":(float((vals[-1]-vals[-2])/abs(vals[-2])*100) if len(vals)>=2 and vals[-2] else None)})
    if len(nums)>=2:
        corr=df[nums[:min(len(nums),8)]].apply(pd.to_numeric,errors="coerce").corr()
        pairs=[]
        for i,a in enumerate(corr.columns):
            for b in corr.columns[i+1:]:
                v=corr.loc[a,b]
                if pd.notna(v): pairs.append((abs(float(v)),float(v),a,b))
        for _,v,a,b in sorted(pairs,reverse=True)[:3]: result["findings"].append({"title":"Strong numeric relationship","metrics":[a,b],"correlation":v})
    result["recommendations"] = recommendations(df)
    result["recommended_questions"]=[
        f"Why did {primary} change over time?" if primary and dates else "What are the main drivers in this dataset?",
        f"What are the top 5 {cats[0]} by {primary}?" if cats and primary else "Which segments perform best?",
        f"Find anomalies in {primary}." if primary else "Check data quality",
        "Compare the strongest and weakest segments."
    ]
    return result

def report_html(path,dataset_name,df,last_answer=""):
    p=profile(df);ks=kpis(df);ins=insights(df);rec=recommendations(df)
    cards="".join(f"<div class='card'><b>{k}</b><br><span>{v:,.2f}</span></div>" if isinstance(v,(float,int)) else f"<div class='card'><b>{k}</b><br><span>{v}</span></div>" for k,v in ks.items())
    body=f"""<!doctype html><html><head><meta charset='utf-8'><title>INSITEVA Report</title><style>body{{font-family:Arial;background:#07111f;color:#e6edf7;padding:30px}}h1{{color:#7dd3fc}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.card{{background:#0d1b2e;border:1px solid #24486c;border-radius:12px;padding:16px}}.card span{{font-size:22px;font-weight:800}}pre{{white-space:pre-wrap;background:#0d1b2e;padding:18px;border-radius:12px}}</style></head><body><h1>◈ INSITEVA</h1><p>{dataset_name} • {p['rows']:,} rows • {p['columns']} columns</p><div class='grid'>{cards}</div><h2>Insights</h2><ul>{''.join('<li>'+x['message']+'</li>' for x in ins)}</ul><h2>Recommendations</h2><ul>{''.join('<li>['+x['priority']+'] '+x['message']+'</li>' for x in rec)}</ul><h2>Last AI Analysis</h2><pre>{last_answer}</pre></body></html>"""
    Path(path).write_text(body,encoding="utf-8")

# Advanced deterministic analysis helpers used by the AI Analyst for harder analyst questions.
def complex_analysis(question, df):
    q=question.lower()
    if any(k in q for k in ["correlation", "correlate", "relationship between"]):
        ms=detect_metrics(question,df)
        if len(ms)>=2:
            a=df[[ms[0],ms[1]]].apply(pd.to_numeric,errors="coerce").dropna()
            if len(a)>=2:return {"status":"ok","type":"correlation","metrics":ms[:2],"correlation":float(a.iloc[:,0].corr(a.iloc[:,1])),"rows":len(a)}
    if any(k in q for k in ["missing", "null", "data quality"]):
        return {"status":"ok","type":"data_quality","missing_by_column":df.isna().sum().astype(int).to_dict(),"duplicate_rows":int(df.duplicated().sum()),"rows":len(df),"columns":len(df.columns)}
    if any(k in q for k in ["outlier", "unusual", "anomal"]):
        ms=detect_metrics(question,df) or business_numeric(df)[:1]
        if ms:
            return {"status":"ok","type":"outlier_screen","results":{m:outlier_counts(df,m) for m in ms}}
    if any(k in q for k in ["growth", "month-over-month", "mom"]):
        ms=detect_metrics(question,df) or business_numeric(df)[:1]
        if ms:
            tr=monthly_trend(df,ms[0])
            if tr.get("status")=="ok":
                vals=tr["values"]; growth=[None]+[(vals[i]-vals[i-1])/abs(vals[i-1])*100 if vals[i-1] else None for i in range(1,len(vals))]
                return {"status":"ok","type":"growth","metric":ms[0],"periods":tr["periods"],"values":vals,"mom_growth_pct":growth}
    return None

def outlier_counts(df,col):
    x=pd.to_numeric(df[col],errors="coerce").dropna()
    if x.empty:return {"iqr":0,"z_score":0}
    q1,q3=x.quantile(.25),x.quantile(.75);iqr=q3-q1;iqr_n=int(((x<q1-1.5*iqr)|(x>q3+1.5*iqr)).sum())
    sd=x.std(ddof=0);z_n=0 if sd==0 else int((((x-x.mean())/sd).abs()>3).sum())
    return {"iqr":iqr_n,"z_score":z_n}
