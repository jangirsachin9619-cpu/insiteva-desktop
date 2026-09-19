"""Desktop-first intelligence helpers for INSITEVA.
Deterministic: calculations stay in pandas/duckdb; this module never asks an LLM to invent numbers.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Dict, List
import numpy as np
import pandas as pd

from .analytics import business_numeric, profile, detect_metric, detect_category


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def semantic_candidates(question: str, df: pd.DataFrame, limit: int = 8) -> Dict[str, List[Dict[str, Any]]]:
    """Rank likely metrics/categories/date columns using transparent lexical/business signals."""
    q = _norm(question)
    tokens = set(q.split())
    metric_rows=[]; cat_rows=[]; date_rows=[]
    for c in df.columns:
        name=_norm(c); score=0
        if name and name in q: score += 8
        if name.replace(' ','') in q.replace(' ',''): score += 4
        overlap=len(tokens & set(name.split())); score += overlap*2
        if pd.api.types.is_numeric_dtype(df[c]) and c in business_numeric(df):
            if any(w in q for w in ('sales','revenue','amount','turnover','profit','margin','cost','quantity','units','discount')): score += 2
            metric_rows.append({'column':str(c),'score':score})
        elif pd.api.types.is_datetime64_any_dtype(df[c]):
            if any(w in q for w in ('date','month','year','trend','over time','growth','change')): score += 6
            date_rows.append({'column':str(c),'score':score})
        elif pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_categorical_dtype(df[c]):
            nun=int(df[c].nunique(dropna=True))
            if 1 < nun <= 100: score += 2
            if any(w in q for w in ('region','category','product','customer','channel','department','segment','rep')): score += 2
            cat_rows.append({'column':str(c),'score':score,'unique_values':nun})
    metric_rows=sorted(metric_rows,key=lambda x:(-x['score'],x['column']))[:limit]
    cat_rows=sorted(cat_rows,key=lambda x:(-x['score'],x['unique_values'],x['column']))[:limit]
    date_rows=sorted(date_rows,key=lambda x:(-x['score'],x['column']))[:limit]
    # Existing detectors are a useful deterministic tie-breaker.
    dm=detect_metric(question,df)
    dc=detect_category(question,df)
    if dm:
        metric_rows=[{'column':str(dm),'score':max([x['score'] for x in metric_rows if x['column']==str(dm)] or [0])+3}] + [x for x in metric_rows if x['column']!=str(dm)]
    if dc:
        cat_rows=[{'column':str(dc),'score':max([x['score'] for x in cat_rows if x['column']==str(dc)] or [0])+3,'unique_values':int(df[dc].nunique(dropna=True))}] + [x for x in cat_rows if x['column']!=str(dc)]
    return {'metrics':metric_rows[:limit], 'categories':cat_rows[:limit], 'dates':date_rows[:limit]}


def desktop_scan(df: pd.DataFrame, dataset_name: str = '') -> Dict[str, Any]:
    """Create a compact analyst briefing without modifying the dataframe."""
    if df is None or df.empty:
        return {'status':'error','message':'No dataset is loaded.'}
    p=profile(df, fast=len(df)>250_000)
    nums=business_numeric(df)
    dates=p.get('dates',[])
    metric=detect_metric('sales revenue amount profit',df) or (nums[0] if nums else None)
    quality=[]
    missing=int(df.isna().sum().sum()); dup=int(df.duplicated().sum()) if len(df)<=500_000 else None
    if missing: quality.append(f'{missing:,} missing cells')
    if dup: quality.append(f'{dup:,} duplicate rows')
    if not quality: quality.append('No missing cells or duplicate rows detected')
    kpi={}
    if metric:
        s=pd.to_numeric(df[metric],errors='coerce').dropna()
        if len(s):
            kpi={'metric':str(metric),'total':float(s.sum()),'average':float(s.mean()),'median':float(s.median()),'min':float(s.min()),'max':float(s.max())}
    top=[]
    cat=detect_category('sales revenue amount',df)
    if metric and cat:
        g=df.assign(_m=pd.to_numeric(df[metric],errors='coerce')).groupby(cat,dropna=False)['_m'].sum().sort_values(ascending=False).head(5)
        top=[{'category':str(k),'value':float(v)} for k,v in g.items()]
    trend=None
    if metric and dates:
        d=dates[0]; work=df[[d,metric]].copy(); work[metric]=pd.to_numeric(work[metric],errors='coerce'); work=work.dropna(subset=[d,metric])
        if not work.empty:
            g=work.groupby(work[d].dt.to_period('M'))[metric].sum().sort_index()
            if len(g)>=2:
                prev=float(g.iloc[-2]); curr=float(g.iloc[-1]); delta=curr-prev
                trend={'date_column':str(d),'previous_period':str(g.index[-2]),'current_period':str(g.index[-1]),'previous':prev,'current':curr,'delta':delta,'change_pct':None if prev==0 else delta/abs(prev)*100}
    return {'status':'ok','dataset':dataset_name,'rows':int(len(df)),'columns':int(len(df.columns)),'memory_mb':round(float(df.memory_usage(deep=True).sum()/1024**2),2),'quality':quality,'metric':metric,'kpi':kpi,'top_segments':top,'trend':trend,'semantic_candidates':semantic_candidates('sales trend',df),'large_data_mode':bool(len(df)>=250_000)}


def recommend_questions(df: pd.DataFrame, max_items: int=8) -> List[str]:
    if df is None or df.empty: return []
    metric=detect_metric('sales revenue amount profit',df)
    cat=detect_category('region category product customer',df)
    dates=profile(df,fast=True).get('dates',[])
    out=[]
    if metric and cat: out += [f'Which {cat} generated the highest {metric}?',f'Which {cat} is declining fastest?']
    if metric and dates: out += [f'Show the monthly trend of {metric}.',f'Why did {metric} change in the latest period?']
    if metric: out += [f'Find unusual {metric} values.',f'What should I do to improve {metric}?']
    out += ['Check data quality.','Create an executive summary.']
    return out[:max_items]


def duckdb_available() -> bool:
    try:
        import duckdb  # noqa: F401
        return True
    except Exception:
        return False


def query_large_dataframe(df: pd.DataFrame, sql: str) -> pd.DataFrame:
    """Run read-only SQL over a pandas DataFrame through DuckDB when installed."""
    if not duckdb_available():
        raise RuntimeError('DuckDB is not installed. Install the optional large-data dependency: pip install duckdb')
    if not re.match(r'^\s*(select|with)\b', sql, flags=re.I):
        raise ValueError('Large-data SQL mode is read-only: use SELECT or WITH queries only.')
    import duckdb
    con=duckdb.connect(database=':memory:')
    try:
        con.register('data',df)
        return con.execute(sql).fetchdf()
    finally:
        con.close()
