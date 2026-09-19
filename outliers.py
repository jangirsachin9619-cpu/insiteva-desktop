from __future__ import annotations
import numpy as np
import pandas as pd

def _series(df, col):
    if col not in df.columns: raise ValueError(f"Column not found: {col}")
    return pd.to_numeric(df[col], errors="coerce")

def _bounds(x, method, threshold):
    if method.startswith("IQR"):
        q1=x.quantile(.25); q3=x.quantile(.75); iqr=q3-q1
        return q1-1.5*iqr, q3+1.5*iqr
    mu=x.mean(); sd=x.std(ddof=0)
    return mu-threshold*sd, mu+threshold*sd

def outlier_summary(df, col, threshold=3.0):
    x=_series(df,col); valid=x.dropna(); lo,hi=_bounds(valid,"Z-Score" if threshold else "IQR",threshold)
    z=(valid-valid.mean())/valid.std(ddof=0) if valid.std(ddof=0) else valid*0
    iqr_lo,iqr_hi=_bounds(valid,"IQR",threshold)
    return {"column":col,"rows":len(df),"non_null":int(valid.size),"iqr_bounds":[float(iqr_lo),float(iqr_hi)],"iqr_outliers":int(((valid<iqr_lo)|(valid>iqr_hi)).sum()),"z_bounds":[float(lo),float(hi)],"z_outliers":int((z.abs()>threshold).sum())}

def treat_outliers(df, col, method="IQR — Remove", threshold=3.0):
    out=df.copy(); x=_series(out,col); valid=x.dropna()
    if valid.empty:return out
    if method.startswith("IQR"): lo,hi=_bounds(valid,"IQR",threshold)
    else: lo,hi=_bounds(valid,"Z",threshold)
    mask=(x<lo)|(x>hi)
    if "Remove" in method: return out.loc[~mask.fillna(False)].copy()
    if "Cap" in method:
        out.loc[x<lo,col]=lo; out.loc[x>hi,col]=hi; return out
    med=float(valid.median()); out.loc[mask.fillna(False),col]=med; return out
