from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import re
import pandas as pd
from .analytics import load_file


def norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())

@dataclass
class Relationship:
    left_table: str
    left_key: str
    right_table: str
    right_key: str
    cardinality: str = 'Many-to-One'
    active: bool = True

class DataModel:
    """Lightweight Power BI-style semantic model for local CSV/XLSX tables."""
    def __init__(self):
        self.tables: dict[str, pd.DataFrame] = {}
        self.paths: dict[str, str] = {}
        self.relationships: list[Relationship] = []
        self.primary: str | None = None

    def add_file(self, path: str, table_name: str | None = None):
        name = table_name or Path(path).stem
        base = name
        i = 2
        while name in self.tables:
            name = f'{base}_{i}'; i += 1
        self.tables[name] = load_file(path)
        self.paths[name] = str(path)
        if self.primary is None: self.primary = name
        # Relationship inference is intentionally deferred for stability on large datasets.
        return name

    def add_dataframe(self, name: str, df: pd.DataFrame, infer_relationships: bool = False):
        self.tables[name] = df.copy()
        if self.primary is None: self.primary = name
        if infer_relationships:
            self.infer_relationships()

    def infer_relationships(self):
        existing={(r.left_table,r.left_key,r.right_table,r.right_key) for r in self.relationships}
        names=list(self.tables)
        for i,a in enumerate(names):
            for b in names[i+1:]:
                da,db=self.tables[a],self.tables[b]
                best=None
                for ca in da.columns:
                    for cb in db.columns:
                        if norm(ca)!=norm(cb): continue
                        score=0
                        n=norm(ca)
                        if n.endswith('id') or n=='id': score+=3
                        if da[ca].nunique(dropna=True)==db[cb].nunique(dropna=True): score+=1
                        if score and (best is None or score>best[0]): best=(score,ca,cb)
                if best:
                    _,ca,cb=best
                    if (a,ca,b,cb) not in existing:
                        card='Many-to-One' if db[cb].nunique(dropna=True)==len(db[cb].dropna()) else 'Many-to-Many'
                        self.relationships.append(Relationship(a,str(ca),b,str(cb),card))

    def add_relationship(self,left_table,left_key,right_table,right_key,cardinality='Many-to-One'):
        if left_table not in self.tables or right_table not in self.tables: raise ValueError('Both tables must exist.')
        if left_key not in self.tables[left_table].columns or right_key not in self.tables[right_table].columns: raise ValueError('Relationship columns must exist.')
        r=Relationship(left_table,left_key,right_table,right_key,cardinality)
        self.relationships=[x for x in self.relationships if not (x.left_table==left_table and x.right_table==right_table and x.left_key==left_key and x.right_key==right_key)]
        self.relationships.append(r); return r

    def remove_relationship(self,index):
        if 0<=index<len(self.relationships): self.relationships.pop(index)

    def model_view(self, primary=None):
        """Return a safe denormalized view. Only joins dimension-like unique-key tables."""
        primary=primary or self.primary
        if not primary or primary not in self.tables: return pd.DataFrame()
        out=self.tables[primary].copy(); used={primary}; changed=True
        while changed:
            changed=False
            for r in self.relationships:
                if not r.active: continue
                if r.left_table in used and r.right_table not in used:
                    left,right=r.left_table,r.right_table; lk,rk=r.left_key,r.right_key
                elif r.right_table in used and r.left_table not in used:
                    left,right=r.right_table,r.left_table; lk,rk=r.right_key,r.left_key
                else: continue
                rd=self.tables[right]
                # Dimension-side join only; prevents accidental fact-to-fact row multiplication.
                if not rd[rk].is_unique:
                    continue
                add=rd.copy()
                collisions=[c for c in add.columns if c in out.columns and c!=rk]
                add=add.rename(columns={c:f'{right}.{c}' for c in collisions})
                out=out.merge(add,left_on=lk,right_on=rk,how='left',suffixes=('',f'_{right}'))
                used.add(right); changed=True
        return out

    def summary(self):
        return {'primary':self.primary,'tables':{k:{'rows':len(v),'columns':len(v.columns)} for k,v in self.tables.items()},'relationships':[asdict(r) for r in self.relationships]}
